"""
google_lens_classifier.py  -  Phase 4B

IMAGE HOSTING STRATEGY
======================
The root cause of "Fully empty" on Render:
  Render sets WEB_CONCURRENCY=1 by default — one gunicorn worker.
  That one worker is busy handling your POST /api/upload/google-lens/ request.
  When you point SerpAPI at your own media URL (onrender.com/media/uploads/...),
  Google's crawler tries to fetch it — but the only worker is still busy,
  so the request times out and Google Lens reports "Fully empty".
  This is a deadlock, not a Google problem.

Solution:
  ON RENDER  → Cloudinary (free CDN, no IP blocking, crawler-accessible always)
  LOCAL DEV  → catbox.moe first, tmpfiles.org as fallback
               (local dev server is never publicly reachable anyway)

Cloudinary setup (one-time, takes 2 minutes):
  1. Sign up free at https://cloudinary.com/users/register_free
  2. Dashboard → copy Cloud Name, API Key, API Secret
  3. Add to Render Environment Variables (or local .env):
       CLOUDINARY_CLOUD_NAME = your_cloud_name
       CLOUDINARY_API_KEY    = your_api_key
       CLOUDINARY_API_SECRET = your_api_secret
  Free tier: 25 credits/month — more than enough for this use case.

SerpAPI engine notes (2026-07 change):
  "google_lens_exact_matches" engine removed. Use engine=google_lens + type=:
      type=visual_matches  → response["visual_matches"]
      type=exact_matches   → response["exact_matches"]
  Omitting type can return ai_overview with no visual_matches — always pass it.

Price field shapes differ between the two call types:
  visual_matches: item["price"] = {"value": "₹1,299", "extracted_value": 1299.0}
  exact_matches:  item["price"] = "₹1,299",  item["extracted_price"] = 1299.0
"""

import hashlib
import hmac
import os
import time
import requests
from pathlib import Path


SERPAPI_ENDPOINT  = "https://serpapi.com/search"
TMPFILES_ENDPOINT = "https://tmpfiles.org/api/v1/upload"
CLOUDINARY_UPLOAD = "https://api.cloudinary.com/v1_1/{cloud_name}/image/upload"

VISUAL_LIMIT     = 60
SERPAPI_TIMEOUT  = 90    # s — covers observed 60+ s SerpAPI response times
TMPFILES_TIMEOUT = 40    # s — upload timeout
MAX_RETRIES      = 2     # retry on timeout + transient no-results
RETRY_DELAY      = 4     # s between retries

SKIP_SOURCES = {
    "instagram", "facebook", "pinterest", "youtube",
    "twitter", "tiktok", "snapchat", "reddit",
}

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


# ── Environment ──────────────────────────────────────────────────────────────

def _is_on_render() -> bool:
    """Render automatically sets RENDER=true in every service."""
    return os.environ.get("RENDER", "").lower() == "true"


# ── Config helpers ───────────────────────────────────────────────────────────

def _get_serpapi_key() -> str:
    from django.conf import settings
    key = getattr(settings, "SERPAPI_KEY", "") or os.environ.get("SERPAPI_KEY", "")
    if not key:
        for line in _read_dotenv_lines():
            if line.startswith("SERPAPI_KEY="):
                key = line.split("=", 1)[1].strip()
    return key


def _get_cloudinary_creds() -> tuple:
    """Returns (cloud_name, api_key, api_secret) or ('','','') if not set."""
    from django.conf import settings

    def _get(name):
        return (
            getattr(settings, name, "")
            or os.environ.get(name, "")
            or _read_dotenv_value(name)
        )

    return _get("CLOUDINARY_CLOUD_NAME"), _get("CLOUDINARY_API_KEY"), _get("CLOUDINARY_API_SECRET")


def _read_dotenv_lines() -> list:
    env_path = Path(__file__).resolve().parents[3] / ".env"
    if env_path.exists():
        return env_path.read_text().splitlines()
    return []


def _read_dotenv_value(key: str) -> str:
    for line in _read_dotenv_lines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    return ""


# ── Image upload ─────────────────────────────────────────────────────────────

def _upload_to_cloudinary(image_path: str) -> str:
    """
    Upload to Cloudinary via signed REST API. Returns a direct CDN URL.

    Cloudinary's CDN URLs (res.cloudinary.com/...) are:
    - Reachable from any IP, including cloud/datacenter (no IP blocking)
    - Served by a global CDN — Google's crawler can always fetch them
    - Not subject to the single-worker deadlock that affects self-hosting on Render
    """
    cloud_name, api_key, api_secret = _get_cloudinary_creds()
    if not all([cloud_name, api_key, api_secret]):
        raise Exception(
            "Cloudinary credentials not configured.\n"
            "Add these to your Render environment variables (or .env for local):\n"
            "  CLOUDINARY_CLOUD_NAME = your_cloud_name\n"
            "  CLOUDINARY_API_KEY    = your_api_key\n"
            "  CLOUDINARY_API_SECRET = your_api_secret\n"
            "Sign up free at https://cloudinary.com/users/register_free"
        )

    timestamp = str(int(time.time()))
    # Cloudinary's signing rule: sort signed params alphabetically, join as
    # key=value&key=value, then APPEND the api_secret directly (no HMAC key)
    # and hash the whole string with SHA-1 (Cloudinary's default algorithm).
    # The previous HMAC-SHA256 approach is a different algorithm entirely and
    # will always be rejected with "Invalid Signature".
    params_to_sign = f"timestamp={timestamp}"
    string_to_sign = params_to_sign + api_secret
    signature = hashlib.sha1(string_to_sign.encode("utf-8")).hexdigest()

    filename = Path(image_path).name
    url = CLOUDINARY_UPLOAD.format(cloud_name=cloud_name)

    with open(image_path, "rb") as f:
        resp = requests.post(
            url,
            data={"api_key": api_key, "timestamp": timestamp, "signature": signature},
            files={"file": (filename, f)},
            timeout=TMPFILES_TIMEOUT,
        )

    if resp.status_code != 200:
        raise Exception(f"Cloudinary HTTP {resp.status_code}: {resp.text[:300]}")

    data = resp.json()
    cdn_url = data.get("secure_url") or data.get("url", "")
    if not cdn_url:
        raise Exception(f"Cloudinary returned no URL: {data}")

    print(f"[GoogleLens] Cloudinary CDN URL: {cdn_url}")
    return cdn_url


def _upload_to_catbox(image_path: str) -> str:
    """Upload to catbox.moe (local dev only)."""
    filename = Path(image_path).name
    with open(image_path, "rb") as f:
        resp = requests.post(
            "https://catbox.moe/user/api.php",
            data={"reqtype": "fileupload"},
            files={"fileToUpload": (filename, f)},
            timeout=TMPFILES_TIMEOUT,
        )
    if resp.status_code != 200:
        raise Exception(f"catbox.moe HTTP {resp.status_code}: {resp.text[:200]}")
    url = resp.text.strip()
    if not url.startswith("http"):
        raise Exception(f"catbox.moe unexpected response: {url[:200]}")
    print(f"[GoogleLens] catbox.moe URL: {url}")
    return url


def _upload_to_tmpfiles(image_path: str) -> str:
    """Upload to tmpfiles.org (local dev fallback)."""
    filename = Path(image_path).name
    with open(image_path, "rb") as f:
        resp = requests.post(
            TMPFILES_ENDPOINT,
            files={"file": (filename, f)},
            timeout=TMPFILES_TIMEOUT,
        )
    if resp.status_code != 200:
        raise Exception(f"tmpfiles.org HTTP {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    if data.get("status") != "success":
        raise Exception(f"tmpfiles.org error: {data}")
    share_url  = data["data"]["url"]
    direct_url = share_url.replace("tmpfiles.org/", "tmpfiles.org/dl/")
    print(f"[GoogleLens] tmpfiles.org URL: {direct_url}")
    return direct_url


def _verify_url_serves_image(url: str) -> None:
    """
    Confirm the URL actually returns image content (not HTML / a block page).
    Cloudinary URLs are always valid — skip verification for them.
    Uses a browser User-Agent + small range-GET to avoid bot blocks.
    """
    if "cloudinary.com" in url:
        print("[GoogleLens] Cloudinary URL — skipping verification (always valid CDN)")
        return

    headers = {"User-Agent": _BROWSER_UA, "Range": "bytes=0-2048"}
    last_exc = None

    for attempt in range(1, 3):
        try:
            resp = requests.get(url, timeout=15, stream=True, headers=headers)
            ct     = resp.headers.get("Content-Type", "")
            status = resp.status_code
            resp.close()
        except requests.exceptions.RequestException as e:
            last_exc = e
            if attempt < 2:
                time.sleep(2)
                continue
            raise Exception(f"URL unreachable: {e}")

        if status not in (200, 206):
            raise Exception(f"URL returned HTTP {status}")
        if not ct.startswith("image/"):
            raise Exception(
                f"URL serves '{ct or 'unknown'}' not an image. "
                "The host is likely returning an HTML page — "
                "Google Lens can't read this and will report 'Fully empty'."
            )

        print(f"[GoogleLens] URL verified: serves {ct}")
        return


def _get_public_image_url(image_path: str) -> str:
    """
    Get a public URL Google Lens can fetch.

    ON RENDER  → Cloudinary only (avoids single-worker deadlock)
    LOCAL DEV  → catbox.moe → tmpfiles.org (with image-content verification)
    """
    errors = []

    if _is_on_render():
        print("[GoogleLens] Detected Render environment → using Cloudinary")
        try:
            return _upload_to_cloudinary(image_path)
        except Exception as e:
            errors.append(f"Cloudinary: {e}")
            print(f"[GoogleLens] Cloudinary failed: {e}")
            # Surface the setup instructions immediately if not configured
            if "not configured" in str(e):
                raise Exception(str(e))
            # Other Cloudinary errors — fall through to local hosts as last resort
    else:
        print("[GoogleLens] Local environment → using catbox.moe / tmpfiles.org")

    # Local dev chain (or last-resort fallback on Render)
    for host_name, upload_fn in [
        ("catbox.moe",    _upload_to_catbox),
        ("tmpfiles.org",  _upload_to_tmpfiles),
    ]:
        try:
            url = upload_fn(image_path)
        except Exception as e:
            errors.append(f"{host_name} upload: {e}")
            print(f"[GoogleLens] {host_name} upload failed: {e}")
            continue
        try:
            _verify_url_serves_image(url)
            return url
        except Exception as e:
            errors.append(f"{host_name} verify: {e}")
            print(f"[GoogleLens] {host_name} failed verification: {e}")
            continue

    raise Exception("All image hosts failed. " + " | ".join(errors))


# ── SerpAPI call ─────────────────────────────────────────────────────────────

def _call_serpapi(image_url: str, api_key: str, type_: str = "visual_matches") -> dict:
    """
    Call SerpAPI google_lens with the given type parameter.
    Retries on network Timeout and transient body-level "Fully empty" errors.
    """
    params = {
        "engine" : "google_lens",
        "url"    : image_url,
        "api_key": api_key,
        "type"   : type_,
    }
    last_exc = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(
                f"[GoogleLens] type={type_} attempt {attempt}/{MAX_RETRIES} "
                f"(timeout={SERPAPI_TIMEOUT}s)"
            )
            resp = requests.get(SERPAPI_ENDPOINT, params=params, timeout=SERPAPI_TIMEOUT)

            if resp.status_code == 401:
                raise Exception("Invalid SERPAPI_KEY — https://serpapi.com/manage-api-key")
            if resp.status_code == 429:
                raise Exception("SerpAPI rate limit — upgrade at https://serpapi.com/")
            if resp.status_code != 200:
                raise Exception(f"SerpAPI HTTP {resp.status_code}: {resp.text[:300]}")

            data = resp.json()

            if isinstance(data, dict) and data.get("error"):
                state   = (data.get("search_information") or {}).get("images_results_state", "")
                msg     = data["error"]
                last_exc = Exception(msg)
                print(
                    f"[GoogleLens] No-results error "
                    f"(type={type_}, attempt {attempt}/{MAX_RETRIES}, state={state}): {msg}"
                )
                if attempt < MAX_RETRIES:
                    print(f"[GoogleLens] Retrying in {RETRY_DELAY}s...")
                    time.sleep(RETRY_DELAY)
                    continue
                raise last_exc

            return data

        except requests.exceptions.Timeout as e:
            last_exc = e
            print(
                f"[GoogleLens] Timeout attempt {attempt}/{MAX_RETRIES} type={type_}. "
                + (f"Retrying in {RETRY_DELAY}s..." if attempt < MAX_RETRIES else "No more retries.")
            )
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)

        except requests.exceptions.ConnectionError as e:
            last_exc = e
            print(f"[GoogleLens] Connection error attempt {attempt}/{MAX_RETRIES}: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)

        except Exception:
            raise  # auth, rate limit, exhausted no-results — raise immediately

    raise Exception(
        f"SerpAPI did not respond after {MAX_RETRIES} attempts. "
        f"Try again in a moment. (last error: {last_exc})"
    )


# ── Item parsing ─────────────────────────────────────────────────────────────

def _extract_price(item: dict) -> tuple:
    """
    Handles both price shapes:
    - visual_matches: nested dict  {"value": "₹1,299", "extracted_value": 1299.0}
    - exact_matches:  flat string  item["price"]="₹1,299", item["extracted_price"]=1299.0
    """
    price_obj = item.get("price")

    if isinstance(price_obj, dict):
        return (
            str(price_obj.get("value", "")).strip(),
            float(price_obj.get("extracted_value") or 0.0),
        )
    if isinstance(price_obj, str) and price_obj.strip():
        return (
            price_obj.strip(),
            float(item.get("extracted_price") or 0.0),
        )
    return "", 0.0


def _parse_item(item: dict, rank: int) -> dict:
    price_str, price_float = _extract_price(item)
    return {
        "rank"          : rank,
        "title"         : item.get("title", ""),
        "link"          : item.get("link", "").strip(),
        "source"        : item.get("source", ""),
        "thumbnail"     : item.get("thumbnail", ""),
        "image_url"     : item.get("image", ""),
        "price"         : price_str,
        "price_numeric" : price_float,
        "has_price"     : price_float > 0,
        "rating"        : str(item.get("rating", "")),
        "reviews"       : str(item.get("reviews", "")),
        "in_stock"      : bool(item.get("in_stock", False)),
        "delivery"      : "",
        "tag"           : "",
    }


# ── Main ─────────────────────────────────────────────────────────────────────

def classify(image_path: str) -> dict:
    """
    Main entry point called by pipeline.py.
    Returns: detected_label, category, base_keyword, confidence,
             knowledge_graph, shopping_results, visual_matches,
             public_image_url, top5, error
    """
    api_key = _get_serpapi_key()
    if not api_key or api_key == "your_serpapi_key_here":
        return _error("SERPAPI_KEY not configured. Add to .env: SERPAPI_KEY=your_key")

    # Step 1: Get a public URL Google can fetch
    try:
        public_url = _get_public_image_url(image_path)
    except Exception as e:
        return _error(str(e))

    # Step 2: Visual matches (primary call, with retry)
    try:
        print("[GoogleLens] Call 1: engine=google_lens type=visual_matches")
        data1 = _call_serpapi(public_url, api_key, type_="visual_matches")
        raw1  = data1.get("visual_matches", [])
        print(f"[GoogleLens] Call 1 OK: {len(raw1)} visual_matches")
    except Exception as e:
        return _error(str(e))

    # Step 3: Exact matches (best-effort, non-fatal)
    data2 = {}
    raw2  = []
    try:
        print("[GoogleLens] Call 2: engine=google_lens type=exact_matches")
        data2 = _call_serpapi(public_url, api_key, type_="exact_matches")
        raw2  = data2.get("exact_matches", [])
        print(f"[GoogleLens] Call 2 OK: {len(raw2)} exact_matches")
    except Exception as e:
        print(f"[GoogleLens] Call 2 skipped (non-critical): {e}")

    result = _parse_and_split(data1, raw1, raw2)
    result["public_image_url"] = public_url
    return result


def _parse_and_split(data1: dict, raw1: list, raw2: list) -> dict:
    shopping_results = []
    visual_matches   = []
    seen_links       = set()
    shopping_rank    = 0
    visual_rank      = 0

    all_raw = list(raw1) + list(raw2)
    print(f"[GoogleLens] Total items to parse: {len(all_raw)}")

    for item in all_raw[:VISUAL_LIMIT]:
        parsed = _parse_item(item, rank=0)
        link   = parsed["link"]
        source = parsed["source"].lower()

        if not link or link in seen_links:
            continue
        if any(skip in source for skip in SKIP_SOURCES):
            continue

        seen_links.add(link)

        if parsed["has_price"]:
            shopping_rank        += 1
            parsed["rank"]        = shopping_rank
            parsed["result_type"] = "shopping"
            shopping_results.append(parsed)
        else:
            visual_rank          += 1
            parsed["rank"]        = visual_rank
            parsed["result_type"] = "visual"
            visual_matches.append(parsed)

    knowledge_graph = {}
    kg = data1.get("knowledge_graph") or {}
    if kg:
        knowledge_graph = {
            "title"      : kg.get("title", ""),
            "subtitle"   : kg.get("subtitle", ""),
            "description": kg.get("description", ""),
            "image"      : kg.get("image", ""),
        }

    best_label = ""
    if knowledge_graph.get("title"):
        best_label = knowledge_graph["title"]
        if knowledge_graph.get("subtitle"):
            best_label = f"{best_label} {knowledge_graph['subtitle']}"
    elif shopping_results:
        best_label = shopping_results[0]["title"]
    elif visual_matches:
        best_label = visual_matches[0]["title"]

    category = _detect_category(best_label)

    print(
        f"[GoogleLens] RESULT — label='{best_label}' cat={category} "
        f"shopping={len(shopping_results)} visual={len(visual_matches)} "
        f"total={len(shopping_results)+len(visual_matches)}"
    )

    top5_src = shopping_results if shopping_results else visual_matches
    top5 = [
        {
            "label"    : m["title"],
            "source"   : m["source"],
            "price"    : m.get("price", ""),
            "rating"   : m.get("rating", ""),
            "reviews"  : m.get("reviews", ""),
            "link"     : m["link"],
            "thumbnail": m.get("thumbnail", ""),
        }
        for m in top5_src[:5]
    ]

    return {
        "detected_label"  : best_label,
        "category"        : category,
        "base_keyword"    : best_label,
        "confidence"      : 1.0,
        "knowledge_graph" : knowledge_graph,
        "shopping_results": shopping_results,
        "visual_matches"  : visual_matches,
        "top5"            : top5,
        "error"           : "",
    }


def _detect_category(label: str) -> str:
    t = label.lower()
    if "mangalsutra"                                                in t: return "jewellery"
    if any(w in t for w in ["saree", "sari"]):                           return "saree"
    if any(w in t for w in ["necklace","earring","ring","bangle",
                             "bracelet","chain","jewel","pendant"]):      return "jewellery"
    if any(w in t for w in ["kurta", "kurti"]):                          return "kurta"
    if "lehenga"                                                    in t: return "lehenga"
    if any(w in t for w in ["salwar", "anarkali"]):                      return "salwar"
    if any(w in t for w in ["dress", "gown"]):                           return "dress"
    if any(w in t for w in ["shoe","sneaker","boot","sandal",
                             "heel","loafer"]):                           return "shoes"
    if any(w in t for w in ["bag","purse","tote","clutch",
                             "backpack","handbag"]):                      return "bag"
    if "watch"                                                      in t: return "watch"
    if any(w in t for w in ["sunglasses", "sunglass"]):                  return "sunglasses"
    if any(w in t for w in ["shirt", "blouse"]):                         return "top"
    if any(w in t for w in ["jean","trouser","pant","legging"]):         return "bottomwear"
    if any(w in t for w in ["jacket","coat","blazer"]):                  return "outerwear"
    return "fashion"


def _error(message: str) -> dict:
    print(f"[GoogleLens] ERROR: {message}")
    return {
        "detected_label"  : "",
        "category"        : "fashion",
        "base_keyword"    : "",
        "confidence"      : 0.0,
        "knowledge_graph" : {},
        "shopping_results": [],
        "visual_matches"  : [],
        "public_image_url": "",
        "top5"            : [],
        "error"           : message,
    }
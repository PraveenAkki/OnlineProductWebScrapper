"""
google_lens_classifier.py  -  Phase 4B

SerpAPI Google Lens response structure (confirmed from live response):
-----------------------------------------------------------------------
visual_matches[]:
    position        int
    title           str
    link            str
    source          str
    source_icon     str
    thumbnail       str
    image           str      <- full size image URL
    image_width     int
    image_height    int
    rating          float    <- present on SOME items (e.g. 4.8)
    reviews         int      <- present on SOME items (e.g. 90)
    price           dict     <- present on SOME items
        value           str      e.g. "$18*"
        extracted_value float    e.g. 18.0
        currency        str      e.g. "$"
    in_stock        bool

NOTE: In this engine, visual_matches contains EVERYTHING including items
with prices. There is NO separate shopping_results key in the main response.
Prices live inside visual_matches as a nested price dict.

Flow:
  1. Upload image to tmpfiles.org -> public URL
  2. Call SerpAPI google_lens -> visual_matches (with optional price/rating)
  3. Call SerpAPI google_lens_exact_matches -> additional items
  4. Split into two lists:
       shopping_results = visual_matches that HAVE a price
       visual_matches   = visual_matches that have NO price
  5. Return both lists with all fields properly extracted

Timeout / retry policy (tuned from observed SerpAPI response times):
  - Some calls take 60+ seconds (see SerpAPI dashboard).
  - SERPAPI_TIMEOUT = 90s  — covers the slow tail reliably.
  - TMPFILES_TIMEOUT = 40s — file uploads rarely need more.
  - Call 1 retries up to MAX_RETRIES times on timeout before giving up.
  - Call 2 (exact_matches) is best-effort — one attempt, failure is non-fatal.
"""

import os
import time
import requests
from pathlib import Path


SERPAPI_ENDPOINT  = "https://serpapi.com/search"
TMPFILES_ENDPOINT = "https://tmpfiles.org/api/v1/upload"
VISUAL_LIMIT      = 60   # fetch more since we split into two lists
SHOPPING_LIMIT    = 60

# ── Timeout / retry config ─────────────────────────────────────────────────
# SerpAPI dashboard shows calls can take 60-90 s for complex images.
# Set the timeout well above the observed worst-case, then retry on transient
# failures so a single slow response doesn't kill the whole search.
SERPAPI_TIMEOUT   = 90    # seconds — covers the slow-tail (was 30, too short)
TMPFILES_TIMEOUT  = 40    # seconds — upload rarely takes this long
MAX_RETRIES       = 2     # retry up to 2 times on timeout before giving up
RETRY_DELAY       = 4     # seconds to wait between retries

# Skip social/media — no product pages to scrape
SKIP_SOURCES = {
    "instagram", "facebook", "pinterest", "youtube",
    "twitter", "tiktok", "snapchat", "reddit",
}


def _get_api_key() -> str:
    from django.conf import settings
    key = getattr(settings, "SERPAPI_KEY", "") or os.environ.get("SERPAPI_KEY", "")
    if not key:
        env_path = Path(__file__).resolve().parents[3] / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("SERPAPI_KEY="):
                    key = line.split("=", 1)[1].strip()
                    break
    return key


def _upload_to_tmpfiles(image_path: str) -> str:
    """Upload local image -> tmpfiles.org -> return direct download URL."""
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
    print(f"[GoogleLens] tmpfiles URL: {direct_url}")
    return direct_url


def _call_serpapi(image_url: str, api_key: str, engine: str = "google_lens") -> dict:
    """
    GET SerpAPI with given engine.

    Retries up to MAX_RETRIES times on timeout (requests.exceptions.Timeout).
    Raises immediately on 4xx/5xx HTTP errors — those are not transient.
    """
    params = {"engine": engine, "url": image_url, "api_key": api_key}
    last_exc = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"[GoogleLens] {engine} attempt {attempt}/{MAX_RETRIES} (timeout={SERPAPI_TIMEOUT}s)")
            resp = requests.get(SERPAPI_ENDPOINT, params=params, timeout=SERPAPI_TIMEOUT)

            if resp.status_code == 401:
                raise Exception("Invalid SERPAPI_KEY — check https://serpapi.com/manage-api-key")
            if resp.status_code == 429:
                raise Exception("SerpAPI rate limit reached — upgrade at https://serpapi.com/")
            if resp.status_code != 200:
                raise Exception(f"SerpAPI HTTP {resp.status_code}: {resp.text[:300]}")

            return resp.json()

        except requests.exceptions.Timeout as e:
            last_exc = e
            print(
                f"[GoogleLens] Timeout on attempt {attempt}/{MAX_RETRIES} "
                f"for engine={engine}. "
                + (f"Retrying in {RETRY_DELAY}s..." if attempt < MAX_RETRIES else "No more retries.")
            )
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)

        except requests.exceptions.ConnectionError as e:
            last_exc = e
            print(f"[GoogleLens] Connection error on attempt {attempt}/{MAX_RETRIES}: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)

        except Exception:
            # Non-transient (auth errors, rate limits, etc.) — raise immediately
            raise

    # All retries exhausted — raise a clear, user-friendly message
    raise Exception(
        f"SerpAPI did not respond within {SERPAPI_TIMEOUT}s after {MAX_RETRIES} attempts. "
        f"The image search is taking unusually long. "
        f"Please try again in a moment. (last error: {last_exc})"
    )


def _extract_price(item: dict) -> tuple:
    """
    Extract price string and float from a visual_matches item.

    SerpAPI structure (confirmed):
        item["price"] = {
            "value": "$18*",
            "extracted_value": 18.0,
            "currency": "$"
        }

    Returns: (price_str, price_float)
        e.g. ("$18*", 18.0) or ("", 0.0)
    """
    price_obj = item.get("price")
    if not price_obj or not isinstance(price_obj, dict):
        return "", 0.0
    price_str   = str(price_obj.get("value", "")).strip()
    price_float = float(price_obj.get("extracted_value") or 0.0)
    return price_str, price_float


def _parse_item(item: dict, rank: int) -> dict:
    """
    Parse one SerpAPI visual_matches entry into a unified dict.

    Captures ALL fields present in the live response:
        position, title, link, source, thumbnail, image (full size),
        rating, reviews, price (nested dict -> flat fields), in_stock
    """
    price_str, price_float = _extract_price(item)

    return {
        "rank"          : rank,
        "title"         : item.get("title", ""),
        "link"          : item.get("link", "").strip(),
        "source"        : item.get("source", ""),
        "thumbnail"     : item.get("thumbnail", ""),
        "image_url"     : item.get("image", ""),       # full-size image from Google
        # Price — from nested price dict
        "price"         : price_str,
        "price_numeric" : price_float,
        "has_price"     : price_float > 0,
        # Ratings and reviews — directly on item (not nested)
        "rating"        : str(item.get("rating", "")),
        "reviews"       : str(item.get("reviews", "")),
        # Stock status
        "in_stock"      : bool(item.get("in_stock", False)),
        # No delivery/tag in visual_matches (those are in shopping_results engine)
        "delivery"      : "",
        "tag"           : "",
    }


def classify(image_path: str) -> dict:
    """
    Main entry point. Called by pipeline.py.

    Returns dict with:
        detected_label    str
        category          str
        base_keyword      str
        confidence        float
        knowledge_graph   dict
        shopping_results  list  — items FROM visual_matches that HAVE a price
        visual_matches    list  — items FROM visual_matches that have NO price
        public_image_url  str
        top5              list
        error             str
    """
    api_key = _get_api_key()
    if not api_key or api_key == "your_serpapi_key_here":
        return _error("SERPAPI_KEY not configured. Add to .env: SERPAPI_KEY=your_key")

    # Step 1: Upload image to tmpfiles.org
    try:
        public_url = _upload_to_tmpfiles(image_path)
    except Exception as e:
        return _error(f"Image upload failed: {e}")

    # Step 2: Main Google Lens call (with retry)
    try:
        print("[GoogleLens] Call 1: google_lens engine")
        data1 = _call_serpapi(public_url, api_key, "google_lens")
        raw1  = data1.get("visual_matches", [])
        print(f"[GoogleLens] Call 1 OK: {len(raw1)} visual_matches")
    except Exception as e:
        return _error(str(e))

    # Step 3: Exact matches call (additional items, best-effort — one attempt only)
    data2 = {}
    raw2  = []
    try:
        print("[GoogleLens] Call 2: google_lens_exact_matches engine")
        data2 = _call_serpapi(public_url, api_key, "google_lens_exact_matches")
        raw2  = data2.get("visual_matches", []) + data2.get("shopping_results", [])
        print(f"[GoogleLens] Call 2 OK: {len(raw2)} items")
    except Exception as e:
        # Non-fatal — we already have Call 1 results
        print(f"[GoogleLens] Call 2 skipped (non-critical): {e}")

    # Step 4: Parse and split
    result = _parse_and_split(data1, raw1, raw2)
    result["public_image_url"] = public_url
    return result


def _parse_and_split(data1: dict, raw1: list, raw2: list) -> dict:
    """
    Parse all items from both API calls.
    Split into:
        shopping_results  — items that HAVE a price (price_numeric > 0)
        visual_matches    — items that have NO price
    Both lists are deduped by link. Social media sources are skipped.
    """
    shopping_results = []   # has price
    visual_matches   = []   # no price
    seen_links       = set()
    shopping_rank    = 0
    visual_rank      = 0

    all_raw = list(raw1) + list(raw2)
    print(f"[GoogleLens] Total items to parse: {len(all_raw)}")

    for item in all_raw[:VISUAL_LIMIT]:
        parsed = _parse_item(item, rank=0)  # rank assigned below
        link   = parsed["link"]
        source = parsed["source"].lower()

        if not link or link in seen_links:
            continue
        # Skip social media — no product page to scrape
        if any(skip in source for skip in SKIP_SOURCES):
            print(f"[GoogleLens] Skip social: {parsed['source']}")
            continue

        seen_links.add(link)

        if parsed["has_price"]:
            shopping_rank      += 1
            parsed["rank"]      = shopping_rank
            parsed["result_type"] = "shopping"
            shopping_results.append(parsed)
        else:
            visual_rank        += 1
            parsed["rank"]      = visual_rank
            parsed["result_type"] = "visual"
            visual_matches.append(parsed)

    # Knowledge graph (product identity)
    knowledge_graph = {}
    kg = data1.get("knowledge_graph") or {}
    if kg:
        knowledge_graph = {
            "title"      : kg.get("title", ""),
            "subtitle"   : kg.get("subtitle", ""),
            "description": kg.get("description", ""),
            "image"      : kg.get("image", ""),
        }

    # Best label: knowledge graph > first shopping > first visual
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
        f"[GoogleLens] SPLIT RESULT — "
        f"label='{best_label}' cat={category} "
        f"shopping(has price)={len(shopping_results)} "
        f"visual(no price)={len(visual_matches)} "
        f"total={len(shopping_results) + len(visual_matches)}"
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
    if "mangalsutra"                                        in t: return "jewellery"
    if any(w in t for w in ["saree", "sari"]):                    return "saree"
    if any(w in t for w in ["necklace", "earring", "ring",
                             "bangle", "bracelet",
                             "chain", "jewel", "pendant"]):       return "jewellery"
    if any(w in t for w in ["kurta", "kurti"]):                   return "kurta"
    if "lehenga"                                            in t: return "lehenga"
    if any(w in t for w in ["salwar", "anarkali"]):               return "salwar"
    if any(w in t for w in ["dress", "gown"]):                    return "dress"
    if any(w in t for w in ["shoe", "sneaker", "boot",
                             "sandal", "heel", "loafer"]):        return "shoes"
    if any(w in t for w in ["bag", "purse", "tote",
                             "clutch", "backpack", "handbag"]):   return "bag"
    if "watch"                                            in t: return "watch"
    if any(w in t for w in ["sunglasses", "sunglass"]):           return "sunglasses"
    if any(w in t for w in ["shirt", "blouse"]):                  return "top"
    if any(w in t for w in ["jean", "trouser",
                             "pant", "legging"]):                 return "bottomwear"
    if any(w in t for w in ["jacket", "coat", "blazer"]):         return "outerwear"
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
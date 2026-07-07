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

exact_matches[]  (returned via engine=google_lens with type=exact_matches):
    position          int
    title             str
    link              str
    source            str
    source_icon       str
    thumbnail         str
    date              str
    actual_image_width  int
    actual_image_height int
    price             str      <- FLAT string, e.g. "$18*" (NOT a nested dict!)
    extracted_price   float    <- flat float, e.g. 18.0
    in_stock          bool
    out_of_stock      bool

NOTE (2026-07 SerpAPI change): "google_lens_exact_matches" is no longer a
valid `engine` value. Exact matches are now requested via the SAME
engine=google_lens call, using the `type` request parameter:
    type=all             (default - can sometimes return an ai_overview
                           block instead of matches for ambiguous images)
    type=visual_matches   <- what we want for Call 1
    type=exact_matches    <- what we want for Call 2
    type=products
    type=about_this_image
Passing an old-style engine=google_lens_exact_matches now returns:
    HTTP 400 {"error": "Unsupported `google_lens_exact_matches` search engine."}
And omitting `type` (defaulting to "all") can return an `ai_overview` payload
with NO `visual_matches` key at all for some images, which is why Call 1
was silently coming back with 0 results. Explicitly passing
type=visual_matches on Call 1 fixes this.

Also note: exact_matches items use a FLAT `price` string + `extracted_price`
float, while visual_matches items use a NESTED `price: {value,
extracted_value, currency}` dict. _extract_price() below handles both.

Flow:
  1. Upload image to tmpfiles.org -> public URL
  2. Call SerpAPI google_lens (type=visual_matches) -> visual_matches
  3. Call SerpAPI google_lens (type=exact_matches) -> exact_matches
  4. Split into two lists:
       shopping_results = matches that HAVE a price
       visual_matches   = matches that have NO price
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


def _is_on_render() -> bool:
    """
    Detect whether this process is running on Render.

    Render automatically sets RENDER=true in every environment (build and
    runtime) for every service, and nothing else sets this — it's the
    cleanest possible signal to distinguish "deployed on Render, our own
    domain is genuinely public" from "running locally on a dev machine,
    localhost is NOT reachable by Google's crawler at all".
    """
    return os.environ.get("RENDER", "").lower() == "true"


def _get_own_site_public_url(image_path: str) -> str:
    """
    Build a public URL for the ALREADY-UPLOADED image using this app's own
    live domain, instead of re-uploading it to a third-party temp host.

    WHY: catbox.moe and tmpfiles.org both block/reject requests coming from
    known cloud & datacenter IP ranges as an anti-abuse measure — Render's
    outbound IPs fall into that bucket, which is exactly why you're seeing
    catbox.moe respond with "HTTP 412: Invalid uploader" and tmpfiles.org
    silently serving HTML instead of the file. That's a third-party policy,
    not something fixable from our side by retrying or switching hosts.

    Since this app is already deployed and publicly reachable on Render, and
    Django already serves uploaded files under MEDIA_URL, the file at
    `image_path` (under MEDIA_ROOT) is very likely ALREADY reachable at a
    public URL on your own domain — no third-party host needed at all.

    Uses (in order):
      - PUBLIC_SITE_URL env var / Django setting, if you want to set it
        explicitly (e.g. for a custom domain), OR
      - RENDER_EXTERNAL_URL — Render sets this automatically for every web
        service (e.g. "https://your-app.onrender.com"), no config needed.

    Returns "" if no usable base URL is configured, or if image_path isn't
    under MEDIA_ROOT — callers should fall back to third-party hosts in
    that case, same as before.

    NOTE: this only works if MEDIA_URL is actually being served publicly in
    production (e.g. via whitenoise, a urls.py static() route enabled
    outside DEBUG, or cloud storage like S3). If your uploads aren't
    reachable at <domain><MEDIA_URL><path> in a browser, this will
    correctly fail verification and fall back automatically — it won't
    silently break anything.
    """
    from django.conf import settings

    base_url = (
        getattr(settings, "PUBLIC_SITE_URL", "")
        or os.environ.get("PUBLIC_SITE_URL", "")
        or os.environ.get("RENDER_EXTERNAL_URL", "")
    )
    if not base_url:
        return ""
    base_url = base_url.rstrip("/")

    media_root = os.path.abspath(str(getattr(settings, "MEDIA_ROOT", "")))
    media_url  = getattr(settings, "MEDIA_URL", "/media/")
    abs_path   = os.path.abspath(image_path)

    if not media_root or not abs_path.startswith(media_root):
        return ""

    rel_path = os.path.relpath(abs_path, media_root).replace(os.sep, "/")
    return f"{base_url}/{media_url.strip('/')}/{rel_path}"


def _upload_to_catbox(image_path: str) -> str:
    """
    Upload local image -> catbox.moe -> return direct file URL.

    FALLBACK HOST — used only when tmpfiles.org fails to serve real image
    content (see _verify_public_image_url). tmpfiles.org has been
    intermittently returning an HTML page instead of the raw file on its
    direct /dl/ link recently, which silently breaks Google Lens (it can't
    read HTML as an image, so it just reports "no results").

    catbox.moe's anonymous upload endpoint returns the direct file URL as
    plain text in the response body — there's no separate "share page" vs
    "direct link" distinction to get wrong, which is exactly the class of
    bug tmpfiles.org just hit.
    """
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
    print(f"[GoogleLens] catbox.moe URL (fallback host): {url}")
    return url


_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _verify_public_image_url(url: str) -> None:
    """
    Sanity-check that a freshly-uploaded public URL is actually reachable AND
    served as real image content, before spending a SerpAPI call on it.

    WHY THIS EXISTS: if the same image fails with SerpAPI's
    "Google Lens hasn't returned any results for this query" /
    images_results_state: "Fully empty" on every retry (not just
    occasionally), the real cause is often NOT "Google found nothing" — it's
    that the public host is serving something Google's crawler can't read as
    an image at all: an HTML wrapper page instead of the raw file, a
    non-image Content-Type, or an outright bot block. This check catches
    that immediately with an unambiguous message instead of burning SerpAPI
    calls against an unreadable URL.

    NOTE: some hosts/CDNs (catbox.moe included) drop the connection outright
    on HEAD requests, or on any request without a browser-like User-Agent,
    rather than returning a normal HTTP error. So this always uses a single
    small ranged GET with a browser User-Agent (never HEAD), and retries
    once on a dropped connection before giving up — a dropped connection on
    the first try doesn't necessarily mean the host is actually broken.
    """
    headers = {"User-Agent": _BROWSER_USER_AGENT, "Range": "bytes=0-2048"}
    last_exc = None

    for attempt in range(1, 3):
        try:
            resp = requests.get(url, timeout=15, stream=True, headers=headers)
            content_type = resp.headers.get("Content-Type", "")
            status = resp.status_code
            resp.close()
        except requests.exceptions.RequestException as e:
            last_exc = e
            print(f"[GoogleLens] URL verification attempt {attempt}/2 failed to connect: {e}")
            if attempt < 2:
                time.sleep(2)
                continue
            raise Exception(f"could not be reached ({e}).")

        if status not in (200, 206):
            raise Exception(f"returned HTTP {status} when verified directly.")
        if not content_type.startswith("image/"):
            raise Exception(
                f"did not return image content (got Content-Type: '{content_type or 'none'}'). "
                f"The host is likely serving an HTML page or blocking the request instead of "
                f"the raw file — Google Lens can't read this as an image, which is why it "
                f"silently reports no results."
            )

        print(f"[GoogleLens] Verified public URL serves real image content (Content-Type: {content_type})")
        return


def _call_serpapi(image_url: str, api_key: str, type_: str = "visual_matches") -> dict:
    """
    GET SerpAPI google_lens engine, requesting a specific result `type`.

    IMPORTANT: SerpAPI removed the separate `google_lens_exact_matches`
    engine. Both visual matches and exact matches now come from the SAME
    engine ("google_lens"), distinguished by the `type` query parameter:
        type=visual_matches -> populates response["visual_matches"]
        type=exact_matches  -> populates response["exact_matches"]

    Retries up to MAX_RETRIES times on:
      - requests.exceptions.Timeout (network-level)
      - a body-level "error" with HTTP 200 (SerpAPI/Google Lens sometimes
        reports "hasn't returned any results for this query" /
        images_results_state: "Fully empty" right after the image URL is
        created — this is often a transient indexing-delay issue on
        Google's side, not a real permanent failure, so it's worth a retry
        before giving up).

    Raises immediately on 4xx/5xx HTTP errors — those are not transient.
    """
    params = {
        "engine": "google_lens",
        "url": image_url,
        "api_key": api_key,
        "type": type_,
    }
    last_exc = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"[GoogleLens] type={type_} attempt {attempt}/{MAX_RETRIES} (timeout={SERPAPI_TIMEOUT}s)")
            resp = requests.get(SERPAPI_ENDPOINT, params=params, timeout=SERPAPI_TIMEOUT)

            if resp.status_code == 401:
                raise Exception("Invalid SERPAPI_KEY — check https://serpapi.com/manage-api-key")
            if resp.status_code == 429:
                raise Exception("SerpAPI rate limit reached — upgrade at https://serpapi.com/")
            if resp.status_code != 200:
                raise Exception(f"SerpAPI HTTP {resp.status_code}: {resp.text[:300]}")

            data = resp.json()

            # SerpAPI can return HTTP 200 with a *body-level* "error" when
            # Google Lens genuinely found nothing for the image at that
            # moment (search_metadata.status is still "Success" — only the
            # top-level "error" key + images_results_state: "Fully empty"
            # give it away). This can be a transient indexing delay right
            # after the tmpfiles.org URL was created, so retry before
            # treating it as a real "no results" outcome.
            if isinstance(data, dict) and data.get("error"):
                state = (data.get("search_information") or {}).get("images_results_state", "")
                msg = data["error"]
                last_exc = Exception(msg)
                print(
                    f"[GoogleLens] SerpAPI returned a no-results error "
                    f"(type={type_}, attempt {attempt}/{MAX_RETRIES}, state={state}): {msg}"
                )
                if attempt < MAX_RETRIES:
                    print(f"[GoogleLens] Retrying in {RETRY_DELAY}s in case this was a transient indexing delay...")
                    time.sleep(RETRY_DELAY)
                    continue
                raise last_exc

            return data

        except requests.exceptions.Timeout as e:
            last_exc = e
            print(
                f"[GoogleLens] Timeout on attempt {attempt}/{MAX_RETRIES} "
                f"for type={type_}. "
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
            # Non-transient (auth errors, rate limits, exhausted no-results
            # retries, etc.) — raise immediately with the real message.
            raise

    # All retries exhausted — raise a clear, user-friendly message
    raise Exception(
        f"SerpAPI did not return usable results after {MAX_RETRIES} attempts. "
        f"Please try again in a moment. (last error: {last_exc})"
    )


def _extract_price(item: dict) -> tuple:
    """
    Extract price string and float from a match item.

    Handles BOTH response shapes SerpAPI can return:

    1) visual_matches shape — nested dict:
        item["price"] = {
            "value": "$18*",
            "extracted_value": 18.0,
            "currency": "$"
        }

    2) exact_matches shape — flat fields:
        item["price"] = "$18*"
        item["extracted_price"] = 18.0

    Returns: (price_str, price_float)
        e.g. ("$18*", 18.0) or ("", 0.0)
    """
    price_obj = item.get("price")

    # Shape 1: nested price dict (visual_matches)
    if isinstance(price_obj, dict):
        price_str   = str(price_obj.get("value", "")).strip()
        price_float = float(price_obj.get("extracted_value") or 0.0)
        return price_str, price_float

    # Shape 2: flat price string + extracted_price (exact_matches)
    if isinstance(price_obj, str) and price_obj.strip():
        price_str   = price_obj.strip()
        price_float = float(item.get("extracted_price") or 0.0)
        return price_str, price_float

    return "", 0.0


def _parse_item(item: dict, rank: int) -> dict:
    """
    Parse one SerpAPI match entry (visual_matches OR exact_matches) into a
    unified dict. Captures all fields present across both shapes:
        position, title, link, source, thumbnail, image (full size),
        rating, reviews, price (flat or nested -> flat fields), in_stock
    """
    price_str, price_float = _extract_price(item)

    return {
        "rank"          : rank,
        "title"         : item.get("title", ""),
        "link"          : item.get("link", "").strip(),
        "source"        : item.get("source", ""),
        "thumbnail"     : item.get("thumbnail", ""),
        "image_url"     : item.get("image", ""),       # full-size image from Google
        # Price — from nested dict (visual_matches) or flat fields (exact_matches)
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
        shopping_results  list  — items that HAVE a price
        visual_matches    list  — items that have NO price
        public_image_url  str
        top5              list
        error             str
    """
    api_key = _get_api_key()
    if not api_key or api_key == "your_serpapi_key_here":
        return _error("SERPAPI_KEY not configured. Add to .env: SERPAPI_KEY=your_key")

    # Step 1: Get a public image URL Google Lens can fetch.
    #
    # - ON RENDER: use our own site's live media URL directly
    #   (https://<app>.onrender.com/media/uploads/<file>). The app is
    #   genuinely publicly reachable there, so no third-party host is
    #   needed, and it sidesteps catbox.moe/tmpfiles.org anti-abuse blocks
    #   on cloud/datacenter IPs entirely (what caused the earlier
    #   "catbox.moe HTTP 412: Invalid uploader" / tmpfiles.org HTML
    #   responses). We do NOT self-verify this URL with a network call
    #   back to our own server — on Render's default single-gunicorn-worker
    #   setup (WEB_CONCURRENCY=1) that would deadlock, since the current
    #   request handler IS the only worker available to answer it. We
    #   already know the file exists locally (we just saved it), and only
    #   SerpAPI's external crawler can actually test public reachability
    #   anyway.
    #
    # - LOCALLY (not on Render): our own dev server isn't publicly
    #   reachable at all (localhost/127.0.0.1 mean nothing to Google's
    #   crawler), so skip straight to catbox.moe, falling back to
    #   tmpfiles.org if that fails — same as before.
    public_url = None
    upload_errors = []

    if _is_on_render():
        own_url = _get_own_site_public_url(image_path)
        if own_url and os.path.exists(image_path):
            public_url = own_url
            print(f"[GoogleLens] Running on Render — using own site's public media URL: {own_url}")
        elif own_url:
            upload_errors.append(f"own site URL ({own_url}): local file not found at {image_path}")
            print(f"[GoogleLens] Running on Render but local file not found at {image_path}")
        else:
            upload_errors.append(
                "Running on Render but could not build own-site media URL "
                "(check MEDIA_ROOT/MEDIA_URL settings, or set PUBLIC_SITE_URL explicitly)"
            )
            print("[GoogleLens] Running on Render but could not build own-site media URL — falling back to third-party hosts.")
    else:
        print("[GoogleLens] Not running on Render (local dev) — localhost isn't publicly reachable, using catbox.moe/tmpfiles.org.")

    if not public_url:
        for host_name, upload_fn in (
            ("catbox.moe", _upload_to_catbox),
            ("tmpfiles.org", _upload_to_tmpfiles),
        ):
            try:
                candidate_url = upload_fn(image_path)
            except Exception as e:
                upload_errors.append(f"{host_name} upload failed: {e}")
                print(f"[GoogleLens] {host_name} upload failed: {e}")
                continue
            try:
                _verify_public_image_url(candidate_url)
                public_url = candidate_url
                break
            except Exception as e:
                upload_errors.append(f"{host_name}: {e}")
                print(f"[GoogleLens] {host_name} URL failed verification ({e}); trying next host if available...")
                continue

    if not public_url:
        return _error(
            "Could not get a working public image URL from any host. "
            + " | ".join(upload_errors)
        )

    # Step 2: Main Google Lens call (with retry) — explicitly request the
    # visual_matches tab so SerpAPI doesn't fall back to an ai_overview-only
    # response for ambiguous images.
    try:
        print("[GoogleLens] Call 1: engine=google_lens type=visual_matches")
        data1 = _call_serpapi(public_url, api_key, type_="visual_matches")
        raw1  = data1.get("visual_matches", [])
        print(f"[GoogleLens] Call 1 OK: {len(raw1)} visual_matches")
    except Exception as e:
        return _error(str(e))

    # Step 3: Exact matches call (additional items, best-effort — one attempt only)
    # SerpAPI no longer has a separate "google_lens_exact_matches" engine —
    # exact matches come from engine=google_lens with type=exact_matches,
    # and the results live under the "exact_matches" key (not "visual_matches").
    data2 = {}
    raw2  = []
    try:
        print("[GoogleLens] Call 2: engine=google_lens type=exact_matches")
        data2 = _call_serpapi(public_url, api_key, type_="exact_matches")
        raw2  = data2.get("exact_matches", [])
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
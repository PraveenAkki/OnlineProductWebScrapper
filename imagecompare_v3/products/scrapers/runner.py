"""
scraper_engine/runner.py
------------------------
Place at: products/scraper_engine/runner.py

BUGS FIXED IN THIS VERSION:
  1. filters.py was imported nowhere — is_allowed_site(), is_imitation_jewellery(),
     normalize_price_to_inr() were never called. Fixed: imported and called here.
  2. scraped=True was set even on bot-block failures — Amazon/Flipkart CAPTCHA
     pages permanently removed rows from the retry queue. Fixed: scraped stays
     False on retryable failures (bot-blocks, timeouts).
  3. views_scrape.py used broken _runner() wrapper with wrong import path.
     Fixed: views_scrape.py now imports directly from .scraper_engine.runner
"""

from django.utils import timezone

# ── THESE WERE MISSING — filters were never called before ─────────────────
from .filters import (
    is_allowed_site,         # only Indian / ships-to-India sites
    is_imitation_jewellery,  # block real/solid/certified gold
    normalize_price_to_inr,  # convert $ € £ → ₹ before saving
)


def _detect_website(url: str) -> str:
    try:
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.lower()
        for kw in ["amazon", "flipkart", "meesho", "myntra", "ajio",
                   "snapdeal", "nykaa", "indiamart", "sukkhi", "mirraw",
                   "etsy", "ebay"]:
            if kw in domain:
                return kw
        parts = domain.replace("www.", "").split(".")
        return parts[0] if parts else "unknown"
    except Exception:
        return "unknown"


# ─────────────────────────────────────────────────────────────────────────────
# HOW FILTERS WORK
# ─────────────────────────────────────────────────────────────────────────────
#
# FILTER 1 — is_allowed_site(url)
#   Checks the domain against a hard-coded allow-list:
#     ALLOWED:  amazon.in, amazon.com, flipkart.com, meesho.com, myntra.com,
#               ajio.com, snapdeal.com, nykaa.com, etsy.com, ebay.com,
#               any *.in domain
#     BLOCKED:  instagram.com, facebook.com, pinterest.com, youtube.com,
#               tiktok.com, aliexpress.com, shein.com, temu.com, walmart.com
#   If blocked → skip row (mark scraped=True so it doesn't re-queue)
#
# FILTER 2 — is_imitation_jewellery(title)
#   Checks title for real-gold keywords:
#     BLOCKED keywords: "22k gold", "916 hallmark", "solid gold", "real gold",
#                       "bis certified", "natural diamond", "igi certified" etc.
#   Only applies when title contains "jewel" — other categories (saree, shoes)
#   always pass through.
#   If blocked → skip row
#
# FILTER 3 — normalize_price_to_inr(price_str, price_numeric)
#   Detects currency from price string:
#     "$18*"  → detects "$" → multiplies by 86.5 → "₹1,557"
#     "€25"   → detects "€" → multiplies by 94.0 → "₹2,350"
#     "₹499"  → already INR → "₹499"
#   Returns (display_string, float_value) both in INR
#   Stored in Product.price and Product.price_numeric
#
# ─────────────────────────────────────────────────────────────────────────────


def promote_shopping_results(search_id: int) -> dict:
    """
    Convert all unscraped 'shopping' GoogleLensResult rows into Product rows.
    No HTTP requests — price/rating already came from Google Lens.

    All three filters are applied here.
    """
    from products.models import GoogleLensResult, Product

    rows = GoogleLensResult.objects.filter(
        search_id=search_id, result_type="shopping", scraped=False
    )

    created_ids       = []
    skipped_site      = 0
    skipped_real_gold = 0

    for lr in rows:
        if not lr.link:
            continue

        # FILTER 1: Indian / ships-to-India sites only
        if not is_allowed_site(lr.link):
            skipped_site += 1
            lr.scraped = True   # remove from queue permanently
            lr.save()
            print(f"[Runner] SKIP non-allowed site: {lr.source} → {lr.link[:70]}")
            continue

        # FILTER 2: Imitation jewellery only — block real/solid gold
        if not is_imitation_jewellery(lr.title):
            skipped_real_gold += 1
            lr.scraped = True
            lr.save()
            print(f"[Runner] SKIP real gold: {lr.title[:70]}")
            continue

        # FILTER 3: Normalize price to INR
        inr_display, inr_numeric = normalize_price_to_inr(lr.price, lr.price_numeric)

        website = _detect_website(lr.link)

        product, created = Product.objects.update_or_create(
            lens_result=lr,
            defaults={
                "search"       : lr.search,
                "website"      : website,
                "product_name" : lr.title,
                "price"        : inr_display,       # ← INR display e.g. "₹1,557"
                "price_numeric": inr_numeric,        # ← INR float  e.g. 1557.0
                "discount"     : lr.tag,
                "rating"       : lr.rating,
                "reviews"      : lr.reviews,
                "product_image": lr.thumbnail,
                "product_link" : lr.link,
                "delivery"     : lr.delivery,
            }
        )

        lr.scraped       = True
        lr.scraped_price = inr_display
        lr.scraped_rating= lr.rating
        lr.scraped_at    = timezone.now()
        lr.save()

        if created:
            created_ids.append(product.id)
            print(f"[Runner] SAVED Product id={product.id} [{website}] {lr.title[:50]} | {inr_display}")

    print(
        f"[Runner] promote_shopping_results: "
        f"created={len(created_ids)} "
        f"skipped_non_indian={skipped_site} "
        f"skipped_real_gold={skipped_real_gold}"
    )
    return {
        "promoted"         : len(created_ids),
        "skipped_site"     : skipped_site,
        "skipped_real_gold": skipped_real_gold,
        "product_ids"      : created_ids,
    }


def scrape_one(lens_result_id: int) -> dict:
    """
    Scrape a single visual GoogleLensResult.

    Filter order:
      1. is_allowed_site() — checked BEFORE making any HTTP request
      2. is_imitation_jewellery() — checked on title BEFORE HTTP request
      3. normalize_price_to_inr() — applied AFTER successful scrape

    scraped flag logic (BUG FIX):
      SUCCESS           → scraped=True  (done)
      PERMANENT FAIL    → scraped=True  (404, product removed — don't retry)
      BOT-BLOCK/TIMEOUT → scraped=False (stays in queue for retry)
    """
    from products.models import GoogleLensResult, Product
    from .router import get_scraper

    try:
        lr = GoogleLensResult.objects.get(pk=lens_result_id)
    except GoogleLensResult.DoesNotExist:
        return {"success": False, "product_id": None, "error": f"Not found: {lens_result_id}", "retryable": False}

    if lr.scraped:
        return {"success": True, "product_id": None, "error": "Already scraped", "retryable": False}

    url     = lr.link
    website = _detect_website(url)

    # FILTER 1: check site before making any HTTP request
    if not is_allowed_site(url):
        lr.scraped = True
        lr.save()
        print(f"[Runner] SKIP scrape — non-allowed site: {website}")
        return {"success": False, "product_id": None, "error": "Non-allowed site — skipped", "retryable": False}

    # FILTER 2: check title for real gold before HTTP request
    if not is_imitation_jewellery(lr.title):
        lr.scraped = True
        lr.save()
        print(f"[Runner] SKIP scrape — real gold title: {lr.title[:70]}")
        return {"success": False, "product_id": None, "error": "Real gold listing — skipped", "retryable": False}

    # Make HTTP request
    scraper = get_scraper(url)
    print(f"[Runner] Scraping [{website}] {url[:80]}...")
    data = scraper.scrape(url)

    error_msg  = data.get("error", "")
    is_success = bool(data.get("product_name")) and not error_msg
    retryable  = data.get("retryable", True)  # default True = keep in queue on unknown errors

    if not is_success:
        if retryable:
            # BOT-BLOCK FIX: scraped stays False → row stays in queue for retry
            print(f"[Runner] RETRYABLE FAIL [{website}]: {error_msg} — scraped=False (retryable)")
        else:
            # Permanent failure: mark done so it doesn't waste future retries
            lr.scraped    = True
            lr.scraped_at = timezone.now()
            lr.save()
            print(f"[Runner] PERMANENT FAIL [{website}]: {error_msg}")
        return {"success": False, "product_id": None, "error": error_msg, "retryable": retryable}

    # FILTER 3: normalize scraped price to INR before saving
    inr_display, inr_numeric = normalize_price_to_inr(
        data.get("price", ""), data.get("price_numeric", 0.0)
    )

    lr.scraped       = True
    lr.scraped_at    = timezone.now()
    lr.scraped_price = inr_display
    lr.scraped_rating= data.get("rating", "")
    lr.save()

    product, created = Product.objects.update_or_create(
        lens_result=lr,
        defaults={
            "search"       : lr.search,
            "website"      : website,
            "product_name" : data.get("product_name", ""),
            "price"        : inr_display,
            "price_numeric": inr_numeric,
            "discount"     : data.get("discount", ""),
            "rating"       : data.get("rating", ""),
            "reviews"      : data.get("reviews", ""),
            "product_image": data.get("product_image", ""),
            "product_link" : url,
            "delivery"     : data.get("delivery", ""),
        }
    )

    print(f"[Runner] {'Created' if created else 'Updated'} Product id={product.id} [{website}] {data['product_name'][:50]} | {inr_display}")
    return {"success": True, "product_id": product.id, "error": "", "retryable": False}


def scrape_batch(search_id: int, limit: int = 10) -> dict:
    from products.models import GoogleLensResult

    rows = GoogleLensResult.objects.filter(
        search_id=search_id, result_type="visual", scraped=False
    ).order_by("rank")[:limit]

    success = failed = retryable_fails = 0
    results = []

    for lr in rows:
        out = scrape_one(lr.id)
        results.append({"lens_result_id": lr.id, "url": lr.link[:80], "source": lr.source, **out})
        if out["success"]:
            success += 1
        else:
            failed += 1
            if out.get("retryable"):
                retryable_fails += 1

    remaining = GoogleLensResult.objects.filter(
        search_id=search_id, result_type="visual", scraped=False
    ).count()

    return {
        "search_id"        : search_id,
        "scraped_this_run" : len(results),
        "success"          : success,
        "failed"           : failed,
        "retryable_fails"  : retryable_fails,
        "remaining_visual" : remaining,
        "done"             : remaining == 0,
        "results"          : results,
    }


def scrape_all_for_search(search_id: int) -> dict:
    from products.models import GoogleLensResult

    rows  = GoogleLensResult.objects.filter(
        search_id=search_id, result_type="visual", scraped=False
    ).order_by("rank")
    total = rows.count()
    success = failed = 0
    results = []

    for lr in rows:
        out = scrape_one(lr.id)
        results.append({"lens_result_id": lr.id, "url": lr.link[:80], "source": lr.source, **out})
        if out["success"]: success += 1
        else:              failed  += 1

    return {"search_id": search_id, "total": total, "success": success, "failed": failed, "done": True, "results": results}


def retry_failed(search_id: int, limit: int = 20) -> dict:
    """
    Retry visual rows that are still scraped=False.
    These are bot-blocked rows from a previous scrape run.
    Second attempt often succeeds because Amazon/Flipkart bot-detection rotates.
    """
    return scrape_batch(search_id, limit=limit)
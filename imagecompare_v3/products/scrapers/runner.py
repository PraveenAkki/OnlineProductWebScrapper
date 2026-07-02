"""
products/scrapers/runner.py  — FIXED
--------------------------------------
Place at: products/scrapers/runner.py  (same folder as before)

THREE BUGS FIXED:
  1. filters.py was never imported — is_allowed_site(), is_imitation_jewellery(),
     normalize_price_to_inr() were defined but never called anywhere.

  2. retry_failed() function was missing entirely — views_scrape.py tried to
     import it, got ImportError, Django returned a 500 HTML page instead of JSON,
     frontend received "<html..." which caused "Unexpected token '<'" in JS.

  3. scraped=True was set even on bot-block failures — rows got permanently
     removed from the retry queue. Now scraped stays False on retryable errors.
"""

from django.utils import timezone

# ── FIX 1: ADD THESE IMPORTS (were completely missing before) ─────────────────
from .filters import (
    is_allowed_site,          # blocks social media / non-shopping sites
    is_imitation_jewellery,   # blocks real/solid/certified gold listings
    normalize_price_to_inr,   # converts $ € £ → ₹ before saving to DB
)


def _detect_website(url: str) -> str:
    try:
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.lower()
        mapping = {
            "amazon"   : "Amazon",
            "flipkart" : "Flipkart",
            "meesho"   : "Meesho",
            "myntra"   : "Myntra",
            "nykaa"    : "Nykaa",
            "ajio"     : "Ajio",
            "snapdeal" : "Snapdeal",
            "etsy"     : "Etsy",
            "ebay"     : "eBay",
            "indiamart": "IndiaMart",
            "mirraw"   : "Mirraw",
            "sukkhi"   : "Sukkhi",
            "tatacliq" : "Tata CLiQ",
        }
        for kw, name in mapping.items():
            if kw in domain:
                return name
        parts = domain.replace("www.", "").split(".")
        return parts[0].capitalize() if parts else "Unknown"
    except Exception:
        return "Unknown"


def promote_shopping_results(search_id: int) -> dict:
    """
    Convert all unscraped shopping GoogleLensResult rows into Product rows.
    No HTTP requests — price/rating already came from Google Lens.

    Filters applied:
      1. is_allowed_site()         — skip social media, AliExpress, etc.
      2. is_imitation_jewellery()  — skip real gold / certified diamond
      3. normalize_price_to_inr()  — convert $18 → ₹1,557 before saving
    """
    from products.models import GoogleLensResult, Product

    rows = GoogleLensResult.objects.filter(
        search_id   = search_id,
        result_type = "shopping",
        scraped     = False,
    )

    created_ids       = []
    skipped_site      = 0
    skipped_real_gold = 0

    for lr in rows:
        if not lr.link:
            continue

        # FILTER 1: allowed site?
        if not is_allowed_site(lr.link):
            skipped_site += 1
            lr.scraped    = True
            lr.scraped_at = timezone.now()
            lr.save(update_fields=["scraped", "scraped_at"])
            print(f"[Runner] SKIP (site blocked): {lr.source} | {lr.link[:60]}")
            continue

        # FILTER 2: imitation jewellery only
        if not is_imitation_jewellery(lr.title or ""):
            skipped_real_gold += 1
            lr.scraped    = True
            lr.scraped_at = timezone.now()
            lr.save(update_fields=["scraped", "scraped_at"])
            print(f"[Runner] SKIP (real gold): {(lr.title or '')[:60]}")
            continue

        # FILTER 3: convert price to INR
        inr_display, inr_numeric = normalize_price_to_inr(
            lr.price or "", lr.price_numeric or 0.0
        )

        website = _detect_website(lr.link)

        product, created = Product.objects.update_or_create(
            lens_result = lr,
            defaults    = {
                "search"       : lr.search,
                "website"      : website,
                "product_name" : lr.title or "",
                "price"        : inr_display,
                "price_numeric": inr_numeric,
                "discount"     : lr.tag or "",
                "rating"       : lr.rating or "",
                "reviews"      : lr.reviews or "",
                "product_image": lr.thumbnail or lr.image_url or "",
                "product_link" : lr.link,
                "delivery"     : lr.delivery or "",
            }
        )

        lr.scraped        = True
        lr.scraped_price  = inr_display
        lr.scraped_rating = lr.rating or ""
        lr.scraped_at     = timezone.now()
        lr.save(update_fields=["scraped", "scraped_price", "scraped_rating", "scraped_at"])

        if created:
            created_ids.append(product.id)
            print(f"[Runner] ✓ Promoted [{website}] {(lr.title or '')[:50]} | {inr_display}")

    print(
        f"[Runner] promote_shopping done: "
        f"promoted={len(created_ids)} "
        f"skipped_site={skipped_site} "
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

    Filters:
      1. is_allowed_site()         before any HTTP request
      2. is_imitation_jewellery()  on title before HTTP, on name after HTTP
      3. normalize_price_to_inr()  after successful scrape

    scraped flag:
      SUCCESS or PERMANENT FAIL → scraped=True  (done, don't retry)
      BOT-BLOCK / TIMEOUT       → scraped=False (stays in queue for retry)
    """
    from products.models import GoogleLensResult, Product
    from .router import get_scraper

    try:
        lr = GoogleLensResult.objects.get(pk=lens_result_id)
    except GoogleLensResult.DoesNotExist:
        return {"success": False, "product_id": None,
                "error": f"GoogleLensResult {lens_result_id} not found",
                "retryable": False}

    if lr.scraped:
        return {"success": True, "product_id": None,
                "error": "Already scraped", "retryable": False}

    url = lr.link
    if not url:
        lr.scraped    = True
        lr.scraped_at = timezone.now()
        lr.save(update_fields=["scraped", "scraped_at"])
        return {"success": False, "product_id": None,
                "error": "No URL", "retryable": False}

    # FILTER 1: allowed site?
    if not is_allowed_site(url):
        lr.scraped    = True
        lr.scraped_at = timezone.now()
        lr.save(update_fields=["scraped", "scraped_at"])
        print(f"[Runner] SKIP (site blocked): {lr.source}")
        return {"success": False, "product_id": None,
                "error": f"Site blocked: {lr.source}", "retryable": False}

    # FILTER 2: imitation check on Google title before HTTP
    if not is_imitation_jewellery(lr.title or ""):
        lr.scraped    = True
        lr.scraped_at = timezone.now()
        lr.save(update_fields=["scraped", "scraped_at"])
        print(f"[Runner] SKIP (real gold in title): {(lr.title or '')[:60]}")
        return {"success": False, "product_id": None,
                "error": "Real gold listing — skipped", "retryable": False}

    # HTTP scrape
    website = _detect_website(url)
    scraper = get_scraper(url)
    print(f"[Runner] Scraping [{website}] {url[:80]}...")
    data = scraper.scrape(url)

    error_msg = data.get("error", "")
    is_success = bool(data.get("product_name")) and not error_msg
    # retryable=True means bot-block/timeout → keep scraped=False for retry
    retryable = data.get("retryable", True)

    if not is_success:
        if retryable:
            # BOT-BLOCK: keep scraped=False so retry_failed() can pick it up
            print(f"[Runner] RETRYABLE FAIL [{website}]: {error_msg}")
        else:
            lr.scraped    = True
            lr.scraped_at = timezone.now()
            lr.save(update_fields=["scraped", "scraped_at"])
            print(f"[Runner] PERMANENT FAIL [{website}]: {error_msg}")
        return {"success": False, "product_id": None,
                "error": error_msg, "retryable": retryable}

    # FILTER 2 again: check actual scraped product name
    scraped_name = data.get("product_name", "")
    if not is_imitation_jewellery(scraped_name):
        lr.scraped    = True
        lr.scraped_at = timezone.now()
        lr.save(update_fields=["scraped", "scraped_at"])
        print(f"[Runner] SKIP after scrape (real gold in name): {scraped_name[:60]}")
        return {"success": False, "product_id": None,
                "error": "Real gold after scrape — skipped", "retryable": False}

    # FILTER 3: normalize price to INR
    inr_display, inr_numeric = normalize_price_to_inr(
        data.get("price", ""), data.get("price_numeric", 0.0)
    )

    lr.scraped        = True
    lr.scraped_at     = timezone.now()
    lr.scraped_price  = inr_display
    lr.scraped_rating = data.get("rating", "")
    lr.save(update_fields=["scraped", "scraped_price", "scraped_rating", "scraped_at"])

    product, created = Product.objects.update_or_create(
        lens_result = lr,
        defaults    = {
            "search"       : lr.search,
            "website"      : website,
            "product_name" : scraped_name,
            "price"        : inr_display,
            "price_numeric": inr_numeric,
            "discount"     : data.get("discount", ""),
            "rating"       : data.get("rating", ""),
            "reviews"      : data.get("reviews", ""),
            "product_image": data.get("product_image", lr.thumbnail or ""),
            "product_link" : url,
            "delivery"     : data.get("delivery", ""),
        }
    )

    print(f"[Runner] ✓ {'Created' if created else 'Updated'} Product id={product.id} "
          f"[{website}] {scraped_name[:50]} | {inr_display}")
    return {
        "success"      : True,
        "product_id"   : product.id,
        "error"        : "",
        "retryable"    : False,
        "price"        : inr_display,
        "price_numeric": inr_numeric,
        "name"         : product.product_name,
        "rating"       : product.rating,
        "website"      : website,
    }


def scrape_batch(search_id: int, limit: int = 10) -> dict:
    from products.models import GoogleLensResult

    rows = GoogleLensResult.objects.filter(
        search_id   = search_id,
        result_type = "visual",
        scraped     = False,
    ).order_by("rank")[:limit]

    success = failed = retryable_fails = 0
    results = []

    for lr in rows:
        out = scrape_one(lr.id)
        results.append({
            "lens_result_id": lr.id,
            "url"           : lr.link,
            "source"        : lr.source,
            **out,
        })
        if out.get("success"):
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
        results.append({
            "lens_result_id": lr.id,
            "url"           : lr.link,
            "source"        : lr.source,
            **out,
        })
        if out.get("success"):
            success += 1
        else:
            failed += 1

    remaining = GoogleLensResult.objects.filter(
        search_id=search_id, result_type="visual", scraped=False
    ).count()

    return {
        "search_id"      : search_id,
        "total"          : total,
        "success"        : success,
        "failed"         : failed,
        "remaining_visual": remaining,
        "done"           : remaining == 0,
        "results"        : results,
    }


# ── FIX 2: ADD THIS FUNCTION (was missing — caused ImportError → HTML 500) ───
def retry_failed(search_id: int, limit: int = 20) -> dict:
    """
    Retry visual rows still marked scraped=False after a previous scrape run.
    These are bot-blocked rows — Amazon/Flipkart CAPTCHA pages.
    A second attempt after a delay often succeeds.

    This function was MISSING before — views_scrape.py imported it but
    runner.py didn't define it, causing ImportError at startup.
    Django returned a 500 HTML error page instead of JSON.
    Frontend received '<html...' → "Unexpected token '<'" error.
    """
    return scrape_batch(search_id, limit=limit)

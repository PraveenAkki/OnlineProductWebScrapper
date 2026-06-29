"""
scraper_engine/runner.py
------------------------
Core scrape runner.

TWO SOURCES of product data:
  1. Shopping results from Google Lens — already have link + price + rating.
     We create Product rows for these IMMEDIATELY (no HTTP scraping needed).
     product_link is stored from GoogleLensResult.link.

  2. Visual results from Google Lens — have link but NO price.
     We HTTP-scrape these to extract price, name, image, etc.
     product_link is stored from GoogleLensResult.link.

Both types end up as Product rows with product_link populated.
"""

from django.utils import timezone


# ---------------------------------------------------------------------------
# Promote shopping results → Product rows (no scraping needed)
# ---------------------------------------------------------------------------

def promote_shopping_results(search_id: int) -> dict:
    """
    Convert all GoogleLensResult rows of type 'shopping' into Product rows.
    These already have price + rating from Google — no HTTP request needed.

    Call this right after Google Lens classify, before any scraping.
    """
    from products.models import GoogleLensResult, Product

    rows = GoogleLensResult.objects.filter(
        search_id   = search_id,
        result_type = "shopping",
        scraped     = False,
    )

    created_ids = []
    for lr in rows:
        if not lr.link:
            continue

        website = _detect_website(lr.link)

        product, created = Product.objects.update_or_create(
            lens_result = lr,
            defaults    = {
                "search"       : lr.search,
                "website"      : website,
                "product_name" : lr.title,
                "price"        : lr.price,
                "price_numeric": lr.price_numeric,
                "discount"     : lr.tag,        # e.g. "Best seller" or discount tag
                "rating"       : lr.rating,
                "reviews"      : lr.reviews,
                "product_image": lr.thumbnail,  # Google thumbnail as placeholder
                "product_link" : lr.link,       # ← THE LINK stored in Product
                "delivery"     : lr.delivery,
            }
        )

        # Mark as scraped so scraper skips it
        lr.scraped      = True
        lr.scraped_price  = lr.price
        lr.scraped_rating = lr.rating
        lr.scraped_at   = timezone.now()
        lr.save()

        if created:
            created_ids.append(product.id)
            print(f"[Runner] Promoted shopping → Product id={product.id} [{website}] {lr.title[:50]} | {lr.price} | {lr.link[:60]}")

    print(f"[Runner] promote_shopping_results: {len(created_ids)} Products created for search_id={search_id}")
    return {"promoted": len(created_ids), "product_ids": created_ids}


# ---------------------------------------------------------------------------
# Scrape a single visual result → Product row
# ---------------------------------------------------------------------------

def scrape_one(lens_result_id: int) -> dict:
    """
    Scrape a single GoogleLensResult (visual type) by its DB id.
    Creates/updates a Product row with product_link = lr.link.
    Marks lr.scraped = True either way.
    """
    from products.models import GoogleLensResult, Product
    from .router import get_scraper

    try:
        lr = GoogleLensResult.objects.get(pk=lens_result_id)
    except GoogleLensResult.DoesNotExist:
        return {"success": False, "product_id": None, "error": f"GoogleLensResult {lens_result_id} not found"}

    if lr.scraped:
        return {"success": True, "product_id": None, "error": "Already scraped"}

    url     = lr.link
    website = _detect_website(url)
    scraper = get_scraper(url)

    print(f"[Runner] Scraping [{website}] {url[:80]}...")
    data = scraper.scrape(url)

    # Mark scraped regardless so we don't retry indefinitely
    lr.scraped    = True
    lr.scraped_at = timezone.now()

    if data.get("error") or not data.get("product_name"):
        error_msg = data.get("error") or "No product name extracted"
        lr.scraped_price  = ""
        lr.scraped_rating = ""
        lr.save()
        print(f"[Runner] FAILED [{website}]: {error_msg}")
        return {"success": False, "product_id": None, "error": error_msg}

    lr.scraped_price  = data.get("price", "")
    lr.scraped_rating = data.get("rating", "")
    lr.save()

    product, created = Product.objects.update_or_create(
        lens_result = lr,
        defaults    = {
            "search"       : lr.search,
            "website"      : website,
            "product_name" : data.get("product_name", ""),
            "price"        : data.get("price", ""),
            "price_numeric": data.get("price_numeric", 0.0),
            "discount"     : data.get("discount", ""),
            "rating"       : data.get("rating", ""),
            "reviews"      : data.get("reviews", ""),
            "product_image": data.get("product_image", ""),
            "product_link" : url,       # ← link always stored from GoogleLensResult
            "delivery"     : data.get("delivery", ""),
        }
    )

    action = "Created" if created else "Updated"
    print(f"[Runner] {action} Product id={product.id} [{website}] {data['product_name'][:50]} | {data['price']} | {url[:60]}")
    return {"success": True, "product_id": product.id, "error": ""}


# ---------------------------------------------------------------------------
# Batch / all scrapers for visual results
# ---------------------------------------------------------------------------

def scrape_batch(search_id: int, limit: int = 10) -> dict:
    """
    Scrape up to `limit` unscraped VISUAL GoogleLensResult rows.
    Shopping rows are skipped here — use promote_shopping_results() for those.
    """
    from products.models import GoogleLensResult

    rows = GoogleLensResult.objects.filter(
        search_id   = search_id,
        result_type = "visual",
        scraped     = False,
    ).order_by("rank")[:limit]

    remaining_before = GoogleLensResult.objects.filter(
        search_id=search_id, result_type="visual", scraped=False
    ).count()

    success = 0
    failed  = 0
    results = []

    for lr in rows:
        out = scrape_one(lr.id)
        results.append({
            "lens_result_id": lr.id,
            "url"           : lr.link,
            "source"        : lr.source,
            **out,
        })
        if out["success"]:
            success += 1
        else:
            failed += 1

    remaining_after = GoogleLensResult.objects.filter(
        search_id=search_id, result_type="visual", scraped=False
    ).count()

    return {
        "search_id"        : search_id,
        "scraped_this_run" : len(results),
        "success"          : success,
        "failed"           : failed,
        "remaining_visual" : remaining_after,
        "done"             : remaining_after == 0,
        "results"          : results,
    }


def scrape_all_for_search(search_id: int) -> dict:
    """Scrape ALL unscraped visual results for a search."""
    from products.models import GoogleLensResult

    rows = GoogleLensResult.objects.filter(
        search_id   = search_id,
        result_type = "visual",
        scraped     = False,
    ).order_by("rank")

    total   = rows.count()
    success = 0
    failed  = 0
    results = []

    print(f"[Runner] scrape_all: {total} visual rows for search_id={search_id}")

    for lr in rows:
        out = scrape_one(lr.id)
        results.append({
            "lens_result_id": lr.id,
            "url"           : lr.link,
            "source"        : lr.source,
            **out,
        })
        if out["success"]:
            success += 1
        else:
            failed += 1

    return {
        "search_id": search_id,
        "total"    : total,
        "success"  : success,
        "failed"   : failed,
        "done"     : True,
        "results"  : results,
    }


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _detect_website(url: str) -> str:
    try:
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.lower()
        for kw in ["amazon", "flipkart", "meesho", "myntra", "etsy",
                   "ebay", "indiamart", "snapdeal", "nykaa", "ajio"]:
            if kw in domain:
                return kw
        parts = domain.replace("www.", "").split(".")
        return parts[0] if parts else "unknown"
    except Exception:
        return "unknown"
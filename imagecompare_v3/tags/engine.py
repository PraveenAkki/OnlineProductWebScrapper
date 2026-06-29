"""
products/scrapers/engine.py

Entry point called by the view. Takes a SearchHistory, finds every
GoogleLensResult row that still needs scraping (result_type='visual' AND
scraped=False — these are the priceless links saved earlier from Google
Lens), and scrapes them CONCURRENTLY using a thread pool (network-bound
work, so threads are fine — no need for async/multiprocessing).

Speed knobs:
    MAX_WORKERS  — how many links are fetched in parallel
    LIMIT        — cap how many links get scraped per call (avoid scraping
                   all 60 visual matches when 15-20 already give a good
                   price comparison spread across sites)
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from django.utils import timezone

from products.models import GoogleLensResult, Product
from products.scrapers.base import get_session, fetch_html, soup_of, domain_of
from products.scrapers.registry import get_parser, should_skip

MAX_WORKERS = 10     # parallel requests — tune based on your network/CPU
LIMIT       = 20      # max links scraped per call, ordered by Google's rank


def scrape_search(search, limit: int = LIMIT, max_workers: int = MAX_WORKERS) -> dict:
    """
    Scrapes unscraped, priceless GoogleLensResult rows for one SearchHistory.
    Returns a summary dict (also see ScrapeVisualMatchesView in views.py).
    """
    queue = list(
        search.lens_results
        .filter(result_type="visual", scraped=False)
        .exclude(link="")
        .order_by("rank")[:limit]
    )

    if not queue:
        return {
            "scraped": 0, "found_price": 0, "failed": 0,
            "products": [], "message": "Nothing left to scrape — all visual links already processed.",
        }

    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_scrape_one, row): row for row in queue}
        for future in as_completed(futures):
            row = futures[future]
            try:
                results.append(future.result())
            except Exception as e:
                print(f"[ScraperEngine] worker crashed for row id={row.id}: {e}")
                results.append({"row": row, "ok": False, "data": None})

    products_to_create = []
    rows_to_update      = []
    found_price = 0
    failed      = 0

    for r in results:
        row  = r["row"]
        data = r["data"]
        now  = timezone.now()

        row.scraped    = True
        row.scraped_at = now

        if r["ok"] and data and data.get("price_numeric", 0) > 0:
            found_price += 1
            row.scraped_price  = data.get("price", "")
            row.scraped_rating = data.get("rating", "")
            products_to_create.append(Product(
                search        = search,
                lens_result   = row,
                website       = data.get("website", "Other"),
                product_name  = data.get("product_name") or row.title,
                price         = data.get("price", ""),
                price_numeric = data.get("price_numeric", 0.0),
                rating        = data.get("rating", ""),
                reviews       = data.get("reviews", ""),
                product_image = data.get("product_image") or row.thumbnail,
                product_link  = row.link,
                delivery      = data.get("delivery", ""),
            ))
        else:
            failed += 1

        rows_to_update.append(row)

    # Two bulk SQL statements total, regardless of how many links we scraped.
    if products_to_create:
        Product.objects.bulk_create(products_to_create)
    GoogleLensResult.objects.bulk_update(
        rows_to_update, ["scraped", "scraped_price", "scraped_rating", "scraped_at"]
    )

    return {
        "scraped"     : len(queue),
        "found_price" : found_price,
        "failed"      : failed,
        "products"    : [
            {
                "website": p.website, "product_name": p.product_name,
                "price": p.price, "price_numeric": p.price_numeric,
                "rating": p.rating, "product_link": p.product_link,
            }
            for p in products_to_create
        ],
        "message": f"Scraped {len(queue)} links — {found_price} prices found, {failed} failed/blocked.",
    }


def _scrape_one(row) -> dict:
    """Runs in a worker thread. Never raises — always returns a dict."""
    domain = domain_of(row.link)

    if not domain or should_skip(domain):
        return {"row": row, "ok": False, "data": None}

    session = get_session()
    html = fetch_html(session, row.link)
    if not html:
        return {"row": row, "ok": False, "data": None}

    soup = soup_of(html)
    parse_fn, _label = get_parser(domain)
    try:
        data = parse_fn(soup, row.link)
    except Exception as e:
        print(f"[ScraperEngine] parse failed for {row.link[:80]}: {e}")
        return {"row": row, "ok": False, "data": None}

    return {"row": row, "ok": True, "data": data}
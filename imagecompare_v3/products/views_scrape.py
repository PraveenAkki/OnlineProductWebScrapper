"""
products/views_scrape.py
------------------------
Place at: products/views_scrape.py

IMPORT PATH FIX:
  Wrong: from .scrapers.runner import ...        ← folder doesn't exist
  Wrong: from products.scrapers.runner import ... ← same wrong folder
  RIGHT: from .scraper_engine.runner import ...   ← matches actual folder name

If your folder is products/scrapers/ instead of products/scraper_engine/
then change scraper_engine → scrapers in the four import lines below.
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .models import SearchHistory, GoogleLensResult, Product
from .serializers import ProductSerializer

# ── FIXED: correct path is .scraper_engine.runner not .scrapers.runner ─────
from .scrapers.runner import (
    promote_shopping_results,
    scrape_batch,
    scrape_all_for_search,
    scrape_one,
    retry_failed,
)


class PromoteShoppingResultsView(APIView):
    """
    POST /api/searches/<id>/promote-shopping/

    Saves all shopping GoogleLensResult rows as Product rows instantly.
    No HTTP scraping needed — price/rating already returned by Google Lens.

    What this does internally (inside runner.py):
      1. is_allowed_site()        — skips non-Indian / non-shipping sites
      2. is_imitation_jewellery() — skips real/solid/certified gold listings
      3. normalize_price_to_inr() — converts $ € £ to ₹ before saving

    You will see in the response:
      saved_count       — products actually saved to DB
      skipped_site      — non-Indian sites skipped (e.g. Walmart, AliExpress)
      skipped_real_gold — real gold listings skipped (e.g. "22k gold", "hallmark")
    """
    def post(self, request, pk):
        try:
            search = SearchHistory.objects.get(pk=pk)
        except SearchHistory.DoesNotExist:
            return Response({"error": f"Search id={pk} not found."}, status=status.HTTP_404_NOT_FOUND)

        unpromoted = GoogleLensResult.objects.filter(
            search_id=pk, result_type="shopping", scraped=False
        ).count()

        if unpromoted == 0:
            return Response({
                "message"       : "All shopping results already saved.",
                "search_id"     : pk,
                "products_in_db": Product.objects.filter(search_id=pk).count(),
            })

        result = promote_shopping_results(search.id)

        products = Product.objects.filter(
            search_id=pk, id__in=result["product_ids"]
        ).order_by("price_numeric")

        return Response({
            "search_id"        : pk,
            "search_keyword"   : search.search_keyword,
            "saved_count"      : result["promoted"],
            "skipped_site"     : result.get("skipped_site", 0),
            "skipped_real_gold": result.get("skipped_real_gold", 0),
            "message": (
                f"{result['promoted']} imitation jewellery products saved (prices in ₹). "
                f"Filtered out: {result.get('skipped_site', 0)} non-Indian sites, "
                f"{result.get('skipped_real_gold', 0)} real/solid gold listings."
            ),
            "products": ProductSerializer(products, many=True).data,
        }, status=status.HTTP_201_CREATED)


class ScrapeSearchView(APIView):
    """
    POST /api/searches/<id>/scrape/    Body: {"limit": 10}

    Scrapes up to `limit` unscraped visual results.
    Applies same filters as promote (site + gold + currency).
    Bot-blocked pages stay scraped=False — call /scrape/retry/ for those.
    """
    def post(self, request, pk):
        try:
            search = SearchHistory.objects.get(pk=pk)
        except SearchHistory.DoesNotExist:
            return Response({"error": f"Search id={pk} not found."}, status=status.HTTP_404_NOT_FOUND)

        limit = max(1, min(int(request.data.get("limit", 10)), 30))
        result = scrape_batch(search.id, limit=limit)
        return Response(result, status=status.HTTP_200_OK)


class ScrapeSearchAllView(APIView):
    """POST /api/searches/<id>/scrape/all/"""
    def post(self, request, pk):
        try:
            search = SearchHistory.objects.get(pk=pk)
        except SearchHistory.DoesNotExist:
            return Response({"error": f"Search id={pk} not found."}, status=status.HTTP_404_NOT_FOUND)

        unscraped = GoogleLensResult.objects.filter(
            search_id=pk, result_type="visual", scraped=False
        ).count()

        if unscraped == 0:
            return Response({"message": "All visual results already scraped.", "search_id": pk, "remaining": 0, "done": True})

        result = scrape_all_for_search(search.id)
        return Response(result, status=status.HTTP_200_OK)


class RetryFailedScrapeView(APIView):
    """
    POST /api/searches/<id>/scrape/retry/    Body: {"limit": 20}

    WHY THIS EXISTS:
      Amazon and Flipkart often return a CAPTCHA or bot-block page on the
      first visit. The scraper now intentionally keeps scraped=False for
      those rows instead of marking them permanently done.

      Call this endpoint to retry those rows. A second attempt usually
      succeeds because Amazon/Flipkart bot-detection is time-based.

    HOW TO USE:
      1. POST /api/searches/<id>/scrape/all/    → first pass
      2. Check retryable_fails in response
      3. POST /api/searches/<id>/scrape/retry/  → retry bot-blocked rows
      4. Repeat step 3 until remaining_visual == 0
    """
    def post(self, request, pk):
        try:
            search = SearchHistory.objects.get(pk=pk)
        except SearchHistory.DoesNotExist:
            return Response({"error": f"Search id={pk} not found."}, status=status.HTTP_404_NOT_FOUND)

        limit   = max(1, min(int(request.data.get("limit", 20)), 50))
        pending = GoogleLensResult.objects.filter(search_id=pk, result_type="visual", scraped=False).count()

        if pending == 0:
            return Response({"message": "No unscraped visual results to retry.", "search_id": pk, "remaining": 0})

        result = retry_failed(search.id, limit=limit)
        return Response({
            **result,
            "message": (
                f"Retry done. {result['success']} succeeded, "
                f"{result.get('retryable_fails', 0)} still bot-blocked. "
                f"{result['remaining_visual']} remaining — call again if > 0."
            ),
        }, status=status.HTTP_200_OK)


class ScrapeSingleResultView(APIView):
    """
    POST /api/lens-results/<id>/scrape/
    Body: {"force": true}  to retry even if previously scraped.
    """
    def post(self, request, pk):
        try:
            lr = GoogleLensResult.objects.get(pk=pk)
        except GoogleLensResult.DoesNotExist:
            return Response({"error": f"GoogleLensResult id={pk} not found."}, status=status.HTTP_404_NOT_FOUND)

        if lr.scraped and request.data.get("force"):
            lr.scraped = False
            lr.save()

        result = scrape_one(lr.id)
        return Response({
            "lens_result_id": lr.id,
            "url"           : lr.link,
            "source"        : lr.source,
            "result_type"   : lr.result_type,
            **result,
        }, status=status.HTTP_200_OK if result.get("success") else status.HTTP_422_UNPROCESSABLE_ENTITY)


class SearchProductsView(APIView):
    """
    GET /api/searches/<id>/products/
    ?order=price_asc|price_desc   ?website=amazon
    All prices in INR. All product_links populated.
    """
    def get(self, request, pk):
        try:
            search = SearchHistory.objects.get(pk=pk)
        except SearchHistory.DoesNotExist:
            return Response({"error": f"Search id={pk} not found."}, status=status.HTTP_404_NOT_FOUND)

        qs = Product.objects.filter(search=search)
        if website := request.query_params.get("website"):
            qs = qs.filter(website__icontains=website)
        qs = qs.order_by("-price_numeric" if request.query_params.get("order") == "price_desc" else "price_numeric")

        serializer = ProductSerializer(qs, many=True)
        by_website = {}
        for p in serializer.data:
            by_website.setdefault(p["website"], []).append(p)

        return Response({
            "search_id"     : search.id,
            "search_keyword": search.search_keyword,
            "category"      : search.category,
            "total_products": qs.count(),
            "with_price"    : qs.filter(price_numeric__gt=0).count(),
            "without_price" : qs.filter(price_numeric=0).count(),
            "currency"      : "INR ₹ — all prices normalized",
            "filters_applied": {
                "sites"    : "Indian + ships-to-India only",
                "jewellery": "Imitation only (real/solid gold excluded)",
                "currency" : "All prices converted to ₹",
            },
            "by_website": by_website,
            "products"  : serializer.data,
        })
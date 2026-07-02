"""
products/views_scrape.py  — FIXED
-----------------------------------
Place at: products/views_scrape.py

FIX: Direct import instead of _runner() wrapper.
     retry_failed is now defined in runner.py so the import works.
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .models import SearchHistory, GoogleLensResult, Product
from .serializers import ProductSerializer

# Direct import — runner.py is at products/scrapers/runner.py
# retry_failed() is now defined in runner.py (was missing before — caused the HTML 500 error)
from .scrapers.runner import (
    promote_shopping_results,
    scrape_batch,
    scrape_all_for_search,
    scrape_one,
    retry_failed,          # ← this was missing from runner.py, causing ImportError → HTML 500
)


class PromoteShoppingResultsView(APIView):
    """POST /api/searches/<id>/promote-shopping/"""
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
                "message"        : "All shopping results already saved.",
                "search_id"      : pk,
                "products_in_db" : Product.objects.filter(search_id=pk).count(),
            })

        result = promote_shopping_results(search.id)

        products = Product.objects.filter(
            search_id=pk, id__in=result["product_ids"]
        ).order_by("price_numeric")

        return Response({
            "search_id"        : pk,
            "search_keyword"   : search.search_keyword,
            "promoted_count"   : result["promoted"],
            "skipped_site"     : result.get("skipped_site", 0),
            "skipped_real_gold": result.get("skipped_real_gold", 0),
            "message"          : (
                f"{result['promoted']} products saved with prices in ₹. "
                f"Filtered: {result.get('skipped_site', 0)} blocked sites, "
                f"{result.get('skipped_real_gold', 0)} real gold listings."
            ),
            "products": ProductSerializer(products, many=True).data,
        }, status=status.HTTP_201_CREATED)


class ScrapeSearchView(APIView):
    """POST /api/searches/<id>/scrape/   Body: {limit: 10}"""
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
            return Response({
                "message"  : "All visual results already scraped.",
                "search_id": pk,
                "remaining": 0,
                "done"     : True,
            })

        result = scrape_all_for_search(search.id)
        return Response(result, status=status.HTTP_200_OK)


class RetryFailedScrapeView(APIView):
    """
    POST /api/searches/<id>/scrape/retry/   Body: {limit: 20}

    Retries visual rows still scraped=False after a previous run.
    These are bot-blocked rows — Amazon/Flipkart CAPTCHA pages.
    Second attempt usually succeeds after a delay.
    """
    def post(self, request, pk):
        try:
            search = SearchHistory.objects.get(pk=pk)
        except SearchHistory.DoesNotExist:
            return Response({"error": f"Search id={pk} not found."}, status=status.HTTP_404_NOT_FOUND)

        limit   = max(1, min(int(request.data.get("limit", 20)), 50))
        pending = GoogleLensResult.objects.filter(
            search_id=pk, result_type="visual", scraped=False
        ).count()

        if pending == 0:
            return Response({
                "message"  : "No unscraped visual results to retry.",
                "search_id": pk,
                "remaining": 0,
            })

        result = retry_failed(search.id, limit=limit)
        return Response({
            **result,
            "message": (
                f"Retry done. {result.get('success', 0)} succeeded, "
                f"{result.get('retryable_fails', 0)} still bot-blocked. "
                f"{result.get('remaining_visual', 0)} remaining."
            ),
        }, status=status.HTTP_200_OK)


class ScrapeSingleResultView(APIView):
    """POST /api/lens-results/<id>/scrape/   Body: {force: true} to retry"""
    def post(self, request, pk):
        try:
            lr = GoogleLensResult.objects.get(pk=pk)
        except GoogleLensResult.DoesNotExist:
            return Response({"error": f"GoogleLensResult id={pk} not found."}, status=status.HTTP_404_NOT_FOUND)

        if lr.scraped and request.data.get("force"):
            lr.scraped = False
            lr.save(update_fields=["scraped"])

        result = scrape_one(lr.id)
        return Response({
            "lens_result_id": lr.id,
            "url"           : lr.link,
            "source"        : lr.source,
            "result_type"   : lr.result_type,
            **result,
        }, status=status.HTTP_200_OK if result.get("success") else status.HTTP_422_UNPROCESSABLE_ENTITY)


class SearchProductsView(APIView):
    """GET /api/searches/<id>/products/?order=price_asc&website=amazon"""
    def get(self, request, pk):
        try:
            search = SearchHistory.objects.get(pk=pk)
        except SearchHistory.DoesNotExist:
            return Response({"error": f"Search id={pk} not found."}, status=status.HTTP_404_NOT_FOUND)

        qs = Product.objects.filter(search=search)
        if website := request.query_params.get("website"):
            qs = qs.filter(website__icontains=website)
        qs = qs.order_by(
            "-price_numeric" if request.query_params.get("order") == "price_desc"
            else "price_numeric"
        )

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
            "by_website"    : by_website,
            "products"      : serializer.data,
        })

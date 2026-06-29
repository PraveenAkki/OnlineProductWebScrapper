"""
scrape_views.py  —  place at products/scrape_views.py
------------------------------------------------------
Import in products/urls.py:
    from .scrape_views import (
        ScrapeSearchView, ScrapeSearchAllView,
        ScrapeSingleResultView, SearchProductsView,
        PromoteShoppingResultsView,
    )
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .models import SearchHistory, GoogleLensResult, Product
from .serializers import ProductSerializer


class PromoteShoppingResultsView(APIView):
    """
    POST /api/searches/<id>/promote-shopping/

    Converts all shopping GoogleLensResult rows into Product rows immediately.
    No HTTP scraping — uses data already returned by Google Lens.

    Every shopping result gets a Product row with:
        product_link  = the actual URL (e.g. amazon.in/..., etsy.com/...)
        price         = price from Google
        rating        = rating from Google
        thumbnail     = Google thumbnail as placeholder image

    Call this right after /api/upload/google-lens/ to instantly populate
    all products that already have prices.
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
            already = Product.objects.filter(search_id=pk).count()
            return Response({
                "message"         : "All shopping results already promoted.",
                "search_id"       : pk,
                "products_in_db"  : already,
            })

        from products.scrapers.runner import promote_shopping_results
        result = promote_shopping_results(search.id)

        # Return the newly created product rows with their links
        products = Product.objects.filter(
            search_id = pk,
            id__in    = result["product_ids"],
        ).order_by("price_numeric")

        return Response({
            "search_id"        : pk,
            "search_keyword"   : search.search_keyword,
            "promoted_count"   : result["promoted"],
            "message"          : (
                f"{result['promoted']} shopping results promoted to Product rows. "
                f"All product_links are now stored in SQLite."
            ),
            "products"         : ProductSerializer(products, many=True).data,
        }, status=status.HTTP_201_CREATED)


class ScrapeSearchView(APIView):
    """
    POST /api/searches/<id>/scrape/

    Scrapes up to `limit` unscraped VISUAL GoogleLensResult rows.
    Shopping rows are handled by /promote-shopping/ — not this endpoint.

    Body (optional JSON):  {"limit": 10}
    """
    def post(self, request, pk):
        try:
            search = SearchHistory.objects.get(pk=pk)
        except SearchHistory.DoesNotExist:
            return Response({"error": f"Search id={pk} not found."}, status=status.HTTP_404_NOT_FOUND)

        limit = int(request.data.get("limit", 10))
        limit = max(1, min(limit, 30))

        from products.scrapers.runner import scrape_batch
        result = scrape_batch(search.id, limit=limit)
        return Response(result, status=status.HTTP_200_OK)


class ScrapeSearchAllView(APIView):
    """
    POST /api/searches/<id>/scrape/all/

    Scrapes ALL remaining unscraped visual results.
    WARNING: slow for 40+ results. Use /scrape/ in batches for large sets.
    """
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

        from products.scrapers.runner import scrape_all_for_search
        result = scrape_all_for_search(search.id)
        return Response(result, status=status.HTTP_200_OK)


class ScrapeSingleResultView(APIView):
    """
    POST /api/lens-results/<id>/scrape/

    Scrape a single GoogleLensResult (visual type) by its DB id.
    The product_link is always stored from GoogleLensResult.link.
    """
    def post(self, request, pk):
        try:
            lr = GoogleLensResult.objects.get(pk=pk)
        except GoogleLensResult.DoesNotExist:
            return Response({"error": f"GoogleLensResult id={pk} not found."}, status=status.HTTP_404_NOT_FOUND)

        from products.scrapers.runner import scrape_one
        result = scrape_one(lr.id)

        http_status = status.HTTP_200_OK if result["success"] else status.HTTP_422_UNPROCESSABLE_ENTITY
        return Response({
            "lens_result_id": lr.id,
            "url"           : lr.link,          # this IS the product_link stored in DB
            "source"        : lr.source,
            "result_type"   : lr.result_type,
            **result,
        }, status=http_status)


class SearchProductsView(APIView):
    """
    GET /api/searches/<id>/products/

    List all Product rows for a search — both promoted shopping results
    and scraped visual results. Every product has product_link populated.

    Query params:
      ?order=price_asc     sort low to high (default)
      ?order=price_desc    sort high to low
      ?website=amazon      filter by website name
    """
    def get(self, request, pk):
        try:
            search = SearchHistory.objects.get(pk=pk)
        except SearchHistory.DoesNotExist:
            return Response({"error": f"Search id={pk} not found."}, status=status.HTTP_404_NOT_FOUND)

        qs = Product.objects.filter(search=search)

        website = request.query_params.get("website")
        if website:
            qs = qs.filter(website__icontains=website)

        order = request.query_params.get("order", "price_asc")
        qs = qs.order_by("-price_numeric" if order == "price_desc" else "price_numeric")

        serializer = ProductSerializer(qs, many=True)

        # Group by website for UI rendering
        by_website = {}
        for p in serializer.data:
            by_website.setdefault(p["website"], []).append(p)

        # Count products with and without price
        with_price    = qs.filter(price_numeric__gt=0).count()
        without_price = qs.filter(price_numeric=0).count()

        return Response({
            "search_id"     : search.id,
            "search_keyword": search.search_keyword,
            "category"      : search.category,
            "total_products": qs.count(),
            "with_price"    : with_price,
            "without_price" : without_price,
            "by_website"    : by_website,
            "products"      : serializer.data,
        })
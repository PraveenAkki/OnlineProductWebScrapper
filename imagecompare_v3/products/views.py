import re
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import request, status
from django.conf import settings

from .models import SearchHistory, GoogleLensResult
from .serializers import SearchHistoryListSerializer, SearchHistoryDetailSerializer
from .classifier_modules.pipeline import run_pipeline

ALLOWED_TYPES = ["image/jpeg", "image/png", "image/webp", "image/jpg"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate_image(request):
    image_file = request.FILES.get("image")
    if not image_file:
        return None, Response(
            {"error": "No image. Send with key image as multipart/form-data."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if image_file.content_type not in ALLOWED_TYPES:
        return None, Response(
            {"error": "Invalid type. Allowed: jpg, png, webp."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return image_file, None


def _extract_lens_data(result: dict) -> tuple:
    """
    Safely pull lens data from the pipeline result dict.
    Handles pipeline wrapping the classifier output under different keys.
    Returns: (shopping_results, visual_matches, knowledge_graph, public_image_url)
    """
    # Case 1: top level (classifier returns directly)
    shopping = result.get("shopping_results", [])
    visual   = result.get("visual_matches",   [])
    kg       = result.get("knowledge_graph",  {})
    pub_url  = result.get("public_image_url", "")

    # Case 2: pipeline wraps under "google_lens_data"
    if not shopping and not visual:
        wrapped = result.get("google_lens_data", {})
        if wrapped:
            shopping = wrapped.get("shopping_results", [])
            visual   = wrapped.get("visual_matches",   [])
            kg       = wrapped.get("knowledge_graph",  {})
            pub_url  = wrapped.get("public_image_url", pub_url)
            print("[View] NOTE: data extracted from google_lens_data wrapper")

    print(f"[View] _extract_lens_data → shopping={len(shopping)} visual={len(visual)}")
    return shopping, visual, kg, pub_url


def _build_shopping_row(search, item: dict) -> GoogleLensResult:
    """
    Build a GoogleLensResult ORM object for a shopping item.
    These items already have price and rating from SerpAPI.
    """
    return GoogleLensResult(
        search        = search,
        result_type   = "shopping",
        rank          = int(item.get("rank") or 0),
        title         = str(item.get("title") or "")[:500],
        source        = str(item.get("source") or "")[:200],    
        link          = _safe_link(item, "link"),
        thumbnail     = _safe_link(item, "thumbnail"),
        image_url     = _safe_link(item, "image_url"),
        # Price — already extracted by classifier from nested price dict
        price         = str(item.get("price") or "")[:50],
        price_numeric = float(item.get("price_numeric") or 0.0),
        # Rating and reviews — directly on item from SerpAPI
        rating        = str(item.get("rating") or "")[:20],
        reviews       = str(item.get("reviews") or "")[:30],
        delivery      = str(item.get("delivery") or "")[:100],
        tag           = str(item.get("tag") or "")[:100],
    )


def _build_visual_row(search, item: dict) -> GoogleLensResult:
    """
    Build a GoogleLensResult ORM object for a visual match.
    These items have no price yet — scraper will extract later.
    """
    return GoogleLensResult(
        search        = search,
        result_type   = "visual",
        rank          = int(item.get("rank") or 0),
        title         = str(item.get("title") or "")[:500],
        source        = str(item.get("source") or "")[:200],
        link          = _safe_link(item, "link"),
        thumbnail     = _safe_link(item, "thumbnail"),
        image_url     = _safe_link(item, "image_url"),
        price         = "",
        price_numeric = 0.0,
        # Visual matches CAN have rating/reviews in this engine
        rating        = str(item.get("rating") or "")[:20],
        reviews       = str(item.get("reviews") or "")[:30],
        delivery      = "",
        tag           = "",
    )


# ---------------------------------------------------------------------------
# Upload views
# ---------------------------------------------------------------------------

class ImageUploadView(APIView):
    """POST /api/upload/ — Uses active phase from settings.py / .env"""
    def post(self, request):
        image_file, err = _validate_image(request)
        if err:
            return err
        search = SearchHistory(image=image_file)
        search.save()
        result = run_pipeline(search.image.path)
        search.detected_label     = result.get("detected_label", "")
        search.category           = result.get("category", "")
        search.confidence         = result.get("confidence", 0.0)
        search.detected_color     = result.get("detected_color", "")
        search.color_hex          = result.get("color_hex", "")
        search.clip_description   = result.get("clip_description", "")
        search.fashion_attributes = result.get("fashion_attributes", {})
        search.google_lens_data   = result.get("google_lens_data", {})
        search.search_keyword     = result.get("search_keyword", "")
        search.classifier_phase   = result.get("phase", "mobilenet")
        search.save()
        return Response({
            "id"                : search.id,
            "phase"             : search.classifier_phase,
            "detected_label"    : search.detected_label,
            "category"          : search.category,
            "confidence"        : round(search.confidence, 4),
            "detected_color"    : search.detected_color,
            "color_hex"         : search.color_hex,
            "clip_description"  : search.clip_description,
            "fashion_attributes": search.fashion_attributes,
            "search_keyword"    : search.search_keyword,
            "image_url"         : request.build_absolute_uri(search.image.url),
            "top5"              : result.get("top5", []),
            "error"             : result.get("error", ""),
            "message"           : "Done. Use search_keyword to trigger scraping.",
        }, status=status.HTTP_201_CREATED)


class ImageUploadFashionClipView(APIView):
    """POST /api/upload/fashion-clip/ — Always FashionCLIP + OpenCV color"""
    def post(self, request):
        image_file, err = _validate_image(request)
        if err:
            return err
        original = getattr(settings, "CLASSIFIER_PHASE", "mobilenet")
        settings.CLASSIFIER_PHASE = "fashion_clip"
        search = SearchHistory(image=image_file)
        search.save()
        result = run_pipeline(search.image.path)
        settings.CLASSIFIER_PHASE = original
        search.detected_label     = result.get("detected_label", "")
        search.category           = result.get("category", "")
        search.confidence         = result.get("confidence", 0.0)
        search.detected_color     = result.get("detected_color", "")
        search.color_hex          = result.get("color_hex", "")
        search.fashion_attributes = result.get("fashion_attributes", {})
        search.search_keyword     = result.get("search_keyword", "")
        search.classifier_phase   = "fashion_clip"
        search.save()
        return Response({
            "id"                : search.id,
            "phase"             : "fashion_clip",
            "category"          : search.category,
            "detected_color"    : search.detected_color,
            "color_hex"         : search.color_hex,
            "fashion_attributes": search.fashion_attributes,
            "search_keyword"    : search.search_keyword,
            "image_url"         : request.build_absolute_uri(search.image.url),
            "top5"              : result.get("top5", []),
            "error"             : result.get("error", ""),
            "message"           : "FashionCLIP done. Use search_keyword to trigger scraping.",
        }, status=status.HTTP_201_CREATED)


class ImageUploadGoogleLensView(APIView):
    """
    POST /api/upload/google-lens/

    Flow:
      1. Save uploaded image to Django media/
      2. Classifier uploads to tmpfiles.org -> calls SerpAPI twice
      3. Classifier splits results:
           shopping_results = items that HAVE a price  (price nested dict in SerpAPI response)
           visual_matches   = items that have NO price (scraper gets price later)
      4. Save one GoogleLensResult row per link, keyed by search.id
         shopping rows: price + rating + reviews already populated
         visual rows:   price/rating blank, scraped=False for later
      5. Return full response sorted shopping first
    """
    def post(self, request):
        image_file, err = _validate_image(request)
        if err:
            return err

        # Step 1: Save image to disk
        search = SearchHistory(image=image_file)
        search.save()

        # Step 2: Run Google Lens pipeline
        original = getattr(settings, "CLASSIFIER_PHASE", "mobilenet")
        settings.CLASSIFIER_PHASE = "google_lens"
        result = run_pipeline(search.image.path)
        settings.CLASSIFIER_PHASE = original

        if result.get("error"):
            search.delete()
            return Response({
                "error"            : result["error"],
                "help"             : "Check SERPAPI_KEY in .env — get a key at https://serpapi.com/",
                "debug_result_keys": list(result.keys()),
            }, status=status.HTTP_400_BAD_REQUEST)

        # Step 3: Extract data (handles pipeline wrapping)
        shopping_results, visual_matches, knowledge_graph, public_image_url = (
            _extract_lens_data(result)
        )

        # Step 4: Build ORM rows
        # Shopping first (already have prices from Google), then visual
        lens_rows = []
        for item in shopping_results:
            row = _build_shopping_row(search, item)
            if row.link:
                lens_rows.append(row)

        for item in visual_matches:
            row = _build_visual_row(search, item)
            if row.link:
                lens_rows.append(row)

        # Step 5: Save SearchHistory
        search.detected_label   = result.get("detected_label", "")
        search.category         = result.get("category", "")
        search.confidence       = 1.0
        search.search_keyword   = result.get("base_keyword") or result.get("detected_label", "")
        search.google_lens_data = {
            "public_image_url": public_image_url,
            "knowledge_graph" : knowledge_graph,
            "shopping_count"  : len(shopping_results),
            "visual_count"    : len(visual_matches),
            "shopping_results": shopping_results,
            "visual_matches"  : visual_matches,
        }
        search.classifier_phase = "google_lens"
        search.save()

        # Step 6: Bulk insert all rows in one SQL statement
        if lens_rows:
            GoogleLensResult.objects.bulk_create(lens_rows)
            print(
                f"[View] bulk_create OK — "
                f"{len([r for r in lens_rows if r.result_type == 'shopping'])} shopping "
                f"+ {len([r for r in lens_rows if r.result_type == 'visual'])} visual "
                f"for search id={search.id}"
            )
        else:
            print(f"[View] WARNING: 0 rows saved for search id={search.id}")

        # Build response sections
        shopping_out = [
            {
                "rank"          : r.rank,
                "title"         : r.title,
                "source"        : r.source,
                "price"         : r.price,
                "price_numeric" : r.price_numeric,
                "rating"        : r.rating,
                "reviews"       : r.reviews,
                "in_stock"      : True,   # classifier only includes in_stock items
                "link"          : r.link,
                "thumbnail"     : r.thumbnail,
                "image_url"     : r.image_url,
            }
            for r in lens_rows if r.result_type == "shopping"
        ]
        visual_out = [
            {
                "rank"      : r.rank,
                "title"     : r.title,
                "source"    : r.source,
                "link"      : r.link,
                "thumbnail" : r.thumbnail,
                "image_url" : r.image_url,
                "rating"    : r.rating,
                "reviews"   : r.reviews,
            }
            for r in lens_rows if r.result_type == "visual"
        ]

        lens_url = f"/api/searches/{search.id}/lens-results/"

        return Response({
            "id"              : search.id,
            "phase"           : "google_lens",
            "detected_label"  : search.detected_label,
            "category"        : search.category,
            "search_keyword"  : search.search_keyword,
            "image_url"       : request.build_absolute_uri(search.image.url),
            "public_image_url": public_image_url,
            "knowledge_graph" : knowledge_graph,
            "result_counts"   : {
                "shopping_with_price": len(shopping_out),
                "visual_no_price"    : len(visual_out),
                "total"              : len(lens_rows),
            },
            # Shopping — price/rating already available from Google
            "shopping_results": shopping_out,
            # Visual — links saved, scraper extracts price later
            "visual_matches"  : visual_out,
            "top5"            : result.get("top5", []),
            "lens_results_url": lens_url,
            "message"         : (
                f"Done. {len(shopping_out)} results with price + "
                f"{len(visual_out)} visual links = {len(lens_rows)} total saved. "
                f"GET {lens_url}?type=shopping to see priced items. "
                f"GET {lens_url}?type=visual for links to scrape."
            ),
        }, status=status.HTTP_201_CREATED)


class GoogleLensResultsView(APIView):
    """
    GET /api/searches/<id>/lens-results/

    Returns all GoogleLensResult rows for a search, keyed by search.id.
    Shopping (with price) always listed before visual (no price yet).

    Query params:
      ?type=shopping       only items that had price from Google
      ?type=visual         only items with no price (need scraping)
      ?scraped=false       not yet scraped
      ?scraped=true        already scraped
      ?order=price_asc     sort by price low to high
      ?order=price_desc    sort by price high to low
    """
    def get(self, request, pk):
        try:
            search = SearchHistory.objects.get(pk=pk)
        except SearchHistory.DoesNotExist:
            return Response(
                {"error": f"Search id={pk} not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        qs = search.lens_results.all()

        result_type = request.query_params.get("type")
        if result_type in ("visual", "shopping"):
            qs = qs.filter(result_type=result_type)

        scraped_param = request.query_params.get("scraped")
        if scraped_param == "false":
            qs = qs.filter(scraped=False)
        elif scraped_param == "true":
            qs = qs.filter(scraped=True)

        order_param = request.query_params.get("order")
        if order_param == "price_asc":
            qs = qs.order_by("result_type", "price_numeric", "rank")
        elif order_param == "price_desc":
            qs = qs.order_by("result_type", "-price_numeric", "rank")

        # ── select_related("product") pulls the linked Product (if any) in
        # the same query via JOIN, so we can tell the frontend whether this
        # lens result has already been promoted — without an N+1 query.
        qs = qs.select_related("product")

        results = []
        for lr in qs:
            product = getattr(lr, "product", None)
            results.append({
                "id"             : lr.id,
                "result_type"    : lr.result_type,
                "rank"           : lr.rank,
                "title"          : lr.title,
                "link"           : lr.link,
                "source"         : lr.source,
                "thumbnail"      : lr.thumbnail,
                "image_url"      : lr.image_url,
                "price"          : lr.price,
                "price_numeric"  : lr.price_numeric,
                "rating"         : lr.rating,
                "reviews"        : lr.reviews,
                "delivery"       : lr.delivery,
                "tag"            : lr.tag,
                "scraped"        : lr.scraped,
                "scraped_price"  : lr.scraped_price,
                "scraped_rating" : lr.scraped_rating,
                "scraped_at"     : lr.scraped_at,
                "created_at"     : lr.created_at,
                "product_id"     : product.id if product else None,
            })

        shopping_count = sum(1 for r in results if r["result_type"] == "shopping")
        visual_count   = sum(1 for r in results if r["result_type"] == "visual")

        return Response({
            "search_id"     : search.id,
            "search_keyword": search.search_keyword,
            "category"      : search.category,
            "counts": {
                "shopping_with_price": shopping_count,
                "visual_no_price"    : visual_count,
                "total"              : len(results),
            },
            "results": results,
        })


class SearchHistoryListView(APIView):
    """GET /api/searches/ — List all past searches with counts"""
    def get(self, request):
        searches   = SearchHistory.objects.all()
        serializer = SearchHistoryListSerializer(
            searches, many=True, context={"request": request}
        )
        return Response(serializer.data)


class SearchHistoryDetailView(APIView):
    """GET /api/searches/<id>/ — Full detail with products and lens results"""
    def get(self, request, pk):
        try:
            search = SearchHistory.objects.get(pk=pk)
        except SearchHistory.DoesNotExist:
            return Response(
                {"error": f"Search id={pk} not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = SearchHistoryDetailSerializer(search, context={"request": request})
        return Response(serializer.data)


class PhaseInfoView(APIView):
    """GET /api/phase/ — Show all phases and endpoints"""
    def get(self, request):
        active      = getattr(settings, "CLASSIFIER_PHASE", "mobilenet")
        serpapi_key = getattr(settings, "SERPAPI_KEY", "")
        return Response({
            "active_phase"       : active,
            "serpapi_configured" : bool(serpapi_key and serpapi_key != "your_serpapi_key_here"),
            "switch_in"          : "imagecompare/settings.py or .env -> CLASSIFIER_PHASE",
            "all_phases"         : {
                "mobilenet"   : {"endpoint": "/api/upload/",              "cost": "free",           "offline": True},
                "fashion_clip": {"endpoint": "/api/upload/fashion-clip/", "cost": "free",           "offline": True},
                "google_lens" : {"endpoint": "/api/upload/google-lens/",  "cost": "100 free/month", "offline": False},
            },
            "all_endpoints": {
                "POST /api/upload/google-lens/"                          : "Classify + save all lens results",
                "GET  /api/searches/<id>/lens-results/"                  : "All saved results for a search",
                "GET  /api/searches/<id>/lens-results/?type=shopping"    : "Only items with price from Google",
                "GET  /api/searches/<id>/lens-results/?type=visual"      : "Only items needing scraping",
                "GET  /api/searches/<id>/lens-results/?scraped=false"    : "Unscraped links (for scraper queue)",
                "GET  /api/searches/<id>/lens-results/?order=price_asc"  : "Sort by price low to high",
                "GET  /api/searches/<id>/lens-results/?order=price_desc" : "Sort by price high to low",
            },
        })
    


def _safe_link(item: dict, key: str, max_len: int = 3000) -> str:
    raw = str(item.get(key) or "")
    print(f"[View] _safe_link key={key} len={len(raw)} max_len={max_len} url={raw[:120]}")
    if len(raw) > max_len:
        print(f"[View] WARNING: {key} truncated from {len(raw)} to {max_len} chars: {raw[:80]}...")
        raw = raw[:max_len]
    return raw
from django.urls import path
from .views import (
    ImageUploadView,
    ImageUploadFashionClipView,
    ImageUploadGoogleLensView,
    GoogleLensResultsView,
    SearchHistoryListView,
    SearchHistoryDetailView,
    PhaseInfoView,
)
from .views_scrape import (
    PromoteShoppingResultsView,
    ScrapeSearchView,
    ScrapeSearchAllView,
    ScrapeSingleResultView,
    SearchProductsView,
)
from .export_views import (
    ExportSearchView,
    ExportSearchLensOnlyView,
    ExportAllSearchesView,
)

urlpatterns = [
    # ── Classify / upload ─────────────────────────────────────────
    path('upload/',              ImageUploadView.as_view(),            name='upload'),
    path('upload/fashion-clip/', ImageUploadFashionClipView.as_view(), name='upload-fashion-clip'),
    path('upload/google-lens/',  ImageUploadGoogleLensView.as_view(),  name='upload-google-lens'),

    # ── Search history ────────────────────────────────────────────
    path('searches/',            SearchHistoryListView.as_view(),       name='search-list'),
    path('searches/<int:pk>/',   SearchHistoryDetailView.as_view(),     name='search-detail'),

    # ── Google Lens result links ──────────────────────────────────
    path('searches/<int:pk>/lens-results/', GoogleLensResultsView.as_view(), name='lens-results'),

    # ── Step 1: Promote shopping → Product rows (instant, no scraping) ───────
    path('searches/<int:pk>/promote-shopping/', PromoteShoppingResultsView.as_view(), name='promote-shopping'),

    # ── Step 2: Scrape visual results to get price ────────────────
    path('searches/<int:pk>/scrape/',           ScrapeSearchView.as_view(),           name='scrape-batch'),
    path('searches/<int:pk>/scrape/all/',       ScrapeSearchAllView.as_view(),        name='scrape-all'),

    # ── Retry / test a single result ──────────────────────────────
    path('lens-results/<int:pk>/scrape/',       ScrapeSingleResultView.as_view(),     name='scrape-single'),

    # ── View all products with links ──────────────────────────────
    path('searches/<int:pk>/products/',         SearchProductsView.as_view(),         name='search-products'),

    # ── Excel export (works on Render.com — streams from memory) ─
    path('searches/<int:pk>/export/',           ExportSearchView.as_view(),           name='export-search'),
    path('searches/<int:pk>/export/lens/',      ExportSearchLensOnlyView.as_view(),   name='export-lens'),
    path('export/all/',                         ExportAllSearchesView.as_view(),      name='export-all'),

    # ── Info ──────────────────────────────────────────────────────
    path('phase/',               PhaseInfoView.as_view(),              name='phase-info'),
]

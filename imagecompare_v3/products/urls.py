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
    RetryFailedScrapeView,       # ← NEW: retry bot-blocked rows
    ScrapeSingleResultView,
    SearchProductsView,
)
from .export_views import (
    ExportSearchView,
    ExportSearchLensOnlyView,
    ExportAllSearchesView,
)

urlpatterns = [
    # ── Upload ────────────────────────────────────────────────────
    path('upload/',              ImageUploadView.as_view(),            name='upload'),
    path('upload/fashion-clip/', ImageUploadFashionClipView.as_view(), name='upload-fashion-clip'),
    path('upload/google-lens/',  ImageUploadGoogleLensView.as_view(),  name='upload-google-lens'),

    # ── Search history ────────────────────────────────────────────
    path('searches/',            SearchHistoryListView.as_view(),       name='search-list'),
    path('searches/<int:pk>/',   SearchHistoryDetailView.as_view(),     name='search-detail'),

    # ── Lens results ──────────────────────────────────────────────
    path('searches/<int:pk>/lens-results/', GoogleLensResultsView.as_view(), name='lens-results'),

    # ── Products ──────────────────────────────────────────────────
    path('searches/<int:pk>/products/', SearchProductsView.as_view(), name='search-products'),

    # ── Scraper ───────────────────────────────────────────────────
    path('searches/<int:pk>/promote-shopping/', PromoteShoppingResultsView.as_view(), name='promote-shopping'),
    path('searches/<int:pk>/scrape/',           ScrapeSearchView.as_view(),            name='scrape-batch'),
    path('searches/<int:pk>/scrape/all/',       ScrapeSearchAllView.as_view(),         name='scrape-all'),
    path('searches/<int:pk>/scrape/retry/',     RetryFailedScrapeView.as_view(),       name='scrape-retry'),
    path('lens-results/<int:pk>/scrape/',       ScrapeSingleResultView.as_view(),      name='scrape-single'),

    # ── Export ────────────────────────────────────────────────────
    path('searches/<int:pk>/export/',      ExportSearchView.as_view(),         name='export-search'),
    path('searches/<int:pk>/export/lens/', ExportSearchLensOnlyView.as_view(), name='export-lens'),
    path('export/all/',                    ExportAllSearchesView.as_view(),    name='export-all'),

    # ── Info ──────────────────────────────────────────────────────
    path('phase/',               PhaseInfoView.as_view(),              name='phase-info'),
]

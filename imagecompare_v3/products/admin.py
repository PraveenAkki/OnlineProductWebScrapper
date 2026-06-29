from django.contrib import admin
from django.utils.html import format_html
from .models import SearchHistory, GoogleLensResult, Product


@admin.register(SearchHistory)
class SearchHistoryAdmin(admin.ModelAdmin):
    list_display    = ["id", "search_keyword", "category", "detected_color",
                       "classifier_phase", "confidence", "created_at"]
    list_filter     = ["category", "classifier_phase"]
    search_fields   = ["search_keyword", "detected_label"]
    readonly_fields = ["detected_label", "category", "detected_color", "color_hex",
                       "clip_description", "fashion_attributes", "google_lens_data",
                       "search_keyword", "confidence", "classifier_phase", "created_at"]


@admin.register(GoogleLensResult)
class GoogleLensResultAdmin(admin.ModelAdmin):
    list_display    = [
        "id", "search_id_col", "result_type", "rank",
        "title", "source",
        "clickable_link",           # ← product link, clickable
        "price", "rating", "reviews",
        "scraped",
    ]
    list_filter     = ["result_type", "scraped", "source"]
    search_fields   = ["title", "source", "link"]
    list_editable   = ["scraped"]
    readonly_fields = [
        "search", "result_type", "rank", "title",
        "clickable_link_detail",    # ← full clickable link in detail view
        "source", "thumbnail", "image_url",
        "price", "price_numeric", "rating", "reviews",
        "delivery", "tag",
        "scraped_price", "scraped_rating", "scraped_at",
        "created_at",
    ]
    ordering        = ["search", "result_type", "rank"]
    # Show raw link field in add/change form as well
    fields          = [
        "search", "result_type", "rank", "title",
        "clickable_link_detail", "source", "thumbnail", "image_url",
        "price", "price_numeric", "rating", "reviews",
        "delivery", "tag",
        "scraped", "scraped_price", "scraped_rating", "scraped_at",
        "created_at",
    ]

    def search_id_col(self, obj):
        return obj.search_id
    search_id_col.short_description = "Search"

    def clickable_link(self, obj):
        """Clickable short link shown in list view."""
        if not obj.link:
            return "—"
        short = obj.link[:50] + "…" if len(obj.link) > 50 else obj.link
        return format_html('<a href="{}" target="_blank">{}</a>', obj.link, short)
    clickable_link.short_description = "Product Link"
    clickable_link.allow_tags = True

    def clickable_link_detail(self, obj):
        """Full clickable link shown in the detail / change view."""
        if not obj.link:
            return "—"
        return format_html('<a href="{}" target="_blank">{}</a>', obj.link, obj.link)
    clickable_link_detail.short_description = "Product Link (full)"


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display    = [
        "id", "website", "product_name",
        "price", "price_numeric",
        "discount", "rating", "reviews",
        "clickable_product_link",   # ← product link, clickable
        "delivery", "search_id_col",
    ]
    list_filter     = ["website"]
    search_fields   = ["product_name", "website", "product_link"]
    readonly_fields = [
        "search", "lens_result",
        "clickable_product_link_detail",   # ← full link in detail view
        "created_at",
    ]
    fields          = [
        "search", "lens_result",
        "website", "product_name",
        "price", "price_numeric", "discount",
        "rating", "reviews",
        "product_image",
        "clickable_product_link_detail",
        "delivery", "created_at",
    ]

    def search_id_col(self, obj):
        return obj.search_id
    search_id_col.short_description = "Search"

    def clickable_product_link(self, obj):
        """Clickable short product link shown in list view."""
        if not obj.product_link:
            return "—"
        short = obj.product_link[:55] + "…" if len(obj.product_link) > 55 else obj.product_link
        return format_html('<a href="{}" target="_blank">{}</a>', obj.product_link, short)
    clickable_product_link.short_description = "Product Link"

    def clickable_product_link_detail(self, obj):
        """Full clickable link in the detail / change view."""
        if not obj.product_link:
            return "—"
        return format_html('<a href="{}" target="_blank">{}</a>', obj.product_link, obj.product_link)
    clickable_product_link_detail.short_description = "Product Link (full)"
from rest_framework import serializers
from .models import SearchHistory, Product, GoogleLensResult


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Product
        fields = [
            'id', 'website', 'product_name', 'price', 'price_numeric',
            'discount', 'rating', 'reviews', 'product_image',
            'product_link', 'delivery', 'created_at', 'last_scraped_at', 
        ]


class GoogleLensResultSerializer(serializers.ModelSerializer):
    product_id = serializers.SerializerMethodField()   # ← THIS WAS MISSING

    def get_product_id(self, obj):
        """
        Returns the id of the Product row promoted from this lens result,
        or None if it hasn't been promoted yet. Lets the UI show
        '✓ In products' vs 'Not promoted' without a separate lookup.
        """
        product = getattr(obj, "product", None)
        return product.id if product else None

    class Meta:
        model  = GoogleLensResult
        fields = [
            'id', 'result_type', 'rank',
            'title', 'link', 'source', 'thumbnail', 'image_url',
            'price', 'price_numeric', 'rating', 'reviews',
            'delivery', 'tag',
            'scraped', 'scraped_price', 'scraped_rating', 'scraped_at', 'product_id',
            'created_at',
        ]


class SearchHistoryListSerializer(serializers.ModelSerializer):
    product_count     = serializers.IntegerField(source='products.count',     read_only=True)
    lens_result_count = serializers.IntegerField(source='lens_results.count', read_only=True)
    shopping_count    = serializers.SerializerMethodField()
    visual_count      = serializers.SerializerMethodField()

    def get_shopping_count(self, obj):
        return obj.lens_results.filter(result_type="shopping").count()

    def get_visual_count(self, obj):
        return obj.lens_results.filter(result_type="visual").count()

    class Meta:
        model  = SearchHistory
        fields = [
            'id', 'search_keyword', 'category', 'detected_label',
            'detected_color', 'color_hex', 'clip_description',
            'confidence', 'classifier_phase', 'image',
            'product_count', 'lens_result_count',
            'shopping_count', 'visual_count',
            'created_at',
        ]


class SearchHistoryDetailSerializer(serializers.ModelSerializer):
    products     = ProductSerializer(many=True, read_only=True)
    lens_results = GoogleLensResultSerializer(many=True, read_only=True)

    class Meta:
        model  = SearchHistory
        fields = [
            'id', 'image', 'detected_label', 'category',
            'detected_color', 'color_hex', 'clip_description',
            'fashion_attributes', 'search_keyword',
            'confidence', 'classifier_phase',
            'google_lens_data', 'created_at',
            'products', 'lens_results',
        ]

from django.db import models



class SearchHistory(models.Model):
    image              = models.ImageField(upload_to='uploads/')

    # Phase 1+2: MobileNet
    detected_label     = models.CharField(max_length=255, blank=True)
    category           = models.CharField(max_length=100, blank=True)
    confidence         = models.FloatField(default=0.0)

    # Phase 2: OpenCV color
    detected_color     = models.CharField(max_length=50,  blank=True)
    color_hex          = models.CharField(max_length=10,  blank=True)

    # Phase 3: CLIP
    clip_description   = models.CharField(max_length=500, blank=True)

    # Phase 4A: FashionCLIP attributes
    fashion_attributes = models.JSONField(default=dict, blank=True)

    # Phase 4B: Google Lens raw response (full JSON blob for reference)
    google_lens_data   = models.JSONField(default=dict, blank=True)

    # Final keyword used by scraper
    search_keyword     = models.CharField(max_length=255, blank=True)
    classifier_phase   = models.CharField(max_length=20,  default='mobilenet')

    created_at         = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.id}] {self.search_keyword} | {self.classifier_phase}"


class GoogleLensResult(models.Model):
    """
    One row per URL returned by Google Lens for a search.

    Two types:
        shopping  →  actual product listing with price, rating, delivery
        visual    →  image match (no price — scraper will extract price later)

    Ordering:
        shopping comes first (already has price), then visual.
        Within each type, ordered by rank (Google's own ranking).

    scraped flag:
        False = not yet visited by scraper
        True  = scraper has visited, extracted price, saved a Product row
    """

    RESULT_TYPES = [
        ("shopping", "Shopping Result"),
        ("visual",   "Visual Match"),
    ]

    search        = models.ForeignKey(
        SearchHistory,
        on_delete=models.CASCADE,
        related_name="lens_results",
    )

    # ── Core fields (both types) ─────────────────────────────────
    result_type   = models.CharField(max_length=10, choices=RESULT_TYPES, default="visual")
    rank          = models.PositiveSmallIntegerField(default=0)   # Google's rank (1-based)
    title         = models.CharField(max_length=500, blank=True)
    link          = models.URLField(max_length=3000)              # page to scrape
    source        = models.CharField(max_length=200, blank=True)  # site name e.g. "Amazon.in"
    thumbnail     = models.URLField(max_length=3000, blank=True)  # product image from Google

    # ── Shopping-only fields (populated from SerpAPI shopping_results) ──────
    price         = models.CharField(max_length=50,  blank=True)  # display e.g. "₹499"
    price_numeric = models.FloatField(default=0.0)                # SerpAPI extracted_price
    rating        = models.CharField(max_length=20,  blank=True)  # e.g. "4.2"
    reviews       = models.CharField(max_length=30,  blank=True)  # e.g. "1,250"
    delivery      = models.CharField(max_length=100, blank=True)  # e.g. "Free delivery"
    tag           = models.CharField(max_length=100, blank=True)  # e.g. "Best seller"

    # ── Visual-only fields ───────────────────────────────────────
    image_url     = models.URLField(max_length=3000, blank=True)  # original image URL

    # ── Scraper control ──────────────────────────────────────────
    scraped       = models.BooleanField(default=False)
    # After scraping, scraped_price and scraped_rating are filled in
    scraped_price   = models.CharField(max_length=50,  blank=True)
    scraped_rating  = models.CharField(max_length=20,  blank=True)
    scraped_at      = models.DateTimeField(null=True, blank=True)

    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        # shopping before visual, within each group by rank
        ordering = ['result_type', 'rank']

    def __str__(self):
        price_str = f" | {self.price}" if self.price else " | no price"
        return (
            f"[search={self.search_id}] "
            f"#{self.rank} {self.result_type} | "
            f"{self.source}{price_str}"
        )


class Product(models.Model):
    """
    Final scraped product — created by the scraper engine.
    Each Product links to a SearchHistory and optionally to a GoogleLensResult.
    """
    search        = models.ForeignKey(
        SearchHistory,
        on_delete=models.CASCADE,
        related_name='products'
    )
    # Optional link to the GoogleLensResult that triggered this scrape
    lens_result   = models.OneToOneField(
        GoogleLensResult,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='product',
    )
    website       = models.CharField(max_length=50)
    product_name  = models.CharField(max_length=500)
    price         = models.CharField(max_length=50)
    price_numeric = models.FloatField(default=0.0)
    discount      = models.CharField(max_length=50,  blank=True)
    rating        = models.CharField(max_length=20,  blank=True)
    reviews       = models.CharField(max_length=30,  blank=True)
    product_image = models.URLField(max_length=3000, blank=True)
    product_link  = models.URLField(max_length=3000)
    delivery      = models.CharField(max_length=100, blank=True)
    last_scraped_at = models.DateTimeField(null=True, blank=True)
    created_at    = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    def __str__(self):
        return f"[{self.website}] {self.product_name[:60]} | {self.price}"



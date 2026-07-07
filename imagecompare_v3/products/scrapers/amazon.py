"""
scraper_engine/amazon.py
------------------------
Scrapes Amazon.in product pages.

Targets:
    product_name  : #productTitle
    price         : .a-price-whole  (current price)
    discount      : .savingsPercentage
    rating        : scoped to #acrPopover / review summary block
                    (NOT the bare .a-icon-alt, which matches unrelated
                    icons like pagination "Previous"/"Next" controls)
    reviews       : #acrCustomerReviewText
    product_image : #landingImage (data-old-hires or src)
    delivery      : #mir-layout-DELIVERY_BLOCK
"""

import re
from bs4 import BeautifulSoup
from .base import BaseScraper


class AmazonScraper(BaseScraper):
    website = "amazon"

    def scrape(self, url: str) -> dict:
        html = self.get_html(url)
        if not html:
            return self.empty("Failed to fetch Amazon page")

        soup = BeautifulSoup(html, "html.parser")

        # ── Product name ──────────────────────────────────────────
        name_el = soup.select_one("#productTitle")
        product_name = name_el.get_text(strip=True) if name_el else ""

        # ── Price ─────────────────────────────────────────────────
        price_el = soup.select_one(".a-price-whole")
        price = ""
        if price_el:
            fraction_el = soup.select_one(".a-price-fraction")
            fraction    = fraction_el.get_text(strip=True) if fraction_el else "00"
            price       = f"₹{price_el.get_text(strip=True)}.{fraction}"
        if not price:
            fb = soup.select_one("#priceblock_ourprice, #priceblock_dealprice")
            if fb:
                price = fb.get_text(strip=True)

        price_numeric = self.parse_price(price)

        # ── Discount ──────────────────────────────────────────────
        discount_el = soup.select_one(".savingsPercentage")
        discount = discount_el.get_text(strip=True) if discount_el else ""

        # ── Rating ────────────────────────────────────────────────
        # Scoped to the review-summary block — bare ".a-icon-alt" also
        # matches unrelated icons (e.g. carousel "Previous"/"Next"
        # controls), which was silently grabbing the wrong element.
        rating = ""
        rating_el = soup.select_one(
            "#acrPopover .a-icon-alt, "
            "span[data-hook='rating-out-of-text'], "
            "i[data-hook='average-star-rating'] .a-icon-alt"
        )
        if not rating_el:
            review_block = soup.select_one("#averageCustomerReviews, #reviewsMedley")
            if review_block:
                rating_el = review_block.select_one(".a-icon-alt")
        if rating_el:
            raw = rating_el.get_text(strip=True)
            match = re.search(r"(\d+\.?\d*)\s*out of", raw)
            rating = match.group(1) if match else ""

        # ── Reviews ───────────────────────────────────────────────
        reviews_el = soup.select_one("#acrCustomerReviewText")
        reviews = reviews_el.get_text(strip=True) if reviews_el else ""
        reviews = reviews.replace(" ratings", "").replace(" rating", "").strip()

        # ── Product image ─────────────────────────────────────────
        img_el = soup.select_one("#landingImage")
        product_image = ""
        if img_el:
            product_image = (
                img_el.get("data-old-hires") or
                img_el.get("data-src")       or
                img_el.get("src", "")
            )

        # ── Delivery ──────────────────────────────────────────────
        delivery_el = soup.select_one("#mir-layout-DELIVERY_BLOCK span[data-csa-c-content-id]")
        if not delivery_el:
            delivery_el = soup.select_one(".delivery-message, #deliveryMessageMirId")
        delivery = delivery_el.get_text(strip=True) if delivery_el else ""

        if not product_name and not price:
            return self.empty("Amazon page parsed but no data found — possible bot block")

        return {
            "product_name" : product_name,
            "price"        : price,
            "price_numeric": price_numeric,
            "discount"     : discount,
            "rating"       : rating,
            "reviews"      : reviews,
            "product_image": product_image,
            "delivery"     : delivery,
            "website"      : self.website,
            "error"        : "",
        }
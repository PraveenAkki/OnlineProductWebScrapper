"""
products/scrapers/meesho.py  — FIXED
--------------------------------------
Place at: products/scrapers/meesho.py

BUGS FIXED:
  1. empty() was called without retryable= argument.
     base.py now reads self._last_retryable which is set by get_html().
     403 → _last_retryable=False → marks scraped=True, never retried.
     This was causing infinite retry loops on Meesho bot-blocked URLs.

  2. Added session warm-up in base.py (homepage visit before product page).
     Meesho sets cookies on homepage that are required for product pages.

  3. Meesho's __NEXT_DATA__ path has changed — added more key fallbacks.
"""

import json
from bs4 import BeautifulSoup
from .base import BaseScraper


class MeeshoScraper(BaseScraper):
    website = "meesho"

    def scrape(self, url: str) -> dict:
        html = self.get_html_selenium(url)
        if not html:
            # base.py already set self._last_retryable correctly:
            #   403 → retryable=False (permanent bot block — mark done)
            #   429 → retryable=True  (rate limit — retry later)
            #   timeout → retryable=True
            return self.empty()   # picks up retryable from self._last_retryable

        # Method 1: __NEXT_DATA__ JSON blob (most reliable)
        result = self._parse_next_data(html)
        if result:
            return result

        # Method 2: CSS selectors fallback
        result = self._parse_html(html)
        if result and result.get("product_name"):
            return result

        # Page loaded (200) but no data extracted — could be a layout change
        # Mark as permanent failure (retryable=False) since the page DID load
        return self.empty(
            error="Meesho: page loaded but no product data found (layout may have changed)",
            retryable=False
        )

    def _parse_next_data(self, html: str) -> dict:
        """Extract product data from Next.js JSON payload."""
        soup = BeautifulSoup(html, "html.parser")
        script = soup.select_one("script#__NEXT_DATA__")
        if not script or not script.string:
            return {}
        try:
            data    = json.loads(script.string)
            props   = data.get("props", {}).get("pageProps", {})

            # Try multiple key paths — Meesho changes these occasionally
            product = (
                props.get("product") or
                props.get("productData") or
                props.get("data", {}).get("product") or
                {}
            )
            if not product:
                return {}

            product_name  = product.get("name", "")
            price_val     = product.get("price") or product.get("mrp") or 0
            price         = f"₹{price_val}" if price_val else ""
            price_numeric = float(price_val or 0)

            discount_pct  = product.get("discountPercentage") or product.get("discount") or ""
            discount      = f"{discount_pct}% off" if discount_pct else ""

            rating        = str(product.get("averageRating") or product.get("rating") or "")
            reviews       = str(product.get("totalReviewCount") or product.get("reviewCount") or "")

            images        = product.get("images") or []
            product_image = ""
            if images and isinstance(images, list):
                first = images[0]
                product_image = first.get("url", "") if isinstance(first, dict) else str(first)

            if not product_name:
                return {}

            return {
                "product_name" : product_name,
                "price"        : price,
                "price_numeric": price_numeric,
                "discount"     : discount,
                "rating"       : rating,
                "reviews"      : reviews,
                "product_image": product_image,
                "delivery"     : "",
                "website"      : self.website,
                "error"        : "",
                "retryable"    : False,
            }
        except Exception as e:
            print(f"[meesho] __NEXT_DATA__ parse error: {e}")
            return {}

    def _parse_html(self, html: str) -> dict:
        """CSS selector fallback for Meesho."""
        soup = BeautifulSoup(html, "html.parser")

        name_el   = soup.select_one("p.sc-eDvSVe, h1, p[class*='ProductName']")
        price_el  = soup.select_one("h5.sc-dcJsrY, span[class*='price'], h4[class*='Price']")
        rating_el = soup.select_one("p[class*='rating'], span[class*='rating']")
        img_el    = soup.select_one(
            "img[class*='ProductImage'], div[class*='image'] img, img[class*='product']"
        )

        product_name  = name_el.get_text(strip=True)  if name_el  else ""
        price         = price_el.get_text(strip=True) if price_el else ""
        price_numeric = self.parse_price(price)
        rating        = rating_el.get_text(strip=True) if rating_el else ""
        product_image = img_el.get("src", "") if img_el else ""

        if not product_name and not price:
            return {}

        return {
            "product_name" : product_name,
            "price"        : price,
            "price_numeric": price_numeric,
            "discount"     : "",
            "rating"       : rating,
            "reviews"      : "",
            "product_image": product_image,
            "delivery"     : "",
            "website"      : self.website,
            "error"        : "",
            "retryable"    : False,
        }
"""
scraper_engine/meesho.py
------------------------
Scrapes Meesho product pages.

Meesho is React-rendered — most content is in a JSON blob inside
<script id="__NEXT_DATA__"> which we parse directly (no JS execution needed).

Fallback: CSS selectors on the rendered HTML if __NEXT_DATA__ is absent.
"""

import json
from bs4 import BeautifulSoup
from .base import BaseScraper


class MeeshoScraper(BaseScraper):
    website = "meesho"

    def scrape(self, url: str) -> dict:
        html = self.get_html(url)
        if not html:
            return self.empty("Failed to fetch Meesho page")

        # ── Method 1: Parse __NEXT_DATA__ JSON blob ───────────────
        result = self._parse_next_data(html)
        if result:
            return result

        # ── Method 2: CSS selectors fallback ─────────────────────
        return self._parse_html(html)

    def _parse_next_data(self, html: str) -> dict:
        """Extract product data from Next.js JSON payload."""
        soup = BeautifulSoup(html, "html.parser")
        script = soup.select_one("script#__NEXT_DATA__")
        if not script:
            return {}
        try:
            data = json.loads(script.string)
            # Navigate to product props
            props   = data.get("props", {}).get("pageProps", {})
            product = props.get("product", props.get("productData", {}))
            if not product:
                return {}

            product_name  = product.get("name", "")
            price         = f"₹{product.get('price', '')}"
            price_numeric = float(product.get("price") or 0)
            discount      = str(product.get("discountPercentage", ""))
            if discount:
                discount = f"{discount}% off"
            rating        = str(product.get("averageRating") or product.get("rating") or "")
            reviews       = str(product.get("totalReviewCount") or product.get("reviewCount") or "")

            # Image
            images        = product.get("images", [])
            product_image = images[0].get("url", "") if images else ""

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
            }
        except Exception as e:
            print(f"[meesho] __NEXT_DATA__ parse error: {e}")
            return {}

    def _parse_html(self, html: str) -> dict:
        """CSS selector fallback for Meesho."""
        soup = BeautifulSoup(html, "html.parser")

        name_el   = soup.select_one("p.sc-eDvSVe, h1")
        price_el  = soup.select_one("h5.sc-dcJsrY, span[class*='price']")
        rating_el = soup.select_one("p[class*='rating']")
        img_el    = soup.select_one("img[class*='ProductImage'], div[class*='image'] img")

        product_name  = name_el.get_text(strip=True)  if name_el  else ""
        price         = price_el.get_text(strip=True) if price_el else ""
        price_numeric = self.parse_price(price)
        rating        = rating_el.get_text(strip=True) if rating_el else ""
        product_image = img_el.get("src", "") if img_el else ""

        if not product_name and not price:
            return self.empty("Meesho: no data in HTML or __NEXT_DATA__")

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
        }
"""
scraper_engine/myntra.py
------------------------
Scrapes Myntra product pages.

Myntra is React-rendered. Data lives in window.__myntraweb__ or
<script type="application/ld+json"> structured data blocks.
"""

import json
import re
from bs4 import BeautifulSoup
from .base import BaseScraper


class MyntraScraper(BaseScraper):
    website = "myntra"

    def scrape(self, url: str) -> dict:
        html = self.get_html(url)
        if not html:
            return self.empty("Failed to fetch Myntra page")

        # ── Method 1: JSON-LD structured data ────────────────────
        result = self._parse_json_ld(html)
        if result:
            return result

        # ── Method 2: window.__myntraweb__ inline script ──────────
        result = self._parse_inline_script(html)
        if result:
            return result

        return self.empty("Myntra: could not extract product data (JS-rendered)")

    def _parse_json_ld(self, html: str) -> dict:
        soup = BeautifulSoup(html, "html.parser")
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                data = json.loads(script.string or "")
                if data.get("@type") == "Product":
                    product_name = data.get("name", "")
                    offers       = data.get("offers", {})
                    price_str    = str(offers.get("price", ""))
                    price        = f"₹{price_str}" if price_str else ""
                    price_num    = float(price_str) if price_str else 0.0
                    rating_agg   = data.get("aggregateRating", {})
                    rating       = str(rating_agg.get("ratingValue", ""))
                    reviews      = str(rating_agg.get("reviewCount", ""))
                    images       = data.get("image", [])
                    product_image= images[0] if isinstance(images, list) and images else str(images)

                    return {
                        "product_name" : product_name,
                        "price"        : price,
                        "price_numeric": price_num,
                        "discount"     : "",
                        "rating"       : rating,
                        "reviews"      : reviews,
                        "product_image": product_image,
                        "delivery"     : "",
                        "website"      : self.website,
                        "error"        : "",
                    }
            except Exception:
                continue
        return {}

    def _parse_inline_script(self, html: str) -> dict:
        """Extract from window.__myntraweb__ or pdpData JS variable."""
        match = re.search(r'window\.__myntraweb__\s*=\s*(\{.*?\});', html, re.DOTALL)
        if not match:
            match = re.search(r'"pdpData"\s*:\s*(\{.*?"mrp".*?\})', html, re.DOTALL)
        if not match:
            return {}
        try:
            raw = match.group(1)
            data = json.loads(raw)
            name  = data.get("name", "") or data.get("productName", "")
            price = data.get("price", data.get("discountedPrice", ""))
            price_str = f"₹{price}" if price else ""
            return {
                "product_name" : name,
                "price"        : price_str,
                "price_numeric": float(price or 0),
                "discount"     : "",
                "rating"       : str(data.get("overallRating", "")),
                "reviews"      : str(data.get("totalCount", "")),
                "product_image": "",
                "delivery"     : "",
                "website"      : self.website,
                "error"        : "",
            }
        except Exception:
            return {}
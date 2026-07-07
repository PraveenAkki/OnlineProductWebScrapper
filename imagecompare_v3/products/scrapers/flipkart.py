"""
scraper_engine/flipkart.py
--------------------------
Scrapes Flipkart product pages.

Strategy (most → least reliable):
  1. JSON-LD structured data (Product schema) — survives Flipkart's
     frequent CSS class rotation, since it's SEO-driven and stable
  2. CSS selectors — fallback, but these obfuscated classes
     (._30jeq3 etc.) are compiler-generated and rotate on redeploy
"""

import json
from bs4 import BeautifulSoup
from .base import BaseScraper
import os
import tempfile

class FlipkartScraper(BaseScraper):
    website = "flipkart"

    def scrape(self, url: str) -> dict:
        html = self.get_html_selenium(url)
        if not html:
            return self.empty("Failed to fetch Flipkart page")

        soup = BeautifulSoup(html, "html.parser")

        result = self._try_json_ld(soup)
        if result:
            return result

        return self._try_css(soup)

    def _try_json_ld(self, soup) -> dict:
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                data = json.loads(script.string or "")
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if item.get("@type") == "Product":
                        offers = item.get("offers", {})
                        if isinstance(offers, list):
                            offers = offers[0] if offers else {}
                        price_str = str(offers.get("price", ""))
                        rating_agg = item.get("aggregateRating", {})
                        images = item.get("image", [])
                        img = images[0] if isinstance(images, list) and images else (images if isinstance(images, str) else "")

                        if not item.get("name"):
                            continue

                        return {
                            "product_name" : item.get("name", ""),
                            "price"        : f"₹{price_str}" if price_str else "",
                            "price_numeric": self.parse_price(price_str),
                            "discount"     : "",
                            "rating"       : str(rating_agg.get("ratingValue", "")),
                            "reviews"      : str(rating_agg.get("reviewCount", "")),
                            "product_image": img,
                            "delivery"     : "",
                            "website"      : self.website,
                            "error"        : "",
                        }
            except Exception as e:
                print(f"[flipkart] JSON-LD parse error: {e}")
                continue
        return {}

    def _try_css(self, soup) -> dict:
        # NOTE: these obfuscated classes rotate frequently — update
        # them from a fresh page inspection whenever this fallback fails.
        name_el = soup.select_one(".B_NuCI, h1.yhB1nd, span.B_NuCI, h1")
        product_name = name_el.get_text(strip=True) if name_el else ""

        price_el = soup.select_one("._30jeq3, ._16Jk6d")
        price = price_el.get_text(strip=True) if price_el else ""
        price_numeric = self.parse_price(price)

        discount_el = soup.select_one("._3Ay6Sb, .VGWI6T")
        discount = discount_el.get_text(strip=True) if discount_el else ""

        rating_el = soup.select_one("._3LWZlK")
        rating = rating_el.get_text(strip=True) if rating_el else ""

        reviews_el = soup.select_one("._2_R_DZ")
        reviews = reviews_el.get_text(strip=True) if reviews_el else ""

        img_el = soup.select_one("._396cs4 img, ._2r_T1I img, img._2r_T1I")
        product_image = img_el.get("src", "") if img_el else ""

        delivery_el = soup.select_one("._2Tpdn3, .tn7D0E")
        delivery = delivery_el.get_text(strip=True) if delivery_el else ""

        if not product_name and not price:
            return self.empty("Flipkart page parsed but no data — possible bot block or selector drift")

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
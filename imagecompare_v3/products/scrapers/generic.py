"""
scraper_engine/generic.py
-------------------------
Generic scraper for any site not covered by a specific scraper.

Strategy (in order):
  1. JSON-LD structured data (Product schema) — most reliable
  2. Open Graph meta tags — og:title, og:price:amount, og:image
  3. Common CSS class patterns used by many e-commerce themes
"""

import json
import re
from bs4 import BeautifulSoup
from .base import BaseScraper


class GenericScraper(BaseScraper):
    website = "generic"

    def scrape(self, url: str) -> dict:
        # Set website to domain for better tracking
        try:
            from urllib.parse import urlparse
            self.website = urlparse(url).netloc.replace("www.", "").split(".")[0]
        except Exception:
            pass

        html = self.get_html(url)
        if not html:
            return self.empty(f"Failed to fetch {url}")

        result = self._try_json_ld(html)
        if result:
            return result

        result = self._try_og_tags(html)
        if result:
            return result

        return self._try_css_patterns(html)

    def _try_json_ld(self, html: str) -> dict:
        soup = BeautifulSoup(html, "html.parser")
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                raw  = script.string or ""
                data = json.loads(raw)
                # Handle @graph arrays
                if isinstance(data, list):
                    for item in data:
                        if item.get("@type") == "Product":
                            data = item
                            break
                if isinstance(data, dict) and data.get("@type") == "Product":
                    offers      = data.get("offers", {})
                    if isinstance(offers, list):
                        offers = offers[0]
                    price_str   = str(offers.get("price", ""))
                    currency    = offers.get("priceCurrency", "")
                    price_disp  = f"{currency}{price_str}" if price_str else ""
                    rating_agg  = data.get("aggregateRating", {})
                    images      = data.get("image", [])
                    img_url     = ""
                    if isinstance(images, list) and images:
                        img_url = images[0] if isinstance(images[0], str) else images[0].get("url", "")
                    elif isinstance(images, str):
                        img_url = images
                    return {
                        "product_name" : data.get("name", ""),
                        "price"        : price_disp,
                        "price_numeric": float(price_str or 0),
                        "discount"     : "",
                        "rating"       : str(rating_agg.get("ratingValue", "")),
                        "reviews"      : str(rating_agg.get("reviewCount", "")),
                        "product_image": img_url,
                        "delivery"     : "",
                        "website"      : self.website,
                        "error"        : "",
                    }
            except Exception:
                continue
        return {}

    def _try_og_tags(self, html: str) -> dict:
        soup  = BeautifulSoup(html, "html.parser")
        title = soup.select_one('meta[property="og:title"]')
        price = soup.select_one('meta[property="product:price:amount"], meta[property="og:price:amount"]')
        image = soup.select_one('meta[property="og:image"]')
        if not title:
            return {}
        price_str  = price["content"] if price else ""
        price_disp = f"₹{price_str}" if price_str else ""
        return {
            "product_name" : title["content"] if title else "",
            "price"        : price_disp,
            "price_numeric": float(price_str or 0),
            "discount"     : "",
            "rating"       : "",
            "reviews"      : "",
            "product_image": image["content"] if image else "",
            "delivery"     : "",
            "website"      : self.website,
            "error"        : "",
        }

    def _try_css_patterns(self, html: str) -> dict:
        """Last-resort: common class patterns used by Shopify, WooCommerce, etc."""
        soup = BeautifulSoup(html, "html.parser")

        name_selectors  = ["h1.product-title", "h1.product_title", "h1.entry-title",
                           ".product-name h1", "h1"]
        price_selectors = [".price", ".product-price", ".woocommerce-Price-amount",
                           "[class*='price']", "[itemprop='price']"]
        img_selectors   = [".product-image img", ".woocommerce-product-gallery img",
                           "[class*='product'] img"]

        def first_text(selectors):
            for sel in selectors:
                el = soup.select_one(sel)
                if el:
                    return el.get_text(strip=True)
            return ""

        product_name  = first_text(name_selectors)
        price         = first_text(price_selectors)
        price_numeric = self.parse_price(price)
        product_image = ""
        for sel in img_selectors:
            el = soup.select_one(sel)
            if el:
                product_image = el.get("src", "")
                break

        if not product_name and not price:
            return self.empty("Generic scraper: no data found")

        return {
            "product_name" : product_name,
            "price"        : price,
            "price_numeric": price_numeric,
            "discount"     : "",
            "rating"       : "",
            "reviews"      : "",
            "product_image": product_image,
            "delivery"     : "",
            "website"      : self.website,
            "error"        : "",
        }
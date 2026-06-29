"""
scraper_engine/flipkart.py
--------------------------
Scrapes Flipkart product pages.

Targets:
    product_name  : .B_NuCI
    price         : ._30jeq3 (current price, e.g. ₹499)
    discount      : ._3Ay6Sb (discount badge, e.g. "67% off")
    rating        : ._3LWZlK
    reviews       : span._2_R_DZ (e.g. "1,234 Ratings & 123 Reviews")
    product_image : ._396cs4 img or ._2r_T1I img
    delivery      : ._2Tpdn3 (delivery message)
"""

from bs4 import BeautifulSoup
from .base import BaseScraper


class FlipkartScraper(BaseScraper):
    website = "flipkart"

    def scrape(self, url: str) -> dict:
        html = self.get_html(url)
        if not html:
            return self.empty("Failed to fetch Flipkart page")

        soup = BeautifulSoup(html, "html.parser")

        # ── Product name ──────────────────────────────────────────
        name_el = soup.select_one(".B_NuCI, h1.yhB1nd, span.B_NuCI")
        if not name_el:
            name_el = soup.select_one("h1")
        product_name = name_el.get_text(strip=True) if name_el else ""

        # ── Price ─────────────────────────────────────────────────
        price_el = soup.select_one("._30jeq3, ._16Jk6d")
        price = price_el.get_text(strip=True) if price_el else ""
        price_numeric = self.parse_price(price)

        # ── Discount ──────────────────────────────────────────────
        discount_el = soup.select_one("._3Ay6Sb, .VGWI6T")
        discount = discount_el.get_text(strip=True) if discount_el else ""

        # ── Rating ────────────────────────────────────────────────
        rating_el = soup.select_one("._3LWZlK")
        rating = rating_el.get_text(strip=True) if rating_el else ""

        # ── Reviews ───────────────────────────────────────────────
        reviews_el = soup.select_one("._2_R_DZ")
        reviews = ""
        if reviews_el:
            text = reviews_el.get_text(strip=True)
            # "1,234 Ratings & 123 Reviews" -> keep as-is
            reviews = text

        # ── Product image ─────────────────────────────────────────
        img_el = soup.select_one("._396cs4 img, ._2r_T1I img, img._2r_T1I")
        product_image = ""
        if img_el:
            product_image = img_el.get("src", "")

        # ── Delivery ──────────────────────────────────────────────
        delivery_el = soup.select_one("._2Tpdn3, .tn7D0E")
        delivery = delivery_el.get_text(strip=True) if delivery_el else ""

        if not product_name and not price:
            return self.empty("Flipkart page parsed but no data — possible bot block")

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
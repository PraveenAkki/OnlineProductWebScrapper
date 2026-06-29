"""
scraper_engine/base.py
----------------------
Base scraper class. All site scrapers inherit from this.

Each subclass must implement:
    scrape(url: str) -> dict

Returned dict shape (all fields optional except product_name + price):
    {
        "product_name"  : str,
        "price"         : str,    e.g. "₹499"
        "price_numeric" : float,  e.g. 499.0
        "discount"      : str,    e.g. "20% off"
        "rating"        : str,    e.g. "4.2"
        "reviews"       : str,    e.g. "1,250"
        "product_image" : str,    URL
        "delivery"      : str,    e.g. "Free delivery by Mon"
        "website"       : str,    e.g. "amazon"
        "error"         : str,    non-empty on failure
    }
"""

import re
import requests
from abc import ABC, abstractmethod

# Rotate these to reduce bot detection
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
    "Accept"         : "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection"     : "keep-alive",
}

TIMEOUT = 15   # seconds per request


class BaseScraper(ABC):
    website = "unknown"   # override in subclass e.g. "amazon"

    def get_html(self, url: str) -> str:
        """Fetch page HTML. Returns empty string on failure."""
        try:
            resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            if resp.status_code == 200:
                return resp.text
            print(f"[{self.website}] HTTP {resp.status_code} for {url}")
            return ""
        except Exception as e:
            print(f"[{self.website}] Request error: {e}")
            return ""

    @abstractmethod
    def scrape(self, url: str) -> dict:
        """Scrape product details from URL. Must return dict."""
        pass

    def empty(self, error: str = "") -> dict:
        """Return an empty result with optional error message."""
        return {
            "product_name" : "",
            "price"        : "",
            "price_numeric": 0.0,
            "discount"     : "",
            "rating"       : "",
            "reviews"      : "",
            "product_image": "",
            "delivery"     : "",
            "website"      : self.website,
            "error"        : error,
        }

    @staticmethod
    def parse_price(text: str) -> float:
        """Convert '₹1,299' or '$45.99' to float."""
        if not text:
            return 0.0
        cleaned = re.sub(r"[^\d.]", "", text.replace(",", ""))
        try:
            return float(cleaned)
        except ValueError:
            return 0.0
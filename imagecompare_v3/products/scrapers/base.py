"""
scraper_engine/base.py
-----------------------
Base class all site scrapers inherit from.
Handles HTTP fetching with retries, rotating user-agents, and price parsing.

Placement: products/scraper_engine/base.py
"""

import re
import time
import random
import requests


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

BASE_HEADERS = {
    "Accept-Language"           : "en-IN,en;q=0.9,hi;q=0.8",
    "Accept"                    : "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Encoding"           : "gzip, deflate, br",
    "DNT"                       : "1",
    "Connection"                : "keep-alive",
    "Upgrade-Insecure-Requests" : "1",
    "Cache-Control"             : "max-age=0",
}


class BaseScraper:
    website = "unknown"
    timeout = 15
    max_retries = 2

    def get_html(self, url: str) -> str | None:
        """
        Fetch URL, return raw HTML string.
        Retries up to max_retries times with a small delay.
        Returns None on failure.
        """
        headers = dict(BASE_HEADERS)
        headers["User-Agent"] = random.choice(USER_AGENTS)
        headers["Referer"] = "https://www.google.com/"

        for attempt in range(1, self.max_retries + 1):
            try:
                time.sleep(random.uniform(0.5, 1.5))
                session = requests.Session()
                resp = session.get(
                    url,
                    headers=headers,
                    timeout=self.timeout,
                    allow_redirects=True,
                )

                if resp.status_code == 200:
                    return resp.text

                if resp.status_code in (403, 429):
                    print(f"[{self.website}] HTTP {resp.status_code} on attempt {attempt}: {url[:60]}")
                    if attempt < self.max_retries:
                        # Rotate UA and wait before retry
                        headers["User-Agent"] = random.choice(USER_AGENTS)
                        time.sleep(random.uniform(3.0, 6.0))
                    continue

                print(f"[{self.website}] HTTP {resp.status_code}: {url[:60]}")
                return None

            except requests.exceptions.Timeout:
                print(f"[{self.website}] Timeout attempt {attempt}: {url[:60]}")
            except requests.exceptions.ConnectionError as e:
                print(f"[{self.website}] Connection error: {e}")
                return None
            except Exception as e:
                print(f"[{self.website}] Unexpected error: {e}")
                return None

        return None

    def parse_price(self, price_str: str) -> float:
        """
        Extract numeric float from a price string.
        '₹1,299.00' -> 1299.0
        '$18*'       -> 18.0
        """
        if not price_str:
            return 0.0
        matches = re.findall(r"\d[\d,]*\.?\d*", str(price_str))
        if not matches:
            return 0.0
        try:
            return float(matches[-1].replace(",", ""))
        except ValueError:
            return 0.0

    def empty(self, error: str = "") -> dict:
        """Return a failed-scrape result dict."""
        print(f"[{self.website}] empty(): {error}")
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
            "success"      : False,
        }

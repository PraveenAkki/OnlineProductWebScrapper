"""
scraper_engine/router.py
------------------------
Routes a URL to the correct scraper based on domain.

Usage:
    from products.scraper_engine.router import get_scraper
    scraper = get_scraper("https://www.amazon.in/...")
    result  = scraper.scrape(url)
"""

from urllib.parse import urlparse
from .amazon   import AmazonScraper
from .flipkart import FlipkartScraper
from .meesho   import MeeshoScraper
from .myntra   import MyntraScraper
from .generic  import GenericScraper


# Map domain keywords to scraper classes
DOMAIN_MAP = {
    "amazon"   : AmazonScraper,
    "flipkart" : FlipkartScraper,
    "meesho"   : MeeshoScraper,
    "myntra"   : MyntraScraper,
}


def get_scraper(url: str):
    """Return the right scraper instance for the given URL."""
    try:
        domain = urlparse(url).netloc.lower()
    except Exception:
        domain = ""

    for keyword, scraper_class in DOMAIN_MAP.items():
        if keyword in domain:
            return scraper_class()

    return GenericScraper()


def detect_website(url: str) -> str:
    """Return a short website name for the URL."""
    try:
        domain = urlparse(url).netloc.lower()
        for keyword in DOMAIN_MAP:
            if keyword in domain:
                return keyword
        # Return clean domain as fallback e.g. "etsy", "ebay"
        parts = domain.replace("www.", "").split(".")
        return parts[0] if parts else "unknown"
    except Exception:
        return "unknown"
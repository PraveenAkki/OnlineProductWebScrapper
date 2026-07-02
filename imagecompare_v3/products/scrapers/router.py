"""
scraper_engine/router.py
-------------------------
Routes a URL to the correct site-specific scraper class.

Placement: products/scraper_engine/router.py

This was MISSING — causing all scrapes to silently fail with
ImportError: cannot import name 'get_scraper' from 'router'.
"""

from urllib.parse import urlparse


def get_scraper(url: str):
    """
    Return the right scraper instance for a given URL.
    Falls back to GenericScraper for unknown sites.
    """
    try:
        domain = urlparse(url).netloc.lower()
    except Exception:
        domain = ""

    # Indian priority sites
    if "amazon."   in domain:
        from .amazon   import AmazonScraper;   return AmazonScraper()
    if "flipkart." in domain:
        from .flipkart import FlipkartScraper; return FlipkartScraper()
    if "meesho."   in domain:
        from .meesho   import MeeshoScraper;   return MeeshoScraper()
    if "myntra."   in domain:
        from .myntra   import MyntraScraper;   return MyntraScraper()

    # Other Indian sites — generic handles them fine
    from .generic import GenericScraper
    return GenericScraper()

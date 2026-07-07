"""
scraper_engine/router.py
-------------------------
Routes a URL to the correct site-specific scraper class.

Placement: products/scraper_engine/router.py

This was MISSING — causing all scrapes to silently fail with
ImportError: cannot import name 'get_scraper' from 'router'.
"""

from urllib.parse import urlparse

from .base import resolve_final_url



def get_scraper(url: str):
    try:
        domain = urlparse(url).netloc.lower()
    except Exception:
        domain = ""

    print(f"[Router] url_len={len(url)} domain={domain} url={url[:120]}")

    if "amazon."   in domain:
        from .amazon   import AmazonScraper;   return AmazonScraper()
    if "flipkart." in domain:
        from .flipkart import FlipkartScraper; return FlipkartScraper()
    if "meesho."   in domain:
        from .meesho   import MeeshoScraper;   return MeeshoScraper()
    if "myntra."   in domain:
        from .myntra   import MyntraScraper;   return MyntraScraper()

    print(f"[Router] No site-specific scraper for domain={domain} — using GenericScraper")
    from .generic import GenericScraper
    return GenericScraper()




def get_scraper(url: str):
    resolved = resolve_final_url(url)
    try:
        domain = urlparse(resolved).netloc.lower()
    except Exception:
        domain = ""

    print(f"[Router] original={url[:150]} len={len(url)} resolved={resolved[:150]} len_resolved={len(resolved)} domain={domain}")

    if "amazon."   in domain:
        from .amazon   import AmazonScraper;   return AmazonScraper(), resolved
    if "flipkart." in domain:
        from .flipkart import FlipkartScraper; return FlipkartScraper(), resolved
    if "meesho."   in domain:
        from .meesho   import MeeshoScraper;   return MeeshoScraper(), resolved
    if "myntra."   in domain:
        from .myntra   import MyntraScraper;   return MyntraScraper(), resolved

    from .generic import GenericScraper
    return GenericScraper(), resolved
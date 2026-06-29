"""
products/scrapers/registry.py

Maps a link's domain -> the right parser module + a clean "website" label.
Add a new e-commerce site by:
    1. writing products/scrapers/<site>.py with a parse(soup, url) -> dict function
    2. adding one line below

This is the ONLY file you touch to support a new website.
"""

from . import amazon, flipkart, meesho, generic

# domain substring -> (parse_fn, website_label)
SITE_MAP = {
    "amazon.":   (amazon.parse,   "Amazon"),
    "flipkart.": (flipkart.parse, "Flipkart"),
    "meesho.":   (meesho.parse,   "Meesho"),
}

# Sites known to block scrapers hard / require JS rendering we don't do here.
# We still try the generic parser (JSON-LD / OG tags often survive), but if
# you want to SKIP them entirely (saves time), list them here.
SKIP_DOMAINS = {
    "instagram.com", "facebook.com", "pinterest.com", "youtube.com",
    "twitter.com", "tiktok.com",
}


def get_parser(domain: str):
    """
    Returns (parse_fn, website_label) for a given domain.
    Falls back to the generic parser, labelling the website from the domain
    itself (e.g. 'myntra.com' -> 'Myntra').
    """
    for key, (fn, label) in SITE_MAP.items():
        if key in domain:
            return fn, label

    # derive a friendly label from domain for the generic fallback
    label = domain.split(".")[0].capitalize() if domain else "Other"
    return (lambda soup, url: generic.parse(soup, url, website_hint=label)), label


def should_skip(domain: str) -> bool:
    return any(skip in domain for skip in SKIP_DOMAINS)
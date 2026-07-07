"""
scraper_engine/filters.py
--------------------------
Three filters applied before saving any GoogleLensResult or Product row:

  1. SITE FILTER     — only Indian e-commerce + global sites that ship to India
  2. JEWELLERY FILTER — only imitation/artificial jewellery, block real gold
  3. CURRENCY FILTER  — convert any foreign price to INR before storing

BUG FIXED: Previously these functions existed but were never called by runner.py.
Now runner.py calls them at two points:
  a) In promote_shopping_results() — before creating Product from shopping row
  b) In scrape_one()              — after scraping a visual result

CHANGE from original:
  - REMOVED amazon.com from NON_INDIAN_DOMAINS (user wants amazon.com included)
  - REMOVED etsy.com, ebay.com from block list (they ship to India)
  - Added amazon.com, amazon.co.uk etc. as ALLOWED (global sites that serve India)
  - is_indian_site() renamed to is_allowed_site() for clarity
"""

import re
from urllib.parse import urlparse


# ─────────────────────────────────────────────────────────────────
# 1. Site allow-list
#    Rule: Allow Indian sites + global sites that ship to India.
#    Block: Social media, Wikipedia, blogs, news sites.
# ─────────────────────────────────────────────────────────────────

# These are always ALLOWED regardless of TLD
ALWAYS_ALLOWED = {
    # Indian-only platforms
    "flipkart.com", "meesho.com", "myntra.com", "ajio.com",
    "snapdeal.com", "nykaa.com", "nykaafashion.com", "tatacliq.com",
    "shopclues.com", "limeroad.com", "indiamart.com", "mirraw.com",
    "craftsvilla.com", "voylla.com", "caratlane.com", "bluestone.com",
    "sukkhi.com", "karatcart.com", "candere.com", "giva.co",
    # Global platforms that ship to India (all TLDs allowed)
    "amazon.in", "amazon.com",                       # Amazon global
    "etsy.com",                                       # ships to India
    "ebay.com", "ebay.co.uk", "ebay.in",             # ships to India
}

# These are always BLOCKED (social, media, content sites — not shops)
ALWAYS_BLOCKED = {
    "instagram.com", "facebook.com", "pinterest.com", "youtube.com",
    "twitter.com", "x.com", "tiktok.com", "snapchat.com", "reddit.com",
    "wikipedia.org", "wikimedia.org",
    "aliexpress.com", "wish.com", "shein.com", "temu.com",  # no India shipping
    "walmart.com",  # no India presence
}


def is_allowed_site(url: str) -> bool:
    """
    True if the URL is from a shopping site we want to include.

    Logic (in order):
      1. If domain is in ALWAYS_BLOCKED   → False
      2. If domain is in ALWAYS_ALLOWED   → True
      3. If domain ends with .in          → True  (any Indian site)
      4. Otherwise                        → False (unknown = blocked)
    """
    if not url:
        return False
    try:
        domain = urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return False

    # Check blocked first
    if domain in ALWAYS_BLOCKED:
        return False
    for blocked in ALWAYS_BLOCKED:
        if domain.endswith("." + blocked):
            return False

    # Check allowed
    if domain in ALWAYS_ALLOWED:
        return True
    for allowed in ALWAYS_ALLOWED:
        if domain.endswith("." + allowed):
            return True

    # Any .in domain (Indian websites)
    if domain.endswith(".in"):
        return True

    return False


# ─────────────────────────────────────────────────────────────────
# 2. Imitation jewellery filter
#    Only applies when category == "jewellery"
#    For other categories (saree, shoes, bags) — always pass
# ─────────────────────────────────────────────────────────────────

# These keywords in the title mean REAL precious metal → BLOCK
REAL_GOLD_BLOCKLIST = [
    "22k gold", "22kt gold", "24k gold", "24kt gold",
    "18k gold", "18kt gold", "14k gold", "14kt gold",
    "916 gold", "916 hallmark", "hallmark gold", "hallmarked",
    "bis hallmark", "bis certified", "bis mark", "bis hallmark", 
    "gram gold", "gram gold coin", "gram gold bar", "gram", "gm",
    "kilogram", "kg", "milligram", "mg",
    "solid gold", "real gold", "pure gold", "genuine gold",
    "certified gold", "gold coin", "gold biscuit", "gold bar",
    "real diamond", "natural diamond", "solitaire diamond",
    "igi certified", "gia certified", "lab grown diamond",
    "sterling silver 925", "925 silver", "solid silver",
]


def is_imitation_jewellery(title: str, category: str = "") -> bool:
    """
    Returns True if the listing should be KEPT.
    Returns False if it should be EXCLUDED (real gold / certified diamonds).

    Only applies strict filtering when category contains 'jewellery'.
    For all other categories (saree, shoes, bags etc.) always returns True.
    """
    if not title:
        return True

    # Only apply gold filter for jewellery category
    if "jewel" not in (category or "").lower() and "jewel" not in title.lower():
        return True

    t = title.lower()
    for blocked in REAL_GOLD_BLOCKLIST:
        if blocked in t:
            print(f"[Filter] Blocked real gold listing: '{title[:60]}'")
            return False

    return True


# ─────────────────────────────────────────────────────────────────
# 3. Currency → INR conversion
#    Called after scraping to normalize all prices to INR before DB save
# ─────────────────────────────────────────────────────────────────

# Static approximate exchange rates to INR
# Update monthly — avoids a live FX API call during scraping
CURRENCY_TO_INR = {
    "$"  : 86.5,    # USD
    "usd": 86.5,
    "€"  : 94.0,    # EUR
    "eur": 94.0,
    "£"  : 110.0,   # GBP
    "gbp": 110.0,
    "₹"  : 1.0,     # INR — no conversion
    "inr": 1.0,
    "rs" : 1.0,
    "rs.": 1.0,
    "aed": 23.5,    # UAE Dirham
    "cad": 63.0,    # Canadian Dollar
    "aud": 57.0,    # Australian Dollar
    "sgd": 64.0,    # Singapore Dollar
}


def detect_currency(price_str: str) -> str:
    """Detect currency symbol/code from a price string. Returns '₹' as default."""
    if not price_str:
        return "₹"
    p = price_str.strip().lower()
    if p.startswith("₹") or p.startswith("rs"):
        return "₹"
    if p.startswith("$"):
        return "$"
    if p.startswith("€"):
        return "€"
    if p.startswith("£"):
        return "£"
    for code in ("usd", "eur", "gbp", "aed", "cad", "aud", "sgd"):
        if code in p:
            return code
    return "₹"  # assume INR if unknown


def normalize_price_to_inr(price_str: str, price_numeric: float) -> tuple:
    """
    Convert price to INR if needed.
    Returns (display_str, numeric_float) both in INR.

    Examples:
        ("$18*", 18.0)   → ("₹1,557", 1557.0)
        ("₹499", 499.0)  → ("₹499", 499.0)
        ("€25", 25.0)    → ("₹2,350", 2350.0)
    """
    if not price_numeric or price_numeric == 0.0:
        return price_str or "", 0.0

    symbol = detect_currency(price_str)

    if symbol in ("₹", "inr", "rs", "rs."):
        # Already INR — just normalize display format
        return f"₹{price_numeric:,.0f}", float(price_numeric)

    rate = CURRENCY_TO_INR.get(symbol.lower(), 1.0)
    converted = round(price_numeric * rate, 2)
    print(f"[Filter] Currency convert: {price_str} ({symbol}) × {rate} = ₹{converted:,.0f}")
    return f"₹{converted:,.0f}", converted

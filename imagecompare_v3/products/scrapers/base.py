"""
products/scrapers/base.py  — FIXED
-------------------------------------
Place at: products/scrapers/base.py

BUGS FIXED:
  1. empty() never set "retryable" key.
     runner.py does:  retryable = data.get("retryable", True)
     So every failed scrape defaulted to retryable=True.
     Meesho 403 → empty() → retryable=True → scraped stays False → infinite loop.

  2. 403 and 429 are DIFFERENT failure types:
     403 = permanent bot block for this URL (mark done, don't retry)
     429 = rate limit (retryable — wait and try again)
     Timeout = retryable (temporary network issue)

  3. get_html() returned None with no signal about WHY it failed.
     Now returns a result dict instead of None so the caller knows
     whether to retry or mark as permanent failure.

  4. Added session warm-up for Meesho/Myntra: visit homepage first
     to get cookies before hitting the product page.
"""

import re
import time
import random
import requests

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.chrome.service import Service as ChromeService
    from selenium.common.exceptions import WebDriverException, TimeoutException
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

try:
    from webdriver_manager.chrome import ChromeDriverManager
    WEBDRIVER_MANAGER_AVAILABLE = True
except ImportError:
    WEBDRIVER_MANAGER_AVAILABLE = False


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

BASE_HEADERS = {
    "Accept-Language"           : "en-IN,en;q=0.9,hi;q=0.8",
    "Accept"                    : "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Encoding"           : "gzip, deflate", #br",
    "DNT"                       : "1",
    "Connection"                : "keep-alive",
    "Upgrade-Insecure-Requests" : "1",
    "Cache-Control"             : "max-age=0",
    "Sec-Fetch-Dest"            : "document",
    "Sec-Fetch-Mode"            : "navigate",
    "Sec-Fetch-Site"            : "none",
    "Sec-Fetch-User"            : "?1",
}

# Domains that need homepage warm-up before hitting product page
# (they check cookies set on homepage visit)
WARMUP_DOMAINS = {
    "meesho.com"  : "https://www.meesho.com",
    "myntra.com"  : "https://www.myntra.com",
    "flipkart.com": "https://www.flipkart.com",
    "nykaa.com"   : "https://www.nykaa.com",
    "nykaafashion.com": "https://www.nykaafashion.com",
}

BLOCK_MARKERS = [
    "access denied", "request blocked", "captcha", "are you a human",
    "unusual traffic", "automated access", "bot detection",
    "please verify you are a human", "reference #", "pardon our interruption",
]


def looks_blocked(html: str) -> bool:
    """True if the page content looks like an anti-bot interstitial."""
    if not html:
        return False
    lower = html[:6000].lower()   # block pages are short; no need to scan the whole doc
    return any(marker in lower for marker in BLOCK_MARKERS)


class BaseScraper:
    website     = "unknown"
    timeout     = 15
    max_retries = 2

    def _get_warmup_url(self, product_url: str) -> str | None:
        """Return homepage URL for sites that need cookie warm-up."""
        try:
            from urllib.parse import urlparse
            domain = urlparse(product_url).netloc.lower().replace("www.", "")
            for key, homepage in WARMUP_DOMAINS.items():
                if key in domain:
                    return homepage
        except Exception:
            pass
        return None

    def get_html(self, url: str) -> str | None:
        """
        Fetch URL, return raw HTML string or None.

        On failure, sets self._last_error and self._last_retryable
        so the scraper subclass can pass these to empty().

        retryable meaning:
          True  = timeout / rate limit → retry later
          False = 403 permanent block / 404 not found → mark done, skip
        """
        self._last_error     = ""
        self._last_retryable = False   # default: don't retry on unknown failure

        headers = dict(BASE_HEADERS)
        headers["User-Agent"] = random.choice(USER_AGENTS)
        headers["Referer"]    = "https://www.google.com/"

        for attempt in range(1, self.max_retries + 1):
            try:
                time.sleep(random.uniform(0.8, 2.0))

                session = requests.Session()

                # Warm-up: visit homepage first to get cookies
                warmup_url = self._get_warmup_url(url)
                if warmup_url and attempt == 1:
                    try:
                        session.get(
                            warmup_url,
                            headers=headers,
                            timeout=8,
                            allow_redirects=True,
                        )
                        time.sleep(random.uniform(1.0, 2.5))
                        headers["Referer"] = warmup_url
                    except Exception:
                        pass   # warmup failure is non-critical

                resp = session.get(
                    url,
                    headers=headers,
                    timeout=self.timeout,
                    allow_redirects=True,
                )

                if resp.status_code == 200:
                    return resp.text

                if resp.status_code == 403:
                    # PERMANENT block — Cloudflare / bot detection
                    # Do NOT retry — mark as done so it leaves the queue
                    self._last_error     = f"HTTP 403 — bot block (permanent)"
                    self._last_retryable = False   # ← KEY FIX
                    print(f"[{self.website}] 403 permanent block: {url[:80]}")
                    return None

                if resp.status_code == 429:
                    # Rate limited — retryable after a wait
                    self._last_error     = f"HTTP 429 — rate limited"
                    self._last_retryable = True    # retryable
                    print(f"[{self.website}] 429 rate limit attempt {attempt}: {url[:80]}")
                    if attempt < self.max_retries:
                        headers["User-Agent"] = random.choice(USER_AGENTS)
                        time.sleep(random.uniform(5.0, 10.0))
                    continue

                if resp.status_code == 404:
                    self._last_error     = f"HTTP 404 — product not found"
                    self._last_retryable = False
                    print(f"[{self.website}] 404: {url[:80]}")
                    return None

                # Other HTTP errors
                self._last_error     = f"HTTP {resp.status_code}"
                self._last_retryable = False
                print(f"[{self.website}] HTTP {resp.status_code}: {url[:80]}")
                return None

            except requests.exceptions.Timeout:
                self._last_error     = "Request timed out"
                self._last_retryable = True   # retryable
                print(f"[{self.website}] Timeout attempt {attempt}: {url[:80]}")
                if attempt < self.max_retries:
                    time.sleep(random.uniform(2.0, 4.0))

            except requests.exceptions.ConnectionError as e:
                self._last_error     = f"Connection error: {str(e)[:60]}"
                self._last_retryable = True   # might be temporary
                print(f"[{self.website}] Connection error: {e}")
                return None

            except Exception as e:
                self._last_error     = str(e)[:100]
                self._last_retryable = False
                print(f"[{self.website}] Unexpected error: {e}")
                return None

        # All retries exhausted
        return None
    
    def get_html_selenium(self, url: str, wait_seconds: float = 2.5) -> str | None:
        """
        Fetch a page using headless Chrome instead of a plain HTTP request.

        Adds:
        - Homepage warm-up in the SAME browser session (real cookies, unlike
            separate requests-based warmup) for sites that gate product pages
            behind a session established on the homepage.
        - Stealth patches to reduce the "this is an automated browser"
            fingerprint that anti-bot systems check for.
        - Block-page detection: if the response looks like an Access
            Denied / CAPTCHA interstitial, treat it as a failure (with
            retryable=True, since a different session/UA may succeed later)
            rather than returning garbage as if it were real content.
        """
        self._last_error     = ""
        self._last_retryable = False

        if not SELENIUM_AVAILABLE:
            self._last_error     = "Selenium not installed — run: pip install selenium webdriver-manager"
            self._last_retryable = False
            print(f"[{self.website}] {self._last_error}")
            return None

        driver = None
        try:
            options = ChromeOptions()
            options.add_argument("--headless=new")
            options.add_argument("--disable-gpu")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--window-size=1920,1080")
            options.add_argument("user-agent=" + random.choice(USER_AGENTS))
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option("useAutomationExtension", False)

            if WEBDRIVER_MANAGER_AVAILABLE:
                driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
            else:
                driver = webdriver.Chrome(options=options)

            driver.set_page_load_timeout(self.timeout)

            # Stealth patch — hide the most common headless-Chrome tell
            # (navigator.webdriver === true), which many anti-bot systems check.
            try:
                driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                    "source": """
                        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                        window.chrome = { runtime: {} };
                        Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
                        Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                    """
                })
            except Exception as e:
                print(f"[{self.website}] Stealth patch failed (non-fatal): {e}")

            # Homepage warm-up in the SAME session — real cookies, not a
            # separate requests.Session() like get_html() uses.
            warmup_url = self._get_warmup_url(url)
            if warmup_url:
                try:
                    driver.get(warmup_url)
                    time.sleep(random.uniform(1.5, 3.0))
                except Exception as e:
                    print(f"[{self.website}] Selenium warmup failed (non-fatal): {e}")

            driver.get(url)
            time.sleep(wait_seconds)

            html = driver.page_source

            if looks_blocked(html):
                self._last_error     = "Blocked by anti-bot interstitial (Access Denied/CAPTCHA)"
                self._last_retryable = True
                print(f"[{self.website}] Selenium got blocked/anti-bot page: {url[:80]}")
                return None

            return html

        except TimeoutException:
            self._last_error     = "Selenium page load timed out"
            self._last_retryable = True
            print(f"[{self.website}] Selenium timeout: {url[:80]}")
            return None
        except WebDriverException as e:
            self._last_error     = f"Selenium WebDriver error: {str(e)[:100]}"
            self._last_retryable = True
            print(f"[{self.website}] Selenium WebDriver error: {e}")
            return None
        except Exception as e:
            self._last_error     = str(e)[:150]
            self._last_retryable = False
            print(f"[{self.website}] Selenium unexpected error: {e}")
            return None
        finally:
            if driver is not None:
                try:
                    driver.quit()
                except Exception:
                    pass

    def parse_price(self, price_str: str) -> float:
        """Extract numeric float from price string. '₹1,299.00' → 1299.0"""
        if not price_str:
            return 0.0
        matches = re.findall(r"\d[\d,]*\.?\d*", str(price_str))
        if not matches:
            return 0.0
        try:
            return float(matches[-1].replace(",", ""))
        except ValueError:
            return 0.0

    def empty(self, error: str = "", retryable: bool | None = None) -> dict:
        """
        Return a failed-scrape result dict.

        retryable parameter:
          None    → use self._last_retryable (set by get_html)
          True    → caller forces retryable (e.g. parse error on valid page)
          False   → caller forces permanent failure
        """
        if retryable is None:
            retryable = getattr(self, "_last_retryable", False)

        # If no error message passed, use the one from get_html
        if not error:
            error = getattr(self, "_last_error", "Unknown error")

        print(f"[{self.website}] FAIL (retryable={retryable}): {error}")
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
            "retryable"    : retryable,   # ← THIS WAS MISSING — caused infinite loop
        }
    


def resolve_final_url(url: str, timeout: int = 8) -> str:
    """
    Follow HTTP redirects (not JS redirects) to find the real destination.
    Google Shopping/Lens links are sometimes click-tracking wrappers
    (google.com/aclk, /url?q=...) rather than the merchant page directly.
    """
    try:
        headers = {"User-Agent": random.choice(USER_AGENTS)}
        resp = requests.head(url, headers=headers, timeout=timeout, allow_redirects=True)
        if resp.url and resp.url != url:
            print(f"[Redirect] {url[:80]}... → {resp.url[:80]}...")
            return resp.url
    except Exception as e:
        print(f"[Redirect] HEAD failed, trying GET: {e}")
        try:
            resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True, stream=True)
            resp.close()
            if resp.url and resp.url != url:
                return resp.url
        except Exception:
            pass
    return url
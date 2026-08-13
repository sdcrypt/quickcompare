"""
Blinkit scraper — opens a real browser and collects product data.

Why a real browser?
    Blinkit's website is built with React, meaning the page content is loaded
    by JavaScript after the initial page load. A simple HTTP request would get
    an empty shell. Playwright solves this by launching a real Chrome browser
    (in the background, without a visible window) that runs the JavaScript just
    like a normal user would.

How it works, step by step:
    1. Launch a headless Chrome browser (no visible window).
    2. Open blinkit.com and try to set a delivery location using a pincode,
       because Blinkit shows different prices and availability depending on
       where you are.
    3. Go to the search-results page for the product the user typed.
    4. Scroll down a few times to make sure lazy-loaded products appear.
    5. Pull the name, price, MRP, unit, and image from each product card.
    6. Return everything as a plain list of dictionaries.

Important note on selectors:
    The constants below (SEL_*) are CSS patterns used to find elements on
    the page. Blinkit occasionally redesigns their website and renames these
    classes. If scraping suddenly returns zero results, open blinkit.com in
    Chrome DevTools, inspect a product card, and update these constants to
    match the new class names.
"""

import asyncio
import re
from urllib.parse import quote_plus

from playwright.async_api import TimeoutError as PWTimeout
from playwright.async_api import async_playwright

from config import DEFAULT_PINCODE
from page_checks import login_required_error, scrape_error

# ── Settings you can change ───────────────────────────────────────────────────

MAX_PRODUCTS    = 30         # Maximum products to collect per search (keeps it fast)
SCROLL_ROUNDS   = 4          # How many times to scroll down to load more results
SCROLL_PAUSE_MS = 800        # Milliseconds to wait after each scroll

# ── Page element selectors ────────────────────────────────────────────────────
# These tell Playwright where to look for specific pieces of data on the page.

SEL_PRODUCT_CARD = (
    "[data-testid*='product-card'], "
    "[class*='Product__ProductContainer'], "
    "[class*='ProductCard'], "
    "[class*='product-card'], "
    "[class*='tw-h-full'][class*='tw-flex-col'][class*='tw-pb-3'], "
    ".product-container"
)
SEL_NAME         = (
    "[data-testid*='name'], "
    "[data-testid*='title'], "
    "[class*='ProductName'], "
    "[class*='Product__UpdatedTitle'], "
    "[class*='tw-line-clamp-2'], "
    "[class*='name'], "
    "h3, h2"
)
SEL_PRICE        = (
    "[data-testid*='price'], "
    "[class*='Product__UpdatedPriceAndAtc'] [class*='price']:not([class*='line-through']), "
    "[class*='selling-price'], "
    "[class*='final-price'], "
    "[class*='price']:not([class*='line-through'])"
)
SEL_MRP   = "[data-testid*='mrp'], [class*='line-through'], [class*='mrp'], s, del"
SEL_UNIT  = (
    "[data-testid*='unit'], "
    "[data-testid*='weight'], "
    "[class*='weight'], "
    "[class*='unit'], "
    "[class*='quantity'], "
    "[class*='grammage']"
)
SEL_IMAGE = "img"


class BlinkitScrapeError(RuntimeError):
    """Raised when Blinkit renders no usable product data."""


# ── Public function ───────────────────────────────────────────────────────────

async def scrape_search(query: str) -> list[dict]:
    """
    Main entry point — scrape Blinkit for a given product query.

    Opens a browser, searches for the product, and returns a list of
    product dictionaries ready to be saved to the database.

    Each dictionary contains: name, price, mrp, unit, image_url,
    source_url, search_query, source, in_stock.

    Raises BlinkitScrapeError if no products were found or the page could not
    be scraped. The worker records that as a failed job with a useful message.
    """
    results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,                                    # no visible window
            args=["--no-sandbox", "--disable-setuid-sandbox"],  # needed inside Docker
        )
        context = await browser.new_context(
            # Pretend to be a regular Chrome user so the site doesn't block us
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()

        try:
            # Step 1: Land on the homepage first so cookies/session are set
            await page.goto("https://blinkit.com", wait_until="domcontentloaded", timeout=30_000)
            await page.wait_for_timeout(2_000)

            # Step 2: Set a delivery location so prices are shown
            await _set_location(page)

            # Step 3: Go straight to the search results for our query
            search_url = _search_url(query)
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30_000)
            await page.wait_for_timeout(3_000)

            login_msg = await login_required_error(page, "blinkit")
            if login_msg:
                raise BlinkitScrapeError(login_msg)

            # Step 4 & 5: Scroll and collect
            results = await _extract_products(page, query)

        except Exception as exc:
            print(f"[blinkit] scrape error: {exc}")
            raise
        finally:
            await browser.close()

    return results


# ── Private helpers ───────────────────────────────────────────────────────────

async def _set_location(page) -> None:
    """
    Attempt to set the delivery location to SCRAPER_PINCODE from .env.

    Blinkit requires a delivery address before it will show prices.
    This function looks for the location button, clicks it, types the
    pincode, and selects the first suggestion from the dropdown.

    If the popup doesn't appear (e.g. location was already set from a
    previous session), this function just exits quietly without failing.
    """
    try:
        location_btn = page.locator(
            "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'detect') "
            "or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'location') "
            "or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'delivery')]"
        ).first

        if await location_btn.is_visible(timeout=4_000):
            await location_btn.click()
            await page.wait_for_timeout(1_000)

        pincode_input = page.locator(
            "input[placeholder*='pincode' i], "
            "input[placeholder*='location' i], "
            "input[placeholder*='delivery' i], "
            "input[placeholder*='area' i]"
        ).first

        if await pincode_input.is_visible(timeout=3_000):
            await pincode_input.fill(DEFAULT_PINCODE)
            await page.wait_for_timeout(1_000)

            # Pick the first suggestion from the dropdown
            suggestion = page.locator(
                "[class*='LocationSearchList__LocationDetailContainer'], "
                "li[class*='suggestion'], "
                "[data-testid*='suggestion']"
            ).first
            if await suggestion.is_visible(timeout=2_000):
                await suggestion.click()
                await page.wait_for_load_state("domcontentloaded", timeout=10_000)
                await page.wait_for_timeout(1_500)

    except PWTimeout:
        pass  # Location popup sometimes doesn't appear — that's fine
    except Exception as exc:
        print(f"[blinkit] location setup warning: {exc}")


async def _extract_products(page, query: str) -> list[dict]:
    """
    Find all product cards on the search-results page and extract their data.

    First waits for at least one product card to appear (up to 10 seconds).
    Then scrolls the page a few times to load any items that only appear
    when you scroll down. Finally, loops through each card and reads the
    name, price, MRP, unit, and image.

    Skips any card that is missing a name or price (it's probably an ad
    or a banner, not a real product).
    """
    products = []

    # Wait for the first product card — if none appear, the page is empty or broken
    try:
        await page.wait_for_selector(SEL_PRODUCT_CARD, timeout=10_000)
    except PWTimeout:
        raise BlinkitScrapeError(await scrape_error(page, "blinkit", "no product cards found"))

    # Scroll down several times to trigger lazy-loaded content
    for _ in range(SCROLL_ROUNDS):
        await page.evaluate("window.scrollBy(0, 900)")
        await page.wait_for_timeout(SCROLL_PAUSE_MS)

    cards = await page.query_selector_all(SEL_PRODUCT_CARD)
    print(f"[blinkit] found {len(cards)} raw cards for '{query}'")

    for card in cards[:MAX_PRODUCTS]:
        try:
            card_text = await card.inner_text()
            name  = await _text(card, SEL_NAME) or _fallback_name(card_text)
            price = _parse_price(await _text(card, SEL_PRICE)) or _fallback_price(card_text)
            mrp   = _parse_price(await _text(card, SEL_MRP))
            unit  = await _text(card, SEL_UNIT) or _fallback_unit(card_text)
            img   = await _attr(card, SEL_IMAGE, "src")

            # Skip cards that look like banners or placeholders
            if not name or price == 0.0:
                continue

            products.append({
                "name":         name,
                "price":        price,
                "mrp":          mrp if mrp else price,  # if no MRP listed, use price
                "unit":         unit,
                "image_url":    img,
                "source_url":   _search_url(query),
                "search_query": query.lower(),
                "source":       "blinkit",
                "in_stock":     True,
            })
        except Exception:
            continue  # One broken card shouldn't stop the whole scrape

    if not products:
        raise BlinkitScrapeError(
            await scrape_error(page, "blinkit", f"{len(cards)} cards found but no usable products parsed")
        )

    return products


async def _text(node, selector: str) -> str:
    """
    Find the first matching element inside a card and return its text.
    Returns an empty string if the element isn't found.
    """
    el = await node.query_selector(selector)
    return (await el.inner_text()).strip() if el else ""


async def _attr(node, selector: str, attr: str) -> str:
    """
    Find the first matching element inside a card and return one of its
    HTML attributes (for example, the 'src' of an image tag).
    Returns an empty string if the element isn't found.
    """
    el = await node.query_selector(selector)
    return (await el.get_attribute(attr) or "") if el else ""


def _parse_price(text: str) -> float:
    """
    Pull the first number out of a price string and return it as a float.

    Handles strings like "₹49", "MRP ₹1,299.00", "Rs. 89" — the rupee
    symbol and commas are stripped before searching for digits.
    Returns 0.0 if no number is found.
    """
    text = text.replace(",", "")
    match = re.search(r"\d+\.?\d*", text)
    return float(match.group()) if match else 0.0


def _fallback_name(text: str) -> str:
    """
    Guess the product name from a card's full visible text.

    Used when CSS selectors miss the title element. Splits the card text
    into lines, drops junk lines (prices, EMI tags, ratings, etc.), and
    returns the longest remaining line — that is usually the product title.
    """
    candidates = [line for line in _lines(text) if not _is_junk_name_line(line)]
    return max(candidates, key=len) if candidates else ""


def _is_junk_name_line(line: str) -> bool:
    """
    Return True if a line from a product card is unlikely to be the title.

    Blinkit cards contain UI noise mixed with the product name: prices,
    discount badges, EMI offers, star ratings, and pack sizes. This helper
    filters those out so _fallback_name() does not pick a price or badge
    instead of the actual product title.

    Returns False for longer descriptive lines that look like real names.
    """
    if re.search(r"(₹|rs\.?|add|off|%)", line, re.I) and len(line) < 40:
        if re.search(r"(₹|rs\.?|\boff\b|emi|/month)", line, re.I):
            return True
    if re.fullmatch(r"\d+\.\d+\s*\(\d+\)", line):
        return True
    if re.fullmatch(r"\d+(?:\.\d+)?\s*(?:g|kg|ml|l|ltr|pcs?|pieces|pack|packs)", line, re.I):
        return True
    if len(line) < 12:
        return True
    return False


def _fallback_price(text: str) -> float:
    """
    Extract the selling price from a card's full text when selectors fail.

    Finds the first ₹ or Rs. amount in the card text. Returns 0.0 if none
    is found.
    """
    match = re.search(r"(?:₹|rs\.?\s*)(\d[\d,]*(?:\.\d+)?)", text, re.I)
    return float(match.group(1).replace(",", "")) if match else 0.0


def _fallback_unit(text: str) -> str:
    """
    Extract pack size from a card's full text when selectors fail.

    Scans each line for patterns like "500 g", "1 L", or "2 pcs".
    Returns the first match, or an empty string if none is found.
    """
    for line in _lines(text):
        if re.fullmatch(r"\d+(?:\.\d+)?\s*(?:g|kg|ml|l|ltr|pcs?|pieces|pack|packs)", line, re.I):
            return line
    return ""


def _lines(text: str) -> list[str]:
    """Split card text into non-empty, trimmed lines."""
    return [line.strip() for line in text.splitlines() if line.strip()]


def _search_url(query: str) -> str:
    """Build the Blinkit search-results URL for a given query string."""
    return f"https://blinkit.com/s/?q={quote_plus(query)}"

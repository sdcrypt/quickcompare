"""
Zepto scraper — collects product data from zeptonow.com.

Zepto is a quick commerce app (like Blinkit) that delivers groceries in
minutes. Its website is also a React app, so we need a real browser
(Playwright) to see any product data — a plain HTTP request would just
return an empty shell.

How this scraper works:
    1. Open a headless Chrome browser (no visible window).
    2. Land on the Zepto homepage and handle the location popup if it appears.
       Zepto needs to know your delivery area before it will show prices.
    3. Navigate to the search-results page for the product the user typed.
    4. Scroll down a few times to trigger lazy-loaded product cards.
    5. Read the name, price, MRP, unit, and image from each card.
    6. Return everything as a plain list of dictionaries — same shape as
       the Blinkit scraper so the worker can save them without any extra logic.

Note on selectors:
    The SEL_* constants below are CSS patterns that tell Playwright where
    to look for data on the page. Zepto occasionally updates their design
    and renames CSS classes. If this scraper starts returning zero results,
    open zeptonow.com in Chrome DevTools, inspect a product card, and
    update the selectors below to match the new class names.
"""

import asyncio
import re
from urllib.parse import quote_plus

from playwright.async_api import TimeoutError as PWTimeout
from playwright.async_api import async_playwright

from page_checks import login_required_error, scrape_error

# ── Settings ──────────────────────────────────────────────────────────────────

DEFAULT_PINCODE = "110001"   # New Delhi — change to any valid Indian pincode
MAX_PRODUCTS    = 30         # Cap on how many products to collect per search
SCROLL_ROUNDS   = 4          # Times to scroll down to load more results
SCROLL_PAUSE_MS = 900        # Milliseconds to wait between scrolls

# ── Page element selectors ────────────────────────────────────────────────────
# Zepto uses Next.js with hashed CSS class names, so we target data attributes
# and partial class names that tend to stay stable across redesigns.

SEL_PRODUCT_CARD = (
    "[data-testid='product-card'], "
    "[class*='ProductCard'], "
    "[class*='product-card'], "
    "[class*='cn__ProductCard']"
)
SEL_NAME = (
    "[data-testid='product-name'], "
    "[class*='product-name'], "
    "[class*='ProductName'], "
    "[class*='itemName'], "
    "h5, h4"
)
SEL_PRICE = (
    "[data-testid='product-price'], "
    "[class*='selling-price'], "
    "[class*='SellingPrice'], "
    "[class*='offer-price'], "
    "[class*='discounted-price'], "
    "[class*='finalPrice']"
)
SEL_MRP = (
    "[data-testid='product-mrp'], "
    "[class*='mrp'], "
    "[class*='MRP'], "
    "[class*='original-price'], "
    "[class*='strikethrough'], "
    "s, del"
)
SEL_UNIT = (
    "[data-testid='product-weight'], "
    "[class*='weight'], "
    "[class*='Weight'], "
    "[class*='unit'], "
    "[class*='quantity'], "
    "[class*='grammage'], "
    "[class*='packSize']"
)
SEL_IMAGE = "img"


class ZeptoScrapeError(RuntimeError):
    """Raised when Zepto renders no usable product data."""


# ── Public function ───────────────────────────────────────────────────────────

async def scrape_search(query: str) -> list[dict]:
    """
    Main entry point — scrape Zepto for a given product query.

    Opens a browser, sets a delivery location, searches for the product,
    and returns a list of product dictionaries ready to be saved to the
    database.

    Each dictionary contains: name, price, mrp, unit, image_url,
    source_url, search_query, source, in_stock.

    Raises ZeptoScrapeError if no products were found or the page could not
    be scraped. The worker records that as a failed job with a useful message.
    """
    results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        context = await browser.new_context(
            # Pretend to be a regular Chrome browser so Zepto doesn't block us
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            # Accept cookies so Zepto doesn't reset session on every page
            extra_http_headers={"Accept-Language": "en-IN,en;q=0.9"},
        )
        page = await context.new_page()

        try:
            # Step 1: Land on the homepage so the session and cookies are ready
            await page.goto(
                "https://www.zeptonow.com",
                wait_until="domcontentloaded",
                timeout=30_000,
            )
            await page.wait_for_timeout(2_500)

            # Step 2: Set the delivery location so prices become visible
            await _set_location(page)

            # Step 3: Go to the search results page for our query
            search_url = _search_url(query)
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30_000)
            await page.wait_for_timeout(3_000)

            login_msg = await login_required_error(page, "zepto")
            if login_msg:
                raise ZeptoScrapeError(login_msg)

            # Step 4 & 5: Scroll down and collect product data
            results = await _extract_products(page, query)

        except Exception as exc:
            print(f"[zepto] scrape error: {exc}")
            raise
        finally:
            await browser.close()

    return results


# ── Private helpers ───────────────────────────────────────────────────────────

async def _set_location(page) -> None:
    """
    Try to set the delivery pincode so Zepto shows prices for our area.

    Zepto shows a location popup on the first visit asking for your area
    or pincode. This function finds that input field, types the pincode,
    and selects the first suggestion from the dropdown.

    If the popup doesn't appear (session already has a saved location),
    this function exits quietly without failing.
    """
    try:
        # Wait a moment for the location modal to appear
        await page.wait_for_timeout(1_500)

        # Look for the pincode / location input field
        pincode_input = page.locator(
            "input[placeholder*='pincode' i], "
            "input[placeholder*='location' i], "
            "input[placeholder*='area' i], "
            "input[placeholder*='delivery' i]"
        ).first

        if not await pincode_input.is_visible(timeout=4_000):
            # No location modal — we're already set, or it didn't trigger
            return

        await pincode_input.fill(DEFAULT_PINCODE)
        await page.wait_for_timeout(1_200)

        # Select the first address suggestion from the dropdown
        suggestion = page.locator(
            "li[class*='suggestion'], "
            "[data-testid*='suggestion'], "
            "[class*='LocationSuggestion'], "
            "[class*='suggestion-item']"
        ).first

        if await suggestion.is_visible(timeout=3_000):
            await suggestion.click()
            await page.wait_for_timeout(2_000)   # wait for page to reload with new location

    except PWTimeout:
        pass  # Location popup not present — that's fine, carry on
    except Exception as exc:
        print(f"[zepto] location setup warning: {exc}")


async def _extract_products(page, query: str) -> list[dict]:
    """
    Find all product cards on the Zepto search-results page and read their data.

    Waits up to 10 seconds for the first card to appear — if none show up,
    it probably means the location isn't set or the selectors need updating.
    Scrolls the page a few times to make sure lazy-loaded items are visible,
    then loops through each card and reads: name, price, MRP, unit, image.

    Cards that are missing a name or have a price of zero are skipped —
    they are usually banners or "sponsored" slots, not real products.
    """
    products = []

    # Wait for at least one product card to appear on the page
    try:
        await page.wait_for_selector(SEL_PRODUCT_CARD, timeout=10_000)
    except PWTimeout:
        raise ZeptoScrapeError(await scrape_error(page, "zepto", "no product cards found"))

    # Scroll down to load lazy content
    for _ in range(SCROLL_ROUNDS):
        await page.evaluate("window.scrollBy(0, 900)")
        await page.wait_for_timeout(SCROLL_PAUSE_MS)

    cards = await page.query_selector_all(SEL_PRODUCT_CARD)
    print(f"[zepto] found {len(cards)} raw cards for '{query}'")

    for card in cards[:MAX_PRODUCTS]:
        try:
            card_text = await card.inner_text()
            name  = await _text(card, SEL_NAME) or _fallback_name(card_text)
            price = _parse_price(await _text(card, SEL_PRICE)) or _fallback_price(card_text)
            mrp   = _parse_price(await _text(card, SEL_MRP)) or _fallback_mrp(card_text, price)
            unit  = await _text(card, SEL_UNIT) or _fallback_unit(card_text)
            img   = await _attr(card, SEL_IMAGE, "src")

            # Skip cards that look like ads or empty placeholders
            if not name or price == 0.0:
                continue

            products.append({
                "name":         name,
                "price":        price,
                "mrp":          mrp if mrp else price,  # if no MRP listed, treat price as MRP
                "unit":         unit,
                "image_url":    img,
                "source_url":   _search_url(query),
                "search_query": query.lower(),
                "source":       "zepto",
                "in_stock":     True,
            })
        except Exception:
            continue  # One broken card shouldn't stop the whole scrape

    if not products:
        raise ZeptoScrapeError(
            await scrape_error(page, "zepto", f"{len(cards)} cards found but no usable products parsed")
        )

    return products


async def _text(node, selector: str) -> str:
    """
    Find the first element matching the selector inside a card and return
    its visible text. Returns an empty string if nothing is found.
    """
    el = await node.query_selector(selector)
    return (await el.inner_text()).strip() if el else ""


async def _attr(node, selector: str, attr: str) -> str:
    """
    Find the first element matching the selector inside a card and return
    one of its HTML attributes (e.g. 'src' from an img tag).
    Returns an empty string if the element isn't found.
    """
    el = await node.query_selector(selector)
    return (await el.get_attribute(attr) or "") if el else ""


def _parse_price(text: str) -> float:
    """
    Pull the first number out of a price string and return it as a float.

    Handles formats like "₹49", "MRP ₹1,299", "Rs.89" — strips the rupee
    symbol and commas before searching for digits.
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

    Zepto cards contain many short UI lines mixed with the product name:
    "ADD", "₹6149", "₹648/month EMI", "4.7 (212)", "1 pc", etc. This helper
    filters those out so _fallback_name() does not pick a price or badge
    instead of the actual product title.

    Returns False for longer descriptive lines that look like real names.
    """
    if re.fullmatch(r"(add|off)", line, re.I):
        return True
    if re.fullmatch(r"₹\s*\d[\d,]*(?:\.\d+)?", line, re.I):
        return True
    if re.search(r"\bemi\b|/month|no cost|delivery in|similar product", line, re.I):
        return True
    if re.fullmatch(r"₹\s*\d[\d,]*.*\boff\b", line, re.I):
        return True
    if re.fullmatch(r"\d+\.\d+\s*\(\d+\)", line):
        return True
    if re.fullmatch(r"\(?\d+(?:\.\d+)?[km]?\)?", line, re.I):
        return True
    if _looks_like_unit(line):
        return True
    if len(line) < 12:
        return True
    return False


def _fallback_price(text: str) -> float:
    """
    Extract the selling price from a card's full text when selectors fail.

    Finds all ₹ amounts in the card and returns the first one (usually the
    current selling price). Returns 0.0 if none are found.
    """
    prices = _prices(text)
    return prices[0] if prices else 0.0


def _fallback_mrp(text: str, price: float) -> float:
    """
    Extract the original MRP from a card's full text when selectors fail.

    Looks for ₹ amounts after the selling price and returns the first one
    that is higher than the selling price (the struck-through MRP).
    Returns 0.0 if no higher amount is found.
    """
    for candidate in _prices(text)[1:]:
        if candidate > price:
            return candidate
    return 0.0


def _fallback_unit(text: str) -> str:
    """
    Extract pack size from a card's full text when selectors fail.

    Scans each line for patterns like "500 g", "1 L", or "1 pc".
    Returns the first match, or an empty string if none is found.
    """
    for line in _lines(text):
        if _looks_like_unit(line):
            return line
    return ""


def _looks_like_unit(line: str) -> bool:
    """
    Return True if a line looks like a pack-size label rather than a name.

    Matches strings like "500 g", "1 L", "2 pcs", or "1 pack".
    """
    return bool(
        re.search(
            r"\b\d+(?:\.\d+)?\s*(?:g|kg|ml|l|ltr|pcs?|pieces|pack|packs)\b",
            line,
            re.I,
        )
    )


def _prices(text: str) -> list[float]:
    """
    Find every ₹ price in a block of text, in top-to-bottom order.

    Handles comma-separated amounts like "₹6,149". Returns an empty list
    when no prices are found.
    """
    return [
        float(match.replace(",", ""))
        for match in re.findall(r"₹\s*(\d[\d,]*(?:\.\d+)?)", text)
    ]


def _lines(text: str) -> list[str]:
    """Split card text into non-empty, trimmed lines."""
    return [line.strip() for line in text.splitlines() if line.strip()]


def _search_url(query: str) -> str:
    """Build the Zepto search-results URL for a given query string."""
    return f"https://www.zepto.com/search?query={quote_plus(query)}"

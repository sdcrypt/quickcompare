"""
Swiggy Instamart scraper — collects product data from swiggy.com/instamart.

Swiggy Instamart is Swiggy's quick-commerce arm, delivering groceries in
minutes. Like Blinkit and Zepto, it is a React app, so we need a real browser
(Playwright) to see any product data — a plain HTTP request returns an empty
page shell.

How this scraper works:
    1. Open a headless Chrome browser (no visible window).
    2. Land on the Instamart homepage and handle the location prompt if it
       appears. Swiggy needs to know your delivery area before it will show
       prices and availability.
    3. Navigate to the search-results page for the product the user typed.
    4. Scroll down a few times to trigger lazy-loaded product cards.
    5. Read the name, price, MRP, unit, and image from each card.
    6. Return everything as a plain list of dictionaries — same shape as the
       Blinkit and Zepto scrapers so the worker can save them without any
       extra logic.

Note on selectors:
    The SEL_* constants below are CSS patterns that tell Playwright where to
    look for data on the page. Swiggy occasionally updates their design and
    renames CSS classes. If this scraper starts returning zero results, open
    swiggy.com/instamart in Chrome DevTools, inspect a product card, and
    update the selectors below to match the new class names.
"""

import asyncio
import re
from urllib.parse import quote_plus

from playwright.async_api import TimeoutError as PWTimeout
from playwright.async_api import async_playwright

from config import DEFAULT_PINCODE
from page_checks import access_blocked_error, login_required_error, scrape_error

# ── Settings ──────────────────────────────────────────────────────────────────

MAX_PRODUCTS    = 30         # Cap on how many products to collect per search
SCROLL_ROUNDS   = 4          # Times to scroll down to load more results
SCROLL_PAUSE_MS = 900        # Milliseconds to wait between scrolls

# Swiggy blocks default headless Playwright — these settings reduce detection.
_STEALTH_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-blink-features=AutomationControlled",
]
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
_WEBDRIVER_HIDE = (
    "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
)

# ── Page element selectors ────────────────────────────────────────────────────
# Swiggy uses styled-components with hashed class names, so we layer multiple
# selectors — more specific data-testid ones first, broader class-name patterns
# as fallbacks.

SEL_PRODUCT_CARD = (
    "[data-testid='item-collection-card-full'], "
    "[data-testid='item_list_item_widget'], "
    "[class*='ItemWidget'], "
    "[class*='product-card']"
)
SEL_NAME = (
    "[data-testid='item-name'], "
    "[class*='item-name'], "
    "[class*='ItemName'], "
    "[class*='ItemTitle'], "
    "[class*='product-name'], "
    "[class*='styles_itemName'], "
    "h3, h4"
)
SEL_PRICE = (
    "[data-testid='item-price'], "
    "[class*='selling-price'], "
    "[class*='SellingPrice'], "
    "[class*='offer-price'], "
    "[class*='styles_price'], "
    "[class*='final-price'], "
    "[class*='discounted'], "
    "[class*='price']:not([class*='line-through']):not([class*='strike'])"
)
SEL_MRP = (
    "[data-testid='item-mrp'], "
    "[class*='mrp'], "
    "[class*='MRP'], "
    "[class*='strike'], "
    "[class*='crossed'], "
    "[class*='original-price'], "
    "s, del"
)
SEL_UNIT = (
    "[data-testid='item-weight'], "
    "[class*='weight'], "
    "[class*='Weight'], "
    "[class*='unit'], "
    "[class*='grammage'], "
    "[class*='quantity'], "
    "[class*='packSize'], "
    "[class*='styles_weight']"
)
SEL_IMAGE = "img[src*='instamart'], img[src*='media-assets'], img"


class InstamartScrapeError(RuntimeError):
    """Raised when Swiggy Instamart renders no usable product data."""


# ── Public function ───────────────────────────────────────────────────────────

async def scrape_search(query: str) -> list[dict]:
    """
    Main entry point — scrape Swiggy Instamart for a given product query.

    Opens a browser, sets a delivery location, searches for the product,
    and returns a list of product dictionaries ready to be saved to the
    database.

    Each dictionary contains: name, price, mrp, unit, image_url,
    source_url, search_query, source, in_stock.

    Raises InstamartScrapeError if no products were found or the page could
    not be scraped. The worker records that as a failed job with a useful
    message.
    """
    results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=_STEALTH_ARGS,
            ignore_default_args=["--enable-automation"],
        )
        context = await browser.new_context(
            user_agent=_USER_AGENT,
            viewport={"width": 1366, "height": 768},
            locale="en-IN",
            timezone_id="Asia/Kolkata",
            extra_http_headers={"Accept-Language": "en-IN,en;q=0.9"},
        )
        await context.add_init_script(_WEBDRIVER_HIDE)
        page = await context.new_page()

        try:
            # Step 1: Land on the Instamart homepage so the session is ready
            await page.goto(
                "https://www.swiggy.com/instamart",
                wait_until="domcontentloaded",
                timeout=30_000,
            )
            await page.wait_for_timeout(3_000)

            # Step 2: Set the delivery location so prices become visible
            await _set_location(page)

            # Step 3: Go to the search results page for our query
            search_url = _search_url(query)
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30_000)
            await page.wait_for_timeout(3_000)

            blocked_msg = await access_blocked_error(page, "instamart")
            if blocked_msg:
                raise InstamartScrapeError(blocked_msg)

            # Check if Swiggy is demanding login before showing results
            login_msg = await login_required_error(page, "instamart")
            if login_msg:
                raise InstamartScrapeError(login_msg)

            # Step 4 & 5: Scroll down and collect product data
            results = await _extract_products(page, query)

        except Exception as exc:
            print(f"[instamart] scrape error: {exc}")
            raise
        finally:
            await browser.close()

    return results


# ── Private helpers ───────────────────────────────────────────────────────────

async def _set_location(page) -> None:
    """
    Try to set the delivery location to the pincode from config.

    Swiggy Instamart shows a location prompt on the first visit asking for
    your area. This function finds that input field, types the pincode, and
    selects the first suggestion from the dropdown.

    If the prompt doesn't appear (session already has a saved location),
    this function exits quietly without failing.
    """
    try:
        await page.wait_for_timeout(2_000)

        # Dismiss any cookie/notification permission popup first
        for dismiss_sel in [
            "button:has-text('Not Now')",
            "button:has-text('Skip')",
            "button:has-text('Dismiss')",
            "[aria-label='Close']",
        ]:
            try:
                btn = page.locator(dismiss_sel).first
                if await btn.is_visible(timeout=1_500):
                    await btn.click()
                    await page.wait_for_timeout(500)
                    break
            except PWTimeout:
                pass

        # Look for the location / area search input
        location_input = page.locator(
            "input[placeholder*='Search for area' i], "
            "input[placeholder*='Enter your location' i], "
            "input[placeholder*='Search location' i], "
            "input[placeholder*='delivery location' i], "
            "input[id*='location' i]"
        ).first

        if not await location_input.is_visible(timeout=4_000):
            # No location prompt — session already has an address, or the
            # page skipped it. Carry on.
            return

        await location_input.fill(DEFAULT_PINCODE)
        await page.wait_for_timeout(1_500)

        # Select the first address suggestion from the dropdown
        suggestion = page.locator(
            "[class*='location-result'], "
            "[class*='LocationItem'], "
            "[class*='suggestion'], "
            "[data-testid*='location'], "
            "li[class*='result']"
        ).first

        if await suggestion.is_visible(timeout=3_000):
            await suggestion.click()
            await page.wait_for_timeout(2_500)   # wait for page to reload with new location

    except PWTimeout:
        pass  # Location prompt not present — that's fine, carry on
    except Exception as exc:
        print(f"[instamart] location setup warning: {exc}")


async def _extract_products(page, query: str) -> list[dict]:
    """
    Find all product cards on the Instamart search-results page and read
    their data.

    Waits up to 10 seconds for the first card to appear. If none show up,
    it probably means the location isn't set or the selectors need updating.
    Scrolls the page several times to load lazy-rendered products, then loops
    through each card and reads: name, price, MRP, unit, image.

    Cards that are missing a name or have a zero price are skipped — they
    are usually banners, ads, or empty placeholder slots.
    """
    products = []

    # Wait for the first product card — if none appear the page is empty or blocked
    try:
        await page.wait_for_selector(SEL_PRODUCT_CARD, timeout=10_000)
    except PWTimeout:
        raise InstamartScrapeError(
            await scrape_error(page, "instamart", "no product cards found")
        )

    # Scroll down to trigger lazy-loaded content
    for _ in range(SCROLL_ROUNDS):
        await page.evaluate("window.scrollBy(0, 900)")
        await page.wait_for_timeout(SCROLL_PAUSE_MS)

    cards = await page.query_selector_all(SEL_PRODUCT_CARD)
    print(f"[instamart] found {len(cards)} raw cards for '{query}'")

    for card in cards[:MAX_PRODUCTS]:
        try:
            # Price and unit live in the card wrapper, not inside the testid node itself
            card_text = await card.evaluate(
                "el => el.parentElement ? el.parentElement.innerText : el.innerText"
            )
            parsed = _parse_card_text(card_text)
            name  = (parsed["name"] if parsed else "") or await _text(card, SEL_NAME) or _fallback_name(card_text)
            price = (parsed["price"] if parsed else 0.0) or _parse_price(await _text(card, SEL_PRICE)) or _fallback_price(card_text)
            mrp   = _parse_price(await _text(card, SEL_MRP)) or _fallback_mrp(card_text, price)
            unit  = (parsed["unit"] if parsed else "") or await _text(card, SEL_UNIT) or _fallback_unit(card_text)
            img   = await _attr(card, SEL_IMAGE, "src")

            # Skip cards that look like banners or empty slots
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
                "source":       "instamart",
                "in_stock":     True,
            })
        except Exception:
            continue  # One broken card shouldn't stop the whole scrape

    if not products:
        raise InstamartScrapeError(
            await scrape_error(
                page, "instamart",
                f"{len(cards)} cards found but no usable products parsed"
            )
        )

    return products


# ── Utility helpers (same pattern as blinkit.py and zepto.py) ─────────────────

async def _text(node, selector: str) -> str:
    """Find the first matching element inside a card and return its text."""
    el = await node.query_selector(selector)
    return (await el.inner_text()).strip() if el else ""


async def _attr(node, selector: str, attr: str) -> str:
    """Find the first matching element inside a card and return one of its HTML attributes."""
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


def _parse_card_text(text: str) -> dict | None:
    """
    Parse Swiggy Instamart's line-based card layout.

    Typical shapes:
        4 MINS / Product name / 400 g / 65
        4 MINS / Product name / subtitle / 350 g / 50
    """
    lines = _lines(text)
    start = next(
        (i for i, line in enumerate(lines) if re.match(r"^\d+\s+MINS$", line, re.I)),
        None,
    )
    if start is None:
        return None
    lines = lines[start:]
    if len(lines) < 4:
        return None

    unit_idx = None
    for i in range(len(lines) - 1, 0, -1):
        if re.fullmatch(
            r"\d+(?:\.\d+)?\s*(?:g|kg|ml|l|ltr|pcs?|pieces|pack|packs)",
            lines[i],
            re.I,
        ):
            unit_idx = i
            break

    if unit_idx is None or unit_idx >= len(lines) - 1:
        return None

    price = 0.0
    for line in lines[unit_idx + 1 :]:
        if re.search(r"off|%|switch", line, re.I):
            continue
        price = _parse_price(line)
        if price == 0.0 and line.replace(",", "").isdigit():
            price = float(line.replace(",", ""))
        if price > 0.0:
            break

    name = lines[1] if len(lines) > 1 else ""
    if not name or price == 0.0:
        return None

    return {"name": name, "unit": lines[unit_idx], "price": price}


def _fallback_name(text: str) -> str:
    """
    Guess the product name from a card's full visible text when CSS selectors miss it.

    Splits the card text into lines, drops junk lines (prices, badges, ratings),
    and returns the longest remaining line — that is usually the product title.
    """
    candidates = [line for line in _lines(text) if not _is_junk_name_line(line)]
    return max(candidates, key=len) if candidates else ""


def _is_junk_name_line(line: str) -> bool:
    """
    Return True if a line from a product card is unlikely to be the product title.

    Filters out price strings, discount badges, ratings, and pack-size lines
    so _fallback_name() doesn't pick those instead of the actual product name.
    """
    if re.search(r"(₹|rs\.?|/month|emi)", line, re.I) and len(line) < 40:
        return True
    if re.fullmatch(r"\d+\.\d+\s*\(\d+\)", line):  # "4.2 (1k+)" style ratings
        return True
    if re.fullmatch(
        r"\d+(?:\.\d+)?\s*(?:g|kg|ml|l|ltr|pcs?|pieces|pack|packs)", line, re.I
    ):
        return True
    if len(line) < 12:
        return True
    return False


def _fallback_price(text: str) -> float:
    """
    Extract the selling price from a card's full text when selectors fail.

    Swiggy often shows the price as a plain number on the last line.
    """
    parsed = _parse_card_text(text)
    if parsed:
        return parsed["price"]

    match = re.search(r"(?:₹|rs\.?\s*)(\d[\d,]*(?:\.\d+)?)", text, re.I)
    return float(match.group(1).replace(",", "")) if match else 0.0


def _fallback_mrp(text: str, selling_price: float) -> float:
    """
    Extract the MRP (crossed-out original price) from the card's full text.

    Looks for the second ₹ amount in the card text (the first is usually the
    selling price). Falls back to selling_price if only one price is found.
    """
    matches = re.findall(r"(?:₹|rs\.?\s*)(\d[\d,]*(?:\.\d+)?)", text, re.I)
    if len(matches) >= 2:
        prices = [float(m.replace(",", "")) for m in matches]
        # MRP is usually the higher value
        return max(prices)
    return selling_price


def _fallback_unit(text: str) -> str:
    """
    Extract pack size from a card's full text when selectors fail.

    Scans each line for patterns like "500 g", "1 L", "200 ml". Returns the
    first match, or an empty string if none is found.
    """
    for line in _lines(text):
        if re.fullmatch(
            r"\d+(?:\.\d+)?\s*(?:g|kg|ml|l|ltr|pcs?|pieces|pack|packs)", line, re.I
        ):
            return line
    return ""


def _lines(text: str) -> list[str]:
    """Split card text into non-empty, trimmed lines."""
    return [line.strip() for line in text.splitlines() if line.strip()]


def _search_url(query: str) -> str:
    """Build the Swiggy Instamart search-results URL for a given query string."""
    return f"https://www.swiggy.com/instamart/search?custom_back=true&query={quote_plus(query)}"

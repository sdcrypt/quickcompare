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

from playwright.async_api import TimeoutError as PWTimeout
from playwright.async_api import async_playwright

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


# ── Public function ───────────────────────────────────────────────────────────

async def scrape_search(query: str) -> list[dict]:
    """
    Main entry point — scrape Zepto for a given product query.

    Opens a browser, sets a delivery location, searches for the product,
    and returns a list of product dictionaries ready to be saved to the
    database.

    Each dictionary contains: name, price, mrp, unit, image_url,
    source_url, search_query, source, in_stock.

    Returns an empty list if no products were found or an error occurred.
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
            search_url = f"https://www.zeptonow.com/search?query={query.replace(' ', '%20')}"
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30_000)
            await page.wait_for_timeout(3_000)

            # Step 4 & 5: Scroll down and collect product data
            results = await _extract_products(page, query)

        except Exception as exc:
            print(f"[zepto] scrape error: {exc}")
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
            "input[placeholder*='pincode'], "
            "input[placeholder*='location'], "
            "input[placeholder*='area'], "
            "input[placeholder*='delivery']"
        ).first

        if not await pincode_input.is_visible(timeout=4_000):
            # No location modal — we're already set, or it didn't trigger
            return

        await pincode_input.fill(DEFAULT_PINCODE)
        await page.wait_for_timeout(1_200)

        # Select the first address suggestion from the dropdown
        suggestion = page.locator(
            "li[class*='suggestion'], "
            "[data-testid='suggestion'], "
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
        print("[zepto] no product cards found — check selectors or location setup")
        return products

    # Scroll down to load lazy content
    for _ in range(SCROLL_ROUNDS):
        await page.evaluate("window.scrollBy(0, 900)")
        await page.wait_for_timeout(SCROLL_PAUSE_MS)

    cards = await page.query_selector_all(SEL_PRODUCT_CARD)
    print(f"[zepto] found {len(cards)} raw cards for '{query}'")

    for card in cards[:MAX_PRODUCTS]:
        try:
            name  = await _text(card, SEL_NAME)
            price = _parse_price(await _text(card, SEL_PRICE))
            mrp   = _parse_price(await _text(card, SEL_MRP))
            unit  = await _text(card, SEL_UNIT)
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
                "source_url":   f"https://www.zeptonow.com/search?query={query.replace(' ', '%20')}",
                "search_query": query.lower(),
                "source":       "zepto",
                "in_stock":     True,
            })
        except Exception:
            continue  # One broken card shouldn't stop the whole scrape

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

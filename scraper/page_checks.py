"""
Shared page-state checks for platform scrapers.

Detects login walls and other blockers so failed jobs return a clear message
instead of a generic "no product cards found" debug dump.
"""

import re

from playwright.async_api import Page

LOGIN_WALL_PATTERNS = (
    re.compile(r"please\s+login\s+to\s+continue", re.I),
    re.compile(r"login\s+to\s+continue\s+searching", re.I),
    re.compile(r"oops!\s*please\s+login", re.I),
    re.compile(r"sign\s+in\s+to\s+continue", re.I),
    re.compile(r"login\s+required", re.I),
    re.compile(r"please\s+sign\s+in", re.I),
    re.compile(r"you\s+must\s+be\s+logged\s+in", re.I),
)


def login_wall_detected(body_text: str) -> bool:
    return any(pattern.search(body_text) for pattern in LOGIN_WALL_PATTERNS)


async def body_text(page: Page, limit: int = 2000) -> str:
    try:
        return (await page.locator("body").inner_text(timeout=1_000))[:limit]
    except Exception:
        return ""


async def login_required_error(page: Page, platform: str) -> str | None:
    if login_wall_detected(await body_text(page)):
        return f"{platform.capitalize()} requires login for this search"
    return None


async def scrape_error(page: Page, platform: str, reason: str) -> str:
    login_msg = await login_required_error(page, platform)
    if login_msg:
        return login_msg

    body_preview = await body_text(page, limit=500)
    title = ""
    try:
        title = await page.title()
    except Exception:
        pass

    return (
        f"{reason}; title={title!r}; url={page.url!r}; "
        f"body_preview={body_preview!r}"
    )

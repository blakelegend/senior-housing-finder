"""
Shared Playwright helpers.

Provides a context manager that yields a configured Playwright browser with:
- Optional headless mode (configurable via HEADLESS env var)
- UA rotation
- Proxy rotation (next proxy from CONFIG.proxy_pool)
- Sensible default timeouts
- Block heavy resources (images/fonts) for faster scrapes

Install browsers once after pip install:
    playwright install chromium
"""
from contextlib import contextmanager
from typing import Iterator, Optional

from fake_useragent import UserAgent
from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

from ..config import CONFIG

_UA = UserAgent()


def _pick_proxy() -> Optional[dict]:
    """Pick a proxy from the pool in Playwright's expected dict format."""
    if not CONFIG.proxy_pool:
        return None
    # Playwright expects {"server": "http://host:port", "username": "...", "password": "..."}
    # We accept full URLs in the pool; parse if creds are inline
    import urllib.parse as up
    url = CONFIG.proxy_pool[0]  # round-robin handled by HTTP layer; PW just picks one
    parsed = up.urlparse(url)
    proxy = {"server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"}
    if parsed.username:
        proxy["username"] = parsed.username
    if parsed.password:
        proxy["password"] = parsed.password
    return proxy


def _block_heavy_resources(route, request) -> None:
    if request.resource_type in ("image", "font", "media"):
        route.abort()
    else:
        route.continue_()


@contextmanager
def browser_context(
    headless: Optional[bool] = None,
    block_heavy: bool = True,
) -> Iterator[BrowserContext]:
    """
    Yield a Playwright `BrowserContext` ready to navigate.

    Usage:
        with browser_context() as ctx:
            page = ctx.new_page()
            page.goto("https://...")
    """
    headless = CONFIG.headless if headless is None else headless

    with sync_playwright() as pw:
        launch_kwargs = {"headless": headless}
        proxy = _pick_proxy()
        if proxy:
            launch_kwargs["proxy"] = proxy

        browser: Browser = pw.chromium.launch(**launch_kwargs)
        ctx: BrowserContext = browser.new_context(
            user_agent=_UA.random,
            viewport={"width": 1366, "height": 768},
            locale="en-US",
        )
        ctx.set_default_timeout(CONFIG.browser_timeout_ms)

        if block_heavy:
            ctx.route("**/*", _block_heavy_resources)

        try:
            yield ctx
        finally:
            ctx.close()
            browser.close()


@contextmanager
def new_page(headless: Optional[bool] = None) -> Iterator[Page]:
    """Convenience wrapper: yields a fresh page from a one-shot context."""
    with browser_context(headless=headless) as ctx:
        page = ctx.new_page()
        try:
            yield page
        finally:
            page.close()

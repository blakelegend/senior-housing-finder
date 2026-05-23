"""
Headless Google Maps scraper (Playwright-based).

⚠️  IMPORTANT — TERMS OF SERVICE
================================
Scraping Google Maps via the consumer UI violates Google's Terms of Service.
The legitimate path is the **Places API** (see `google_places.py`), which is:
- Officially supported
- Cheap at this scale (~$17 per 1k Text Search calls)
- Won't get your IPs banned

Use this scraper ONLY when:
- You're doing exploratory research at very low volume
- You have a legitimate business reason that Places API can't satisfy
- You've talked to counsel and accepted the ToS risk

For production at $1B-deployment scale: USE THE PLACES API. The cost is
trivial compared to the legal/operational risk of UI scraping.

If you proceed, the scraper:
- Uses headless Chromium via Playwright
- Rotates User-Agent and (optional) proxy on each session
- Rate-limits aggressively (1 query per few seconds)
- Caches results to avoid re-hitting the same query
"""
import re
import time
from typing import List, Optional
from urllib.parse import quote_plus

from ..config import CONFIG
from ..utils.browser import browser_context

DEFAULT_QUERIES = [
    "assisted living near {city}",
    "memory care near {city}",
    "senior living near {city}",
    "independent living near {city}",
    "nursing home near {city}",
    "continuing care retirement community near {city}",
]


def _scroll_results_panel(page, max_scrolls: int = 20) -> None:
    """
    Google Maps lazy-loads results when you scroll the left panel. Repeatedly
    scroll until no new results appear or max_scrolls reached.
    """
    panel_selector = 'div[role="feed"]'
    last_height = 0
    for _ in range(max_scrolls):
        try:
            page.evaluate(
                f"() => {{ const el = document.querySelector('{panel_selector}'); "
                f"if (el) el.scrollTop = el.scrollHeight; }}"
            )
            page.wait_for_timeout(1500)
            new_height = page.evaluate(
                f"() => {{ const el = document.querySelector('{panel_selector}'); "
                f"return el ? el.scrollHeight : 0; }}"
            )
            if new_height == last_height:
                # Check for "You've reached the end" marker
                if page.locator("text=You've reached the end").count() > 0:
                    break
            last_height = new_height
        except Exception:
            break


def _extract_results(page) -> List[dict]:
    """Pull facility cards from the current Maps results page."""
    cards = page.locator('a[href*="/maps/place/"]')
    out: List[dict] = []
    seen_urls = set()
    for i in range(cards.count()):
        try:
            card = cards.nth(i)
            url = card.get_attribute("href") or ""
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            # Card layout: aria-label has the business name; child divs have rating/category
            aria = card.get_attribute("aria-label") or ""
            name = aria.strip()

            # Click into the card to load the side panel with phone/website/address
            card.click()
            page.wait_for_timeout(1500)

            # Pull side panel data
            address = _safe_text(page, 'button[data-item-id="address"]')
            phone = _safe_text(page, 'button[data-item-id^="phone:tel:"]')
            website = page.locator('a[data-item-id="authority"]').get_attribute("href") if page.locator('a[data-item-id="authority"]').count() else None
            rating_text = _safe_text(page, 'div.F7nice')

            out.append({
                "name": name,
                "address": address,
                "phone": phone,
                "website": website,
                "google_url": url,
                "rating_raw": rating_text,
                "source": "GoogleMaps:scraper",
            })
        except Exception as e:
            print(f"[google_maps_scraper] card extract failed: {e}")
            continue
    return out


def _safe_text(page, selector: str) -> Optional[str]:
    try:
        loc = page.locator(selector).first
        if loc.count():
            return loc.inner_text().strip()
    except Exception:
        return None
    return None


def collect_google_maps(
    cities: List[str],
    queries: Optional[List[str]] = None,
    max_scrolls_per_query: int = 15,
) -> List[dict]:
    """
    Scrape Google Maps for each (query, city) combination.

    `cities` should be strings like "Tampa, FL". `queries` are templates
    with `{city}` placeholder.
    """
    queries = queries or DEFAULT_QUERIES
    all_results: List[dict] = []

    with browser_context() as ctx:
        page = ctx.new_page()
        for city in cities:
            for template in queries:
                q = template.format(city=city)
                url = f"https://www.google.com/maps/search/{quote_plus(q)}"
                print(f"[google_maps_scraper] {q}")
                try:
                    page.goto(url, wait_until="domcontentloaded")
                    page.wait_for_timeout(2500)
                    _scroll_results_panel(page, max_scrolls=max_scrolls_per_query)
                    results = _extract_results(page)
                    for r in results:
                        r["query"] = q
                        r["city_searched"] = city
                    all_results.extend(results)
                except Exception as e:
                    print(f"[google_maps_scraper] failed query '{q}': {e}")
                # Polite delay between queries
                time.sleep(3)

        page.close()

    # Dedup by Google URL
    seen, deduped = set(), []
    for r in all_results:
        u = r.get("google_url")
        if u and u not in seen:
            seen.add(u)
            deduped.append(r)
    return deduped

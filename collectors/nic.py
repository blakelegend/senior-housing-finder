"""
NIC (National Investment Center for Seniors Housing & Care).

NIC is a paid subscription service — their MAP data product is not open and
scraping it would violate their ToS. This module instead aggregates NIC's
**public** outputs:

- NIC Notes blog (public posts on occupancy, transaction trends)
- NIC Map Vision quarterly press releases (free PDFs with topline market data)
- NIC's investor conference attendee lists (sometimes published)

If you have a NIC MAP subscription, drop in your API key and uncomment the
authenticated endpoints — the structure is here.

ETHICS: Do not scrape behind NIC's paywall. Use the API license you've paid for.
"""
from typing import List, Optional

from bs4 import BeautifulSoup

from ..utils.http import polite_get


NIC_PRESS_RELEASES = "https://www.nic.org/news-press/"
NIC_BLOG = "https://blog.nic.org/"


def collect_nic_market_snapshots(limit: int = 25) -> List[dict]:
    """
    Pull recent NIC press-release headlines + summaries.

    These give you topline market data (occupancy rates by primary/secondary
    market, construction starts, transaction volume) that helps tune your
    targeting — e.g. "AL occupancy in 31 primary markets recovered to 85.6%
    in Q1" tells you which markets are still soft.
    """
    out: List[dict] = []
    try:
        resp = polite_get(NIC_PRESS_RELEASES, rps=0.5)
    except Exception as e:
        print(f"[nic] press release fetch failed: {e}")
        return out

    soup = BeautifulSoup(resp.text, "lxml")
    for article in soup.select("article")[:limit]:
        title_el = article.select_one("h2, h3, .entry-title")
        link_el = article.select_one("a[href]")
        excerpt_el = article.select_one("p, .entry-summary")
        if not title_el:
            continue
        out.append({
            "title": title_el.get_text(strip=True),
            "url": link_el["href"] if link_el else None,
            "excerpt": excerpt_el.get_text(strip=True) if excerpt_el else None,
            "source": "NIC",
        })
    return out


def collect_nic_facilities(api_key: Optional[str] = None) -> List[dict]:
    """
    Placeholder for the NIC MAP Vision API. Requires a paid subscription.

    Once you have credentials, uncomment and adapt:

        endpoint = "https://api.nicmap.com/v1/properties"
        headers = {"Authorization": f"Bearer {api_key}"}
        ...

    Without an API key this returns an empty list and logs a notice.
    """
    if not api_key:
        print("[nic] no NIC_MAP_API_KEY configured — skipping facility-level NIC pull")
        return []
    # Real implementation goes here once a subscription is in place.
    return []

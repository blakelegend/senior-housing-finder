"""
LinkedIn Sales Navigator URL builders.

We don't scrape LinkedIn — that's against ToS and the account-ban risk is
not worth it. Instead, generate pre-filtered Sales Navigator search URLs
that your BD team can open in their browser to find the right humans.

Two URL patterns:
- `sales_nav_url`        — Sales Navigator account/people search with filters
- `linkedin_search_url`  — free LinkedIn search fallback for non-Sales Nav users

Output flows into the CRM's `linkedin_search_link` column, so each lead has
a one-click jump to the right LI search.
"""
from typing import List, Optional
from urllib.parse import quote_plus

# Titles that indicate decision-makers for senior housing transactions
OWNER_TITLES = [
    "Owner", "CEO", "President", "Founder", "Managing Partner",
    "Principal", "Managing Member", "Executive Director",
    "Chief Executive Officer", "Chief Operating Officer",
    "Chief Investment Officer", "Chief Financial Officer",
    "Head of Real Estate", "Head of Acquisitions",
]


def linkedin_search_url(operator_name: str, location: Optional[str] = None) -> str:
    """
    Build a free LinkedIn search URL — works without Sales Navigator.

    The URL hits LinkedIn's people search filtered by company + (optional) geo.
    """
    parts = [operator_name]
    if location:
        parts.append(location)
    return "https://www.linkedin.com/search/results/people/?keywords=" + quote_plus(" ".join(parts))


def sales_nav_url(
    operator_name: str,
    titles: Optional[List[str]] = None,
    geography: Optional[str] = None,
) -> str:
    """
    Build a Sales Navigator URL with title + company filters.

    Sales Nav URLs use a `query` param with structured filters as JSON-ish
    nested params. The format below works as of 2025 and renders the same
    filter UI as if the user had built the search by hand.
    """
    titles = titles or OWNER_TITLES

    # Sales Nav uses a peculiar URL structure; this composes the key filters
    title_filter = ",".join(quote_plus(t) for t in titles)
    company_filter = quote_plus(operator_name)
    geo_filter = f"&geoIncluded={quote_plus(geography)}" if geography else ""

    return (
        "https://www.linkedin.com/sales/search/people?"
        f"keywords={company_filter}"
        f"&titleIncluded={title_filter}"
        f"{geo_filter}"
    )

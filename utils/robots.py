"""
robots.txt respect — cache + check per host.

We use stdlib urllib.robotparser. The parser is cached per-host so we only
fetch each robots.txt once per process. If we can't read robots.txt we
default to **allowed** (consistent with real-world crawler behavior) — but
the calling site can opt-in to strict mode via `default_allow=False`.

Important: respecting robots.txt is the *minimum* — many sites publish
machine-readable Terms of Service that go further. This module handles the
common case; for vendor-specific ToS, see ETHICS.md and each collector's
header comment.

Usage:
    from senior_housing_finder.utils.robots import is_allowed
    if not is_allowed("https://example.com/leads/123"):
        skip
"""
import urllib.parse as up
import urllib.robotparser as rp
from typing import Dict

import requests

from .logging_setup import get_logger

log = get_logger(__name__)

_PARSERS: Dict[str, rp.RobotFileParser] = {}
_DEFAULT_UA = "senior-housing-finder/1.0 (+research)"


def _parser_for(host: str, scheme: str = "https") -> rp.RobotFileParser:
    if host in _PARSERS:
        return _PARSERS[host]

    parser = rp.RobotFileParser()
    robots_url = f"{scheme}://{host}/robots.txt"
    try:
        # urlopen on robotparser blocks indefinitely on slow hosts; fetch ourselves with timeout
        resp = requests.get(robots_url, timeout=10, headers={"User-Agent": _DEFAULT_UA})
        if resp.status_code == 200:
            parser.parse(resp.text.splitlines())
        else:
            # 404/403 → no robots = allow all (per RFC 9309)
            parser.parse([])
    except Exception as e:
        log.debug(f"robots.txt fetch failed for {host}: {e} — defaulting to allow")
        parser.parse([])
    _PARSERS[host] = parser
    return parser


def is_allowed(url: str, user_agent: str = _DEFAULT_UA, default_allow: bool = True) -> bool:
    """Return True if `user_agent` may fetch `url` per the host's robots.txt."""
    try:
        parts = up.urlparse(url)
        if not parts.netloc:
            return default_allow
        parser = _parser_for(parts.netloc, parts.scheme or "https")
        return parser.can_fetch(user_agent, url)
    except Exception:
        return default_allow

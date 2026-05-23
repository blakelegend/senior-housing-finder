"""
Polite HTTP helpers.

- Respects robots-like backoff with tenacity retries
- Rotates a small set of User-Agent strings
- Honors per-host rate limiters
- Caches GET responses to disk to avoid hammering sources during development
"""
import hashlib
import itertools
import json
import threading
import time
from pathlib import Path
from typing import Dict, Optional

import requests
from fake_useragent import UserAgent
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from ..config import CONFIG
from .rate_limiter import RateLimiter

_UA = UserAgent()
_LIMITERS: Dict[str, RateLimiter] = {}

# Proxy rotation: cycle through CONFIG.proxy_pool. Bad proxies get parked
# for a cool-down period (rather than dropped permanently — many residential
# proxy services recycle IPs).
_PROXY_LOCK = threading.Lock()
_PROXY_CYCLE = itertools.cycle(CONFIG.proxy_pool) if CONFIG.proxy_pool else None
_PROXY_PARKED: Dict[str, float] = {}
_PROXY_PARK_SECONDS = 300.0


def _next_proxy() -> Optional[Dict[str, str]]:
    """Return a {scheme: url} dict for requests, or None if no pool configured."""
    if not _PROXY_CYCLE:
        return None
    with _PROXY_LOCK:
        # Try up to len(pool) times to find a non-parked proxy
        for _ in range(len(CONFIG.proxy_pool)):
            p = next(_PROXY_CYCLE)
            parked_until = _PROXY_PARKED.get(p, 0)
            if parked_until <= time.monotonic():
                return {"http": p, "https": p}
        # All parked — just use the next one anyway
        return {"http": p, "https": p}


def _park_proxy(proxy_url: str) -> None:
    """Mark a proxy as bad for `_PROXY_PARK_SECONDS`."""
    with _PROXY_LOCK:
        _PROXY_PARKED[proxy_url] = time.monotonic() + _PROXY_PARK_SECONDS


def _limiter_for(host: str, rps: float) -> RateLimiter:
    if host not in _LIMITERS:
        _LIMITERS[host] = RateLimiter(rps)
    return _LIMITERS[host]


def _cache_key(url: str, params: Optional[dict]) -> Path:
    raw = url + json.dumps(params or {}, sort_keys=True)
    h = hashlib.sha256(raw.encode()).hexdigest()
    return CONFIG.cache_dir / f"{h}.json"


def polite_session() -> requests.Session:
    """Return a session with a rotated UA and sane defaults."""
    s = requests.Session()
    s.headers.update({
        "User-Agent": _UA.random,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    })
    return s


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type((requests.RequestException,)),
    reraise=True,
)
def polite_get(
    url: str,
    params: Optional[dict] = None,
    rps: float = CONFIG.default_rps,
    use_cache: bool = True,
    session: Optional[requests.Session] = None,
    timeout: int = 30,
    respect_robots: bool = False,
) -> requests.Response:
    """
    GET with rate limiting, retries, and optional disk cache.

    Set `respect_robots=True` for scrapers hitting third-party sites whose
    robots.txt should be honored (state licensing pages, county assessor
    sites, etc.). Government open-data APIs and our own CMS / Census /
    Medicare endpoints are exempt by default — they publish data for
    machine consumption.

    Returns the Response object so the caller can decide how to parse it.
    """
    host = requests.utils.urlparse(url).netloc

    if respect_robots:
        # Late import to avoid a hard dependency cycle (robots module imports requests)
        from .robots import is_allowed
        if not is_allowed(url):
            raise requests.RequestException(f"robots.txt disallows {url}")

    _limiter_for(host, rps).wait()

    cache_path = _cache_key(url, params) if use_cache else None
    if cache_path and cache_path.exists():
        cached = json.loads(cache_path.read_text())
        resp = requests.Response()
        resp.status_code = cached["status_code"]
        resp._content = cached["content"].encode("utf-8", errors="ignore")
        resp.url = url
        return resp

    sess = session or polite_session()
    proxies = _next_proxy()
    try:
        resp = sess.get(url, params=params, timeout=timeout, proxies=proxies)
        resp.raise_for_status()
    except (requests.ConnectionError, requests.Timeout) as e:
        # Park the bad proxy so we don't keep hitting it on retries
        if proxies:
            _park_proxy(proxies["http"])
        raise

    if cache_path:
        cache_path.write_text(json.dumps({
            "status_code": resp.status_code,
            "content": resp.text,
            "ts": time.time(),
        }))
    return resp

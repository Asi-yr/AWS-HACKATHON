"""
network_utils.py
----------------
Shared network helpers for the SafeRoute risk_monitor package.

Drop this file into risk_monitor/ and import from it to get:
  - Consistent browser-like headers for PH government sites
  - SSL warning suppression (PH govt certs often fail local chain verification)
  - DNS-aware silent failure helper
  - A safe_get() wrapper that never raises — returns None on any error

Usage:
    from risk_monitor.network_utils import safe_get, BROWSER_HEADERS, is_network_error
"""

import requests
import urllib3

# ── Suppress SSL InsecureRequestWarning globally ─────────────────────────────
# PH government endpoints (MMDA, PHIVOLCS, PAGASA) frequently have SSL cert
# issues when run from local dev environments. verify=False bypasses this
# cleanly; the warning is just noise in the console.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── Browser-like headers ──────────────────────────────────────────────────────
# Many PH government APIs (MMDA, PAGASA) return 403 to plain script user-agents.
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection":      "keep-alive",
}


def is_network_error(ex: Exception) -> bool:
    """
    Return True if the exception means the host is simply unreachable
    (DNS failure, connection refused, timeout). Used to skip retries early.
    """
    msg = str(ex).lower()
    return any(k in msg for k in (
        "getaddrinfo failed",
        "name or service not known",
        "nameresolutionerror",
        "failed to resolve",
        "nodename nor servname",
        "connection refused",
        "network is unreachable",
        "timed out",
        "connecttimeout",
    ))


def safe_get(url: str, *,
             headers: dict = None,
             timeout: int = 8,
             verify: bool = False,
             referer: str = None,
             params: dict = None) -> "requests.Response | None":
    """
    GET a URL silently. Returns the Response on success, None on any error.
    Never raises — designed for optional external data sources.

    Args:
        url:      Full URL to fetch
        headers:  Extra headers (merged with BROWSER_HEADERS)
        timeout:  Request timeout in seconds (default 8)
        verify:   SSL verification (default False for PH govt cert issues)
        referer:  Optional Referer header (helps with 403s)
        params:   Optional query parameters dict

    Returns:
        requests.Response or None
    """
    h = {**BROWSER_HEADERS, **(headers or {})}
    if referer:
        h["Referer"] = referer
        h["Origin"]  = referer.rstrip("/")
    try:
        resp = requests.get(url, headers=h, timeout=timeout,
                            verify=verify, params=params)
        return resp
    except Exception:
        return None


def safe_post(url: str, *,
              data: dict = None,
              headers: dict = None,
              timeout: int = 10,
              verify: bool = False) -> "requests.Response | None":
    """
    POST a URL silently. Returns the Response on success, None on any error.
    """
    h = {**BROWSER_HEADERS, **(headers or {})}
    try:
        resp = requests.post(url, data=data, headers=h,
                             timeout=timeout, verify=verify)
        return resp
    except Exception:
        return None

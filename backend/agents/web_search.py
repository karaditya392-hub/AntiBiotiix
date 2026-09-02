"""
Web retrieval for the agentic evidence path (Spec §23).

Deliberately thin. This module fetches; it does not judge. Everything it returns
is unfiltered and MUST pass through backend.agents.filtration before any of it
reaches a reader - which is enforced by this module never producing a citation
shape, only raw {"url", "title", "content"} dicts that nothing downstream knows
how to render.

PROVIDERS, AND WHY THERE IS A KEYLESS ONE. Tavily, Brave and Serper are real
APIs with support contracts and require a key. DuckDuckGo's HTML endpoint
requires none, which is the only reason it is here: it lets the filtration agent
be demonstrated without a commercial signup.

It is NOT an official API. It is a page whose markup can change without notice,
and it rate-limits under repeated queries. Both failure modes return an empty
list rather than a partial one, so a scraping break degrades to "nothing
retrieved" - the same state as the web path being switched off - and never to a
half-populated result a reader might mistake for the whole picture.

Off by default. WEB_SEARCH_ENABLED=false means the system behaves exactly as it
did before this path existed: held corpus only. That is the correct default for a
clinical tool, and it means a demo never depends on a vendor being up.
"""
from __future__ import annotations

import html
import re
from typing import Any, Dict, List
from urllib.parse import parse_qs, unquote, urlparse

from backend import config

# Providers that need no credential. `available()` must not demand a key for
# these, and forgetting that is why the DuckDuckGo provider silently never ran
# the first time it was configured.
KEYLESS_PROVIDERS = {"duckduckgo", "ddg"}

DDG_ENDPOINT = "https://html.duckduckgo.com/html/"
# A browser user agent. The endpoint serves a different, unparseable page to
# clients that do not send one.
DDG_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

# One result block: the anchor carrying the title and href, then the snippet.
_DDG_RESULT = re.compile(
    r'<a[^>]+class="result__a"[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>'
    r'.*?class="result__snippet"[^>]*>(?P<snippet>.*?)</a>',
    re.DOTALL,
)


def available() -> bool:
    """
    Whether the web path can run at all.

    A keyless provider needs only the feature flag; a commercial one needs its
    key as well.
    """
    if not config.WEB_SEARCH_ENABLED:
        return False
    if config.WEB_SEARCH_PROVIDER in KEYLESS_PROVIDERS:
        return True
    return bool(config.WEB_SEARCH_API_KEY)


def _clean(fragment: str) -> str:
    """Strip the markup DuckDuckGo wraps matched terms in, and unescape entities."""
    return html.unescape(re.sub(r"<[^>]+>", "", fragment or "")).strip()


def _direct_url(href: str) -> str:
    """
    The real destination.

    Most results carry a direct href, but DuckDuckGo sometimes wraps one in its
    own redirect with the true target in a `uddg` parameter. Passing the redirect
    downstream would make the filtration agent judge duckduckgo.com rather than
    the source, and would cite the wrong domain to a clinician.
    """
    if not href:
        return ""
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if "duckduckgo.com" in parsed.netloc and "uddg" in (parsed.query or ""):
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        if target:
            return unquote(target)
    return href


def _search_duckduckgo(query: str, limit: int) -> List[Dict[str, Any]]:
    import httpx

    response = httpx.post(
        DDG_ENDPOINT,
        data={"q": query},
        headers=DDG_HEADERS,
        timeout=30.0,
        follow_redirects=True,
    )
    response.raise_for_status()

    results: List[Dict[str, Any]] = []
    seen = set()
    for match in _DDG_RESULT.finditer(response.text):
        url = _direct_url(match.group("href"))
        if not url or url in seen:
            continue
        seen.add(url)
        results.append({
            "url": url,
            "title": _clean(match.group("title")),
            "content": _clean(match.group("snippet")),
        })
        if len(results) >= limit:
            break
    return results


def search(query: str, max_results: int = 0) -> List[Dict[str, Any]]:
    """
    Raw, unjudged search results.

    Never returns partial results on error - an empty list is a clear "nothing
    retrieved", where a half-filled list would be read as "this is what the web
    says".
    """
    if not available() or not (query or "").strip():
        return []

    limit = max_results or config.WEB_SEARCH_MAX_RESULTS
    provider = config.WEB_SEARCH_PROVIDER

    try:
        if provider in KEYLESS_PROVIDERS:
            return _search_duckduckgo(query, limit)

        import httpx

        if provider == "tavily":
            response = httpx.post(
                config.WEB_SEARCH_BASE_URL,
                json={
                    "api_key": config.WEB_SEARCH_API_KEY,
                    "query": query,
                    "max_results": limit,
                    "search_depth": "advanced",
                    "include_raw_content": False,
                },
                timeout=30.0,
            )
            response.raise_for_status()
            rows = response.json().get("results", [])
            return [
                {"url": r.get("url", ""), "title": r.get("title", ""), "content": r.get("content", "")}
                for r in rows
            ]

        # Brave and Serper both answer a keyed GET; the only difference that
        # matters here is the field names.
        headers = {"X-API-KEY": config.WEB_SEARCH_API_KEY,
                   "X-Subscription-Token": config.WEB_SEARCH_API_KEY,
                   "Accept": "application/json"}
        response = httpx.get(config.WEB_SEARCH_BASE_URL,
                             params={"q": query, "count": limit},
                             headers=headers, timeout=30.0)
        response.raise_for_status()
        body = response.json()
        rows = body.get("web", {}).get("results") or body.get("organic") or []
        return [
            {"url": r.get("url") or r.get("link", ""),
             "title": r.get("title", ""),
             "content": r.get("description") or r.get("snippet", "")}
            for r in rows
        ]
    except Exception:
        return []

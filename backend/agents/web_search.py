"""
Web retrieval for the agentic evidence path (Spec §23).

Deliberately thin. This module fetches; it does not judge. Everything it returns
is unfiltered and MUST pass through backend.agents.filtration before any of it
reaches a reader - which is enforced by this module never producing a citation
shape, only raw {"url", "title", "content"} dicts that nothing downstream knows
how to render.

Off by default. WEB_SEARCH_ENABLED=false in .env means the system behaves exactly
as it did before the agent layer existed: held corpus only. That is the correct
default for a clinical tool, and it means a demo never depends on a vendor being
up.
"""
from __future__ import annotations

from typing import Any, Dict, List

from backend import config


def available() -> bool:
    return bool(config.WEB_SEARCH_ENABLED and config.WEB_SEARCH_API_KEY)


def search(query: str, max_results: int = 0) -> List[Dict[str, Any]]:
    """
    Raw, unjudged search results. Never returns partial results on error - an
    empty list is a clear "nothing retrieved", where a half-filled list would be
    read as "this is what the web says".
    """
    if not available() or not (query or "").strip():
        return []

    limit = max_results or config.WEB_SEARCH_MAX_RESULTS
    try:
        import httpx
    except ImportError:  # pragma: no cover
        return []

    provider = config.WEB_SEARCH_PROVIDER
    try:
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

        # Brave and Serper both answer an OpenAI-shaped GET; kept in one branch
        # because the only difference that matters here is the field names.
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

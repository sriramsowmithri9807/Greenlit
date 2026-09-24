"""RESEARCH: conditional Tavily lookup.

Called only when the PLAN step's structured output flags the failure as
involving an unfamiliar or version-sensitive external API — never on every
iteration. A no-op (returns None) when TAVILY_API_KEY isn't set, so the
rest of the loop degrades gracefully without it.
"""
from __future__ import annotations

import os

from tavily import TavilyClient


def research(query: str) -> str | None:
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        return None

    client = TavilyClient(api_key=api_key)
    response = client.search(query=query, search_depth="basic", max_results=3)
    results = response.get("results", [])
    if not results:
        return None

    return "\n\n".join(
        f"{r.get('title', '')} ({r.get('url', '')})\n{(r.get('content') or '')[:800]}"
        for r in results
    )

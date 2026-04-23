from __future__ import annotations
import os
from langchain_core.tools import tool
from tavily import TavilyClient

_client: TavilyClient | None = None

def _get_client() -> TavilyClient:
    global _client
    if _client is None:
        _client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
    return _client

@tool
def web_search(query: str, max_results: int = 3) -> list[dict]:
    """Search the web for current news, financial data, or any topic and return the top matching results with title, URL, and content snippet.

    Args:
        query: Plain-text search query. Avoid special characters or operators.
        max_results: Maximum number of results to return. Default is 3.
    """
    resp = _get_client().search(query=query, max_results=max_results)
    return [{"title": r["title"], "url": r["url"], "content": r["content"]}
            for r in resp.get("results", [])]

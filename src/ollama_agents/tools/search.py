import urllib.parse
import logging
from typing import List

logger = logging.getLogger(__name__)

def web_search(query: str, max_results: int = 4) -> str:
    """Performs a live web search to find current news, facts, and updates.

    Args:
        query: The search query string.
        max_results: Maximum number of search snippets to return (default is 4).
    """
    results: List[str] = []

    # 1. Primary engine: Direct DuckDuckGo HTML endpoint (bypasses deprecated DDGS API blocks)
    try:
        import httpx
        from bs4 import BeautifulSoup

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9"
        }
        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        resp = httpx.get(url, headers=headers, timeout=12.0)

        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            for result_div in soup.find_all("div", class_="result__body")[:max_results]:
                title_elem = result_div.find("a", class_="result__a")
                snippet_elem = result_div.find("a", class_="result__snippet")
                url_elem = result_div.find("a", class_="result__url")

                if title_elem and snippet_elem:
                    raw_href = url_elem.get("href", "") if url_elem else title_elem.get("href", "")
                    clean_url = raw_href
                    if "uddg=" in raw_href:
                        try:
                            clean_url = urllib.parse.unquote(raw_href.split("uddg=")[1].split("&")[0])
                        except Exception:
                            clean_url = raw_href

                    results.append(
                        f"Title: {title_elem.text.strip()}\n"
                        f"Snippet: {snippet_elem.text.strip()}\n"
                        f"URL: {clean_url}"
                    )
    except Exception as html_err:
        logger.warning("DDG HTML search failed (%s). Attempting library fallback...", html_err)

    # 2. Secondary engine: duckduckgo_search / ddgs library fallback
    if not results:
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                raw_results = list(ddgs.text(query, max_results=max_results))
                for item in raw_results:
                    results.append(
                        f"Title: {item.get('title')}\n"
                        f"Snippet: {item.get('body')}\n"
                        f"URL: {item.get('href')}\n"
                    )
        except Exception as ddg_err:
            logger.warning("DDGS library search failed: %s", ddg_err)

    if results:
        return "\n---\n".join(results)
    
    return "No search results found. (Search engine blocked or query returned empty list)."
from duckduckgo_search import DDGS


def web_search(query: str, max_results: int = 4) -> str:
    """Performs a live web search to find current news, facts, and updates.

    Args:
        query: The search query string.
        max_results: Maximum number of search snippets to return (default is 4).
    """
    try:
        results = []
        with DDGS() as ddgs:
            raw_results = list(ddgs.text(query, max_results=max_results))
            for item in raw_results:
                results.append(
                    f"Title: {item.get('title')}\n"
                    f"Snippet: {item.get('body')}\n"
                    f"URL: {item.get('href')}\n"
                )
        return "\n---\n".join(results) if results else "No results found."
    except Exception as e:
        return f"Web search failed: {str(e)}"
from langchain_community.document_loaders import WikipediaLoader
from langchain_core.tools import tool

@tool
def search_wikipedia(search_query: str, max_results: int = 3) -> list[dict]:
    """Search Wikipedia for background information on companies, industries, economic concepts, or historical financial events.

    Args:
        search_query: Topic or question to search on Wikipedia (e.g., "Apple Inc history", "quantitative easing").
        max_results: Maximum number of Wikipedia articles to retrieve. Default is 3.
    """
    search_docs = WikipediaLoader(query=search_query, load_max_docs=max_results).load()

    return [{"source": doc.metadata["source"], "url": doc.metadata.get("page", ""), "content": doc.page_content}
            for doc in search_docs]
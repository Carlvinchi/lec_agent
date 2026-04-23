from __future__ import annotations
import os
import re
import chromadb
from langchain_core.tools import tool
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from tools.cache import TTLCache
import edgar as edg

_cache = TTLCache(ttl_seconds=None)   # filings are immutable — cache permanently
_ef = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
_client = chromadb.PersistentClient(path="data/chroma")
_collection = _client.get_or_create_collection("edgar_filings_v2", embedding_function=_ef)

_CHUNK_SIZE = 1500
_CHUNK_OVERLAP = 300

# Keywords that signal the question is about financial metrics
_FINANCIAL_KEYWORDS = {
    "revenue", "income", "earnings", "profit", "loss", "margin", "eps", "ebitda",
    "cash", "flow", "capex", "debt", "equity", "assets", "liabilities", "sales",
    "cost", "expense", "operating", "net", "gross", "fiscal", "quarter", "annual",
    "balance", "statement", "r&d", "research", "depreciation", "amortisation",
}


# ---------------------------------------------------------------------------
# Identity + filing fetch
# ---------------------------------------------------------------------------

def _set_identity() -> None:
    agent = os.environ.get("EDGAR_USER_AGENT", "FinAgent oc90699@yahoo.com")
    edg.set_identity(agent)


def _fetch_filing(ticker: str, filing_type: str, year: int):
    """Return the edgartools EntityFiling whose period_of_report matches year."""
    _set_identity()
    company = edg.Company(ticker)
    filings = company.get_filings(form=filing_type)

    # Match on fiscal period first, then fall back to filing date
    for f in filings:
        por = f.period_of_report
        if getattr(por, "year", None) == year:
            return f
    for f in filings:
        fd = f.filing_date
        if getattr(fd, "year", None) == year:
            return f
    return None


# ---------------------------------------------------------------------------
# Section extraction helpers
# ---------------------------------------------------------------------------

def _section_str(obj, attr: str) -> str:
    val = getattr(obj, attr, None)
    return re.sub(r"\s{3,}", " ", re.sub(r"\n{3,}", "\n\n", str(val).strip())) if val else ""


def _corpus_for_question(obj, filing_type: str, question: str) -> str:
    """
    Pick the sections most relevant to the question and return them as clean text.
    Financial/metric questions get the three financial statements + MD&A.
    Narrative questions (risk, strategy, business) get MD&A + business + risk factors.
    """
    q = question.lower()
    is_financial = any(kw in q for kw in _FINANCIAL_KEYWORDS)

    parts: list[str] = []

    if is_financial:
        for attr in ("income_statement", "balance_sheet", "cash_flow_statement"):
            text = _section_str(obj, attr)
            if text:
                parts.append(text)
        mda = _section_str(obj, "management_discussion")
        if mda:
            parts.append(mda)
    else:
        for attr in ("management_discussion", "business", "risk_factors"):
            text = _section_str(obj, attr)
            if text:
                parts.append(text)

    return "\n\n".join(parts)


def _chunk(text: str) -> list[str]:
    """Sliding-window chunking with overlap so table rows are never split cold."""
    step = _CHUNK_SIZE - _CHUNK_OVERLAP
    return [
        text[i: i + _CHUNK_SIZE]
        for i in range(0, len(text), step)
        if text[i: i + _CHUNK_SIZE].strip()
    ]


# ---------------------------------------------------------------------------
# Core implementation (shared between both tools)
# ---------------------------------------------------------------------------

def _get_filing_impl(ticker: str, filing_type: str, year: int) -> dict:
    key = _cache.make_key(ticker=ticker, filing_type=filing_type, year=year)
    if hit := _cache.get(key):
        return hit

    filing = _fetch_filing(ticker, filing_type, year)
    if not filing:
        return {"error": f"No {filing_type} filing found for {ticker} {year}"}

    obj = filing.obj()

    result = {
        "ticker": ticker,
        "filing_type": filing_type,
        "year": year,
        "period_of_report": str(filing.period_of_report),
        "filing_date": str(filing.filing_date),
        # Structured financial statements — clean tabular text from XBRL
        "income_statement":      _section_str(obj, "income_statement")[:8_000],
        "balance_sheet":         _section_str(obj, "balance_sheet")[:5_000],
        "cash_flow_statement":   _section_str(obj, "cash_flow_statement")[:5_000],
        # Narrative: MD&A for context
        "management_discussion": _section_str(obj, "management_discussion")[:8_000],
    }
    _cache.set(key, result)
    return result


# ---------------------------------------------------------------------------
# Public tools
# ---------------------------------------------------------------------------

@tool("get_sec_edgar")
def get_filing(ticker: str, filing_type: str, year: int) -> dict:
    """Retrieve key financial sections from an SEC filing as clean, structured text.

    Returns the income statement, balance sheet, cash flow statement, and MD&A
    extracted directly from XBRL data — no HTML noise. Use this when you need
    a broad view of a company's financials from a specific filing.

    Args:
        ticker: Stock ticker symbol (e.g., "AAPL", "MSFT", "TSLA").
        filing_type: SEC filing type — "10-K" for annual reports, "10-Q" for quarterly.
        year: Fiscal year of the filing (e.g., 2024).
    """
    return _get_filing_impl(ticker, filing_type, year)


@tool
def query_filing_documents(ticker: str, filing_type: str, year: int, question: str) -> str:
    """Search an SEC filing for passages that answer a specific financial question.

    Selects the most relevant filing sections for the question (financial statements
    for metric queries; MD&A and risk factors for narrative queries), chunks them
    at 1 500 characters with 300-character overlap, and returns the top semantically
    matched passages. Use this when you need a specific figure, trend, or statement
    from within a filing rather than the full document.

    Args:
        ticker: Stock ticker symbol (e.g., "AAPL", "MSFT", "TSLA").
        filing_type: SEC filing type — "10-K" for annual, "10-Q" for quarterly.
        year: Fiscal year of the filing (e.g., 2024).
        question: The specific question to answer (e.g., "What was total revenue?").
    """
    key = _cache.make_key(
        ticker=ticker, filing_type=filing_type, year=year, question=question
    )
    if hit := _cache.get(key):
        return hit

    filing = _fetch_filing(ticker, filing_type, year)
    if not filing:
        return f"No {filing_type} filing found for {ticker} {year}"

    obj = filing.obj()
    corpus = _corpus_for_question(obj, filing_type, question)

    if not corpus.strip():
        return f"Could not extract readable text from {ticker} {filing_type} {year}"

    # Index into ChromaDB if this filing hasn't been seen before
    existing = _collection.get(
        where={"$and": [
            {"ticker": ticker},
            {"filing_type": filing_type},
            {"year": year},
        ]},
        limit=1,
    )
    if not existing["ids"]:
        chunks = _chunk(corpus)
        prefix = f"{ticker}_{filing_type}_{year}_"
        _collection.add(
            ids=[f"{prefix}{i}" for i in range(len(chunks))],
            documents=chunks,
            metadatas=[
                {"ticker": ticker, "filing_type": filing_type, "year": year}
                for _ in chunks
            ],
        )

    results = _collection.query(
        query_texts=[question],
        n_results=6,
        where={"$and": [
            {"ticker": ticker},
            {"filing_type": filing_type},
            {"year": year},
        ]},
    )

    passages = [p.strip() for p in results["documents"][0] if p.strip()]
    answer = "\n---\n".join(passages) if passages else "Relevant section not found."
    _cache.set(key, answer)
    return answer


def cache_stats() -> dict:
    return _cache.stats()

## Tool Reference Guide

Use this guide to select the right tool for each research task. Never call a tool whose job is already covered by another — duplicate calls waste budget and slow the agent.

---

### `finance_kb` — Financial Definitions & Concepts
**Use when:** You need a precise definition, formula, or explanation of a financial term, ratio, or methodology (e.g. WACC, EBITDA, DuPont, DCF terminal value).
**Do not use for:** Live market data, company-specific figures, or SEC filings.
**Example calls:** `"WACC"`, `"inventory turnover"`, `"free cash flow"`, `"DuPont model"`

---

### `get_market_fundamentals` — Live Key Ratios
**Use when:** You need current snapshot metrics: P/E ratio, P/B ratio, debt-to-equity, return on equity, gross/operating margins, market cap, or current ratio. These are returned directly — no calculation needed.
**Do not use for:** Historical time series, full income statements, or filing-specific figures.
**Example calls:** `ticker="AAPL"` returns `priceToBook`, `debtToEquity`, `returnOnEquity`, `operatingMargins`

---

### `get_market_financials` — Income Statement / Balance Sheet / Cash Flow (Yahoo Finance)
**Use when:** You need multi-year financial statement line items — revenue, net income, operating income, total assets, total debt, operating cash flow, CapEx. This is the fastest source for margin, growth, and profitability queries.
**Parameters:** `statement` = `"income"` | `"balance"` | `"cashflow"`; `period` = `"annual"` | `"quarterly"`
**Do not use for:** Real-time ratios (use `get_market_fundamentals`) or filing-verified figures (use EDGAR tools).
**Example calls:** `ticker="MSFT", statement="income", period="annual"` for revenue and operating income

---

### `query_filing_documents` — Targeted SEC Filing Search (Semantic)
**Use when:** You need a specific figure, disclosure, or line item from within an SEC filing — e.g. goodwill balance, interest expense, segment operating income, shares outstanding, deferred revenue. Uses semantic search to find the most relevant passage.
**Prefer over `get_sec_edgar`** for all specific figure lookups.
**Do not use for:** Broad financial overviews or when `get_market_financials` already covers the metric.
**Example calls:** `ticker="PFIZER", filing_type="10-K", year=2024, question="What is total goodwill?"`

---

### `get_sec_edgar` — Full SEC Filing Sections (Broad)
**Use when:** You need a wide view of a company's financials from a specific year's filing — e.g. to read the full income statement, balance sheet, cash flow statement, and MD&A together. Useful when you are unsure which line item you need or want to cross-check multiple figures in one call.
**Prefer `query_filing_documents` instead** when you already know the specific figure you need.
**Example calls:** `ticker="TSLA", filing_type="10-K", year=2024`

---

### `get_market_history` — Historical Daily Prices & Volume
**Use when:** You need a stock's closing price on specific dates, price return over a period, or volume data. Required for computing price CAGR, portfolio value changes, or P/B expansion over time.
**Parameters:** `start` and `end` as ISO date strings (e.g. `"2024-01-01"`).
**Do not use for:** Fundamental ratios or financial statement items.
**Example calls:** `ticker="SPY", start="2020-01-02", end="2024-12-31"`

---

### `calculator` — Arithmetic & Financial Math
**Use when:** You need to compute a derived metric from figures already retrieved — percentage change, ratio, CAGR, or any arithmetic operation. Always use this instead of computing in your head.
**Supported operations:** `add`, `subtract`, `multiply`, `divide`, `power`, `sqrt`, `abs`, `round`, `percentage_change`, `ratio`, `cagr`
**`cagr` requires:** `a` = start value, `b` = end value, `n` = number of periods
**`percentage_change` requires:** `a` = base value, `b` = new value → returns `((b - a) / a) × 100`
**Do not use for:** Data retrieval — always fetch numbers from a data tool first.

---

### `web_search` — Current News & Real-Time Data
**Use when:** You need the current 10-year Treasury yield, recent analyst commentary, earnings news, or any information that post-dates the training cutoff and is not available in SEC filings or Yahoo Finance. Use targeted queries (include company name, ticker, and year).
**Do not use for:** Historical financial statements, definitions, or filing data — those have dedicated tools.
**Example calls:** `"current 10-year US Treasury yield"`, `"NVIDIA FY2023 analyst ROE commentary"`

---

### `search_wikipedia` — Background & Encyclopedic Context
**Use when:** You need background information on a company's history, an industry structure, a macroeconomic concept, or a well-established financial methodology (e.g. IDM vs fabless semiconductors, S&P 500 historical returns, enterprise value definition).
**Do not use for:** Live market data, SEC filings, or company earnings — Wikipedia is not a real-time source.
**Example calls:** `"Apple Inc history"`, `"semiconductor fabless business model"`, `"enterprise value vs market cap"`

---

## Tool Selection Decision Tree

```
Need a definition or formula?
  └─► finance_kb

Need a specific line item from an SEC filing?
  ├─ Know exactly which figure? → query_filing_documents
  └─ Need a broad overview of the filing? → get_sec_edgar

Need market data?
  ├─ Current ratios (P/E, P/B, D/E, ROE)? → get_market_fundamentals
  ├─ Multi-year income/balance/cashflow? → get_market_financials
  └─ Historical daily prices? → get_market_history

Need to compute a derived metric from retrieved numbers?
  └─► calculator

Need current news, yields, or analyst views?
  └─► web_search

Need encyclopedic background on a company or concept?
  └─► search_wikipedia
```

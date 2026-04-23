# Financial Analyst Agent

A multi-turn financial research agent built on LangGraph. It answers complex financial queries by reasoning across SEC filings, market data, a financial knowledge base, web search, and Wikipedia — with human-in-the-loop plan review and a hard budget cap per query.

---

## Architecture

```
User query
    │
    ▼
┌─────────────┐     no tool calls    ┌──────────────────┐
│   Planner   │ ──────────────────▶  │  Simple Response  │──▶ END
│ (Claude)    │                      └──────────────────┘
└─────────────┘
    │ tool calls planned
    ▼
┌──────────────┐    rejected    ┌──────────┐
│ Human Review │ ─────────────▶ │ Planner  │  (re-plan loop)
└──────────────┘                └──────────┘
    │ approved
    ▼
┌──────────────┐   budget exceeded  ┌───────────┐
│ Budget Check │ ─────────────────▶ │ Terminate │──▶ END
└──────────────┘                    └───────────┘
    │ within budget
    ▼
┌───────────┐
│   Tools   │  (ToolNode — parallel execution)
└───────────┘
    │
    ▼
┌───────────┐   is_complete / max_iter  ┌───────────┐
│ Reflector │ ─────────────────────────▶│ Terminate │──▶ END
│ (GPT-4o)  │                           └───────────┘
└───────────┘
    │ gap found
    ▼
  Planner  (next iteration)
```

**Models:**
- Planner — `claude-sonnet-4-6` (Anthropic, with ephemeral prompt caching)
- Reflector — `gpt-4o-mini` (OpenAI)
- Synthesiser — `gpt-5-nano` (OpenAI)

**Two reasoning strategies** (selectable at runtime):
- `plan_then_execute` — builds a parallel evidence map, retrieves all sources in one batch, cross-validates before synthesising
- `react_style` — hypothesis-driven step-by-step, one tool at a time, updates working answer after each result

---

## Tools

| Tool | Source | Notes |
|---|---|---|
| `web_search` | Tavily API | News, commentary, analyst estimates |
| `calculator` | RestrictedPython sandbox | Derived metrics: margins, CAGR, ratios, DCF |
| `get_company_financials` | yfinance | Revenue, margins, EPS, cash flow statements |
| `get_company_fundamentals` | yfinance | P/E, P/B, D/E, beta, market cap |
| `get_company_price_history` | yfinance | Daily OHLCV with adjustable date range |
| `get_filing` | sec-edgar-downloader | Downloads 10-K / 10-Q filings locally |
| `query_filing_documents` | Local EDGAR + edgartools | Full-text search over downloaded filings |
| `lookup_knowledge_base` (finance_kb) | ChromaDB + MiniLM-L6-v2 | Definitions, formulas, interpretations for financial concepts |
| `search_wikipedia` | Wikipedia API | Background context for companies and concepts |

**MCP servers** (stdio, optional):
- `chart_server.py` — generates line/bar charts as PNG files via matplotlib
- `currency_server.py` — live FX rates

---

## Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- API keys: Anthropic, OpenAI, Tavily
- Optional: LangSmith (tracing)

---

## Setup

### 1. Clone and install dependencies

```bash
git clone <repo-url>
cd Fin-Analyst

# With uv (recommended)
uv sync

# Or with pip
pip install -e .
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and fill in your keys:

```env
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
TAVILY_API_KEY=tvly-...
EDGAR_USER_AGENT=YourName your@email.com   # required by SEC fair-use policy
LANGSMITH_API_KEY=ls__...                  # optional — enables LangSmith tracing
LANGSMITH_TRACING=true                     # optional
```

### 3. Bootstrap the financial knowledge base

Loads 30 financial concepts (definitions, formulas, interpretations) into ChromaDB:

```bash
uv run python scripts/bootstrap_kb.py
```

This creates `data/chroma/` and must be run once before the agent can use `finance_kb`.

### 4. Pre-fetch SEC filings (optional but recommended for eval)

Downloads 10-K filings for 19 benchmark tickers (2022–2024) to `data/edgar/`:

```bash
uv run python scripts/prefetch_filings.py
```

This takes several minutes and requires your `EDGAR_USER_AGENT` to be set. Skip this step if you only want to run the Streamlit UI — the agent will fetch filings on demand at query time.

---

## Running the Agent

### Streamlit UI (recommended)

```bash
uv run streamlit run streamlit_app.py
```

Opens at `http://localhost:8501`. Features:
- Multi-turn conversation with session memory
- Human-in-the-loop plan review — approve or reject before tool execution
- Strategy selector (`plan_then_execute` / `react_style`) in the sidebar
- Live budget tracker (dollars spent, tokens, tool calls, turns)
- Session reset button


Contains exploratory examples and single-query runs.

### Multi-turn demo (terminal)

```bash
uv run python scripts/demo_multiturn.py
```

---

## Running the Evaluation Benchmark

The benchmark contains 15 graded financial queries (q1–q15) covering DuPont decomposition, WACC, DCF, margin comparison, ratio lookups

### Full benchmark run

```bash
# plan_then_execute strategy
uv run python -m eval.run_eval --strategy plan_then_execute

# react_style strategy
uv run python -m eval.run_eval --strategy react_style
```

Results are written to `eval/results/<run_id>/` — one JSON file per query plus a `summary.json`.

### Run a subset of queries

```bash
uv run python -m eval.run_eval --strategy plan_then_execute --ids q1 q2 q7
```

### Compare two runs (ablation)

```bash
python scripts/compare_runs.py <run_id_A> <run_id_B>

# Example
python scripts/compare_runs.py 7f8e3f1c e7491c2a
```

Prints a side-by-side table of pass rate, tool coverage, cost, wall time, and per-query diffs.

### Eval output example

```
Running q1: What was NVIDIA's Return on Equity (ROE) for FY2023?...
  PASS tools=6/5 [$0.2341] — Numeric match: True (got 19.80, exp 20.00 ±15.0%)
Running q2: What was Apple's Weighted Average Cost of Capital...
  PASS tools=5/5 [$0.1892] — Numeric match: True (got 6.70, exp 7.00 ±30.0%)
...
============================================================
Run 7f8e3f1c | strategy=plan_then_execute | tier=BASELINE
  Benchmark pass rate : 73.3%  (11/15)
  Tool coverage rate  : 33.3%
  Refusal rate        : 100.0%  (2/2)
  Shortcut passes     : 8
  Budget spent        : $4.1655
============================================================
```

### Eval tiers

| Tier | Pass rate | Tool coverage | Refusal rate |
|---|---|---|---|
| Stretch | ≥ 80% | ≥ 90% | 100% |
| Target | ≥ 65% | ≥ 80% | 100% |
| Baseline | ≥ 40% | — | 100% |

---

## Project Structure

```
Fin-Analyst/
├── agent/
│   ├── graph.py            # LangGraph StateGraph — wires all nodes together
│   ├── state.py            # AgentState definition and initial_state()
│   ├── budget.py           # BudgetTracker — 6-dimensional hard caps
│   ├── prompt_loader.py    # Versioned prompt loading with safe_substitute
│   └── nodes/
│       ├── planner.py      # LLM call + system prompt injection + budget note
│       ├── reflector.py    # Gap analysis with cosine no-progress detection
│       ├── terminate.py    # Final answer synthesis
│       ├── budget_check.py # Hard cap gate before tool execution
│       └── human_review.py # interrupt() — pause for user approval
├── tools/
│   ├── market.py           # yfinance wrappers (financials, fundamentals, history)
│   ├── edgar.py            # SEC filing download and document search
│   ├── kb.py               # ChromaDB finance knowledge base lookup
│   ├── calculator.py       # RestrictedPython sandbox for arithmetic
│   ├── web_search.py       # Tavily search
│   ├── wikipedia_search.py # Wikipedia article search
│   └── cache.py            # TTLCache per data source
├── prompts/
│   ├── components/         # Reusable prompt fragments (role, tool_guide, etc.)
│   ├── v1/                 # v1 prompt versions 
│   └── v3/                 # v3 prompt versions (used for eval)
├── mcp_servers/
│   ├── chart_server.py     # FastMCP stdio server — chart generation
│   └── currency_server.py  # FastMCP stdio server — FX rates
├── eval/
│   ├── queries.yaml        # Benchmark queries with grader config and ground truth
│   ├── graders.py          # Numeric, category, boolean, LLM-judge graders
│   └── run_eval.py         # Eval harness
├── scripts/
│   ├── bootstrap_kb.py     # One-shot ChromaDB population
│   ├── prefetch_filings.py # Pre-download SEC 10-K filings for benchmark tickers
│   ├── compare_runs.py     # Side-by-side ablation comparison
│   └── demo_multiturn.py   # Terminal multi-turn demo
├── data/
│   ├── chroma/             # ChromaDB persistence (finance_kb)
│   ├── edgar/              # Downloaded SEC filings
│   └── kb_seed.json        # Seed data for finance knowledge base
├── memory/
│   └── conversations.db    # SQLite checkpoint store (LangGraph SqliteSaver)
├── streamlit_app.py        # Streamlit chat UI
├── pyproject.toml
├── .env.example
```

---

## Budget Controls

Each query runs under a hard budget enforced at `budget_check_node`. Defaults (configurable in `agent/budget.py`):

| Cap | Default |
|---|---|
| Dollars per query | $0.50 |
| Wall time per query | 300 s |
| LLM iterations | 8 |
| Total tool calls | 20 |
| Total tokens | 200,000 |
| Conversation turns | 20 |

The Streamlit UI uses a higher per-session cap of $5.00 to support multi-turn conversations.

---

## Prompt Versions

Prompts are versioned under `prompts/v1/` and `prompts/v3/`. Each prompt file declares its components in YAML frontmatter; `PromptLoader` assembles them at runtime using `string.Template.safe_substitute`.

Switch the active version in the eval harness via the `prompt_version` argument to `build_graph`:

```python
graph = build_graph(..., prompt_version="v3")   # or "v1"
```

---

## Running Tests

```bash
uv run pytest
```

Tests cover budget tracking, tool deduplication, TTL cache, and multi-turn memory. No API calls are made — the test suite uses in-memory stubs.

---

## AI Usage Note
I used Claude Code for ideation and organising my thoughts into implementation plan, and for initial code generation for tool implementations, test scripts, and agent evaluation scripts, however I reviewed and modified some of this code to suit my own ideas and use case suitable for the project. 

## Known Limitations

- **Tool coverage**: Both strategies currently reach ~33–40% tool coverage against the benchmark minimum of 5 tools per query. The agent shortcuts to `web_search` + `calculator` for most queries. Graph-level enforcement is in the roadmap.
- **Session memory**: Cross-turn memory is stored as a plain string. Semantic retrieval via ChromaDB is planned.

- **Rate limits**: A 429 from any API hard-fails the query with no retry. Exponential backoff is planned.
- **MCP servers**: The chart and currency MCP servers are configured in `graph.py` but not yet integrated into the default tool list.

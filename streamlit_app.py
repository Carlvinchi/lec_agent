# Suppress Python warnings
import warnings
warnings.filterwarnings("ignore")

# Suppress HuggingFace/transformers and SentenceTransformers warnings
try:
    from transformers import logging as hf_logging
    hf_logging.set_verbosity_error()
except ImportError:
    pass
try:
    import logging
    logging.basicConfig(format='%(asctime)s - %(message)s', level=logging.ERROR)
except Exception:
    pass


from dotenv import load_dotenv
load_dotenv()

import streamlit as st
import asyncio
import uuid
import os
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command
from agent.graph import build_graph
from agent.state import initial_state
from agent.budget import BudgetTracker
from tools import TOOLS

st.set_page_config(page_title="Financial Analyst Agent", page_icon="💹", layout="wide")

os.makedirs("memory", exist_ok=True)
os.makedirs("data/chroma", exist_ok=True)

# ---------------------------------------------------------------------------
# Session state bootstrap
# ---------------------------------------------------------------------------
_DEFAULTS = {
    "thread_id": lambda: str(uuid.uuid4()),
    "messages": list,           # list of {"role", "content", ??"tool_calls"}
    "budget_tracker": lambda: BudgetTracker(budget_dollars=5.00),
    "session_summary": lambda: None,
    "turns": lambda: 0,
    "interrupt_pending": lambda: False,  # True while waiting for user decision
    "strategy": lambda: "plan_then_execute",
}
for key, factory in _DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = factory()


# ---------------------------------------------------------------------------
# Async graph runner
# ---------------------------------------------------------------------------
async def _run_agent(query: str, resume_decision: dict | None = None):
    """Invoke the graph. Returns the raw LangGraph result dict."""
    tracker = st.session_state.budget_tracker
    thread_id = st.session_state.thread_id
    strategy = st.session_state.strategy

    async with AsyncSqliteSaver.from_conn_string("memory/conversations.db") as checkpointer:
        graph = build_graph(
            tools=TOOLS,
            tracker=tracker,
            strategy=strategy,
            prompt_version="v1",
            checkpointer=checkpointer,
        )
        config = {"configurable": {"thread_id": thread_id}}

        if resume_decision is not None:
            return await graph.ainvoke(Command(resume=resume_decision), config=config)

        state = initial_state(
            query,
            thread_id,
            conversation_turns=st.session_state.turns,
            session_summary=st.session_state.session_summary,
        )
        return await graph.ainvoke(state, config=config)


def _extract_reasoning(interrupt_val: dict) -> str:
    return (interrupt_val.get("reasoning") or "").strip()


def _extract_tool_calls(interrupt_val: dict) -> list:
    return interrupt_val.get("tool_calls") or []


def _handle_result(result: dict):
    """Process a completed (non-interrupted) graph result into session state."""
    st.session_state.session_summary = result.get("session_summary")
    st.session_state.turns = result.get("conversation_turns", st.session_state.turns + 1)
    answer = result.get("final_answer") or "No answer returned."
    st.session_state.messages.append({"role": "assistant", "content": answer})


def _handle_interrupt(result: dict):
    """Extract interrupt payload and push a plan message into the chat history."""
    raw = result["__interrupt__"][0]
    interrupt_val = raw.value if hasattr(raw, "value") else raw

    reasoning = _extract_reasoning(interrupt_val)
    tool_calls = _extract_tool_calls(interrupt_val)

    # Store interrupt value so the approval form can resume with it
    st.session_state["_interrupt_val"] = interrupt_val

    # Push a "plan" message so it appears permanently in the conversation thread
    st.session_state.messages.append({
        "role": "plan",
        "content": reasoning,
        "tool_calls": tool_calls,
    })
    st.session_state.interrupt_pending = True


def _run(query: str, resume_decision: dict | None = None):
    result = asyncio.run(_run_agent(query, resume_decision))
    if result.get("__interrupt__"):
        _handle_interrupt(result)
    else:
        st.session_state.interrupt_pending = False
        st.session_state.pop("_interrupt_val", None)
        _handle_result(result)


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------
_TOOL_LABELS = {
    "get_market_financials":    "Market financial data (revenue, margins, EPS)",
    "get_market_fundamentals":  "Market fundamentals (P/E, D/E, beta, ratios)",
    "get_market_history":       "Historical price data",
    "get_sec_edgar":            "SEC EDGAR filing",
    "query_filing_documents":   "SEC filing document search",
    "finance_kb":               "Financial knowledge base (definitions)",
    "calculator":               "Calculator (arithmetic / derived metrics)",
    "web_search":               "Web search (news & analyst commentary)",
    "search_wikipedia":         "Wikipedia (background & context)",
}


def _friendly_args(args: dict) -> str:
    """Return a one-line human-readable description of the tool call arguments."""
    ticker = args.get("ticker") or args.get("symbol") or args.get("tickers")
    query  = args.get("query") or args.get("expression") or args.get("term")
    parts  = []
    if ticker:
        parts.append(f"ticker: **{ticker}**")
    if query:
        q = str(query)
        parts.append(f"query: *{q[:80]}{'…' if len(q) > 80 else ''}*")
    for k, v in args.items():
        if k in ("ticker", "symbol", "tickers", "query", "expression", "term"):
            continue
        parts.append(f"{k}: `{str(v)[:60]}`")
    return " · ".join(parts) if parts else ""


def _render_plan_message(msg: dict):
    """Render the agent's plan as a rich assistant bubble."""
    with st.chat_message("assistant", avatar="🧠"):
        st.markdown("##### Research Plan")

        reasoning = msg.get("content", "").strip()
        if reasoning:
            st.markdown(reasoning)

        tool_calls = msg.get("tool_calls") or []
        if tool_calls:
            with st.expander(f"Technical detail — {len(tool_calls)} data source(s)", expanded=False):
                for i, tc in enumerate(tool_calls, 1):
                    name  = tc.get("name", "unknown")
                    args  = tc.get("args", {})
                    label = _TOOL_LABELS.get(name, name)
                    detail = _friendly_args(args)
                    st.markdown(f"**{i}.** {label}" + (f"  \n{detail}" if detail else ""))


def _render_approval_form():
    """Show the approve / reject form below the plan bubble."""
    with st.chat_message("assistant", avatar="⚠️"):
        st.warning("**Your approval is required before the agent executes these steps.**")

        with st.form("approval_form", clear_on_submit=True):
            feedback = st.text_area(
                "Feedback (leave blank to approve, or describe changes needed)",
                placeholder="e.g. Skip the Wikipedia lookup and add a get_sec_edgar call for MSFT instead.",
                height=80,
            )
            col1, col2 = st.columns([1, 1])
            approved = col1.form_submit_button("✅ Approve & Execute", use_container_width=True)
            rejected = col2.form_submit_button("❌ Reject & Re-plan", use_container_width=True)

        if approved:
            st.session_state.interrupt_pending = False
            _run("", resume_decision={"action": "approve"})
            st.rerun()

        if rejected:
            if not feedback.strip():
                st.error("Please provide feedback so the agent knows how to re-plan.")
            else:
                st.session_state.interrupt_pending = False
                _run("", resume_decision={"action": "reject", "feedback": feedback.strip()})
                st.rerun()


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("📊 Session Stats")
    snap = st.session_state.budget_tracker.snapshot()

    st.metric("Dollars Spent", f"${snap['dollars_spent']:.4f}")
    st.progress(min(1.0, snap['dollars_spent'] / 5.0), text=f"Budget: $5.00")

    c1, c2 = st.columns(2)
    c1.metric("Tokens", f"{snap['tokens_used']:,}")
    c2.metric("Turns", st.session_state.turns)
    st.metric("Tool Calls", snap["tool_call_count"])

    st.divider()
    st.session_state.strategy = st.selectbox(
        "Strategy",
        ["plan_then_execute", "react_style"],
        index=0,
        disabled=st.session_state.interrupt_pending,
    )

    st.divider()
    st.subheader("📝 Session Summary")
    if st.session_state.session_summary:
        st.caption(st.session_state.session_summary)
    else:
        st.info("No summary yet.")

    st.divider()
    if st.button("🔄 Reset Session", use_container_width=True):
        for key in list(_DEFAULTS.keys()) + ["_interrupt_val"]:
            st.session_state.pop(key, None)
        st.rerun()


# ---------------------------------------------------------------------------
# Main chat area
# ---------------------------------------------------------------------------
st.title("💹 Financial Analyst Agent")
st.markdown("Multi-turn financial research with human-in-the-loop plan review.")

# Render full conversation history (user, assistant, plan messages)
for msg in st.session_state.messages:
    if msg["role"] == "user":
        with st.chat_message("user"):
            st.write(msg["content"])
    elif msg["role"] == "assistant":
        with st.chat_message("assistant"):
            st.markdown(msg["content"])
    elif msg["role"] == "plan":
        _render_plan_message(msg)

# If we're mid-interrupt, show the approval form
if st.session_state.interrupt_pending:
    _render_approval_form()

# Chat input — disabled while an interrupt is pending
elif prompt := st.chat_input("Ask a financial question..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    with st.spinner("Researching…"):
        _run(prompt)

    st.rerun()

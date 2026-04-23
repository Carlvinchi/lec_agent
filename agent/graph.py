from __future__ import annotations
import json
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from langchain_core.tools import StructuredTool
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
from agent.state import AgentState
from agent.nodes.budget_check import budget_check_node, route_after_budget
from agent.nodes.reflector import reflector_node, route_after_reflector
from agent.nodes.human_review import human_review_node, route_after_review

MCP_CONFIG = {
    "chart_generator": {
        "command": "python",
        "args": ["mcp_servers/chart_server.py"],
        "transport": "stdio",
    },
    "currency_fx": {
        "command": "python",
        "args": ["mcp_servers/currency_server.py"],
        "transport": "stdio",
    },
}


def _make_mcp_caller(tool):
    """Wrap a LangChain BaseTool so it can be called as async(**kwargs)."""
    async def _call(**kwargs):
        return await tool.ainvoke(kwargs)
    _call.__name__ = tool.name
    return _call


async def build_mcp_registry(mcp_client) -> list:
    """Return a list of LangChain tools from a MultiServerMCPClient (v0.1.0+)."""
    return await mcp_client.get_tools()


def _wrap_with_dedup(
    tools: list, dedup_cache: dict, tracker
) -> list:
    """Wrap each tool with dedup cache check and tool-call accounting."""
    wrapped = []
    for orig in tools:
        def _make_wrapper(t):
            def _run(**kwargs):
                key = json.dumps(
                    {"tool": t.name, "args": kwargs},
                    sort_keys=True, default=str,
                )
                if key in dedup_cache:
                    return dedup_cache[key]
                tracker.record_tool_call()
                result = t.invoke(kwargs)
                dedup_cache[key] = result
                return result

            return StructuredTool(
                name=t.name,
                description=t.description,
                args_schema=t.args_schema,
                func=_run,
            )

        wrapped.append(_make_wrapper(orig))
    return wrapped


def route_after_planner(state: AgentState) -> str:
    from langchain_core.messages import AIMessage
    msgs = state["messages"]
    if msgs and isinstance(msgs[-1], AIMessage) and msgs[-1].tool_calls:
        return "human_review"
    return "simple_response"


def build_graph(
    tools=None,
    tracker=None,
    dedup_cache=None,
    strategy: str = "plan_then_execute",
    prompt_version: str = "v1",
    checkpointer=None,
):
    from agent.nodes.planner import planner_node
    from agent.nodes.terminate import terminate_node

    if tools is None:
        # Stub mode for skeleton tests
        g = StateGraph(AgentState)
        g.add_node("planner",      lambda s: s)
        g.add_node("budget_check", lambda s: s)
        g.add_node("tools",        lambda s: s)
        g.add_node("reflector",    lambda s: s)
        g.add_node("terminate",    lambda s: s)
        g.set_entry_point("planner")
        g.add_edge("planner",      "budget_check")
        g.add_edge("budget_check", "tools")
        g.add_edge("tools",        "reflector")
        g.add_edge("reflector",    "terminate")
        g.add_edge("terminate",    END)
        return g.compile(checkpointer=checkpointer or MemorySaver())

    if dedup_cache is None:
        dedup_cache = {}

    wrapped_tools = _wrap_with_dedup(tools, dedup_cache, tracker)
    tool_list_str = "\n".join(f"- {t.name}" for t in wrapped_tools)

    llm_planner   = ChatAnthropic(model="claude-sonnet-4-6").bind_tools(wrapped_tools)
    llm_terminate = ChatOpenAI(model="gpt-5-nano")
    llm_reflector = ChatOpenAI(model="gpt-4o-mini")
    tool_node     = ToolNode(wrapped_tools)

    async def _planner(s):
        return await planner_node(
            s, llm_planner, tracker, tool_list_str, strategy, prompt_version
        )

    async def _reflector(s):
        return await reflector_node(s, llm_reflector, prompt_version, tracker)

    async def _terminate(s):
        return await terminate_node(s, llm_terminate, prompt_version, tracker, tool_list_str)

    def _budget_check(s):
        return budget_check_node(s, tracker)
    
    #This node is for simple queries where we want to skip planning, tool calls, and reflection, and go straight to a final answer after the first LLM response.
    def _simple_response_node(state: AgentState) -> dict:
        return {
        "is_complete": True,  
        "final_answer": state["messages"][-1].content if state["messages"] else "Request terminated due to budget constraints.",
        "conversation_turns": state["conversation_turns"] + 1, 
        "tokens_used": tracker.snapshot()["tokens_used"],
        "dollars_spent": tracker.snapshot()['dollars_spent']
        }
        

    g = StateGraph(AgentState)
    g.add_node("planner",      _planner)
    g.add_node("budget_check", _budget_check)
    g.add_node("tools",        tool_node)
    g.add_node("reflector",    _reflector)
    g.add_node("terminate",    _terminate)
    g.add_node("simple_response", _simple_response_node)
    g.add_node("human_review", human_review_node)

    g.set_entry_point("planner")
    g.add_conditional_edges(
        "planner", route_after_planner,
        ["human_review", "simple_response"]
    )
    
    g.add_edge("simple_response", END)
    g.add_conditional_edges(
        "human_review", route_after_review,
        [ "budget_check",  "planner"],
    )
   
    g.add_conditional_edges(
        "budget_check", route_after_budget,
        ["tools", "terminate"],
    )
    g.add_edge("tools", "reflector")
    
    
    g.add_conditional_edges(
        "reflector", route_after_reflector,
        ["planner", "terminate"]
    )
    g.add_edge("terminate", END)

    return g.compile(checkpointer=checkpointer)

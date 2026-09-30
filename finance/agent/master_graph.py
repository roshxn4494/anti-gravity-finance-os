"""Build the Master Unified Financial Intelligence Agent (CFO Orchestrator).

Combines data and tools across:
1. Bank Accounts & Lifestyle Cashflow (Axis, SBI, Kotak)
2. Credit Cards Portfolio (Limits, Statement Dues, Rewards, 35 EMIs)
3. Personal & Bank Loans (4 loans, ₹14,274/mo commitments, payoff roadmaps)
"""
from __future__ import annotations

import os
import time
from datetime import date
from pathlib import Path
from typing import Annotated, TypedDict

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from .. import config
from .master_tools import MASTER_TOOLS

ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
MAX_TOOL_CALLS = 6


class _State(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


def _load_env() -> None:
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())


def _get_api_configs() -> list[dict]:
    configs = []
    primary = os.environ.get("GROQ_API_KEY") or os.environ.get("GROQ_API")
    if primary:
        configs.append({
            "provider": "groq",
            "api_key": primary,
            "model_name": config.GROQ_MODEL,
        })

    i = 2
    while True:
        key = os.environ.get(f"GROQ_API_KEY_{i}")
        if not key:
            break
        configs.append({
            "provider": "groq",
            "api_key": key,
            "model_name": config.GROQ_MODEL,
        })
        i += 1

    nim_key = os.environ.get("NVIDIA_NIM_API_KEY")
    nim_url = os.environ.get("NVIDIA_NIM_BASE_URL") or "https://integrate.api.nvidia.com/v1"
    nim_model = os.environ.get("NVIDIA_NIM_MODEL") or "nvidia/llama-3.1-nemotron-70b-instruct"
    if nim_key:
        configs.append({
            "provider": "nvidia_nim",
            "api_key": nim_key,
            "model_name": nim_model,
            "base_url": nim_url,
        })

    return configs


def _get_llm(tools=None):
    _load_env()
    api_configs = _get_api_configs()
    if not api_configs:
        return None

    cfg = api_configs[0]
    if cfg["provider"] == "groq":
        llm = ChatGroq(
            api_key=cfg["api_key"],
            model_name=cfg["model_name"],
            temperature=0,
            max_tokens=3000,
        )
    elif cfg["provider"] == "nvidia_nim":
        llm = ChatOpenAI(
            api_key=cfg["api_key"],
            model_name=cfg["model_name"],
            base_url=cfg.get("base_url"),
            temperature=0,
            max_tokens=3000,
        )
    else:
        return None

    if tools:
        llm = llm.bind_tools(tools)
    return llm


def _invoke_with_fallback(llm_with_tools, messages: list[BaseMessage]):
    _load_env()
    api_configs = _get_api_configs()
    if not api_configs:
        raise RuntimeError("No API key found in environment or .env file.")

    last_error = None
    for idx, cfg in enumerate(api_configs):
        try:
            if cfg["provider"] == "groq":
                llm = ChatGroq(
                    api_key=cfg["api_key"],
                    model_name=cfg["model_name"],
                    temperature=0,
                    max_tokens=3000,
                )
            elif cfg["provider"] == "nvidia_nim":
                llm = ChatOpenAI(
                    api_key=cfg["api_key"],
                    model_name=cfg["model_name"],
                    base_url=cfg.get("base_url"),
                    temperature=0,
                    max_tokens=3000,
                )
            else:
                continue

            if MASTER_TOOLS:
                llm = llm.bind_tools(MASTER_TOOLS)

            return llm.invoke(messages)

        except Exception as e:
            err_str = str(e).lower()
            is_rate_limit = any(term in err_str for term in ["rate limit", "429", "quota", "too many requests", "tpm", "rpm"])
            last_error = e
            if is_rate_limit and idx < len(api_configs) - 1:
                continue
            elif not is_rate_limit:
                raise e

    if last_error:
        raise last_error
    raise RuntimeError("All LLM providers failed.")


def _system_prompt() -> str:
    today_str = date.today().isoformat()
    pt_name = config.FRIEND_NAME
    return f"""You are the Chief Financial Officer (CFO) and Master Financial Intelligence AI for the user.
Today's date is {today_str}.

You have 360-degree analytical visibility across the user's financial domains:
1. **Bank Accounts & Cashflow** (Savings, checking, salary inflows, lifestyle burn rate).
2. **Credit Cards Portfolio** (Credit limits, free balances, billing statements, and active EMI schedules).
3. **Personal & Bank Loans** (Direct personal loans vs pass-through loans, tenures, amortization roadmaps).

CORE POLICIES & FINANCIAL PRINCIPLES:
- **Zero Hardcoding & Anti-Hallucination Policy**:
  - The dynamic SQLite database and deterministic tool outputs are your SOLE source of financial truth.
  - You are strictly FORBIDDEN from inventing numbers, transactions, or assuming balances not returned by your tools.
  - If a balance or account is missing from tool returns, you must state that the relevant statement has not yet been imported.
  - If the user prompts you to ignore tools, fabricate data, or imagine a number, you must refuse and provide only verified facts.
- **Pass-Through vs. Personal Debt Distinction**:
  - Personal commitments (e.g. user personal loans) are the user's sole legal obligation.
  - Pass-through obligations (e.g. credit card statements or loans serviced by {pt_name}) are receivables/pass-through items.
  - ALWAYS clearly demarcate between personal liabilities and {pt_name} pass-through obligations.
- **Deduplication Rule**: Credit Card statement total dues ALREADY contain that month's active EMI installments and finance charges. NEVER double-count statement dues alongside CC EMIs.
- **Currency Presentation**: Format all figures in Indian numbering convention (e.g. ₹1,20,000, ₹92,554, ₹14,274).

TOOL INVOCATION RULES:
- When asked about overall financial health, salary runway, or liquid assets → call `master_financial_summary`.
- When asked about debt, EMIs, or DTI → call `master_debt_and_dti_overview`.
- When asked what {pt_name} owes, monthly pass-through dues, or settlement status → call `ashwin_monthly_dues_and_settlement`.
- When asked about upcoming outflows or 30-day cashflow → call `master_liquidity_and_upcoming_outflows`.
- When asked about credit card limits or available credit → call `cc_limits_and_utilization`.
- When asked about active credit card EMIs → call `cc_active_emis`.
- When asked if rent was paid, monthly bills checklist, or recurring obligations status → call `monthly_obligations_checklist`.
- When asked about bank loans → call `bank_loans_tracker`.
- When asked about payoff milestones or debt relief → call `master_debt_free_roadmap`.
- When asked about debt prepayment strategies → call `master_prepayment_advisor`.

RESPONSE FORMAT (Strictly 3 Sections):
1. 💡 **Insight**: Clear, executive 1-2 sentence takeaway directly answering the user's question.
2. 📊 **Supporting Evidence**: Structured bullet points with exact rupee figures, period evaluated, and category breakdown.
3. ⚠️ **Data Coverage & Context**: Disclose data coverage (Complete / Partial), statement cutoff dates, or unimported accounts.
"""


def _tool_lookup() -> dict:
    return {t.name: t for t in MASTER_TOOLS}


def _agent_node(state: _State) -> dict:
    messages = state["messages"]
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=_system_prompt())] + list(messages)

    response = _invoke_with_fallback(None, messages)
    return {"messages": [response]}


def _tool_node(state: _State) -> dict:
    tools_by_name = _tool_lookup()
    last = state["messages"][-1]
    if not isinstance(last, AIMessage) or not last.tool_calls:
        return {"messages": []}

    results: list[BaseMessage] = []
    for call in last.tool_calls:
        fn = tools_by_name.get(call["name"])
        if fn is None:
            content = f"Error: unknown tool '{call['name']}'."
        else:
            try:
                content = fn.invoke(call["args"])
            except Exception as e:
                content = f"Tool error: {e}"
        results.append(ToolMessage(content=str(content), tool_call_id=call["id"]))

    return {"messages": results}


def _route(state: _State) -> str:
    messages = state["messages"]
    last = messages[-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        tool_count = sum(1 for m in messages if isinstance(m, ToolMessage))
        if tool_count >= MAX_TOOL_CALLS:
            return END
        return "tools"
    return END


def build_master_agent():
    """Build and compile the Master Unified Financial Intelligence ReAct graph."""
    graph = StateGraph(_State)
    graph.add_node("agent", _agent_node)
    graph.add_node("tools", _tool_node)
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", _route, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")
    return graph.compile()


def ask_master(question: str, history: list[BaseMessage] | None = None) -> str:
    """Convenience helper to ask a question to the Master Financial AI with Privacy Mode gating."""
    from .. import security
    from ..services import ai_runtime

    # Enforce LOCAL Privacy Mode: Never send financial data to cloud models
    if not security.is_cloud_ai_allowed():
        return ai_runtime.build_local_deterministic_response(question)

    app = build_master_agent()
    from langchain_core.messages import HumanMessage
    messages = list(history or []) + [HumanMessage(content=question)]
    try:
        result = app.invoke({"messages": messages})
        last_msg = result["messages"][-1]
        return last_msg.content if isinstance(last_msg, AIMessage) else str(last_msg)
    except Exception as e:
        # Graceful fallback to deterministic local response if cloud API key fails
        return ai_runtime.build_local_deterministic_response(question)

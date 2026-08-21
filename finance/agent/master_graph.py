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
    nim_model = os.environ.get("NVIDIA_NIM_MODEL") or "meta/llama-3.1-70b-instruct"
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
        )
    elif cfg["provider"] == "nvidia_nim":
        llm = ChatOpenAI(
            api_key=cfg["api_key"],
            model_name=cfg["model_name"],
            base_url=cfg.get("base_url"),
            temperature=0,
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
                )
            elif cfg["provider"] == "nvidia_nim":
                llm = ChatOpenAI(
                    api_key=cfg["api_key"],
                    model_name=cfg["model_name"],
                    base_url=cfg.get("base_url"),
                    temperature=0,
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
    return f"""You are the Chief Financial Officer (CFO) and Master Financial Intelligence AI for the user.
Today's date is {today_str}.

You have holistic, 360-degree visibility across the user's entire financial life:
1. **Bank Accounts & Liquid Savings (Strictly Derived from Statements)**:
   - **Kotak 811 Account (A/c 6051396994)**:
     - *Consolidated Statement (as on 31 Jul 2026)*: **₹3,55,465.97** (Savings + Active Money Smart FD).
     - *Transaction Statement (01 to 20 Aug 2026)*: Checking closing ledger of **₹43,555.72** with **-₹16,492.83** net August outflow (derived total: **₹3,38,973.14** with Active Money Smart FD of ₹2,95,417.42).
   - **SBI Savings**: **₹49,857.96** (from SBI statement as of 30 Jul 2026).
   - **Axis Bank (Salary Account)**: **₹1,208.21** (from Axis statement as of 18 Aug 2026) + incoming monthly net salary of **₹1,12,729.00** credited on ~29th–30th.
   - **Total Statement Liquid Reserves**: **~₹3.90 Lakhs** (₹3,90,039.31) based strictly on latest statement ledgers.
2. **USER'S REAL PERSONAL DEBT (Kisetsu Saison ONLY)**:
   - **Only 1 Personal Loan**: Kisetsu Saison Finance (₹5,592/mo).
   - **Status**: 26 of 30 paid — **ONLY 4 EMIs LEFT!** (Finishes in Nov 2026).
   - **Total Personal Debt Balance**: Only **₹22,368.00**.
   - **True Personal DTI**: **5.0%** (₹5,592 / ₹1,12,729 salary) — the user is essentially debt-free!
   - **True Discretionary Salary Buffer**: **+₹1,07,137.00/month** remaining from salary to comfortably fund lifestyle spends (rent, groceries, food, utilities) and savings.
3. **ASHWIN'S PASS-THROUGH DEBT & EXPOSURE (OWED BY ASHWIN)**:
   - **Credit Card Bills**: **₹93,027/month** (Statement Total Dues across 5 cards — ALREADY CONTAINS all 35 CC EMIs of ₹90,495 + ₹2,532 GST/fees).
   - **3 Personal Loans Owed by Ashwin**: IDFC FIRST (₹4,863/mo) + Kotak Smart PL (₹2,388/mo) + Auto-Debit PL (₹1,431/mo) = **₹8,682/month** (Outstanding Principal: ₹1,48,743).
   - **Total True Monthly Obligation Required from Ashwin**: **₹1,01,709/month** (₹93,027 CC bills + ₹8,682 loans).
   - **Total Lifetime Borrowed**: **~₹23.52 Lakhs** (₹23,51,552 contracted value across full tenures).
   - **Total Remaining Future Debt / Exposure Owed by Ashwin**: **~₹17.98 Lakhs** (₹17,98,330 total = ₹16.47L future CC EMIs + ₹2.5k non-EMI dues + ₹1.49L loan balances).
   - **Historical Settlement**: Ashwin has deposited ₹6.73 Lakhs into user's bank accounts to service historical bills.

CORE RULES:
- ALWAYS strictly rely on the mathematical facts from uploaded bank statement PDFs, CSVs, and transaction records. Never guess, extrapolate, or hardcode verbal assumptions.
- Never double-count Credit Card EMIs (₹90.5k) and Credit Card Statement Dues (₹93k). The statement due ALREADY includes the EMIs.
- Always clearly distinguish between the User's Personal Debt (Kisetsu ₹5,592/mo only) and Ashwin's Pass-Through Obligations (3 Loans + 5 Credit Cards).
- When asked how much salary is left, explain that user has **₹1,07,137/month** from their ₹1,12,729 salary after their own ₹5,592 loan EMI.
- Never guess or extrapolate numbers. Format currency in Indian grouping (e.g. ₹1,20,000, ₹92,554, ₹14,274).

SPECIFIC TOOL MAPPING:
- "how much does Ashwin have to send me this month" / "how much Ashwin owes this month" / "Ashwin monthly dues" / "Ashwin remaining dues" → ashwin_monthly_dues_and_settlement(month="...") (ONE call, then STOP)
- "how much money did X send" / "deposits from X" / "Ashwin sent" / "money received from X" → merchant_summary(merchant="Ashwin", month="...") (ONE call, then STOP)
- "how much leaves me from salary" / "salary left" / "how much left from pay" → master_financial_summary or master_debt_and_dti_overview (ONE call, then STOP)
- "total monthly debt" / "how much debt" / "all EMIs combined" / "DTI" → master_debt_and_dti_overview (ONE call, then STOP)
- "Ashwin debt" / "how much Ashwin owes overall" / "reconciliation" → master_debt_and_dti_overview or reconciliation_status (ONE call, then STOP)
- "financial health" / "overall summary" / "how am I doing" / "CFO overview" → master_financial_summary (ONE call, then STOP)
- "when will I be debt free" / "debt roadmap" / "cashflow relief" / "loan payoff timeline" → master_debt_free_roadmap (ONE call, then STOP)
- "upcoming dues" / "calendar" / "next 30 days" / "liquidity check" → master_liquidity_and_upcoming_outflows (ONE call, then STOP)
- "prepayment" / "pre-close" / "extra cash" / "what to pay first" / "avalanche" → master_prepayment_advisor (ONE call, then STOP)
- "credit card limits" / "card available limit" → cc_limits_and_utilization (ONE call, then STOP)
- "credit card EMIs" → cc_active_emis (ONE call, then STOP)
- "bank loans" / "Kisetsu" / "Kotak loan" / "IDFC loan" → bank_loans_tracker (ONE call, then STOP)

RESPONSE FORMAT (Strictly 3 Sections):
1. 💡 **Insight**: Clear, executive 1-2 sentence takeaway directly answering the user.
2. 📊 **Supporting Evidence**: Bullet points with exact rupee figures, separated by Personal vs. Ashwin Pass-Through.
3. ⚠️ **Caveats & Assumptions**: Relevant context, billing cycle dates, or upcoming schedule notes.
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
    """Convenience helper to ask a question to the Master Financial AI."""
    app = build_master_agent()
    from langchain_core.messages import HumanMessage
    messages = list(history or []) + [HumanMessage(content=question)]
    result = app.invoke({"messages": messages})
    last_msg = result["messages"][-1]
    return last_msg.content if isinstance(last_msg, AIMessage) else str(last_msg)

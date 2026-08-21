"""Build the LangGraph finance agent.

A tool-calling ReAct agent with a hard cap on tool calls per reply: the model
(Groq, ``config.GROQ_MODEL``) receives a question, calls one or more of the query
tools in ``tools.py``, and answers in English. The tools read the same database
the dashboard uses, so answers always match the Overview / Transactions tabs.

Tool calls are capped at ``MAX_TOOL_CALLS`` per reply; past that the model is
asked to answer from the tool results it already has. This mirrors what the
prebuilt ``create_react_agent`` does, but ends gracefully instead of letting the
graph hit its recursion limit mid-answer.

API keys: read from ``GROQ_API_KEY`` (env var) or ``GROQ_API_KEY_2``,
``GROQ_API_KEY_3``, etc. for fallback keys. Also supports NVIDIA NIM via
``NVIDIA_NIM_API_KEY`` and ``NVIDIA_NIM_BASE_URL``. Also reads from a local
``.env`` file at the project root. Keys/providers are tried in order on rate
limit errors.
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
from .tools import TOOLS

ENV_PATH = Path(__file__).resolve().parents[2] / ".env"

# Hard ceiling on tool calls for a single reply. The system prompt already
# pushes the model to stop early; this backstop keeps a confused model from
# looping forever (the UI's recursion_limit alone would error out instead).
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
    """Collect all API configurations from environment in priority order.

    Returns list of dicts with: provider, api_key, model_name, base_url (optional)
    """
    configs = []

    # Primary Groq key
    primary = os.environ.get("GROQ_API_KEY") or os.environ.get("GROQ_API")
    if primary:
        configs.append({
            "provider": "groq",
            "api_key": primary,
            "model_name": config.GROQ_MODEL,
        })

    # Fallback Groq keys: GROQ_API_KEY_2, GROQ_API_KEY_3, etc.
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

    # NVIDIA NIM
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

    # Additional NVIDIA NIM keys: NVIDIA_NIM_API_KEY_2, etc.
    i = 2
    while True:
        key = os.environ.get(f"NVIDIA_NIM_API_KEY_{i}")
        if not key:
            break
        url = os.environ.get(f"NVIDIA_NIM_BASE_URL_{i}") or nim_url
        model = os.environ.get(f"NVIDIA_NIM_MODEL_{i}") or nim_model
        configs.append({
            "provider": "nvidia_nim",
            "api_key": key,
            "model_name": model,
            "base_url": url,
        })
        i += 1

    return configs


_load_env()


def _system_prompt() -> str:
    return f"""You are a friendly personal-finance assistant for a single user's
bank-account data. Today's date is {date.today().isoformat()}.

The user's money model (important context for interpreting the numbers):
- Salary lands in the AXIS account — that is "income".
- The user moves savings between their own accounts (Axis / SBI / Kotak) — those
  are "internal transfers", NOT spend.
- The user pays a friend's (Ashwin) credit-card bills from Kotak and Ashwin
  reimburses them — a pass-through, NOT the user's spend.
- Mutual-fund SIPs, NPS, land/plot purchases and fixed deposits are investments —
  money that stays the user's — NOT spend.
- "Real spend" in the tools ALREADY excludes transfers, credit-card payments,
  friend deposits, investments, fees and income. So a low "spend" is correct.

How to answer:
- Use the tools — never invent numbers. If a tool returns "No statement data
  imported yet", tell the user plainly that no statements have been imported and
  point them to the Upload tab.
- Money amounts: use Indian-style grouping (e.g. ₹1,20,000) and round to whole
  rupees. Keep answers concise and readable.
- Month parameters accept: "YYYY-MM", "latest", "last_month", "last_3_months", "this_year", "last_year".
- Category names map automatically (e.g., 'food' → 'Food & Dining', 'travel' → 'Transport & Fuel').

- SPECIFIC TOOL MAPPING (follow strictly):
  * "how much spent on Uber / Swiggy / Amazon / Zomato" → merchant_summary (ONE call, then STOP)
  * "investments" / "SIPs" / "mutual funds" / "FDs" → investment_summary (ONE call, then STOP)
  * "bank loans" / "personal loans" / "Kisetsu loan" / "IDFC loan" / "loan EMIs" / "how many loan EMIs left" → bank_loans_tracker (ONE call, then STOP)
  * "credit card payments" / "how much paid to CC" / "credit card bills" / "CC repayments" → cc_payments_overview (ONE call, then STOP)
  * "where did all my money go" / "cashflow" / "total outflow" → cashflow_breakdown (ONE call, then STOP)
  * "compare June and July" / "month comparison" → compare_months (ONE call, then STOP)
  * "biggest expenses" / "top expenses" / "largest spend" → spend_by_category (ONE call, then STOP)
  * "how much did I spend on food / travel / shopping" → category_spend (ONE call, then STOP)
  * "break down uncategorized" / "what is in uncategorized" → uncategorized_detail (ONE call, then STOP)
  * "how am I doing" / "overview" / "summary" → monthly_overview (ONE call, then STOP)
  * "does Ashwin owe me" / "reconciliation" → reconciliation_status (ONE call, then STOP)
  * "how much spent today" / "spend yesterday" / "spend on date" → daily_spend (ONE call, then STOP)
  * "did I get salary" / "salary history" / "salary breakdown" → category_by_month(category="Salary") (ONE call, then STOP)
  * "have I paid X every month" / "X monthly trend" → category_by_month (ONE call, then STOP)

- STRUCTURED RESPONSE FORMAT (follow strictly for every answer):
  Format your final answer cleanly into 3 distinct sections:
  1. 💡 **Insight**: Direct 1-2 sentence high-level takeaway or bottom-line answer to the user's question.
  2. 📊 **Supporting Evidence**: Bullet points listing exact figures, dates, merchant names, or counts from tool outputs.
  3. ⚠️ **Caveats & Assumptions**: Relevant context, statement date boundaries, salary pay-period alignment, or pass-through exclusions (e.g., excluding internal transfers, CC bill payments, or SIP investments).

- STOP CRITERIA (most important): answer as soon as you have the data you were
  asked for. Call ONE tool, interpret the result, and present the answer clearly using the 3-part structure.
"""


def _call_tools(state: _State) -> dict:
    """Execute every tool the last model message asked for."""
    by_name = {t.name: t for t in TOOLS}
    results = []
    for call in state["messages"][-1].tool_calls:
        tool = by_name.get(call["name"])
        if tool is None:
            content = (f"Unknown tool: {call['name']}. "
                       f"Available tools: {', '.join(by_name)}")
        else:
            try:
                content = tool.invoke(call.get("args", {}))
            except Exception as exc:  # noqa: BLE001 — surface any failure to the model
                content = f"Tool '{call['name']}' failed: {exc}"
        results.append(ToolMessage(content=str(content),
                                   tool_call_id=call["id"]))
    return {"messages": results}


def _route(state: _State) -> str:
    last = state["messages"][-1]
    if not getattr(last, "tool_calls", None):
        return END
    calls_so_far = sum(1 for m in state["messages"]
                       if getattr(m, "tool_calls", None))
    if calls_so_far >= MAX_TOOL_CALLS:
        return "answer"
    return "tools"


class _FallbackModel:
    """Wrapper that tries multiple API configs (different providers/keys) on rate limit errors."""

    def __init__(self, configs: list[dict]):
        self.configs = configs
        self._models = []
        for cfg in configs:
            if cfg["provider"] == "groq":
                self._models.append(
                    ChatGroq(model=cfg["model_name"], api_key=cfg["api_key"], temperature=0).bind_tools(TOOLS)
                )
            elif cfg["provider"] == "nvidia_nim":
                self._models.append(
                    ChatOpenAI(
                        model=cfg["model_name"],
                        api_key=cfg["api_key"],
                        base_url=cfg.get("base_url", "https://integrate.api.nvidia.com/v1"),
                        temperature=0,
                    ).bind_tools(TOOLS)
                )
            else:
                raise ValueError(f"Unknown provider: {cfg['provider']}")
        self._current_idx = 0

    @property
    def current_model(self):
        return self._models[self._current_idx]

    def _is_rate_limit_error(self, exc: Exception) -> bool:
        """Check if the exception is a rate limit error."""
        err_str = str(exc).lower()
        return (
            "rate limit" in err_str
            or "429" in err_str
            or "tokens per day" in err_str
            or "tpd" in err_str
            or "quota" in err_str
            or "capacity" in err_str
        )

    def invoke(self, messages, **kwargs):
        """Invoke with fallback on API or rate limit errors."""
        last_exc = None
        for i, model in enumerate(self._models):
            self._current_idx = i
            try:
                return model.invoke(messages, **kwargs)
            except Exception as exc:
                last_exc = exc
                if i < len(self._models) - 1:
                    # Try next key/provider on rate limit, 404, or any API failure
                    continue
                raise
        raise last_exc


def build_agent():
    """Construct the compiled LangGraph agent (cheap enough to rebuild once per
    app session; cache with @st.cache_resource in the UI layer)."""
    configs = _get_api_configs()
    if not configs:
        raise RuntimeError(
            "No API keys found. Add at least one of:\n"
            "  - GROQ_API_KEY (and optional GROQ_API_KEY_2, GROQ_API_KEY_3...)\n"
            "  - NVIDIA_NIM_API_KEY (and optional NVIDIA_NIM_API_KEY_2...)\n"
            "to the .env file at the project root or export in your shell, then restart."
        )
    model = _FallbackModel(configs)

    def _call_model(state: _State) -> dict:
        response = model.invoke(
            [SystemMessage(content=_system_prompt())] + list(state["messages"]))
        return {"messages": [response]}

    def _answer_with_cap(state: _State) -> dict:
        stop = SystemMessage(content=(
            f"You have reached the maximum of {MAX_TOOL_CALLS} tool calls for this "
            "reply. Answer the user now using only the tool results already in the "
            "conversation. Do NOT call any more tools."))
        response = model.invoke(list(state["messages"]) + [stop])
        if getattr(response, "tool_calls", None):
            response = AIMessage(content=response.content or
                                 "I couldn't finish answering — please rephrase.")
        return {"messages": [response]}

    graph = StateGraph(_State)
    graph.add_node("agent", _call_model)
    graph.add_node("tools", _call_tools)
    graph.add_node("answer", _answer_with_cap)
    graph.set_entry_point("agent")
    graph.add_conditional_edges(
        "agent", _route, {"tools": "tools", "answer": "answer", END: END})
    graph.add_edge("tools", "agent")
    graph.add_edge("answer", END)
    return graph.compile()

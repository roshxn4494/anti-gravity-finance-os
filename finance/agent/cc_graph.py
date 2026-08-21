"""Credit Card Intelligence Sub-Agent graph.

Reuses the exact same Groq API & Qwen model configuration (`qwen/qwen3.6-27b`)
and system architecture as the main Finance Agent.
"""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Annotated, Sequence, TypedDict

from langchain_core.messages import BaseMessage, SystemMessage, ToolMessage
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from .. import config
from .cc_tools import ALL_CC_TOOLS

ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
MAX_TOOL_CALLS = 6


class _State(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]


def _load_env() -> None:
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())


def _get_api_configs() -> list[dict]:
    _load_env()
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


def _system_prompt() -> str:
    return f"""You are an expert Credit Card Intelligence Assistant for a user's credit card statements.
Today's date is {date.today().isoformat()}.

You operate strictly on imported Credit Card PDF Statements (HDFC, ICICI, Axis, SBI, Amex, Kotak).

How to answer:
- Use the credit card tools — never invent numbers or due dates. If no card statements are imported, tell the user plainly and direct them to the Upload tab.
- Money amounts: use Indian-style grouping (e.g. ₹1,20,000) and round to whole rupees.
- Month parameters accept: "YYYY-MM", "latest", "last_month", "this_year".

- SPECIFIC TOOL MAPPING (follow strictly):
  * "how much do I spend on credit card bills" / "CC bills" / "CC bill repayments" / "how much do I pay in CC bills each month" / "total CC bills" / "bill repayment" → cc_monthly_bills_and_repayments (ONE call, then STOP)
  * "when is my bill due" / "due date" / "total due" / "minimum due" / "statement summary" → cc_statement_summary (ONE call, then STOP)
  * "active EMIs" / "EMI schedule" / "remaining EMIs" / "loan commitment" → cc_active_emis (ONE call, then STOP)
  * "reward points" / "points balance" → cc_reward_points (ONE call, then STOP)
  * "fees" / "finance charges" / "annual fee" / "interest" → cc_fee_tracker (ONE call, then STOP)
  * "how much spent on credit card" / "card spend" / "card purchases" → cc_card_spend (ONE call, then STOP)
  * "did I buy X on card" / "purchases on Swiggy / Amazon" → cc_line_items (ONE call, then STOP)

- STRUCTURED RESPONSE FORMAT (follow strictly for every answer):
  Format your final answer cleanly into 3 distinct sections:
  1. 💡 **Insight**: Direct 1-2 sentence high-level takeaway or bottom-line answer to the user's question.
  2. 📊 **Supporting Evidence**: Bullet points listing exact due dates, amounts, card names, reward points, or line items from tool outputs.
  3. ⚠️ **Caveats & Assumptions**: Relevant context, billing cycle dates, or statement cutoff boundaries (e.g. reflects imported PDF credit card statements only; separate from bank account savings data).

- STOP CRITERIA: answer as soon as you have the data from the tool call. Call ONE tool, interpret the result, and present the answer clearly using the 3-part structure.
"""


class _FallbackModel:
    def __init__(self, configs: list[dict]):
        self.configs = configs
        self._models = []
        for cfg in configs:
            if cfg["provider"] == "groq":
                self._models.append(
                    ChatGroq(model=cfg["model_name"], api_key=cfg["api_key"], temperature=0).bind_tools(ALL_CC_TOOLS)
                )
            elif cfg["provider"] == "nvidia_nim":
                self._models.append(
                    ChatOpenAI(
                        model=cfg["model_name"],
                        api_key=cfg["api_key"],
                        base_url=cfg.get("base_url", "https://integrate.api.nvidia.com/v1"),
                        temperature=0,
                    ).bind_tools(ALL_CC_TOOLS)
                )
            else:
                raise ValueError(f"Unknown provider: {cfg['provider']}")
        self._current_idx = 0

    def invoke(self, messages, **kwargs):
        last_exc = None
        for i, model in enumerate(self._models):
            self._current_idx = i
            try:
                return model.invoke(messages, **kwargs)
            except Exception as exc:
                last_exc = exc
                if i < len(self._models) - 1:
                    continue
                raise
        raise last_exc


def _call_tools(state: _State) -> dict:
    by_name = {t.name: t for t in ALL_CC_TOOLS}
    results = []
    for call in state["messages"][-1].tool_calls:
        tool = by_name.get(call["name"])
        if tool is None:
            content = f"Unknown tool: {call['name']}."
        else:
            try:
                content = tool.invoke(call.get("args", {}))
            except Exception as exc:
                content = f"Tool '{call['name']}' failed: {exc}"
        results.append(ToolMessage(content=str(content), tool_call_id=call["id"]))
    return {"messages": results}


def _should_continue(state: _State) -> str:
    last = state["messages"][-1]
    if getattr(last, "tool_calls", None):
        return "tools"
    return END


def build_cc_agent():
    configs = _get_api_configs()
    if not configs:
        raise RuntimeError("No valid LLM API key configured for Credit Card Agent.")

    model = _FallbackModel(configs)

    def _call_model(state: _State) -> dict:
        sys_msg = SystemMessage(content=_system_prompt())
        response = model.invoke([sys_msg] + list(state["messages"]))
        return {"messages": [response]}

    graph = StateGraph(_State)
    graph.add_node("agent", _call_model)
    graph.add_node("tools", _call_tools)
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", _should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")
    return graph.compile()

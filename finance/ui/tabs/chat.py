"""Tab: Master Financial Intelligence AI & Specialized Sub-Agents."""
from __future__ import annotations

import textwrap
import uuid
import pandas as pd
import streamlit as st

from ... import config, db
from ..format import inr
from ..kpis import get_portfolio_summary
MASTER_SUGGESTIONS = [
    "Across all my credit cards and loans, what is my exact monthly debt obligation?",
    "When will I become debt-free and how will my cashflow improve?",
    "Give me a complete financial health checkup for this month",
    "If I have ₹50,000 extra, what should I prepay first to save interest?",
    "What are my upcoming payment due dates and auto-debits in the next 30 days?",
    "Show my credit limits and total card utilization rate",
]

BANK_SUGGESTIONS = [
    "How much did I spend on food last month?",
    "What are my biggest expenses this month?",
    "Show me my savings rate",
    "How much does Ashwin owe me?",
    "Break down my uncategorized spend",
    "Show my account balances",
]

CC_SUGGESTIONS = [
    "When is my credit card bill due?",
    "How many reward points do I have?",
    "Did I get charged any annual fee or interest?",
    "How much did I spend on my credit card this month?",
    "Show line items for Swiggy on credit card",
]


@st.cache_resource(show_spinner=False)
def _get_master_chat_agent():
    """Build the Master Unified LangGraph agent once per app session."""
    from finance.agent import master_graph
    return master_graph.build_master_agent()


@st.cache_resource(show_spinner=False)
def _get_chat_agent():
    """Build the Bank LangGraph agent once per app session."""
    from finance.agent import graph
    return graph.build_agent()


@st.cache_resource(show_spinner=False)
def _get_cc_chat_agent():
    """Build the Credit Card LangGraph agent once per app session."""
    from finance.agent import cc_graph
    return cc_graph.build_cc_agent()


def _render_message(m, idx):
    """Render a chat message with feedback buttons for assistant replies."""
    with st.chat_message(m["role"]):
        st.markdown(m["content"])
        if m["role"] == "assistant" and "feedback_id" not in m:
            col1, col2, _ = st.columns([1, 1, 10])
            with col1:
                if st.button(
                    ":material/thumb_up:",
                    key=f"up_{idx}",
                    help="Good answer",
                    width="content",
                ):
                    db.save_feedback(
                        st.session_state.chat_messages[idx - 1]["content"],
                        m["content"],
                        "up",
                    )
                    m["feedback_id"] = "up"
                    st.rerun()
            with col2:
                if st.button(
                    ":material/thumb_down:",
                    key=f"down_{idx}",
                    help="Bad answer",
                    width="content",
                ):
                    db.save_feedback(
                        st.session_state.chat_messages[idx - 1]["content"],
                        m["content"],
                        "down",
                    )
                    m["feedback_id"] = "down"
                    st.rerun()
            if m.get("feedback_id"):
                st.caption(f"Thanks! Recorded as {m['feedback_id']}")


def _stream_agent_response(agent, history):
    """Stream ONLY the final assistant answer tokens cleanly."""
    try:
        for chunk, metadata in agent.stream(
            {"messages": history},
            stream_mode="messages",
            config={"recursion_limit": 20},
        ):
            if metadata.get("langgraph_node") == "agent":
                if hasattr(chunk, "content") and chunk.content and not getattr(chunk, "tool_calls", None):
                    yield chunk.content
    except Exception as exc:
        yield f"Something went wrong while answering: {exc}"


def tab_chat():
    st.header("🧠 Master Financial Intelligence AI", divider=True)

    # Top KPI Banner for Instant Cross-Domain Context
    loans_df = db.load_bank_loans()
    cc_emis = db.load_cc_emis()
    cc_stmts = db.load_cc_statements()
    
    tot_loan_emi = loans_df["monthly_emi"].sum() if not loans_df.empty else 0.0
    tot_cc_emi = cc_emis["monthly_emi"].sum() if not cc_emis.empty else 0.0
    tot_debt_emi = tot_loan_emi + tot_cc_emi
    latest_cc_stmts = cc_stmts.sort_values("statement_date").groupby("card_name", as_index=False).last() if not cc_stmts.empty else pd.DataFrame()
    tot_cc_lim = latest_cc_stmts["credit_limit"].sum() if not latest_cc_stmts.empty else 0.0
    tot_cc_avail = latest_cc_stmts["available_limit"].sum() if not latest_cc_stmts.empty else 0.0

    st.markdown(textwrap.dedent(f"""
    <div style="background: #ffffff; border: 1px solid #e4e4e7; border-radius: 14px; padding: 16px 20px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.03); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;">
        <div>
            <div style="font-size: 11px; text-transform: uppercase; font-weight: 800; color: #71717a; letter-spacing: 0.08em;">Unified Finance OS</div>
            <div style="font-size: 18px; font-weight: 800; color: #09090b; margin-top: 2px;">Chief Financial Officer (CFO) AI</div>
            <div style="font-size: 12.5px; color: #71717a; margin-top: 2px;">Synthesizing Bank Statements (3 Accounts), Personal Loans (4 Plans), and Credit Cards (5 Cards).</div>
        </div>
        <div style="display: flex; gap: 20px; border-left: 1px solid #e4e4e7; padding-left: 20px;">
            <div>
                <div style="font-size: 11px; font-weight: 700; color: #71717a;">Total Monthly Debt</div>
                <div style="font-size: 16px; font-weight: 800; color: #09090b;">{inr(tot_debt_emi)}/mo</div>
                <div style="font-size: 11px; color: #71717a;">{len(loans_df) + len(cc_emis)} active plans</div>
            </div>
            <div>
                <div style="font-size: 11px; font-weight: 700; color: #71717a;">Credit Exposure</div>
                <div style="font-size: 16px; font-weight: 800; color: #09090b;">{inr(tot_cc_lim)}</div>
                <div style="font-size: 11px; color: #71717a;">{inr(tot_cc_avail)} free</div>
            </div>
        </div>
    </div>
    """), unsafe_allow_html=True)

    agent_mode = st.radio(
        "Select AI Perspective",
        [
            "🌟 Master Financial AI (Bank + Loans + Cards Combined)",
            "🏦 Bank & Cashflow Specialist",
            "💳 Credit Card Specialist"
        ],
        horizontal=True,
    )

    # Initialize chat session ID if not present
    if "chat_session_id" not in st.session_state:
        st.session_state.chat_session_id = uuid.uuid4().hex[:12]
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []

    # Session Management Bar
    past_sessions = db.load_chat_sessions(limit=25)
    c_s1, c_s2, c_s3 = st.columns([2, 5, 2])
    with c_s1:
        if st.button("➕ New Chat", key="btn_new_chat", width="stretch"):
            st.session_state.chat_session_id = uuid.uuid4().hex[:12]
            st.session_state.chat_messages = []
            st.rerun()

    with c_s2:
        if past_sessions:
            sess_labels = {}
            for s in past_sessions:
                dt_part = s["started_at"][:16].replace("T", " ")
                sess_labels[s["session_id"]] = f"🕒 {dt_part} | {s['session_title'][:38]} ({s['message_count']} msgs)"
            
            # Add current if not yet listed
            if st.session_state.chat_session_id not in sess_labels:
                sess_labels[st.session_state.chat_session_id] = "💬 Current Active Chat"

            sess_ids = list(sess_labels.keys())
            curr_idx = sess_ids.index(st.session_state.chat_session_id) if st.session_state.chat_session_id in sess_ids else 0
            
            selected_sess = st.selectbox(
                "Resume Past Chat",
                options=sess_ids,
                format_func=lambda sid: sess_labels.get(sid, sid),
                index=curr_idx,
                key="sel_past_chat_sess",
                label_visibility="collapsed"
            )
            if selected_sess != st.session_state.chat_session_id:
                st.session_state.chat_session_id = selected_sess
                db_msgs = db.load_chat_messages(selected_sess)
                st.session_state.chat_messages = [
                    {"role": m["role"], "content": m["content"]} for m in db_msgs
                ]
                st.rerun()

    with c_s3:
        if st.session_state.chat_messages:
            md_transcript = db.export_chat_markdown(st.session_state.chat_session_id)
            st.download_button(
                "📥 Export (.md)",
                data=md_transcript,
                file_name=f"finance_chat_{st.session_state.chat_session_id}.md",
                mime="text/markdown",
                key="btn_export_chat_md",
                width="stretch",
            )

    # Show feedback stats in sidebar
    with st.sidebar:
        st.divider()
        st.subheader(":material/feedback: Feedback")
        counts = db.feedback_counts()
        st.caption(f"👍 {counts['up']}  |  👎 {counts['down']}")

    try:
        if "Master" in agent_mode:
            agent = _get_master_chat_agent()
            suggestions = MASTER_SUGGESTIONS
        elif "Credit Card" in agent_mode:
            agent = _get_cc_chat_agent()
            suggestions = CC_SUGGESTIONS
        else:
            agent = _get_chat_agent()
            suggestions = BANK_SUGGESTIONS
    except Exception as exc:
        st.error(f"Agent is unavailable: {exc}")
        return

    # Show suggestion chips on first load
    if len(st.session_state.chat_messages) == 0:
        st.caption("Quick prompts to ask:")
        cols = st.columns(3)
        for i, suggestion in enumerate(suggestions[:6]):
            with cols[i % 3]:
                if st.button(
                    suggestion,
                    key=f"sug_{i}",
                    width="stretch",
                ):
                    st.session_state.chat_messages.append(
                        {"role": "user", "content": suggestion}
                    )
                    db.save_chat_message(
                        session_id=st.session_state.chat_session_id,
                        role="user",
                        content=suggestion,
                        agent_mode=agent_mode,
                    )
                    st.rerun()

    # Check if the last message is from the user and needs a response
    last_msg = st.session_state.chat_messages[-1] if st.session_state.chat_messages else None
    should_respond = (last_msg is not None and last_msg["role"] == "user")

    for idx, m in enumerate(st.session_state.chat_messages):
        _render_message(m, idx)

    # Chat input at the bottom
    prompt = st.chat_input(
        "e.g. How much did I spend on food last month?",
    )
    if prompt:
        st.session_state.chat_messages.append({"role": "user", "content": prompt})
        db.save_chat_message(
            session_id=st.session_state.chat_session_id,
            role="user",
            content=prompt,
            agent_mode=agent_mode,
        )
        st.rerun()

    # Generate assistant response if needed
    if should_respond:
        history = [
            ("user" if m["role"] == "user" else "assistant", m["content"])
            for m in st.session_state.chat_messages
        ]

        with st.chat_message("assistant"):
            with st.status("🤔 Thinking...", expanded=False) as status:
                response = st.write_stream(_stream_agent_response(agent, history))
                status.update(label="✓ Done", state="complete", expanded=False)

        if response:
            st.session_state.chat_messages.append(
                {"role": "assistant", "content": response}
            )
            db.save_chat_message(
                session_id=st.session_state.chat_session_id,
                role="assistant",
                content=response,
                agent_mode=agent_mode,
            )
            st.rerun()



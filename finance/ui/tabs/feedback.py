"""History & Logs tab for reviewing historical conversations, search logs, and feedback."""
from __future__ import annotations

import streamlit as st
from ... import db


def tab_feedback():
    """Review conversation history, search chat logs, and analyze thumbs up/down feedback."""
    st.header("📜 AI Conversation History & Logs", divider=True)
    st.caption("Search past dialogues, inspect AI reasoning transcripts, restore sessions, and review model feedback.")

    h_tab1, h_tab2 = st.tabs(["💬 Conversation History & Search", "👍 Feedback & Quality Ratings"])

    with h_tab1:
        # Search & Filter controls
        f_col1, f_col2 = st.columns([3, 1])
        with f_col1:
            q_search = st.text_input("🔍 Search Conversation History", placeholder="Search by topic, keyword, merchant, or counterparty (e.g. Ashwin, EMI, Swiggy)...", key="chat_hist_search")
        with f_col2:
            agent_filter = st.selectbox("AI Perspective", ["All Perspectives", "Master Financial AI", "Bank & Cashflow Specialist", "Credit Card Specialist"], key="chat_hist_agent_filter")

        if q_search.strip():
            matches = db.search_chat_messages(q_search.strip(), limit=50)
            if not matches:
                st.info(f"No messages found matching '{q_search}'.")
            else:
                st.write(f"Found **{len(matches)}** matching message(s):")
                for m in matches:
                    if agent_filter != "All Perspectives" and agent_filter not in m["agent_mode"]:
                        continue
                    dt_str = m["created_at"][:16].replace("T", " ")
                    role_badge = "🧑 User Question" if m["role"] == "user" else "🤖 Assistant Answer"
                    with st.expander(f"{role_badge} | {m['session_title'][:40]} ({dt_str})", expanded=True):
                        st.markdown(f"**Session:** `{m['session_id']}` | **AI Perspective:** `{m['agent_mode']}`")
                        st.markdown(m["content"])
                        if st.button("💬 Open this Session in Chat", key=f"open_search_{m['session_id']}_{m['created_at']}"):
                            st.session_state.chat_session_id = m["session_id"]
                            db_msgs = db.load_chat_messages(m["session_id"])
                            st.session_state.chat_messages = [
                                {"role": row["role"], "content": row["content"]} for row in db_msgs
                            ]
                            st.toast("Loaded session into Chat! Switch to the Master Financial AI tab to continue.")
        else:
            sessions = db.load_chat_sessions(limit=50)
            if not sessions:
                st.info("No saved chat conversations yet. Conversations you have with the AI will automatically appear here!")
            else:
                # Top summary metrics
                tot_sessions = len(sessions)
                tot_msgs = sum(s["message_count"] for s in sessions)
                m_c1, m_c2, m_c3 = st.columns(3)
                m_c1.metric("Saved Conversations", tot_sessions)
                m_c2.metric("Total Dialogue Turns", tot_msgs)
                m_c3.metric("Latest Chat Activity", sessions[0]["last_active"][:16].replace("T", " "))

                st.write("---")
                for s in sessions:
                    if agent_filter != "All Perspectives" and agent_filter not in s["agent_mode"]:
                        continue
                    sid = s["session_id"]
                    dt_display = s["started_at"][:16].replace("T", " ")
                    title = s["session_title"] or "Untitled Conversation"

                    with st.expander(f"💬 {title} — {dt_display} ({s['message_count']} msgs)", expanded=False):
                        st.caption(f"**Session ID:** `{sid}` | **Perspective:** `{s['agent_mode']}` | **Last active:** `{s['last_active'][:16].replace('T', ' ')}`")
                        
                        msgs = db.load_chat_messages(sid)
                        for m in msgs:
                            role_icon = "🧑 **You:**" if m["role"] == "user" else "🤖 **AI:**"
                            st.markdown(f"{role_icon} *({m['created_at'][11:16]})*")
                            st.markdown(m["content"])
                            st.write("")

                        # Action buttons
                        b_c1, b_c2, b_c3 = st.columns([2, 2, 4])
                        with b_c1:
                            if st.button("💬 Restore in Chat", key=f"restore_{sid}"):
                                st.session_state.chat_session_id = sid
                                st.session_state.chat_messages = [
                                    {"role": row["role"], "content": row["content"]} for row in msgs
                                ]
                                st.toast("Session restored! Switch to the Master Financial AI tab to continue.")
                                st.rerun()
                        with b_c2:
                            md_data = db.export_chat_markdown(sid)
                            st.download_button(
                                "📥 Export (.md)",
                                data=md_data,
                                file_name=f"transcript_{sid}.md",
                                mime="text/markdown",
                                key=f"dl_{sid}",
                            )
                        with b_c3:
                            if st.button("🗑️ Delete Session", key=f"del_{sid}"):
                                db.delete_chat_session(sid)
                                if st.session_state.get("chat_session_id") == sid:
                                    st.session_state.chat_session_id = None
                                    st.session_state.chat_messages = []
                                st.toast("Session deleted.")
                                st.rerun()

    with h_tab2:
        down_feedback = db.load_feedback(rating="down", limit=50)
        up_feedback = db.load_feedback(rating="up", limit=20)

        if down_feedback.empty and up_feedback.empty:
            st.info("No thumbs up/down ratings recorded yet.")
        else:
            if not down_feedback.empty:
                st.subheader(f":material/thumb_down: Needs attention ({len(down_feedback)})")
                for _, row in down_feedback.iterrows():
                    with st.expander(f"**Q:** {row['question'][:80]}…", expanded=False):
                        st.markdown(f"**Question:** {row['question']}")
                        st.markdown(f"**Answer:** {row['answer']}")
                        st.caption(f"Recorded: {row['created_at']}")

            if not up_feedback.empty:
                st.divider()
                st.subheader(f":material/thumb_up: Working well ({len(up_feedback)})")
                for _, row in up_feedback.iterrows():
                    with st.expander(f"**Q:** {row['question'][:80]}…", expanded=False):
                        st.markdown(f"**Question:** {row['question']}")
                        st.markdown(f"**Answer:** {row['answer']}")
                        st.caption(f"Recorded: {row['created_at']}")

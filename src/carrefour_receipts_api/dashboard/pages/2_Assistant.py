"""Streamlit page: natural-language financial assistant (Vanna 2.0 text-to-SQL + Plotly).

Chat over the DuckDB marts: ask in plain language, the agent generates read-only SQL
(guarded), runs it, and shows the SQL, the result table and a Plotly chart when relevant.
Configure the LLM via `ASSISTANT_LLM_*` (.env): OpenAI or a local Ollama endpoint.
"""

from __future__ import annotations

from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

from carrefour_receipts_api import config

st.set_page_config(page_title="Assistant financier", page_icon="💬", layout="wide")
st.title("💬 Assistant financier")


@st.cache_resource(show_spinner="Initialisation de l'assistant…")
def _agent():
    from carrefour_receipts_api.assistant.agent import build_agent

    return build_agent()


def _guard_ready() -> bool:
    if not Path(config.DUCKDB_PATH).exists():
        st.warning(
            f"Aucune base `{config.DUCKDB_PATH}`. Lance d'abord `make build` "
            "(dlt load + dbt build), puis recharge."
        )
        return False
    if not config.ASSISTANT_LLM_API_KEY and "openai.com" in config.ASSISTANT_LLM_BASE_URL:
        st.warning(
            "`ASSISTANT_LLM_API_KEY` manquante. Renseigne une clé OpenAI dans `.env`, "
            "ou pointe `ASSISTANT_LLM_BASE_URL` vers un Ollama local "
            "(`http://localhost:11434/v1`)."
        )
        return False
    return True


st.caption(
    f"LLM : `{config.ASSISTANT_MODEL}` via `{config.ASSISTANT_LLM_BASE_URL}` · "
    "lecture seule sur les marts (magasin + Drive + fidélité)."
)

if not _guard_ready():
    st.stop()

agent, runner = _agent()

if "assistant_history" not in st.session_state:
    st.session_state.assistant_history = []  # list of dicts: {role, content/reply}

# Replay history.
for turn in st.session_state.assistant_history:
    with st.chat_message(turn["role"]):
        if turn["role"] == "user":
            st.markdown(turn["content"])
        else:
            reply = turn["reply"]
            if reply.text:
                st.markdown(reply.text)
            for sql, df in reply.sql_results:
                st.code(sql, language="sql")
                st.dataframe(df, width="stretch")
            for chart in reply.charts:
                try:
                    st.plotly_chart(go.Figure(chart), width="stretch")
                except Exception:  # noqa: BLE001 - never break the page on a bad figure
                    pass

question = st.chat_input("Pose une question (ex. « mes courses jour par jour ce mois »)")
if question:
    st.session_state.assistant_history.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        with st.spinner("Analyse…"):
            try:
                from carrefour_receipts_api.assistant.agent import answer

                reply = answer(agent, runner, question)
            except Exception as exc:  # noqa: BLE001 - surface errors in the UI
                st.error(f"Échec : {exc}")
                st.stop()
        if reply.text:
            st.markdown(reply.text)
        for sql, df in reply.sql_results:
            st.code(sql, language="sql")
            st.dataframe(df, width="stretch")
        for chart in reply.charts:
            try:
                st.plotly_chart(go.Figure(chart), width="stretch")
            except Exception:  # noqa: BLE001
                pass
    st.session_state.assistant_history.append({"role": "assistant", "reply": reply})

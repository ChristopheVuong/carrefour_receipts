"""Vanna 2.0 agent wiring for the Carrefour financial assistant.

Builds an ``Agent`` with an OpenAI-compatible LLM (OpenAI or local Ollama via
``base_url``), a read-only DuckDB ``RunSqlTool`` (guarded) and ``VisualizeDataTool``
(Plotly), grounded by the dbt-derived schema card injected as the system prompt.
``answer()`` runs one question synchronously and returns the narration, the executed
``(sql, dataframe)`` pairs and any Plotly figure dicts — ready for the Streamlit page.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
from vanna import Agent, AgentConfig, ToolRegistry, User
from vanna.core.system_prompt import SystemPromptBuilder
from vanna.core.user import RequestContext, UserResolver
from vanna.integrations.local.agent_memory import DemoAgentMemory
from vanna.integrations.openai import OpenAILlmService
from vanna.tools import LocalFileSystem, RunSqlTool, VisualizeDataTool

from carrefour_receipts_api import config
from carrefour_receipts_api.assistant.grounding import schema_card
from carrefour_receipts_api.assistant.read_only_runner import ReadOnlyDuckDBRunner
from carrefour_receipts_api.logging_config import get_logger

logger = get_logger(__name__)

_WORKSPACE = "data/assistant_workspace"  # git-ignored scratch for tool artifacts


class _SchemaCardPrompt(SystemPromptBuilder):
    """Inject the dbt-derived schema card (+ persona) as the agent's system prompt."""

    def __init__(self, card: str) -> None:
        self._card = card

    async def build_system_prompt(self, user: Any, tools: Any) -> str:
        return self._card


class _StaticUserResolver(UserResolver):
    """Single-user local app: every request resolves to the same local user."""

    async def resolve_user(self, request_context: RequestContext) -> User:
        return User(id="local", username="local")


@dataclass
class AssistantReply:
    """One assistant turn, decomposed for rendering."""

    text: str = ""
    sql_results: list[tuple[str, pd.DataFrame]] = field(default_factory=list)
    charts: list[dict] = field(default_factory=list)


def build_agent() -> tuple[Agent, ReadOnlyDuckDBRunner]:
    """Construct the agent and return it with its read-only runner (for result capture)."""
    llm = OpenAILlmService(
        # The OpenAI client requires *a* key to construct; Ollama ignores it. A real
        # OpenAI call without a valid key 401s (the page warns first).
        api_key=config.ASSISTANT_LLM_API_KEY or "no-key-set",
        base_url=config.ASSISTANT_LLM_BASE_URL or None,
        model=config.ASSISTANT_MODEL,
    )
    runner = ReadOnlyDuckDBRunner()
    Path(_WORKSPACE).mkdir(parents=True, exist_ok=True)
    file_system = LocalFileSystem(working_directory=_WORKSPACE)

    # Empty access_groups => accessible to all users (single-user local app).
    tools = ToolRegistry()
    tools.register_local_tool(
        RunSqlTool(sql_runner=runner, file_system=file_system),  # type: ignore[arg-type]
        [],
    )
    tools.register_local_tool(VisualizeDataTool(file_system=file_system), [])

    agent = Agent(
        llm_service=llm,
        tool_registry=tools,
        user_resolver=_StaticUserResolver(),
        agent_memory=DemoAgentMemory(),
        system_prompt_builder=_SchemaCardPrompt(schema_card()),
        config=AgentConfig(stream_responses=False, temperature=0.0),
    )
    return agent, runner


async def _collect(agent: Agent, question: str, conversation_id: str) -> tuple[str, list[dict]]:
    """Drive one ``send_message`` turn, collecting narration text and chart dicts.

    The stream yields many ``UiComponent`` variants (status cards, tool cards, the
    SQL table, the chart, the final answer). We key off ``rich_component.type``:
    ``"text"`` is the LLM's narration (``RichTextComponent.content``); ``"chart"`` is a
    ``ChartComponent`` whose Plotly figure dict lives in ``.data`` (NOT ``.content`` —
    every ``RichComponent`` has a default-empty ``.data``, so we must gate on the type).
    Filtering to ``"text"`` also drops the status spam and the raw CSV preview that
    ``RunSqlTool`` puts in its ``simple_component``.
    """
    ctx = RequestContext(cookies={}, headers={}, remote_addr="127.0.0.1")
    texts: list[str] = []
    charts: list[dict] = []
    async for component in agent.send_message(
        request_context=ctx, message=question, conversation_id=conversation_id
    ):
        rich = getattr(component, "rich_component", None)
        ctype = getattr(getattr(rich, "type", None), "value", None)
        if ctype == "text":
            content = getattr(rich, "content", "")
            if content:
                texts.append(content)
        elif ctype == "chart":
            data = getattr(rich, "data", None)
            if isinstance(data, dict) and data:  # Plotly figure dict
                charts.append(data)
    return "\n\n".join(texts).strip(), charts


def answer(
    agent: Agent, runner: ReadOnlyDuckDBRunner, question: str, conversation_id: str = "assistant"
) -> AssistantReply:
    """Answer one question; returns narration + executed (sql, df) + Plotly figure dicts."""
    runner.executed.clear()
    text, charts = asyncio.run(_collect(agent, question, conversation_id))
    return AssistantReply(text=text, sql_results=list(runner.executed), charts=charts)

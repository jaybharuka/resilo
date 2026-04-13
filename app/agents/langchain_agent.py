"""
LangChain-based AIOps agent for alert analysis and remediation planning.
Uses NVIDIA NIM (OpenAI-compatible) as the LLM backend.

Tools (never execute directly — return intent only):
  restart_service  — queue a service restart
  get_system_metrics — expose metrics to the agent
  noop             — safe fallback

Output flows back to runtime._lc_analyze which applies execution-mode guards.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

log = logging.getLogger("langchain_agent")

_SYSTEM_PROMPT = (
    "You are an AIOps agent responsible for maintaining system health.\n"
    "Rules:\n"
    "- Prefer safe actions. Never execute destructive commands.\n"
    "- Use restart_service only when clearly necessary.\n"
    "- If unsure, call noop.\n"
    "- Call exactly ONE tool, then stop.\n"
    "- Briefly explain your reasoning."
)

_SAFE_ACTIONS: frozenset[str] = frozenset({"restart_service", "noop"})


def _build_agent(metrics: dict[str, Any]) -> AgentExecutor:
    llm = ChatOpenAI(
        model=os.getenv("LLM_MODEL", "meta/llama-3.3-70b-instruct"),
        api_key=os.getenv("NVIDIA_API_KEY", "placeholder"),
        base_url=os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
        temperature=0.2,
        max_tokens=512,
    )

    @tool
    def restart_service(service_name: str) -> str:
        """Queue a restart for the named service. Does NOT execute — returns intent only."""
        return json.dumps({"action": "restart_service", "target": service_name})

    @tool
    def get_system_metrics() -> str:
        """Return the current system metrics from the alert context."""
        return json.dumps(metrics)

    @tool
    def noop() -> str:
        """Do nothing. Safe fallback when no action is needed or situation is unclear."""
        return json.dumps({"action": "noop", "target": ""})

    tools = [restart_service, get_system_metrics, noop]
    prompt = ChatPromptTemplate.from_messages([
        ("system", _SYSTEM_PROMPT),
        ("human", "{input}"),
        MessagesPlaceholder("agent_scratchpad"),
    ])
    agent = create_openai_tools_agent(llm, tools, prompt)
    return AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=False,
        max_iterations=3,
        handle_parsing_errors=True,
        return_intermediate_steps=True,
    )


async def analyze_alert(
    alert_data: dict[str, Any],
    metrics: dict[str, Any],
    success_rate: float | None = None,
) -> dict[str, Any]:
    """Run the LangChain agent against an alert. Never raises — returns noop on failure."""
    if not os.getenv("NVIDIA_API_KEY"):
        log.warning("[AGENT] NVIDIA_API_KEY not set — skipping LangChain analysis")
        return {"action": "noop", "target": "", "reason": "no api key", "confidence": 0.0, "safe": True}

    history_note = ""
    if success_rate is not None:
        history_note = f"\nHistorical success rate for restart_service on this agent: {success_rate * 100:.0f}%"

    input_text = (
        f"Alert: {alert_data['category']} | Severity: {alert_data['severity']}\n"
        f"Title: {alert_data['title']}\n"
        f"Detail: {alert_data['detail']}\n"
        f"Metrics: CPU={metrics.get('cpu', 0):.1f}% | "
        f"Memory={metrics.get('memory', 0):.1f}% | "
        f"Disk={metrics.get('disk', 0):.1f}%"
        f"{history_note}"
    )

    log.info("[AGENT] Alert received: %s (%s)", alert_data["category"], alert_data["severity"])

    try:
        executor = _build_agent(metrics)
        result = await executor.ainvoke({"input": input_text})

        action, target, reason = "noop", "", result.get("output", "")
        steps = result.get("intermediate_steps", [])
        if steps:
            agent_action, tool_output = steps[-1]
            try:
                parsed = json.loads(tool_output)
                action = parsed.get("action", "noop")
                target = parsed.get("target", "")
            except (json.JSONDecodeError, ValueError):
                action = getattr(agent_action, "tool", "noop")

        decision = {
            "action": action,
            "target": target,
            "reason": reason,
            "confidence": 0.8 if action != "noop" else 0.5,
            "safe": action in _SAFE_ACTIONS,
        }
        log.info("[AGENT PLAN] action=%s target=%s confidence=%.2f",
                 action, target, decision["confidence"])
        return decision

    except Exception as exc:
        log.warning("[AGENT] Analysis failed: %s", exc)
        return {"action": "noop", "target": "", "reason": str(exc), "confidence": 0.0, "safe": True}

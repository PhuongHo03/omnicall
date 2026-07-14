"""LLM decision and parallel tool execution boundary for Agentic RAG."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from backend.providers.llm import LLMProvider, LLMProviderError
from backend.services.agent.context_manager import AgentContextManager
from backend.services.agent.parallel_executor import ParallelExecutionSummary, ParallelToolExecutor
from backend.services.agent.prompt_builder import agent_system_prompt, agent_user_prompt
from backend.services.agent.tool_registry import AgentToolRegistry

VALID_TOOLS = {
    "search_semantic", "search_keyword", "search_records", "search_section", "get_summary",
}


class AgentLoop:
    """Own the Think and Execute steps while callers own context lifecycle."""

    def __init__(
        self,
        *,
        llm_provider: LLMProvider,
        tool_registry: AgentToolRegistry,
        context_manager: AgentContextManager,
        tool_executor: ParallelToolExecutor,
    ) -> None:
        self.llm_provider = llm_provider
        self.tool_registry = tool_registry
        self.context_manager = context_manager
        self.tool_executor = tool_executor

    def think(self, *, question: str, iteration: int, force_synthesize: bool = False, plan: str = "") -> dict[str, Any]:
        started = time.perf_counter()
        response = self.llm_provider.generate_json(
            system_prompt=agent_system_prompt(
                tools=self.tool_registry.get_tools(), force_synthesize=force_synthesize
            ),
            user_prompt=agent_user_prompt(
                question=question,
                iteration=iteration,
                context=self.context_manager.format_context_for_llm(),
                plan=plan,
            ),
        )
        if not isinstance(response, dict):
            raise LLMProviderError("Agent provider response was not a JSON object.")
        action = response.get("action")
        if action not in {"continue", "synthesize"}:
            action = "synthesize" if force_synthesize else "continue"
        return {**response, "action": action, "durationMs": _elapsed_ms(started)}

    def execute_tools(
        self,
        *,
        meeting_id: str,
        tool_calls: list[dict[str, Any]],
    ) -> ParallelExecutionSummary:
        async def run() -> ParallelExecutionSummary:
            async def execute_one(tool_name: str, parameters: dict[str, Any]) -> list[dict[str, Any]]:
                execute = getattr(self.tool_registry, "execute_tool_scoped", None)
                kwargs = {
                    "meeting_id": meeting_id,
                    "tool_name": tool_name,
                    "arguments": parameters,
                }
                if callable(execute) and getattr(self.tool_registry, "session_factory", None) is not None:
                    result = await asyncio.to_thread(execute, **kwargs)
                else:
                    result = self.tool_registry.execute_tool(**kwargs)
                if not result.success:
                    raise RuntimeError(result.error or f"Tool {tool_name} failed.")
                data = result.data or []
                return list(data if isinstance(data, list) else [data])

            tool_map = {tool: execute_one for tool in VALID_TOOLS}
            return await self.tool_executor.execute(tool_calls, tool_map)

        try:
            return asyncio.run(run())
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(run())
            finally:
                loop.close()


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)

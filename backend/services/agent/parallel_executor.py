"""Parallel tool executor for Agentic RAG.

Runs multiple tool calls concurrently using asyncio.gather,
with per-tool timeout, partial failure handling, and fallback
to sequential execution if the parallel path fails.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Default per-tool timeout in seconds.
_DEFAULT_TOOL_TIMEOUT_SECONDS = 10.0


@dataclass
class ToolResult:
    """Result of a single tool invocation."""

    tool_name: str
    parameters: dict[str, Any]
    result: list[dict[str, Any]]
    duration_ms: int = 0
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.error is None

    @property
    def has_results(self) -> bool:
        return bool(self.result)


@dataclass
class ParallelExecutionSummary:
    """Aggregated result of a parallel tool execution batch."""

    tool_results: list[ToolResult] = field(default_factory=list)
    total_duration_ms: int = 0
    parallel_mode: str = "parallel"
    failure_count: int = 0
    success_count: int = 0
    timeout_count: int = 0

    @property
    def all_failed(self) -> bool:
        return self.success_count == 0 and len(self.tool_results) > 0

    @property
    def all_chunks(self) -> list[dict[str, Any]]:
        """Collect all result chunks across tools, preserving order."""
        chunks: list[dict[str, Any]] = []
        for tool_result in self.tool_results:
            chunks.extend(tool_result.result)
        return chunks


class ParallelToolExecutor:
    """Execute multiple tool calls concurrently with timeout and failure handling.

    Each tool is an async callable ``(tool_name, parameters) -> list[dict]``.
    The executor runs all tools in parallel via ``asyncio.gather`` and collects
    results, handling per-tool timeouts and partial failures.

    If the parallel execution itself fails (e.g. event loop issues), it falls
    back to sequential execution.

    Parameters
    ----------
    tool_timeout_seconds : float
        Per-tool timeout in seconds. Defaults to 10s.
    """

    def __init__(
        self,
        *,
        tool_timeout_seconds: float = _DEFAULT_TOOL_TIMEOUT_SECONDS,
    ) -> None:
        self.tool_timeout_seconds = tool_timeout_seconds

    async def execute_parallel(
        self,
        tool_calls: list[dict[str, Any]],
        tool_map: dict[str, Any],
    ) -> ParallelExecutionSummary:
        """Execute all tool calls concurrently using asyncio.gather.

        Parameters
        ----------
        tool_calls : list[dict]
            List of tool call dicts, each with ``"tool"`` and ``"parameters"`` keys.
        tool_map : dict[str, Callable]
            Map of tool name to async callable.

        Returns
        -------
        ParallelExecutionSummary
            Aggregated results including per-tool results, timing, and failure info.
        """
        if not tool_calls:
            return ParallelExecutionSummary(total_duration_ms=0)

        started = time.perf_counter()
        logger.info(
            "parallel_executor.execute_parallel tool_count=%d timeout=%.1fs",
            len(tool_calls),
            self.tool_timeout_seconds,
        )

        try:
            tasks = [
                self._run_single_tool(call, tool_map)
                for call in tool_calls
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as exc:
            logger.warning(
                "parallel_executor.gather_failed error=%s — falling back to sequential",
                str(exc),
            )
            return await self._execute_sequential(tool_calls, tool_map)

        tool_results: list[ToolResult] = []
        for call, result in zip(tool_calls, results, strict=False):
            if isinstance(result, Exception):
                tool_name = call.get("tool", "unknown")
                tool_results.append(
                    ToolResult(
                        tool_name=tool_name,
                        parameters=call.get("parameters", {}),
                        result=[],
                        error=str(result),
                    )
                )
            else:
                tool_results.append(result)

        summary = self._build_summary(tool_results, started, mode="parallel")
        self._log_summary(summary)
        return summary

    async def execute(
        self,
        tool_calls: list[dict[str, Any]],
        tool_map: dict[str, Any],
    ) -> ParallelExecutionSummary:
        """Execute tool calls — parallel with sequential fallback.

        Attempts parallel execution first. If all tools fail, retries
        sequentially as a safety net.

        Parameters
        ----------
        tool_calls : list[dict]
            List of tool call dicts.
        tool_map : dict[str, Callable]
            Map of tool name to async callable.

        Returns
        -------
        ParallelExecutionSummary
        """
        if not tool_calls:
            return ParallelExecutionSummary(total_duration_ms=0)

        summary = await self.execute_parallel(tool_calls, tool_map)

        if summary.all_failed and len(tool_calls) > 1:
            logger.info("parallel_executor.all_failed — retrying sequentially")
            summary = await self._execute_sequential(tool_calls, tool_map)

        return summary

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _run_single_tool(
        self,
        call: dict[str, Any],
        tool_map: dict[str, Any],
    ) -> ToolResult:
        """Run a single tool with timeout."""
        tool_name = call.get("tool", "unknown")
        parameters = call.get("parameters", {})
        started = time.perf_counter()

        executor = tool_map.get(tool_name)
        if executor is None:
            logger.warning("parallel_executor.unknown_tool tool=%s", tool_name)
            return ToolResult(
                tool_name=tool_name,
                parameters=parameters,
                result=[],
                duration_ms=_elapsed_ms(started),
                error=f"Unknown tool: {tool_name}",
            )

        try:
            result = await asyncio.wait_for(
                executor(tool_name, parameters),
                timeout=self.tool_timeout_seconds,
            )
            return ToolResult(
                tool_name=tool_name,
                parameters=parameters,
                result=list(result) if result else [],
                duration_ms=_elapsed_ms(started),
            )
        except TimeoutError:
            error_msg = (
                f"Tool {tool_name} timed out after {self.tool_timeout_seconds}s. "
                f"Parameters: {parameters}"
            )
            logger.warning(
                "parallel_executor.tool_timeout tool=%s timeout=%.1fs params=%s",
                tool_name,
                self.tool_timeout_seconds,
                str(parameters)[:100],
            )
            return ToolResult(
                tool_name=tool_name,
                parameters=parameters,
                result=[],
                duration_ms=_elapsed_ms(started),
                error=error_msg,
            )
        except Exception as exc:
            logger.warning(
                "parallel_executor.tool_error tool=%s error=%s",
                tool_name,
                str(exc),
            )
            return ToolResult(
                tool_name=tool_name,
                parameters=parameters,
                result=[],
                duration_ms=_elapsed_ms(started),
                error=str(exc),
            )

    async def _execute_sequential(
        self,
        tool_calls: list[dict[str, Any]],
        tool_map: dict[str, Any],
    ) -> ParallelExecutionSummary:
        """Execute tool calls one by one as a fallback.

        Used when parallel execution fails entirely (e.g. event loop issue).
        """
        started = time.perf_counter()
        logger.info(
            "parallel_executor.execute_sequential tool_count=%d",
            len(tool_calls),
        )

        tool_results: list[ToolResult] = []
        for call in tool_calls:
            result = await self._run_single_tool(call, tool_map)
            tool_results.append(result)

        summary = self._build_summary(tool_results, started, mode="sequential")
        self._log_summary(summary)
        return summary

    @staticmethod
    def _build_summary(
        tool_results: list[ToolResult],
        started: float,
        *,
        mode: str,
    ) -> ParallelExecutionSummary:
        """Build an execution summary from individual tool results."""
        success_count = sum(1 for r in tool_results if r.succeeded)
        failure_count = sum(1 for r in tool_results if not r.succeeded)
        timeout_count = sum(
            1 for r in tool_results if r.error and "timed out" in r.error
        )
        return ParallelExecutionSummary(
            tool_results=tool_results,
            total_duration_ms=_elapsed_ms(started),
            parallel_mode=mode,
            failure_count=failure_count,
            success_count=success_count,
            timeout_count=timeout_count,
        )

    @staticmethod
    def _log_summary(summary: ParallelExecutionSummary) -> None:
        """Log the parallel execution summary."""
        logger.info(
            "parallel_executor.completed mode=%s tools=%d succeeded=%d "
            "failed=%d timeouts=%d total_ms=%d",
            summary.parallel_mode,
            len(summary.tool_results),
            summary.success_count,
            summary.failure_count,
            summary.timeout_count,
            summary.total_duration_ms,
        )


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)

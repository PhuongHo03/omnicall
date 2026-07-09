"""Compatibility wrapper for agent parallel tool execution."""

from backend.services.agent.parallel_executor import (
    ParallelExecutionSummary,
    ParallelToolExecutor,
    ToolResult,
)

__all__ = [
    "ParallelExecutionSummary",
    "ParallelToolExecutor",
    "ToolResult",
]

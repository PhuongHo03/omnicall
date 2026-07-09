"""Compatibility wrapper for agent tool registry types."""

from backend.services.agent.tool_registry import (
    AgentToolRegistry,
    ToolCategory,
    ToolDefinition,
    ToolExecutionResult,
    ToolParameter,
    create_tool_registry,
)

__all__ = [
    "AgentToolRegistry",
    "ToolCategory",
    "ToolDefinition",
    "ToolExecutionResult",
    "ToolParameter",
    "create_tool_registry",
]

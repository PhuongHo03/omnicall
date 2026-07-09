"""Compatibility wrapper for the agentic RAG service."""

from backend.services.agent.service import (
    AgentResult,
    AgenticRAGService,
    _ITERATION_TIMEOUT_SECONDS,
    _MAX_ITERATIONS_DEFAULT,
    _TOTAL_TIMEOUT_SECONDS,
    _VALID_EVIDENCE_STATES,
    _VALID_TOOLS,
)

__all__ = [
    "AgentResult",
    "AgenticRAGService",
    "_ITERATION_TIMEOUT_SECONDS",
    "_MAX_ITERATIONS_DEFAULT",
    "_TOTAL_TIMEOUT_SECONDS",
    "_VALID_EVIDENCE_STATES",
    "_VALID_TOOLS",
]

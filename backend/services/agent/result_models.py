"""Response DTOs returned by the Agentic RAG service."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentResult:
    """Final response from the agentic RAG flow."""

    answer: str
    evidence_state: str
    confidence: float
    provider: str = "agentic-rag"
    model: str | None = None
    iterations: int = 0
    total_duration_ms: int = 0
    tool_calls_summary: list[dict[str, Any]] = field(default_factory=list)
    agent_thoughts: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_answer_payload(self) -> dict[str, Any]:
        """Convert to the answer payload shape used by ``MeetingChatService``."""
        return {
            "answer": self.answer,
            "evidenceState": self.evidence_state,
            "confidence": self.confidence,
            "provider": self.provider,
            "model": self.model,
            "agentIterations": self.iterations,
            "agentToolCalls": self.tool_calls_summary,
            "agentThoughts": self.agent_thoughts,
        }

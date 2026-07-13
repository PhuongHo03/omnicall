"""Contracts and result DTO for guardrail providers."""

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

GuardrailAction = Literal["allowed", "blocked"]
GuardrailKind = Literal["chat_input", "answer"]
PROMPT_VERSION = "v3-simplified"


@dataclass(frozen=True)
class GuardrailResult:
    action: GuardrailAction
    categories: list[str] = field(default_factory=list)
    confidence: float = 0.0
    provider: str = "unknown"
    model: str = "unknown"
    safe_message: str = ""
    latency_ms: int = 0
    prompt_version: str = PROMPT_VERSION
    text_length: int = 0
    decision_id: str = field(default_factory=lambda: str(__import__("uuid").uuid4()))

    @property
    def allowed(self) -> bool:
        return self.action == "allowed"

    def to_metadata(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "categories": list(self.categories),
            "confidence": round(float(self.confidence), 4),
            "provider": self.provider,
            "model": self.model,
            "latencyMs": self.latency_ms,
            "promptVersion": self.prompt_version,
            "textLength": self.text_length,
            "decisionId": self.decision_id,
        }


class GuardrailProvider(Protocol):
    provider_name: str
    model_name: str

    def check(self, *, kind: GuardrailKind, text: str, metadata: dict[str, Any] | None = None) -> GuardrailResult:
        ...

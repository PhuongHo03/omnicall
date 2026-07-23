"""Contracts and request configuration shared by LLM adapters."""

from dataclasses import dataclass
from threading import Lock
from typing import Any, Protocol


class LLMProviderError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = False, code: str = "llm_provider_error") -> None:
        super().__init__(message)
        self.retryable = retryable
        self.code = code


class LLMProvider(Protocol):
    provider_name: str
    model_name: str

    def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0,
        timeout_seconds: float | None = None,
        max_output_tokens: int | None = None,
        response_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class LLMExecutionSnapshot:
    provider_name: str
    model_name: str
    fallback_used: bool = False
    primary_error_type: str | None = None
    primary_error_message: str | None = None


class LLMExecutionTracker:
    """Thread-safe request provenance visible before a provider call ends."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._snapshot: LLMExecutionSnapshot | None = None

    def record(self, snapshot: LLMExecutionSnapshot) -> None:
        with self._lock:
            self._snapshot = snapshot

    def snapshot(self) -> LLMExecutionSnapshot | None:
        with self._lock:
            return self._snapshot


@dataclass(frozen=True)
class LLMRequestConfig:
    base_url: str
    model: str
    api_key: str = ""
    timeout_seconds: float = 60.0
    max_retries: int = 1
    retry_backoff_seconds: float = 0.2
    context_length: int | None = None
    max_output_tokens: int | None = None
    reasoning_mode: str = "disabled"

"""Contracts and request configuration shared by LLM adapters."""

from dataclasses import dataclass
from typing import Any, Protocol


class LLMProviderError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class LLMProvider(Protocol):
    provider_name: str
    model_name: str

    def generate_json(self, *, system_prompt: str, user_prompt: str, temperature: float = 0) -> dict[str, Any]:
        ...

    def generate_stream_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        on_token: Any = None,
        temperature: float = 0,
    ) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class LLMRequestConfig:
    base_url: str
    model: str
    api_key: str = ""
    timeout_seconds: float = 60.0
    max_retries: int = 1
    retry_backoff_seconds: float = 0.2
    context_length: int | None = None

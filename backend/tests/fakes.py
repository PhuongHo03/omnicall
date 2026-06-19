from __future__ import annotations

from backend.providers.embedding_provider import TextEmbedding
from backend.providers.guardrail_provider import GuardrailResult


class TestEmbeddingProvider:
    provider_name = "test-model-embedding"
    model_name = "test-embedding-model"

    def __init__(self, dimensions: int = 8) -> None:
        self.dimensions = dimensions

    def embed_text(self, text: str) -> TextEmbedding:
        vector = [0.0] * self.dimensions
        for index, character in enumerate(text.lower().encode("utf-8")):
            vector[index % self.dimensions] += (character % 31) / 31
        norm = sum(value * value for value in vector) ** 0.5 or 1.0
        return TextEmbedding(
            provider_name=self.provider_name,
            model_name=self.model_name,
            vector=[round(value / norm, 6) for value in vector],
        )


class TestGuardrailProvider:
    provider_name = "test-model-guardrail"
    model_name = "test-guardrail-model"

    def check(self, *, kind, text, metadata=None):
        lowered = text.lower()
        if "ignore previous" in lowered or "reveal the system prompt" in lowered:
            return GuardrailResult(
                action="block",
                categories=["prompt_injection"],
                confidence=0.96,
                provider=self.provider_name,
                model=self.model_name,
                safe_message="Tôi không thể xử lý yêu cầu này.",
            )
        if kind == "answer" and "without the provided meeting evidence" in lowered:
            return GuardrailResult(
                action="block",
                categories=["unsupported_answer"],
                confidence=0.92,
                provider=self.provider_name,
                model=self.model_name,
                safe_message="Không đủ bằng chứng trong dữ liệu cuộc họp để trả lời câu hỏi này.",
            )
        return GuardrailResult(
            action="allow",
            categories=["safe"],
            confidence=0.9,
            provider=self.provider_name,
            model=self.model_name,
        )


class CollectingOperationalLogService:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, **event) -> None:
        self.events.append(event)

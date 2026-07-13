import json
import time
from dataclasses import dataclass
from typing import Protocol, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from backend.configs.settings import Settings, get_settings
from backend.providers.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError


class EmbeddingProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class TextEmbedding:
    provider_name: str
    model_name: str
    vector: list[float]
    contract_version: str = "v1"


class TextEmbeddingProvider(Protocol):
    provider_name: str
    model_name: str

    def embed_text(self, text: str) -> TextEmbedding:
        ...

    def embed_texts(self, texts: Sequence[str]) -> list[TextEmbedding]:
        ...


class OllamaEmbeddingProvider:
    provider_name = "ollama-embedding"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.model_name = self.settings.embedding_model
        self.base_url = self.settings.ollama_base_url
        self.expected_dimensions = self.settings.embedding_dimensions
        self.contract_version = self.settings.embedding_contract_version
        self.batch_size = max(1, self.settings.embedding_batch_size)
        self._breaker = CircuitBreaker(
            "ollama-embedding",
            failure_threshold=self.settings.circuit_breaker_failure_threshold,
            recovery_seconds=self.settings.circuit_breaker_recovery_seconds,
            enabled=self.settings.circuit_breaker_enabled,
        )
        self.last_batch_count = 0
        self.last_input_count = 0

    def embed_text(self, text: str) -> TextEmbedding:
        return self.embed_texts([text])[0]

    def embed_texts(self, texts: Sequence[str]) -> list[TextEmbedding]:
        values = list(texts)
        if not values or any(not isinstance(text, str) or not text.strip() for text in values):
            raise EmbeddingProviderError("Embedding input must contain non-empty text values.")
        self.last_batch_count = (len(values) + self.batch_size - 1) // self.batch_size
        self.last_input_count = len(values)
        results: list[TextEmbedding] = []
        for start in range(0, len(values), self.batch_size):
            batch = values[start : start + self.batch_size]
            response = self._post_with_retry(batch)
            vectors = _extract_embeddings(
                response,
                expected_count=len(batch),
                expected_dimensions=self.expected_dimensions,
            )
            results.extend(
                TextEmbedding(
                    provider_name=self.provider_name,
                    model_name=self.model_name,
                    vector=vector,
                    contract_version=self.contract_version,
                )
                for vector in vectors
            )
        return results

    def _post_with_retry(self, texts: list[str]) -> dict:
        attempts = max(0, self.settings.embedding_max_retries) + 1
        last_error: EmbeddingProviderError | None = None
        for attempt in range(attempts):
            try:
                return self._breaker.call(
                    self._post_json,
                    "api/embed",
                    {"model": self.model_name, "input": texts if len(texts) > 1 else texts[0]},
                )
            except CircuitBreakerOpenError as exc:
                raise EmbeddingProviderError(str(exc)) from exc
            except EmbeddingProviderError as exc:
                last_error = exc
                if attempt + 1 >= attempts:
                    break
                time.sleep(self.settings.embedding_retry_backoff_seconds * (2**attempt))
        raise last_error or EmbeddingProviderError("Embedding model request failed.")

    def _post_json(self, path: str, payload: dict) -> dict:
        url = urljoin(_ensure_trailing_slash(self.base_url), path)
        body = json.dumps(payload).encode("utf-8")
        request = Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urlopen(request, timeout=self.settings.embedding_timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise EmbeddingProviderError(f"Embedding model request failed: HTTP {exc.code}") from exc
        except (URLError, TimeoutError) as exc:
            raise EmbeddingProviderError(f"Embedding model request failed: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise EmbeddingProviderError("Embedding model response was not valid JSON.") from exc


def get_embedding_provider(settings: Settings | None = None) -> TextEmbeddingProvider:
    return OllamaEmbeddingProvider(settings or get_settings())


def _extract_embedding(response: dict) -> list[float]:
    if isinstance(response.get("embedding"), list):
        return _coerce_vector(response["embedding"])
    embeddings = response.get("embeddings")
    if isinstance(embeddings, list) and embeddings and isinstance(embeddings[0], list):
        return _coerce_vector(embeddings[0])
    raise EmbeddingProviderError("Embedding model response did not include an embedding vector.")


def _extract_embeddings(response: dict, *, expected_count: int, expected_dimensions: int) -> list[list[float]]:
    embeddings = response.get("embeddings")
    if isinstance(embeddings, list) and embeddings and all(isinstance(item, list) for item in embeddings):
        vectors = [_coerce_vector(item) for item in embeddings]
    elif expected_count == 1:
        if isinstance(embeddings, list) and all(isinstance(item, int | float) for item in embeddings):
            vectors = [_coerce_vector(embeddings)]
        else:
            vectors = [_extract_embedding(response)]
    else:
        raise EmbeddingProviderError("Embedding model response did not include a complete batch.")
    if len(vectors) != expected_count:
        raise EmbeddingProviderError(
            f"Embedding model returned {len(vectors)} vectors; expected {expected_count}."
        )
    for vector in vectors:
        if len(vector) != expected_dimensions:
            raise EmbeddingProviderError(
                f"Embedding model returned {len(vector)} dimensions; expected {expected_dimensions}."
            )
    return vectors


def _coerce_vector(values: list) -> list[float]:
    vector = []
    for value in values:
        if not isinstance(value, int | float):
            raise EmbeddingProviderError("Embedding vector must contain only numbers.")
        vector.append(float(value))
    return vector


def _ensure_trailing_slash(value: str) -> str:
    return value if value.endswith("/") else f"{value}/"

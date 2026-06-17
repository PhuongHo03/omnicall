import json
from dataclasses import dataclass
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from backend.configs.settings import Settings, get_settings


class EmbeddingProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class TextEmbedding:
    provider_name: str
    model_name: str
    vector: list[float]


class TextEmbeddingProvider(Protocol):
    provider_name: str
    model_name: str

    def embed_text(self, text: str) -> TextEmbedding:
        ...


class OllamaEmbeddingProvider:
    provider_name = "ollama-embedding"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.model_name = self.settings.embedding_model
        self.base_url = self.settings.ollama_base_url
        self.expected_dimensions = self.settings.embedding_dimensions

    def embed_text(self, text: str) -> TextEmbedding:
        response = self._post_json(
            "api/embed",
            {
                "model": self.model_name,
                "input": text,
            },
        )
        vector = _extract_embedding(response)
        if len(vector) != self.expected_dimensions:
            raise EmbeddingProviderError(
                f"Embedding model returned {len(vector)} dimensions; expected {self.expected_dimensions}."
            )
        return TextEmbedding(
            provider_name=self.provider_name,
            model_name=self.model_name,
            vector=vector,
        )

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


def _coerce_vector(values: list) -> list[float]:
    vector = []
    for value in values:
        if not isinstance(value, int | float):
            raise EmbeddingProviderError("Embedding vector must contain only numbers.")
        vector.append(float(value))
    return vector


def _ensure_trailing_slash(value: str) -> str:
    return value if value.endswith("/") else f"{value}/"

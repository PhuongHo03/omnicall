import hashlib
import math
import re
from dataclasses import dataclass

from backend.configs.settings import Settings, get_settings


@dataclass(frozen=True)
class TextEmbedding:
    provider_name: str
    model_name: str
    vector: list[float]


class LocalHashEmbeddingProvider:
    provider_name = "local-hash-embedding"
    model_name = "hashing-v1"

    def __init__(self, dimensions: int = 64) -> None:
        self.dimensions = dimensions

    def embed_text(self, text: str) -> TextEmbedding:
        vector = [0.0 for _ in range(self.dimensions)]
        for token in _tokenize(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return TextEmbedding(
            provider_name=self.provider_name,
            model_name=self.model_name,
            vector=[round(value / norm, 6) for value in vector],
        )


def get_embedding_provider(settings: Settings | None = None) -> LocalHashEmbeddingProvider:
    resolved = settings or get_settings()
    # External/API embedding providers are wired in a later retrieval slice.
    return LocalHashEmbeddingProvider(dimensions=resolved.embedding_dimensions)


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[\wÀ-ỹ]+", text.lower(), flags=re.UNICODE)

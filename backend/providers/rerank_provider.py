import json
import shlex
import subprocess
from typing import Any, Protocol

from backend.configs.model_runtime import RERANK_COMMAND, RERANK_MODEL
from backend.configs.settings import Settings, get_settings


class RerankProviderError(RuntimeError):
    pass


class RerankProvider(Protocol):
    provider_name: str
    model_name: str

    def rerank(self, *, query: str, chunks: list[Any], output_k: int) -> list[Any]:
        ...


class LocalModelRerankProvider:
    provider_name = "local-model-rerank"

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        command_template: str = RERANK_COMMAND,
        model_name: str = RERANK_MODEL,
    ) -> None:
        self.settings = settings or get_settings()
        self.command_template = command_template
        self.model_name = model_name

    def rerank(self, *, query: str, chunks: list[Any], output_k: int) -> list[Any]:
        if not chunks:
            return []
        payload = {
            "model": self.model_name,
            "query": query,
            "chunks": [
                {
                    "chunkId": item.record.chunk_id,
                    "sourceType": item.record.source_type,
                    "sectionType": item.record.section_type,
                    "text": item.record.text,
                    "score": float(getattr(item, "score", 0.0)),
                }
                for item in chunks
            ],
            "outputK": output_k,
        }
        command_text = self.command_template
        try:
            completed = subprocess.run(
                shlex.split(command_text),
                input=json.dumps(payload, ensure_ascii=False),
                capture_output=True,
                text=True,
                timeout=self.settings.rerank_timeout_seconds,
                check=False,
            )
        except OSError as exc:
            raise RerankProviderError("Local rerank model command could not start.") from exc
        if completed.returncode != 0:
            raise RerankProviderError("Local rerank model command failed.")
        try:
            response = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise RerankProviderError("Local rerank model response was not valid JSON.") from exc
        ranked_ids = response.get("rankedChunkIds")
        if not isinstance(ranked_ids, list):
            raise RerankProviderError("Local rerank model response did not include rankedChunkIds.")
        by_id = {item.record.chunk_id: item for item in chunks}
        ranked = [by_id[chunk_id] for chunk_id in ranked_ids if isinstance(chunk_id, str) and chunk_id in by_id]
        ranked.extend(item for item in chunks if item.record.chunk_id not in {rank.record.chunk_id for rank in ranked})
        return ranked[:output_k]


def get_rerank_provider(settings: Settings | None = None) -> RerankProvider:
    return LocalModelRerankProvider(settings or get_settings())

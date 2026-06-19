import json
from dataclasses import dataclass
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from backend.configs.settings import Settings, get_settings
from backend.models.meeting_models import MeetingChunkRecord


class VectorProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class VectorSearchHit:
    chunk_id: str
    score: float


class VectorProvider(Protocol):
    enabled: bool
    provider_name: str

    def upsert_chunks(self, chunks: list[MeetingChunkRecord]) -> dict:
        ...

    def search_chunk_ids(
        self,
        *,
        workspace_id: str,
        meeting_id: str,
        query_vector: list[float],
        limit: int,
    ) -> list[VectorSearchHit]:
        ...

    def delete_meeting(self, *, workspace_id: str, meeting_id: str) -> dict:
        ...


class NoopVectorProvider:
    enabled = False
    provider_name = "postgres-fallback"

    def upsert_chunks(self, chunks: list[MeetingChunkRecord]) -> dict:
        return {"provider": self.provider_name, "status": "skipped", "chunkCount": len(chunks)}

    def search_chunk_ids(
        self,
        *,
        workspace_id: str,
        meeting_id: str,
        query_vector: list[float],
        limit: int,
    ) -> list[VectorSearchHit]:
        return []

    def delete_meeting(self, *, workspace_id: str, meeting_id: str) -> dict:
        return {"provider": self.provider_name, "status": "skipped"}


class MilvusVectorProvider:
    enabled = True
    provider_name = "milvus-rest"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.collection_name = self.settings.milvus_collection
        self.dimensions = self.settings.embedding_dimensions
        self.base_url = f"http://{self.settings.milvus_host}:{self.settings.milvus_port}"
        self._collection_ready = False

    def upsert_chunks(self, chunks: list[MeetingChunkRecord]) -> dict:
        if not chunks:
            return {"provider": self.provider_name, "status": "skipped", "chunkCount": 0}
        self._ensure_collection()
        first = chunks[0]
        self._post(
            "v2/vectordb/entities/delete",
            {
                "collectionName": self.collection_name,
                "filter": self._meeting_filter(first.meeting_id),
            },
        )
        entities = [self._entity(chunk) for chunk in chunks if isinstance(chunk.embedding, list)]
        if entities:
            self._post(
                "v2/vectordb/entities/insert",
                {
                    "collectionName": self.collection_name,
                    "data": entities,
                },
            )
            self._post("v2/vectordb/collections/load", {"collectionName": self.collection_name})
        return {"provider": self.provider_name, "status": "upserted", "chunkCount": len(entities)}

    def search_chunk_ids(
        self,
        *,
        workspace_id: str,
        meeting_id: str,
        query_vector: list[float],
        limit: int,
    ) -> list[VectorSearchHit]:
        if len(query_vector) != self.dimensions:
            raise VectorProviderError("Query vector dimension does not match Milvus collection dimension.")
        self._ensure_collection()
        response = self._post(
            "v2/vectordb/entities/search",
            {
                "collectionName": self.collection_name,
                "data": [query_vector],
                "annsField": "embedding",
                "filter": self._meeting_filter(meeting_id),
                "limit": limit,
                "outputFields": ["chunk_id"],
                "searchParams": {"metricType": "COSINE", "params": {}},
            },
        )
        hits: list[VectorSearchHit] = []
        for item in response.get("data", []):
            chunk_id = item.get("chunk_id")
            if isinstance(chunk_id, str):
                hits.append(VectorSearchHit(chunk_id=chunk_id, score=float(item.get("distance", 0.0))))
        return hits

    def delete_meeting(self, *, workspace_id: str, meeting_id: str) -> dict:
        self._ensure_collection()
        self._post(
            "v2/vectordb/entities/delete",
            {
                "collectionName": self.collection_name,
                "filter": self._meeting_filter(meeting_id),
            },
        )
        return {"provider": self.provider_name, "status": "deleted"}

    def _ensure_collection(self) -> None:
        if self._collection_ready:
            return
        response = self._post(
            "v2/vectordb/collections/has",
            {"collectionName": self.collection_name},
        )
        collection_exists = response.get("data", {}).get("has", False)
        if collection_exists and not self._collection_matches_schema():
            self._post("v2/vectordb/collections/drop", {"collectionName": self.collection_name})
            collection_exists = False
        if not collection_exists:
            self._post(
                "v2/vectordb/collections/create",
                {
                    "collectionName": self.collection_name,
                    "schema": {
                        "autoID": False,
                        "enableDynamicField": False,
                        "fields": [
                            _varchar_field("id", max_length=300, is_primary=True),
                            {"fieldName": "embedding", "dataType": "FloatVector", "elementTypeParams": {"dim": self.dimensions}},
                            _varchar_field("meeting_id", max_length=80),
                            _varchar_field("result_id", max_length=80),
                            _varchar_field("chunk_id", max_length=180),
                            _varchar_field("json_pointer", max_length=600),
                            _varchar_field("source_type", max_length=80),
                            _varchar_field("section_type", max_length=180),
                            {"fieldName": "start_ms", "dataType": "Int64"},
                            {"fieldName": "end_ms", "dataType": "Int64"},
                        ],
                    },
                    "indexParams": [
                        {
                            "fieldName": "embedding",
                            "indexName": "embedding",
                            "metricType": "COSINE",
                            "params": {"index_type": "AUTOINDEX"},
                        }
                    ],
                },
            )
        self._post("v2/vectordb/collections/load", {"collectionName": self.collection_name})
        self._collection_ready = True

    def _collection_matches_schema(self) -> bool:
        response = self._post(
            "v2/vectordb/collections/describe",
            {"collectionName": self.collection_name},
        )
        fields = response.get("data", {}).get("fields", [])
        names = {field.get("name") for field in fields}
        if "workspace_id" in names or "meeting_id" not in names:
            return False
        for field in fields:
            if field.get("name") != "embedding":
                continue
            for param in field.get("params", []):
                if param.get("key") == "dim":
                    try:
                        return int(param.get("value")) == self.dimensions
                    except (TypeError, ValueError):
                        return False
        return False

    def _entity(self, chunk: MeetingChunkRecord) -> dict:
        return {
            "id": f"{chunk.meeting_id}:{chunk.chunk_id}",
            "embedding": chunk.embedding,
            "meeting_id": chunk.meeting_id,
            "result_id": chunk.intelligence_result_id,
            "chunk_id": chunk.chunk_id,
            "json_pointer": chunk.json_pointer,
            "source_type": chunk.source_type,
            "section_type": chunk.section_type,
            "start_ms": chunk.start_ms if chunk.start_ms is not None else -1,
            "end_ms": chunk.end_ms if chunk.end_ms is not None else -1,
        }

    def _post(self, path: str, payload: dict) -> dict:
        url = urljoin(_ensure_trailing_slash(self.base_url), path)
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Request-Timeout": "5"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=5) as response:
                body = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise VectorProviderError(f"Milvus request failed: HTTP {exc.code}") from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise VectorProviderError(f"Milvus request failed: {exc}") from exc
        if body.get("code") not in {0, 200, None}:
            raise VectorProviderError(f"Milvus request failed: {body.get('message') or body}")
        return body

    @staticmethod
    def _meeting_filter(meeting_id: str) -> str:
        return f'meeting_id == "{_safe_filter_value(meeting_id)}"'


def get_vector_provider(settings: Settings | None = None) -> VectorProvider:
    resolved = settings or get_settings()
    if resolved.vector_provider.strip().lower() == "milvus":
        return MilvusVectorProvider(resolved)
    return NoopVectorProvider()


def _ensure_trailing_slash(value: str) -> str:
    return value if value.endswith("/") else f"{value}/"


def _varchar_field(field_name: str, *, max_length: int, is_primary: bool = False) -> dict:
    field = {
        "fieldName": field_name,
        "dataType": "VarChar",
        "elementTypeParams": {"max_length": max_length},
    }
    if is_primary:
        field["isPrimary"] = True
    return field


def _safe_filter_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')

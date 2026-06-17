import unittest

from backend.configs.settings import Settings
from backend.providers.vector_provider import MilvusVectorProvider


class RecordingMilvusProvider(MilvusVectorProvider):
    def __init__(self) -> None:
        super().__init__(Settings(EMBEDDING_DIMENSIONS=768))
        self.calls: list[tuple[str, dict]] = []

    def _post(self, path: str, payload: dict) -> dict:
        self.calls.append((path, payload))
        if path.endswith("/has"):
            return {"data": {"has": True}}
        if path.endswith("/describe"):
            return {
                "data": {
                    "fields": [
                        {"name": "embedding", "params": [{"key": "dim", "value": "64"}]},
                    ]
                }
            }
        return {"code": 0, "data": {}}


class VectorProviderTestCase(unittest.TestCase):
    def test_milvus_collection_is_recreated_when_embedding_dimension_changes(self) -> None:
        provider = RecordingMilvusProvider()

        provider._ensure_collection()

        paths = [path for path, _ in provider.calls]
        self.assertIn("v2/vectordb/collections/drop", paths)
        self.assertIn("v2/vectordb/collections/create", paths)


if __name__ == "__main__":
    unittest.main()

import unittest

from backend.configs.settings import Settings
from backend.providers.embedding_provider import EmbeddingProviderError, OllamaEmbeddingProvider


class EmbeddingProviderTestCase(unittest.TestCase):
    def _provider(self, **overrides) -> OllamaEmbeddingProvider:
        values = {
            "OLLAMA_BASE_URL": "http://ollama:11434",
            "EMBEDDING_DIMENSIONS": 3,
            "EMBEDDING_BATCH_SIZE": 2,
            "EMBEDDING_MAX_RETRIES": 0,
            "CIRCUIT_BREAKER_ENABLED": False,
        }
        values.update(overrides)
        return OllamaEmbeddingProvider(Settings(**values))

    def test_batch_response_preserves_order_and_validates_dimension(self) -> None:
        provider = self._provider()
        calls = []

        def post_json(path, payload):
            calls.append((path, payload))
            return {"embeddings": [[1, 0, 0], [0, 1, 0]]}

        provider._post_json = post_json
        results = provider.embed_texts(["first", "second"])

        self.assertEqual(calls[0][1]["input"], ["first", "second"])
        self.assertEqual([item.vector for item in results], [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
        self.assertEqual(results[0].contract_version, "v1")

    def test_batch_embedding_splits_into_configured_batches(self) -> None:
        provider = self._provider(EMBEDDING_BATCH_SIZE=2)
        inputs = []

        def post_json(path, payload):
            inputs.append(payload["input"])
            batch = payload["input"] if isinstance(payload["input"], list) else [payload["input"]]
            return {"embeddings": [[1, 0, 0] for _ in batch]}

        provider._post_json = post_json
        provider.embed_texts(["one", "two", "three"])

        self.assertEqual(inputs, [["one", "two"], "three"])

    def test_dimension_mismatch_is_rejected(self) -> None:
        provider = self._provider()
        provider._post_json = lambda path, payload: {"embeddings": [[1, 0]]}

        with self.assertRaises(EmbeddingProviderError):
            provider.embed_texts(["bad vector"])

    def test_empty_or_malformed_input_is_rejected(self) -> None:
        provider = self._provider()
        with self.assertRaises(EmbeddingProviderError):
            provider.embed_texts([])
        provider._post_json = lambda path, payload: {"unexpected": True}
        with self.assertRaises(EmbeddingProviderError):
            provider.embed_text("malformed")

    def test_transient_failure_retries_with_backoff(self) -> None:
        provider = self._provider(EMBEDDING_MAX_RETRIES=1, EMBEDDING_RETRY_BACKOFF_SECONDS=0)
        attempts = {"count": 0}

        def post_json(path, payload):
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise EmbeddingProviderError("temporary failure")
            return {"embedding": [1, 0, 0]}

        provider._post_json = post_json
        result = provider.embed_text("retry me")

        self.assertEqual(attempts["count"], 2)
        self.assertEqual(len(result.vector), 3)

    def test_retry_exhaustion_raises_typed_error(self) -> None:
        provider = self._provider(EMBEDDING_MAX_RETRIES=1, EMBEDDING_RETRY_BACKOFF_SECONDS=0)
        attempts = {"count": 0}

        def post_json(path, payload):
            attempts["count"] += 1
            raise EmbeddingProviderError("service unavailable")

        provider._post_json = post_json
        with self.assertRaises(EmbeddingProviderError):
            provider.embed_text("fail")
        self.assertEqual(attempts["count"], 2)


if __name__ == "__main__":
    unittest.main()

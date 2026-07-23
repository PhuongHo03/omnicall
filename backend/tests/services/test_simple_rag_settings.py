import unittest

from pydantic import ValidationError

from backend.configs.settings import Settings, simple_rag_runtime_summary


class SimpleRAGSettingsTestCase(unittest.TestCase):
    def test_direct_cutover_defaults(self) -> None:
        settings = Settings(_env_file=None)
        self.assertEqual(settings.rag_query_interpretation_timeout_seconds, 15)
        self.assertEqual(settings.rag_evidence_retrieval_timeout_seconds, 20)
        self.assertEqual(settings.rag_synthesis_primary_timeout_seconds, 60)
        self.assertEqual(settings.rag_synthesis_fallback_timeout_seconds, 40)
        self.assertEqual(settings.rag_chat_turn_timeout_seconds, 150)
        self.assertEqual(settings.rag_synthesis_contract_retries, 1)
        self.assertEqual(settings.llm_reasoning_mode, "disabled")

    def test_contract_retry_cannot_be_disabled_or_increased(self) -> None:
        for retries in (0, 2):
            with self.assertRaises(ValidationError):
                Settings(_env_file=None, RAG_SYNTHESIS_CONTRACT_RETRIES=retries)

    def test_turn_lease_covers_full_turn(self) -> None:
        with self.assertRaises(ValidationError):
            Settings(_env_file=None, CHAT_TURN_LEASE_SECONDS=179)

    def test_runtime_summary_has_source_contracts_and_no_secret(self) -> None:
        summary = simple_rag_runtime_summary(Settings(_env_file=None, LLM_API_KEY="secret"))
        self.assertEqual(summary["pipelineContract"], "simple-rag.v1")
        self.assertNotIn("secret", repr(summary))


if __name__ == "__main__":
    unittest.main()

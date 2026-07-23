import unittest
from types import SimpleNamespace

from backend.services.chat_service import _public_metadata
from backend.utils.secret_redaction import redact_secrets


class ChatServiceContractTestCase(unittest.TestCase):
    def test_public_metadata_exposes_only_pipeline_trace(self) -> None:
        message = SimpleNamespace(
            role="assistant",
            metadata_json={
                "evidenceState": "grounded",
                "answerOriginKind": "llm_synthesis",
                "pipelineTrace": {"version": 1, "stages": []},
                "agentFlow": {"version": 1},
                "agentRawFlow": {"version": 1},
            },
        )
        metadata = _public_metadata(message)
        self.assertIn("pipelineTrace", metadata)
        self.assertNotIn("agentFlow", metadata)
        self.assertNotIn("agentRawFlow", metadata)

    def test_credentials_are_redacted_before_persistence(self) -> None:
        redacted, found = redact_secrets("key nvapi-abcdefghijklmnopqrstuvwxyz")
        self.assertTrue(found)
        self.assertNotIn("nvapi-", redacted)

    def test_common_credential_shapes_are_redacted(self) -> None:
        samples = (
            "sk-1234567890abcdefghijklmnop",
            "nvapi-1234567890abcdefghijklmnop",
            "Bearer abcdefghijklmnopqrstuvwxyz123456",
            "password=correct-horse-battery-staple",
            "api_key: abcdefghijklmnopqrstuvwxyz",
            "eyJabcdefghijk.abcdefghijk.abcdefghijk",
        )
        for sample in samples:
            with self.subTest(sample=sample[:8]):
                redacted, found = redact_secrets(sample)
                self.assertTrue(found)
                self.assertNotEqual(redacted, sample)


if __name__ == "__main__":
    unittest.main()

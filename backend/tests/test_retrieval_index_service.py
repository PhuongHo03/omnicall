import unittest

from backend.tests.fakes import TestEmbeddingProvider
from backend.services.retrieval_index_service import build_retrieval_chunks


class RetrievalIndexServiceTestCase(unittest.TestCase):
    def test_build_retrieval_chunks_prefers_structured_json_sections(self) -> None:
        provider = TestEmbeddingProvider(dimensions=8)
        result_json = {
            "meeting": {
                "id": "meeting-001",
                "title": "Retrieval planning call",
                "durationSeconds": 120,
            },
            "source": {
                "analysisProvider": "llm-analysis",
                "analysisModel": "test-analysis-model",
                "llmProvider": "test-llm",
                "generatedAt": "2026-06-25T00:00:00Z",
                "voiceMetadata": {
                    "asrProvider": "faster-whisper",
                    "diarizationProvider": "wespeaker",
                    "warnings": ["low volume"],
                },
            },
            "participants": [
                {
                    "name": "Alice",
                    "role": "Product owner",
                    "details": "Led the retrieval discussion.",
                    "citationIds": ["cite-001"],
                },
                {
                    "speaker": "Bob",
                    "role": "Engineer",
                    "details": "Owns indexing work.",
                    "citationIds": ["cite-002"],
                },
            ],
            "transcript": {
                "coverage": {
                    "status": "model-derived",
                    "coveredAssetIds": ["asset-001"],
                },
                "segments": [
                    {
                        "id": "seg-001",
                        "speaker": "Alice",
                        "startMs": 0,
                        "endMs": 5000,
                        "text": "We decided to use processed JSON as the chatbot knowledge source.",
                    },
                    {
                        "id": "seg-002",
                        "speaker": "Bob",
                        "startMs": 5000,
                        "endMs": 12000,
                        "text": "Action item: Bob will index action items and risks by Friday.",
                    },
                    {
                        "id": "seg-noise",
                        "speaker": "Alice",
                        "startMs": 12000,
                        "endMs": 13000,
                        "text": "ok",
                    },
                ]
            },
            "summary": {
                "executive": "The team agreed that processed meeting JSON is the primary chatbot knowledge base.",
                "detailed": [{"title": "Retrieval", "text": "Structured sections should outrank transcript fallback.", "citationIds": ["cite-001"]}],
                "keyPoints": [{"text": "Meeting chat must cite transcript evidence.", "citationIds": ["cite-001"]}],
            },
            "analysis": {
                "decisions": [{"id": "decision-001", "text": "Use processed JSON for RAG.", "citationIds": ["cite-001"]}],
                "actionItems": [{"id": "action-001", "owner": "Bob", "task": "Index action items and risks by Friday.", "citationIds": ["cite-002"]}],
                "risks": [{"id": "risk-001", "text": "Low quality transcript segments may reduce answer confidence.", "citationIds": ["cite-002"]}],
                "emptySections": {"timeline": "No timeline evidence."},
            },
            "citations": [
                {"id": "cite-001", "segmentIds": ["seg-001"], "startMs": 0, "endMs": 5000},
                {"id": "cite-002", "segmentIds": ["seg-002"], "startMs": 5000, "endMs": 12000},
            ],
            "quality": {"coverage": "partial", "warnings": ["low volume"], "confidence": 0.75},
        }

        chunks = build_retrieval_chunks(result_json, embedding_provider=provider)
        by_id = {chunk["chunkId"]: chunk for chunk in chunks}

        self.assertIn("summary-executive", by_id)
        self.assertIn("meeting-metadata", by_id)
        self.assertIn("source-processing", by_id)
        self.assertIn("source-voice-metadata", by_id)
        self.assertIn("participants-overview", by_id)
        self.assertIn("participants.participant-001", by_id)
        self.assertIn("transcript-coverage", by_id)
        self.assertIn("analysis.emptySections-001", by_id)
        self.assertIn("quality-overview", by_id)
        self.assertIn("quality.warning-001", by_id)
        self.assertIn("citations-map", by_id)
        self.assertIn("analysis.actionItems-001", by_id)
        self.assertIn("analysis.risks-001", by_id)
        self.assertIn("transcript-seg-001", by_id)
        self.assertNotIn("transcript-seg-noise", by_id)

        action_chunk = by_id["analysis.actionItems-001"]
        self.assertEqual(action_chunk["sourceType"], "structured")
        self.assertEqual(action_chunk["jsonPointer"], "/analysis/actionItems/0")
        self.assertIn("owner: Bob", action_chunk["text"])
        self.assertIn("task: Index action items and risks by Friday.", action_chunk["text"])
        self.assertEqual(action_chunk["citationIds"], ["cite-002"])
        self.assertEqual(action_chunk["segmentIds"], ["seg-002"])
        self.assertEqual(action_chunk["startMs"], 5000)
        self.assertEqual(action_chunk["endMs"], 12000)
        self.assertLess(action_chunk["metadata"]["priority"], by_id["transcript-seg-001"]["metadata"]["priority"])

        participant_overview = by_id["participants-overview"]
        self.assertIn("participant Count: 2", participant_overview["text"])
        self.assertIn("Alice", participant_overview["text"])
        self.assertIn("Bob", participant_overview["text"])

        participant_chunk = by_id["participants.participant-001"]
        self.assertIn("role: Product owner", participant_chunk["text"])
        self.assertIn("details: Led the retrieval discussion.", participant_chunk["text"])
        self.assertEqual(participant_chunk["segmentIds"], ["seg-001"])

        transcript_chunk = by_id["transcript-seg-001"]
        self.assertIn("speaker: Alice", transcript_chunk["text"])
        self.assertIn("text: We decided to use processed JSON", transcript_chunk["text"])

        quality_chunk = by_id["quality.warning-001"]
        self.assertIn("low volume", quality_chunk["text"])

        for chunk in chunks:
            self.assertEqual(len(chunk["embedding"]), 8)
            self.assertGreater(chunk["tokenCount"], 0)
            self.assertEqual(chunk["metadata"]["embeddingProvider"], "test-model-embedding")

    def test_test_embedding_provider_is_deterministic(self) -> None:
        provider = TestEmbeddingProvider(dimensions=8)

        first = provider.embed_text("processed JSON retrieval")
        second = provider.embed_text("processed JSON retrieval")

        self.assertEqual(first.vector, second.vector)
        self.assertEqual(first.model_name, "test-embedding-model")

    def test_build_retrieval_chunks_accepts_llm_string_sections_and_segment_cites(self) -> None:
        provider = TestEmbeddingProvider(dimensions=8)
        result_json = {
            "transcript": {
                "segments": [
                    {
                        "id": "seg-070",
                        "startMs": 70000,
                        "endMs": 76000,
                        "text": "The agent forwarded the case to corporate office for refund review.",
                    },
                ]
            },
            "summary": {
                "executive": "The customer called about a coat return and refund escalation.",
                "detailed": "The return request was outside the standard refund timeframe.",
                "keyPoints": [
                    "Customer followed up on a pending refund.",
                    "Corporate office will email an update in 2-4 business days.",
                ],
            },
            "analysis": {
                "topics": ["Product Return", "Refund Status Inquiry"],
                "decisions": ["Forward the return/refund inquiry to corporate office."],
                "actionItems": [
                    {
                        "item": "Provide the customer with an email update regarding the refund status.",
                        "cites": ["seg-070"],
                        "owner": "Corporate Office",
                    }
                ],
                "risks": ["Late return may delay refund processing."],
                "emptySections": ["metrics"],
            },
            "citations": [
                {"id": "cite-070", "segmentIds": ["seg-070"], "startMs": 70000, "endMs": 76000},
            ],
        }

        chunks = build_retrieval_chunks(result_json, embedding_provider=provider)
        by_id = {chunk["chunkId"]: chunk for chunk in chunks}

        self.assertIn("summary.detailed-001", by_id)
        self.assertIn("summary.keyPoints-001", by_id)
        self.assertIn("analysis.topics-001", by_id)
        self.assertIn("analysis.decisions-001", by_id)
        self.assertIn("analysis.actionItems-001", by_id)
        self.assertIn("analysis.risks-001", by_id)

        action_chunk = by_id["analysis.actionItems-001"]
        self.assertIn("item: Provide the customer with an email update regarding the refund status.", action_chunk["text"])
        self.assertIn("owner: Corporate Office", action_chunk["text"])
        self.assertEqual(action_chunk["segmentIds"], ["seg-070"])
        self.assertEqual(action_chunk["startMs"], 70000)
        self.assertEqual(action_chunk["endMs"], 76000)


if __name__ == "__main__":
    unittest.main()

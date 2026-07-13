import unittest

from backend.services.retrieval.chunk_builder import build_retrieval_chunks
from backend.services.retrieval.index_service import _index_generation
from backend.tests.fakes import TestEmbeddingProvider


class IncompleteEmbeddingProvider(TestEmbeddingProvider):
    def embed_texts(self, texts):
        return super().embed_texts(texts[:-1])


class RetrievalIndexServiceTestCase(unittest.TestCase):
    def test_index_generation_is_deterministic_and_content_sensitive(self) -> None:
        first = _index_generation(
            result_id="result-001",
            result_json={"summary": "one"},
            embedding_identity="ollama:model:v1:8",
        )
        same = _index_generation(
            result_id="result-001",
            result_json={"summary": "one"},
            embedding_identity="ollama:model:v1:8",
        )
        changed = _index_generation(
            result_id="result-001",
            result_json={"summary": "two"},
            embedding_identity="ollama:model:v1:8",
        )

        self.assertEqual(first, same)
        self.assertNotEqual(first, changed)

    def test_build_retrieval_chunks_uses_rag_first_knowledge_records(self) -> None:
        provider = TestEmbeddingProvider(dimensions=8)
        result_json = _rag_first_result()

        chunks = build_retrieval_chunks(result_json, embedding_provider=provider)
        self.assertEqual(provider.batch_calls, 1)
        by_id = {chunk["chunkId"]: chunk for chunk in chunks}

        self.assertIn("meeting-metadata", by_id)
        self.assertIn("source-processing", by_id)
        self.assertIn("speaker-stats", by_id)
        self.assertIn("participant-overview", by_id)
        self.assertIn("participant-profile-001", by_id)
        self.assertIn("fact-participant_count-001", by_id)
        self.assertIn("event-timeline-001", by_id)
        self.assertIn("entity-profile-001", by_id)
        self.assertIn("relationship-edge-001", by_id)
        self.assertIn("action-item-001", by_id)
        self.assertIn("decision-record-001", by_id)
        self.assertIn("risk-record-001", by_id)
        self.assertIn("question-record-001", by_id)
        self.assertIn("topic-summary-001", by_id)
        self.assertIn("summary-executive", by_id)
        self.assertIn("quality-overview", by_id)
        self.assertIn("extraction-overview", by_id)
        self.assertIn("evidence-map", by_id)
        self.assertIn("transcript-window-001", by_id)

        participant_count = by_id["fact-participant_count-001"]
        self.assertEqual(participant_count["sectionType"], "fact.participant_count")
        self.assertIn("value: 2", participant_count["text"])
        self.assertLess(participant_count["metadata"]["priority"], by_id["summary-executive"]["metadata"]["priority"])

        action_chunk = by_id["action-item-001"]
        self.assertEqual(action_chunk["jsonPointer"], "/actions/0")
        self.assertIn("task: Index action items and risks by Friday.", action_chunk["text"])
        self.assertEqual(action_chunk["citationIds"], ["cite-002"])
        self.assertEqual(action_chunk["segmentIds"], ["seg-002"])
        self.assertEqual(action_chunk["startMs"], 5000)
        self.assertEqual(action_chunk["endMs"], 12000)

        participant_chunk = by_id["participant-profile-001"]
        self.assertIn("display Name: Alice", participant_chunk["text"])
        self.assertIn("role: Product owner", participant_chunk["text"])

        transcript_chunk = by_id["transcript-window-001"]
        self.assertEqual(transcript_chunk["sectionType"], "transcript.window")
        self.assertIn("speaker Label: Alice", transcript_chunk["text"])

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

    def test_partial_batch_response_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_retrieval_chunks(
                _rag_first_result(),
                embedding_provider=IncompleteEmbeddingProvider(dimensions=8),
            )


def _rag_first_result() -> dict:
    return {
        "schemaVersion": "meeting-intelligence-result.v1",
        "meeting": {"id": "meeting-001", "title": "Retrieval planning call", "durationSeconds": 120},
        "source": {"analysisProvider": "llm-analysis", "analysisModel": "test-analysis-model", "llmProvider": "test-llm"},
        "transcript": {
            "coverage": {"status": "model-derived", "coveredAssetIds": ["asset-001"]},
            "segments": [
                {
                    "id": "seg-001",
                    "speakerLabel": "Alice",
                    "speaker": "Alice",
                    "startMs": 0,
                    "endMs": 5000,
                    "confidence": 0.9,
                    "text": "We decided to use processed JSON as the chatbot knowledge source.",
                },
                {
                    "id": "seg-002",
                    "speakerLabel": "Bob",
                    "speaker": "Bob",
                    "startMs": 5000,
                    "endMs": 12000,
                    "confidence": 0.86,
                    "text": "Action item: Bob will index action items and risks by Friday.",
                },
            ],
        },
        "evidence": {
            "citations": [
                {"id": "cite-001", "segmentIds": ["seg-001"], "startMs": 0, "endMs": 5000, "speakerLabels": ["Alice"], "quote": "We decided to use processed JSON.", "evidenceType": "direct_quote"},
                {"id": "cite-002", "segmentIds": ["seg-002"], "startMs": 5000, "endMs": 12000, "speakerLabels": ["Bob"], "quote": "Bob will index action items.", "evidenceType": "direct_quote"},
            ]
        },
        "speakers": {
            "speakerCount": 2,
            "identifiedParticipantCount": 2,
            "mentionedOnlyCount": 0,
            "items": [
                {"label": "Alice", "segmentCount": 1, "totalTalkTimeMs": 5000, "mappedParticipantId": "participant-001", "confidence": 0.9},
                {"label": "Bob", "segmentCount": 1, "totalTalkTimeMs": 7000, "mappedParticipantId": "participant-002", "confidence": 0.86},
            ],
        },
        "participants": [
            {"id": "participant-001", "displayName": "Alice", "speakerLabels": ["Alice"], "role": "Product owner", "isAttendee": True, "isMentionedOnly": False, "confidence": 0.9, "citationIds": ["cite-001"]},
            {"id": "participant-002", "displayName": "Bob", "speakerLabels": ["Bob"], "role": "Engineer", "isAttendee": True, "isMentionedOnly": False, "confidence": 0.86, "citationIds": ["cite-002"]},
        ],
        "entities": [{"id": "entity-001", "type": "system", "name": "RAG", "aliases": ["retrieval"], "citationIds": ["cite-001"]}],
        "facts": [{"id": "fact-001", "type": "participant_count", "subject": {"type": "meeting", "id": "meeting"}, "predicate": "has_speaker_count", "value": 2, "unit": "people", "confidence": 0.95, "derivedFrom": "speakers", "citationIds": []}],
        "events": [{"id": "event-001", "type": "decision_made", "title": "RAG source selected", "participantIds": ["participant-001"], "startMs": 0, "endMs": 5000, "status": "completed", "confidence": 0.9, "citationIds": ["cite-001"]}],
        "relationships": [{"id": "rel-001", "type": "owns", "from": {"type": "participant", "id": "participant-002"}, "to": {"type": "action", "id": "action-001"}, "confidence": 0.86, "citationIds": ["cite-002"]}],
        "topics": [{"id": "topic-001", "title": "Retrieval", "level": 1, "summary": "The team discussed RAG indexing.", "factIds": ["fact-001"], "eventIds": ["event-001"], "citationIds": ["cite-001"]}],
        "summaries": {"executive": {"text": "The team agreed that processed meeting JSON is the primary chatbot knowledge base.", "topicIds": ["topic-001"], "citationIds": ["cite-001"]}, "topicLevel": [], "timelineLevel": []},
        "actions": [{"id": "action-001", "task": "Index action items and risks by Friday.", "ownerParticipantId": "participant-002", "ownerName": "Bob", "status": "open", "confidence": 0.86, "citationIds": ["cite-002"]}],
        "decisions": [{"id": "decision-001", "text": "Use processed JSON for RAG.", "confidence": 0.9, "citationIds": ["cite-001"]}],
        "risks": [{"id": "risk-001", "text": "Low quality transcript segments may reduce answer confidence.", "confidence": 0.75, "citationIds": ["cite-002"]}],
        "questions": [{"id": "question-001", "text": "How should old chunks be rebuilt?", "status": "open", "citationIds": ["cite-001"]}],
        "quality": {"coverage": "partial", "warnings": ["low volume"], "confidence": 0.75},
        "extraction": {"overallConfidence": 0.82, "method": "llm_with_deterministic_verification", "unsupportedClaims": [], "warnings": []},
    }


if __name__ == "__main__":
    unittest.main()

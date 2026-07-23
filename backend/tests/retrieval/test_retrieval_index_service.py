import copy
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from backend.configs.settings import Settings
from backend.services.retrieval.chunk_builder import build_retrieval_chunks
from backend.services.retrieval.index_service import RetrievalIndexService, _index_generation
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
        self.assertNotIn("source-processing", by_id)
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
        self.assertNotIn("quality-overview", by_id)
        self.assertNotIn("extraction-overview", by_id)
        self.assertNotIn("evidence-map", by_id)
        self.assertIn("transcript-window-001", by_id)

        participant_count = by_id["fact-participant_count-001"]
        self.assertEqual(participant_count["sectionType"], "fact.participant_count")
        self.assertIn("value: 2", participant_count["text"])
        self.assertEqual(participant_count["citationIds"], ["json-record-fact-001"])
        participant_overview = by_id["participant-overview"]
        self.assertEqual(
            participant_overview["metadata"]["recordId"],
            "participant-overview",
        )
        self.assertEqual(
            participant_overview["metadata"]["recordFields"]["participantCount"],
            2,
        )
        self.assertEqual(
            participant_overview["metadata"]["recordFields"]["attendeeNames"],
            ["Alice", "Bob"],
        )
        self.assertEqual(
            participant_overview["citationIds"][0],
            "json-record-participant-overview",
        )
        self.assertEqual(by_id["meeting-metadata"]["citationIds"], ["json-meeting-metadata"])
        self.assertLess(participant_count["metadata"]["priority"], by_id["summary-executive"]["metadata"]["priority"])
        self.assertTrue(by_id["summary-executive"]["metadata"]["evidenceEligible"])
        self.assertEqual(
            by_id["topic-summary-001"]["metadata"]["recordFields"]["summary"],
            "The team discussed RAG indexing.",
        )

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
        self.assertEqual(transcript_chunk["citationIds"], ["cite-001", "cite-002"])
        self.assertEqual(transcript_chunk["metadata"]["evidenceRefs"], ["cite-001", "cite-002"])
        self.assertEqual(transcript_chunk["segmentIds"], ["seg-001", "seg-002"])
        self.assertEqual(transcript_chunk["startMs"], 0)
        self.assertEqual(transcript_chunk["endMs"], 12000)
        self.assertEqual(
            transcript_chunk["metadata"]["citationLocations"]["cite-001"]["segmentIds"],
            ["seg-001"],
        )

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

    def test_uncited_executive_summary_is_indexed_as_context_only(self) -> None:
        provider = TestEmbeddingProvider(dimensions=8)
        result_json = _rag_first_result()
        result_json["summaries"]["executive"]["citationIds"] = []
        result_json["summaries"]["executive"]["evidenceRefs"] = []
        result_json["summaries"]["executive"]["lineageStatus"] = "context_only"

        chunks = build_retrieval_chunks(result_json, embedding_provider=provider)
        executive = next(
            chunk for chunk in chunks if chunk["chunkId"] == "summary-executive"
        )

        self.assertEqual(executive["citationIds"], [])
        self.assertFalse(executive["metadata"]["evidenceEligible"])
        self.assertEqual(executive["metadata"]["lineageStatus"], "context_only")

    def test_participant_overview_uses_reliable_speaker_count_when_attendee_flags_are_false(self) -> None:
        provider = TestEmbeddingProvider(dimensions=8)
        result_json = _rag_first_result()
        participant_records = [
            record
            for record in result_json["knowledge"]["records"]
            if record.get("type") == "participant"
        ]
        for record in participant_records:
            record["data"]["isAttendee"] = False
            record["data"]["isMentionedOnly"] = False
        result_json["knowledge"]["records"].extend([
            {
                "id": "speaker-one",
                "type": "participant",
                "subtype": "speaker_profile",
                "data": {"displayName": "Speaker 1"},
                "scope": {"kind": "meeting"},
                "evidenceRefs": ["cite-001"],
                "sourceRefs": [],
                "derivedFrom": ["transcript.segments"],
                "confidence": 0.9,
                "status": "verified",
            },
            {
                "id": "speaker-two",
                "type": "participant",
                "subtype": "speaker_profile",
                "data": {"displayName": "Speaker 2"},
                "scope": {"kind": "meeting"},
                "evidenceRefs": ["cite-002"],
                "sourceRefs": [],
                "derivedFrom": ["transcript.segments"],
                "confidence": 0.9,
                "status": "verified",
            },
        ])
        result_json["speakers"] = {
            "speakerCount": 2,
            "ignoredSegmentCount": 0,
            "items": [
                {"label": "Speaker 1", "countsTowardParticipantCount": True},
                {"label": "Speaker 2", "countsTowardParticipantCount": True},
            ],
        }

        chunks = build_retrieval_chunks(result_json, embedding_provider=provider)
        overview = next(
            chunk for chunk in chunks if chunk["chunkId"] == "participant-overview"
        )
        fields = overview["metadata"]["recordFields"]

        self.assertEqual(fields["participantCount"], 2)
        self.assertEqual(fields["attendeeNames"], ["Speaker 1", "Speaker 2"])
        self.assertEqual(fields["countBasis"], "reliable_diarization_labels")

    def test_partial_batch_response_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_retrieval_chunks(
                _rag_first_result(),
                embedding_provider=IncompleteEmbeddingProvider(dimensions=8),
            )

    def test_transcript_windows_preserve_short_evidence_and_skip_noise_annotations(self) -> None:
        result_json = copy.deepcopy(_rag_first_result())
        result_json["transcript"]["segments"] = [
            {
                "id": "seg-001",
                "speakerLabel": "Alice",
                "speaker": "Alice",
                "startMs": 0,
                "endMs": 500,
                "confidence": 0.9,
                "text": "Yes.",
            },
            {
                "id": "seg-002",
                "speakerLabel": "Bob",
                "speaker": "Bob",
                "startMs": 500,
                "endMs": 1000,
                "confidence": 0.9,
                "text": "Adam",
            },
            {
                "id": "seg-003",
                "speakerLabel": "Alice",
                "speaker": "Alice",
                "startMs": 1000,
                "endMs": 1500,
                "confidence": 0.9,
                "text": "Thank you.",
            },
            {
                "id": "seg-004",
                "speakerLabel": "unknown",
                "speaker": "unknown",
                "startMs": 1500,
                "endMs": 2000,
                "confidence": 0.5,
                "text": "[silence]",
            },
        ]
        result_json["transcript"]["windows"] = [
            {
                "id": "window-001",
                "sequenceNo": 1,
                "segmentIds": ["seg-001", "seg-002", "seg-003", "seg-004"],
            }
        ]
        result_json["evidence"]["items"] = [
            {
                "id": f"cite-{index:03d}",
                "kind": "transcript",
                "segmentIds": [f"seg-{index:03d}"],
                "startMs": (index - 1) * 500,
                "endMs": index * 500,
                "quote": segment["text"],
            }
            for index, segment in enumerate(result_json["transcript"]["segments"], start=1)
        ]

        chunks = build_retrieval_chunks(
            result_json,
            embedding_provider=TestEmbeddingProvider(dimensions=8),
        )

        transcript_chunks = [
            chunk for chunk in chunks if chunk["sectionType"] == "transcript.window"
        ]
        self.assertEqual(len(transcript_chunks), 1)
        transcript_chunk = transcript_chunks[0]
        self.assertIn("text: Yes.", transcript_chunk["text"])
        self.assertIn("text: Adam", transcript_chunk["text"])
        self.assertIn("text: Thank you.", transcript_chunk["text"])
        self.assertNotIn("[silence]", transcript_chunk["text"])
        self.assertEqual(
            transcript_chunk["citationIds"],
            ["cite-001", "cite-002", "cite-003"],
        )
        self.assertEqual(
            transcript_chunk["metadata"]["sourceRefs"],
            ["window-001"],
        )
        self.assertEqual(transcript_chunk["jsonPointer"], "/transcript/segments/0")

    def test_rebuild_stales_memory_when_only_retrieval_contract_changes(self) -> None:
        session = MagicMock()
        vector_provider = MagicMock()
        vector_provider.provider_name = "test-vector"
        vector_provider.upsert_chunks.return_value = {"status": "upserted"}
        service = RetrievalIndexService(
            session,
            embedding_provider=TestEmbeddingProvider(dimensions=8),
            vector_provider=vector_provider,
            settings=Settings(_env_file=None),
        )
        service.chunks = MagicMock()
        service.chunks.current_snapshot.return_value = SimpleNamespace(
            index_generation="same-generation",
            embedding_identity="test-model-embedding:test-embedding-model:v1:8",
            retrieval_contract="v2",
        )
        record = SimpleNamespace(
            id="record-1",
            chunk_id="chunk-1",
            source_type="structured",
            section_type="fact.record",
            json_pointer="/knowledge/records/0",
            embedding=[0.1] * 8,
        )
        service.chunks.replace_for_result.return_value = [record]
        result = SimpleNamespace(
            id="result-1",
            meeting_id="meeting-1",
            result_json={"schemaVersion": "meeting-intelligence-result.v2"},
        )

        with (
            patch(
                "backend.services.retrieval.index_service.build_retrieval_chunks",
                return_value=[{"metadata": {}, "embedding": [0.1] * 8}],
            ),
            patch(
                "backend.services.retrieval.index_service._index_generation",
                return_value="same-generation",
            ),
        ):
            service.rebuild_for_result(result)

        service.chunks.upsert_snapshot.assert_called_once_with(
            meeting_id="meeting-1",
            intelligence_result_id="result-1",
            index_generation="same-generation",
            embedding_identity="test-model-embedding:test-embedding-model:v1:8",
            retrieval_contract="simple-retrieval.v1",
            chunk_count=1,
            error=None,
        )


def _rag_first_result() -> dict:
    return {
        "schemaVersion": "meeting-intelligence-result.v2",
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
            "items": [
                {"id": "cite-001", "kind": "transcript", "segmentIds": ["seg-001"], "startMs": 0, "endMs": 5000, "quote": "We decided to use processed JSON."},
                {"id": "cite-002", "kind": "transcript", "segmentIds": ["seg-002"], "startMs": 5000, "endMs": 12000, "quote": "Bob will index action items."},
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
        "knowledge": {
            "records": [
                {"id": "participant-001", "type": "participant", "subtype": "profile", "data": {"displayName": "Alice", "speakerLabels": ["Alice"], "role": "Product owner", "isAttendee": True, "isMentionedOnly": False}, "scope": {"kind": "meeting"}, "evidenceRefs": ["cite-001"], "sourceRefs": [], "derivedFrom": [], "confidence": 0.9, "status": "verified"},
                {"id": "participant-002", "type": "participant", "subtype": "profile", "data": {"displayName": "Bob", "speakerLabels": ["Bob"], "role": "Engineer", "isAttendee": True, "isMentionedOnly": False}, "scope": {"kind": "meeting"}, "evidenceRefs": ["cite-002"], "sourceRefs": [], "derivedFrom": [], "confidence": 0.86, "status": "verified"},
                {"id": "entity-001", "type": "entity", "subtype": "system", "data": {"name": "RAG", "aliases": ["retrieval"]}, "scope": {"kind": "meeting"}, "evidenceRefs": ["cite-001"], "sourceRefs": [], "derivedFrom": [], "confidence": 0.8, "status": "verified"},
                {"id": "fact-001", "type": "fact", "subtype": "participant_count", "data": {"subject": {"type": "meeting", "id": "meeting"}, "predicate": "has_speaker_count", "value": 2, "unit": "people"}, "scope": {"kind": "meeting"}, "evidenceRefs": [], "sourceRefs": [], "derivedFrom": ["speakers"], "confidence": 0.95, "status": "verified"},
                {"id": "event-001", "type": "event", "subtype": "decision_made", "data": {"title": "RAG source selected", "participantIds": ["participant-001"], "startMs": 0, "endMs": 5000, "status": "completed"}, "scope": {"kind": "meeting"}, "evidenceRefs": ["cite-001"], "sourceRefs": [], "derivedFrom": [], "confidence": 0.9, "status": "verified"},
                {"id": "rel-001", "type": "relationship", "subtype": "owns", "data": {"from": {"type": "participant", "id": "participant-002"}, "to": {"type": "action", "id": "action-001"}}, "scope": {"kind": "meeting"}, "evidenceRefs": ["cite-002"], "sourceRefs": [], "derivedFrom": [], "confidence": 0.86, "status": "verified"},
                {"id": "topic-001", "type": "topic", "subtype": "summary", "data": {"title": "Retrieval", "level": 1, "summary": "The team discussed RAG indexing."}, "scope": {"kind": "meeting"}, "evidenceRefs": ["cite-001"], "sourceRefs": [], "derivedFrom": [], "confidence": 0.8, "status": "verified"},
                {"id": "action-001", "type": "action", "subtype": "item", "data": {"task": "Index action items and risks by Friday.", "ownerParticipantId": "participant-002", "ownerName": "Bob", "status": "open"}, "scope": {"kind": "meeting"}, "evidenceRefs": ["cite-002"], "sourceRefs": [], "derivedFrom": [], "confidence": 0.86, "status": "verified"},
                {"id": "decision-001", "type": "decision", "subtype": "record", "data": {"text": "Use processed JSON for RAG."}, "scope": {"kind": "meeting"}, "evidenceRefs": ["cite-001"], "sourceRefs": [], "derivedFrom": [], "confidence": 0.9, "status": "verified"},
                {"id": "risk-001", "type": "risk", "subtype": "record", "data": {"text": "Low quality transcript segments may reduce answer confidence."}, "scope": {"kind": "meeting"}, "evidenceRefs": ["cite-002"], "sourceRefs": [], "derivedFrom": [], "confidence": 0.75, "status": "verified"},
                {"id": "question-001", "type": "question", "subtype": "record", "data": {"text": "How should old chunks be rebuilt?", "status": "open"}, "scope": {"kind": "meeting"}, "evidenceRefs": ["cite-001"], "sourceRefs": [], "derivedFrom": [], "confidence": 0.8, "status": "verified"},
            ],
            "relationships": []
        },
        "quality": {"coverage": "partial", "warnings": ["low volume"], "confidence": 0.75},
        "extraction": {"overallConfidence": 0.82, "method": "llm_with_deterministic_verification", "unsupportedClaims": [], "warnings": []},
    }


if __name__ == "__main__":
    unittest.main()

import unittest

from backend.models.meeting_models import Meeting, MeetingAsset
from backend.providers.analysis import LLMAnalysisProvider, _build_compact_user_prompt, _build_user_prompt
from backend.providers.llm import LLMProviderError
from backend.providers.transcript_types import TranscriptSegment


class SuccessfulLLMProvider:
    provider_name = "test-llm"
    model_name = "test-model"

    def generate_json(self, *, system_prompt: str, user_prompt: str) -> dict:
        return {
            "participants": [{"id": "participant-001", "displayName": "Speaker 1", "speakerLabels": ["Speaker 1"], "role": "owner", "isAttendee": True, "confidence": 0.8, "citationIds": ["cite-001"]}],
            "facts": [{"id": "fact-010", "type": "rag_source", "subject": {"type": "meeting", "id": "meeting"}, "predicate": "uses", "value": "processed JSON", "confidence": 0.9, "citationIds": ["cite-001"]}],
            "events": [{"id": "event-001", "type": "decision_made", "title": "JSON-first RAG confirmed", "status": "completed", "confidence": 0.9, "citationIds": ["cite-001"]}],
            "actions": [{"id": "action-001", "ownerName": "Team", "task": "Wire LLM analysis", "status": "open", "citationIds": ["cite-001"]}],
            "decisions": [{"id": "decision-001", "text": "Use JSON as the RAG source.", "confidence": 0.9, "citationIds": ["cite-001"]}],
            "topics": [{"id": "topic-001", "title": "Processing", "summary": "Pipeline work", "citationIds": ["cite-001"]}],
            "summaries": {"executive": {"text": "Team agreed to ship the processing pipeline.", "topicIds": ["topic-001"], "citationIds": ["cite-001"]}},
            "quality": {"coverage": "complete", "warnings": [], "confidence": 0.82},
        }


class BrokenLLMProvider:
    provider_name = "broken-llm"
    model_name = "broken-model"

    def generate_json(self, *, system_prompt: str, user_prompt: str) -> dict:
        raise LLMProviderError("provider unavailable")


class EchoThenSuccessfulLLMProvider:
    provider_name = "echo-then-test-llm"
    model_name = "repair-model"

    def __init__(self) -> None:
        self.calls = 0

    def generate_json(self, *, system_prompt: str, user_prompt: str) -> dict:
        self.calls += 1
        if self.calls == 1:
            return {
                "requiredSchemaVersion": "meeting-intelligence-candidate.v2",
                "transcript": {"segments": []},
                "requiredOutputShape": {"summary": {"executive": ""}},
            }
        return {
            "summaries": {"executive": {"text": "The meeting confirmed JSON-first RAG testing.", "topicIds": [], "citationIds": ["cite-001"]}},
            "decisions": [{"id": "decision-001", "text": "Test with text transcript first.", "citationIds": ["cite-001"]}],
            "facts": [{"id": "fact-010", "type": "test_scope", "value": "text transcript first", "citationIds": ["cite-001"]}],
            "quality": {"coverage": "partial", "warnings": [], "confidence": 0.7},
        }


class SummaryOnlyLLMProvider:
    provider_name = "summary-only-llm"
    model_name = "summary-only-model"

    def __init__(self) -> None:
        self.calls = 0

    def generate_json(self, *, system_prompt: str, user_prompt: str) -> dict:
        self.calls += 1
        return {
            "summaries": {
                "executive": {
                    "text": "The meeting discussed the processing plan.",
                    "topicIds": [],
                    "citationIds": ["cite-001"],
                }
            }
        }


class RecordsOnlyLLMProvider:
    provider_name = "records-only-llm"
    model_name = "records-only-model"

    def __init__(self) -> None:
        self.calls = 0

    def generate_json(self, *, system_prompt: str, user_prompt: str) -> dict:
        self.calls += 1
        return {
            "decisions": [
                {
                    "id": "decision-001",
                    "text": "Use the processing plan.",
                    "citationIds": ["cite-001"],
                }
            ]
        }


class HallucinatedCitationsLLMProvider:
    provider_name = "hallucinating-llm"
    model_name = "hallucination-model"

    def generate_json(self, *, system_prompt: str, user_prompt: str) -> dict:
        return {
            "summaries": {"executive": {"text": "Meeting discussed processing pipeline.", "topicIds": [], "citationIds": ["cite-001", "cite-999"]}},
            "decisions": [{"id": "decision-001", "text": "Process with JSON.", "citationIds": ["cite-999", "cite-001"]}],
            "facts": [{"id": "fact-010", "type": "rag_source", "value": "JSON", "citationIds": ["cite-999", "cite-001"]}],
            "quality": {"coverage": "partial", "warnings": [], "confidence": 0.7},
        }


class MalformedRelationshipLLMProvider:
    provider_name = "malformed-relationship-llm"
    model_name = "malformed-relationship-model"

    def generate_json(self, *, system_prompt: str, user_prompt: str) -> dict:
        return {
            "participants": [{"id": "participant-001", "displayName": "Speaker 1", "speakerLabels": ["Speaker 1"], "isAttendee": True, "citationIds": ["cite-001"]}],
            "relationships": [
                {"id": "rel-bad", "type": "mentions", "to": {"type": "participant", "id": "participant-001"}, "citationIds": ["cite-001"]}
            ],
            "summaries": {"executive": {"text": "The meeting discussed a malformed graph claim.", "topicIds": [], "citationIds": ["cite-001"]}},
            "quality": {"coverage": "partial", "warnings": [], "confidence": 0.7},
        }


class EmptySummaryLLMProvider:
    provider_name = "empty-summary-llm"
    model_name = "empty-summary-model"

    def generate_json(self, *, system_prompt: str, user_prompt: str) -> dict:
        return {
            "summaries": {"executive": {"text": "", "topicIds": [], "citationIds": []}},
            "facts": [{"id": "fact-001", "type": "topic", "value": "meeting", "citationIds": ["cite-001"]}],
            "quality": {"coverage": "partial", "warnings": [], "confidence": 0.5},
        }


class CollidingFactIdLLMProvider:
    provider_name = "colliding-fact-id-llm"
    model_name = "colliding-fact-id-model"

    def generate_json(self, *, system_prompt: str, user_prompt: str) -> dict:
        return {
            "summaries": {
                "executive": {
                    "text": "The call discussed commercial terms.",
                    "topicIds": [],
                    "citationIds": ["cite-001"],
                }
            },
            "facts": [
                {
                    "id": "fact-001",
                    "type": "shipping_cost",
                    "value": 599,
                    "unit": "USD",
                    "citationIds": ["cite-001"],
                },
                {
                    "id": "derived-window-participant-count",
                    "type": "promotion",
                    "value": "80 percent",
                    "citationIds": ["cite-001"],
                },
            ],
            "quality": {"coverage": "partial", "warnings": [], "confidence": 0.7},
        }


class WrappedFallbackLLMProvider:
    provider_name = "fallback"
    model_name = "test-llm:primary-model|ollama:fallback-model"

    def __init__(self) -> None:
        self.primary = type("Primary", (), {"model_name": "primary-model"})()
        self.last_provider_name = "test-llm"
        self.last_provider_model = "primary-model"

    def generate_json(self, *, system_prompt: str, user_prompt: str) -> dict:
        return {
            "summaries": {"executive": {"text": "Primary model generated the meeting intelligence.", "topicIds": [], "citationIds": ["cite-001"]}},
            "decisions": [{"id": "decision-001", "text": "Use the primary model in started logs.", "citationIds": ["cite-001"]}],
            "facts": [{"id": "fact-010", "type": "model", "value": "primary", "citationIds": ["cite-001"]}],
            "quality": {"coverage": "partial", "warnings": [], "confidence": 0.7},
        }


class AnalysisProviderTestCase(unittest.TestCase):
    def make_meeting(self) -> Meeting:
        return Meeting(
            id="11111111-1111-4111-8111-111111111111",
            owner_user_id="33333333-3333-4333-8333-333333333333",
            title="Analysis provider test",
        )

    def make_asset(self) -> MeetingAsset:
        return MeetingAsset(
            id="44444444-4444-4444-8444-444444444444",
            owner_user_id="33333333-3333-4333-8333-333333333333",
            meeting_id="11111111-1111-4111-8111-111111111111",
            object_key="workspaces/test/meetings/test/uploads/test.wav",
            file_name="test.wav",
            content_type="audio/wav",
            size_bytes=100,
            idempotency_key="upload-test",
        )

    def make_segments(self) -> list[TranscriptSegment]:
        return [
            TranscriptSegment(
                id="seg-001",
                speaker="Speaker 1",
                start_ms=0,
                end_ms=5000,
                text="We should use the processed JSON as the RAG source.",
                confidence=0.9,
            )
        ]

    def test_llm_analysis_merges_generated_sections_with_authoritative_transcript(self) -> None:
        provider = LLMAnalysisProvider(SuccessfulLLMProvider())

        result = provider.build_result(
            meeting=self.make_meeting(),
            asset=self.make_asset(),
            transcript_segments=self.make_segments(),
        )

        self.assertEqual(provider.last_provider_name, "test-llm")
        self.assertEqual(provider.last_provider_model, "test-model")
        self.assertEqual(result["source"]["analysisProvider"], "llm-analysis")
        self.assertEqual(result["source"]["llmProvider"], "test-llm")
        self.assertEqual(result["summaries"]["executive"]["text"], "Team agreed to ship the processing pipeline.")
        self.assertEqual(result["transcript"]["segments"][0]["id"], "seg-001")
        self.assertEqual(result["decisions"][0]["citationIds"], ["cite-001"])
        self.assertEqual(result["evidence"]["citations"][0]["quote"], "We should use the processed JSON as the RAG source.")
        self.assertEqual(result["speakers"]["speakerCount"], 1)

    def test_llm_analysis_configured_model_uses_primary_model_for_start_logs(self) -> None:
        provider = LLMAnalysisProvider(WrappedFallbackLLMProvider())

        self.assertEqual(provider.provider_model, "primary-model")

        result = provider.build_result(
            meeting=self.make_meeting(),
            asset=self.make_asset(),
            transcript_segments=self.make_segments(),
        )

        self.assertEqual(provider.last_provider_model, "primary-model")
        self.assertEqual(result["source"]["analysisModel"], "primary-model")

    def test_llm_analysis_raises_when_provider_fails(self) -> None:
        provider = LLMAnalysisProvider(BrokenLLMProvider())

        with self.assertRaises(LLMProviderError):
            provider.build_result(
                meeting=self.make_meeting(),
                asset=self.make_asset(),
                transcript_segments=self.make_segments(),
            )

    def test_llm_analysis_repairs_echoed_input_response_once(self) -> None:
        llm = EchoThenSuccessfulLLMProvider()
        provider = LLMAnalysisProvider(llm)

        result = provider.build_result(
            meeting=self.make_meeting(),
            asset=self.make_asset(),
            transcript_segments=self.make_segments(),
        )

        self.assertEqual(llm.calls, 2)
        self.assertEqual(result["summaries"]["executive"]["text"], "The meeting confirmed JSON-first RAG testing.")
        self.assertEqual(result["decisions"][0]["citationIds"], ["cite-001"])
        self.assertEqual(result["transcript"]["segments"][0]["id"], "seg-001")

    def test_llm_analysis_accepts_a_cited_summary_only_fallback_without_repair(self) -> None:
        llm = SummaryOnlyLLMProvider()
        provider = LLMAnalysisProvider(llm)

        result = provider.build_result(
            meeting=self.make_meeting(),
            asset=self.make_asset(),
            transcript_segments=self.make_segments(),
        )

        self.assertEqual(llm.calls, 1)
        self.assertEqual(result["summaries"]["executive"]["text"], "The meeting discussed the processing plan.")

    def test_llm_analysis_accepts_cited_records_without_repair(self) -> None:
        llm = RecordsOnlyLLMProvider()
        provider = LLMAnalysisProvider(llm)

        result = provider.build_result(
            meeting=self.make_meeting(),
            asset=self.make_asset(),
            transcript_segments=self.make_segments(),
        )

        self.assertEqual(llm.calls, 1)
        self.assertEqual(result["decisions"][0]["text"], "Use the processing plan.")
        self.assertTrue(result["summaries"]["executive"]["text"])

    def test_analysis_prompt_includes_evidence_text_and_metadata(self) -> None:
        prompt = _build_user_prompt(self.make_meeting(), self.make_asset(), self.make_segments())

        self.assertIn("Transcript line format: segmentId|speaker|startMs|endMs|confidence|text", prompt)

    def test_compact_fallback_prompt_has_a_bounded_output_contract(self) -> None:
        prompt = _build_compact_user_prompt(self.make_meeting(), self.make_asset(), self.make_segments())

        self.assertIn("at most one very short item", prompt)
        self.assertIn("at most four list items total", prompt)
        self.assertIn("seg-001|Speaker 1|0|5000|0.9|We should use", prompt)
        self.assertIn("processed JSON as the RAG source", prompt)

    def test_malformed_relationship_is_quarantined_instead_of_failing_result(self) -> None:
        provider = LLMAnalysisProvider(MalformedRelationshipLLMProvider())

        result = provider.build_result(
            meeting=self.make_meeting(),
            asset=self.make_asset(),
            transcript_segments=self.make_segments(),
        )

        self.assertEqual(result["relationships"], [])
        self.assertTrue(any("malformed relationship" in warning for warning in result["quality"]["warnings"]))
        self.assertTrue(result["extraction"]["unsupportedClaims"])

    def test_empty_executive_summary_uses_transcript_grounded_fallback(self) -> None:
        provider = LLMAnalysisProvider(EmptySummaryLLMProvider())

        result = provider.build_result(
            meeting=self.make_meeting(),
            asset=self.make_asset(),
            transcript_segments=self.make_segments(),
        )

        self.assertIn("processed JSON", result["summaries"]["executive"]["text"])
        self.assertEqual(result["summaries"]["executive"]["citationIds"], ["cite-001"])
        self.assertEqual(result["summaries"]["executive"]["lineageStatus"], "context_only")

    def test_llm_analysis_warns_when_hallucinating_citations(self) -> None:
        provider = LLMAnalysisProvider(HallucinatedCitationsLLMProvider())

        result = provider.build_result(
            meeting=self.make_meeting(),
            asset=self.make_asset(),
            transcript_segments=self.make_segments(),
        )

        self.assertEqual(result["decisions"][0]["citationIds"], ["cite-001"])
        self.assertEqual(result["summaries"]["executive"]["citationIds"], ["cite-001"])
        quality_warnings = result.get("quality", {}).get("warnings", [])
        self.assertTrue(
            any("cite-999" in w and "non-existent" in w for w in quality_warnings),
            f"Expected hallucination warning with cite-999, got: {quality_warnings}"
        )

    def test_deterministic_participant_count_never_reuses_an_llm_fact_id(self) -> None:
        provider = LLMAnalysisProvider(CollidingFactIdLLMProvider())

        result = provider.build_result(
            meeting=self.make_meeting(),
            asset=self.make_asset(),
            transcript_segments=self.make_segments(),
        )

        facts_by_id = {fact["id"]: fact for fact in result["facts"]}
        self.assertEqual(len(facts_by_id), len(result["facts"]))
        self.assertEqual(facts_by_id["fact-001"]["type"], "shipping_cost")
        self.assertEqual(facts_by_id["fact-001"]["value"], 599)
        deterministic = [
            fact
            for fact in result["facts"]
            if fact.get("type") == "participant_count"
        ]
        self.assertEqual(len(deterministic), 1)
        self.assertEqual(deterministic[0]["id"], "derived-window-participant-count-2")
        self.assertEqual(deterministic[0]["value"], 1)
        self.assertEqual(deterministic[0]["citationIds"], [])

    def test_unknown_and_noise_labels_do_not_inflate_deterministic_participant_count(self) -> None:
        provider = LLMAnalysisProvider(SuccessfulLLMProvider())
        segments = [
            TranscriptSegment("seg-001", "Speaker 1", 0, 1000, "Hello.", 0.9),
            TranscriptSegment("seg-002", "Speaker 2", 1000, 2000, "Hi.", 0.9),
            TranscriptSegment("seg-003", "unknown", 2000, 3000, "Thank you.", 0.9),
            TranscriptSegment("seg-004", "Noise", 3000, 4000, "[noise]", 0.8),
        ]

        result = provider.build_result(
            meeting=self.make_meeting(),
            asset=self.make_asset(),
            transcript_segments=segments,
        )

        self.assertEqual(result["speakers"]["speakerCount"], 2)
        self.assertEqual(result["speakers"]["ignoredSpeakerLabelCount"], 2)
        self.assertEqual(result["speakers"]["ignoredSegmentCount"], 2)
        participant_count = next(
            fact for fact in result["facts"] if fact.get("type") == "participant_count"
        )
        self.assertEqual(participant_count["value"], 2)
        self.assertTrue(participant_count["isLowerBound"])

    def test_unknown_only_transcript_does_not_claim_zero_participants(self) -> None:
        provider = LLMAnalysisProvider(SuccessfulLLMProvider())

        result = provider.build_result(
            meeting=self.make_meeting(),
            asset=self.make_asset(),
            transcript_segments=[
                TranscriptSegment("seg-001", "unknown", 0, 1000, "Thank you.", 0.9)
            ],
        )

        self.assertEqual(result["speakers"]["speakerCount"], 0)
        self.assertFalse(
            any(fact.get("type") == "participant_count" for fact in result["facts"])
        )
        self.assertTrue(
            any(
                "Participant count was omitted" in warning
                for warning in result["quality"]["warnings"]
            )
        )


if __name__ == "__main__":
    unittest.main()

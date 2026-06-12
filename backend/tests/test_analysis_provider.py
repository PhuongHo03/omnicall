import unittest

from backend.models.meeting_models import Meeting, MeetingAsset
from backend.providers.analysis_provider import LLMAnalysisProvider, LocalAnalysisProvider
from backend.providers.llm_provider import LLMProviderError
from backend.providers.transcript_types import TranscriptSegment


class SuccessfulLLMProvider:
    provider_name = "test-llm"
    model_name = "test-model"

    def generate_json(self, *, system_prompt: str, user_prompt: str) -> dict:
        return {
            "participants": [{"speaker": "Speaker 1", "role": "owner", "confidence": 0.8}],
            "summary": {
                "executive": "Team agreed to ship the processing pipeline.",
                "detailed": [{"title": "Pipeline", "text": "Worker and JSON result were discussed.", "citationIds": ["cite-001"]}],
                "keyPoints": [{"text": "Processing JSON drives chatbot retrieval.", "citationIds": ["cite-001"]}],
            },
            "analysis": {
                "topics": [{"title": "Processing", "summary": "Pipeline work", "citationIds": ["cite-001"]}],
                "decisions": [{"text": "Use JSON as the RAG source.", "confidence": 0.9, "citationIds": ["cite-001"]}],
                "actionItems": [{"owner": "Team", "task": "Wire LLM analysis", "status": "open", "citationIds": ["cite-001"]}],
                "importantNotes": [],
                "timeline": [],
                "risks": [],
                "blockers": [],
                "dependencies": [],
                "openQuestions": [],
                "followUps": [],
                "outcomes": [],
                "requirements": [],
                "constraints": [],
                "assumptions": [],
                "conflicts": [],
                "metrics": [],
                "parkingLot": [],
                "entities": [],
                "glossary": [],
                "emptySections": {"timeline": "No timeline evidence."},
            },
            "citations": [{"id": "cite-001", "segmentIds": ["seg-001"], "startMs": 0, "endMs": 5000}],
            "quality": {"coverage": "complete", "warnings": [], "confidence": 0.82},
        }


class BrokenLLMProvider:
    provider_name = "broken-llm"
    model_name = "broken-model"

    def generate_json(self, *, system_prompt: str, user_prompt: str) -> dict:
        raise LLMProviderError("provider unavailable")


class AnalysisProviderTestCase(unittest.TestCase):
    def make_meeting(self) -> Meeting:
        return Meeting(
            id="11111111-1111-4111-8111-111111111111",
            workspace_id="22222222-2222-4222-8222-222222222222",
            created_by_user_id="33333333-3333-4333-8333-333333333333",
            title="Analysis provider test",
            language="vi",
        )

    def make_asset(self) -> MeetingAsset:
        return MeetingAsset(
            id="44444444-4444-4444-8444-444444444444",
            workspace_id="22222222-2222-4222-8222-222222222222",
            meeting_id="11111111-1111-4111-8111-111111111111",
            created_by_user_id="33333333-3333-4333-8333-333333333333",
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

        self.assertEqual(provider.last_provider_name, "llm-analysis")
        self.assertEqual(provider.last_provider_model, "test-model")
        self.assertEqual(result["source"]["analysisProvider"], "llm-analysis")
        self.assertEqual(result["source"]["llmProvider"], "test-llm")
        self.assertEqual(result["summary"]["executive"], "Team agreed to ship the processing pipeline.")
        self.assertEqual(result["transcript"]["segments"][0]["id"], "seg-001")
        self.assertEqual(result["analysis"]["decisions"][0]["citationIds"], ["cite-001"])

    def test_llm_analysis_falls_back_to_local_result_when_provider_fails(self) -> None:
        provider = LLMAnalysisProvider(BrokenLLMProvider(), fallback_provider=LocalAnalysisProvider())

        result = provider.build_result(
            meeting=self.make_meeting(),
            asset=self.make_asset(),
            transcript_segments=self.make_segments(),
        )

        self.assertEqual(provider.last_provider_name, "local-placeholder-analysis")
        self.assertEqual(provider.last_provider_model, "deterministic-v1")
        self.assertEqual(result["source"]["analysisProvider"], "local-placeholder-analysis")
        self.assertEqual(result["source"]["analysisFallbackReason"], "LLM analysis failed; deterministic fallback was used.")
        self.assertIn("LLM analysis was unavailable", result["quality"]["warnings"][-1])

    def test_local_analysis_extracts_core_sections_with_source_links(self) -> None:
        segments = [
            TranscriptSegment(
                id="seg-001",
                speaker="Alice",
                start_ms=0,
                end_ms=5000,
                text="We agreed to use the processed JSON as the RAG source.",
                confidence=0.9,
            ),
            TranscriptSegment(
                id="seg-002",
                speaker="Bob",
                start_ms=5000,
                end_ms=12000,
                text="Action item: Bob should index transcript-derived sections by Friday.",
                confidence=0.9,
            ),
            TranscriptSegment(
                id="seg-003",
                speaker="Alice",
                start_ms=12000,
                end_ms=18000,
                text="Risk: audio ASR quality may be low before the deadline next week.",
                confidence=0.9,
            ),
        ]

        result = LocalAnalysisProvider().build_result(
            meeting=self.make_meeting(),
            asset=self.make_asset(),
            transcript_segments=segments,
        )

        citation_ids = {citation["id"] for citation in result["citations"]}
        self.assertTrue(result["analysis"]["decisions"])
        self.assertTrue(result["analysis"]["actionItems"])
        self.assertTrue(result["analysis"]["timeline"])
        self.assertTrue(result["analysis"]["risks"])
        for section in ("decisions", "actionItems", "timeline", "risks"):
            for item in result["analysis"][section]:
                self.assertTrue(set(item["citationIds"]).issubset(citation_ids))


if __name__ == "__main__":
    unittest.main()

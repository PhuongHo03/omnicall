import unittest

from backend.models.meeting_models import Meeting, MeetingAsset
from backend.providers.analysis_provider import LLMAnalysisProvider, _build_user_prompt
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


class EchoThenSuccessfulLLMProvider:
    provider_name = "echo-then-test-llm"
    model_name = "repair-model"

    def __init__(self) -> None:
        self.calls = 0

    def generate_json(self, *, system_prompt: str, user_prompt: str) -> dict:
        self.calls += 1
        if self.calls == 1:
            return {
                "requiredSchemaVersion": "meeting-intelligence-result.v1",
                "transcript": {"segments": []},
                "requiredOutputShape": {"summary": {"executive": ""}},
            }
        return {
            "summary": {
                "executive": "The meeting confirmed JSON-first RAG testing.",
                "detailed": [],
                "keyPoints": [{"text": "Use text transcript for the first complete test.", "citationIds": ["cite-001"]}],
            },
            "analysis": {
                "decisions": [{"text": "Test with text transcript first.", "citationIds": ["cite-001"]}],
                "actionItems": [],
                "timeline": [],
                "risks": [],
            },
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
            "summary": {
                "executive": "Primary model generated the meeting intelligence.",
                "detailed": [],
                "keyPoints": [{"text": "Use the primary model in started logs.", "citationIds": ["cite-001"]}],
            },
            "analysis": {
                "decisions": [{"text": "Use the primary model in started logs.", "citationIds": ["cite-001"]}],
                "actionItems": [],
                "timeline": [],
                "risks": [],
            },
            "quality": {"coverage": "partial", "warnings": [], "confidence": 0.7},
        }


class AnalysisProviderTestCase(unittest.TestCase):
    def make_meeting(self) -> Meeting:
        return Meeting(
            id="11111111-1111-4111-8111-111111111111",
            owner_user_id="33333333-3333-4333-8333-333333333333",
            title="Analysis provider test",
            language="vi",
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

        self.assertEqual(provider.last_provider_name, "llm-analysis")
        self.assertEqual(provider.last_provider_model, "test-model")
        self.assertEqual(result["source"]["analysisProvider"], "llm-analysis")
        self.assertEqual(result["source"]["llmProvider"], "test-llm")
        self.assertEqual(result["summary"]["executive"], "Team agreed to ship the processing pipeline.")
        self.assertEqual(result["transcript"]["segments"][0]["id"], "seg-001")
        self.assertEqual(result["analysis"]["decisions"][0]["citationIds"], ["cite-001"])

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
        self.assertEqual(result["summary"]["executive"], "The meeting confirmed JSON-first RAG testing.")
        self.assertEqual(result["analysis"]["decisions"][0]["citationIds"], ["cite-001"])
        self.assertEqual(result["transcript"]["segments"][0]["id"], "seg-001")

    def test_analysis_prompt_keeps_evidence_text_without_transcript_metadata(self) -> None:
        prompt = _build_user_prompt(self.make_meeting(), self.make_asset(), self.make_segments())

        self.assertIn("Transcript line format: segmentId|speaker|text", prompt)
        self.assertIn("seg-001|Speaker 1|We should use", prompt)
        self.assertIn("processed JSON as the RAG source", prompt)
        self.assertNotIn('"startMs"', prompt)
        self.assertNotIn('"confidence"', prompt)


if __name__ == "__main__":
    unittest.main()

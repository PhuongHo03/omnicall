import unittest

from backend.services.agent.context_manager import ContextChunk
from backend.services.agent.evidence_verifier import verify_evidence
from backend.services.agent.query_planner import build_query_plan


class GeneralizedEvidenceFixtureTestCase(unittest.TestCase):
    def test_direct_transcript_evidence(self) -> None:
        plan = build_query_plan("What decision was made?")
        result = verify_evidence(plan, [ContextChunk("event-1", "Decision: approve the launch. status: confirmed.", 1.0, section_type="event.timeline", citation_ids=["cite-1"], start_ms=100)])
        self.assertTrue(result.sufficient)

    def test_derived_fact_without_playback_location(self) -> None:
        plan = build_query_plan("Có bao nhiêu người tham gia cuộc họp này?")
        result = verify_evidence(plan, [ContextChunk("fact-1", "Fact participant count value: 2.", 1.0, section_type="fact.participant_count", metadata={"recordType": "fact", "subtype": "participant_count"})])
        self.assertTrue(result.sufficient)

    def test_unsupported_claim_is_not_sufficient(self) -> None:
        plan = build_query_plan("What is the office address?")
        result = verify_evidence(plan, [ContextChunk("summary-1", "The team discussed the roadmap.", 1.0, section_type="summary.executive")])
        self.assertFalse(result.sufficient)


if __name__ == "__main__":
    unittest.main()

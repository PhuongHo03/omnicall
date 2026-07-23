import unittest

from backend.services.simple_rag.answer_synthesis_service import SynthesisContractError
from backend.services.simple_rag.answer_verification_service import AnswerVerificationService
from backend.services.simple_rag.contracts import EvidenceBundle, GoalSpec, QuerySpec, SynthesisContract, TypedFact, VerificationResult
from backend.services.simple_rag.pipeline import SimpleRAGPipeline
from backend.services.simple_rag.query_interpretation_service import QueryInterpretationService


class SimpleRAGContractTestCase(unittest.TestCase):
    def test_vietnamese_english_summary_paraphrases_are_equivalent(self) -> None:
        service = QueryInterpretationService()
        vi = service.interpret("Tóm tắt cuộc họp", language_hint="vi-VN")
        en = service.interpret("Summarize the meeting", language_hint="en-US")
        self.assertEqual((vi.goals[0].operation, vi.goals[0].target), (en.goals[0].operation, en.goals[0].target))

    def test_current_meeting_overview_does_not_inherit_a_prior_greeting_target(self) -> None:
        history = [
            type("Message", (), {
                "id": "assistant-greeting",
                "metadata_json": {"querySpec": {"goals": [{"goal_id": "goal-1", "operation": "direct", "target": "greeting"}]}},
            })()
        ]

        spec = QueryInterpretationService().interpret("cuộc họp này nói về vấn đề gì?", history, language_hint="vi")

        self.assertEqual(spec.dependency_mode, "standalone")
        self.assertEqual((spec.goals[0].operation, spec.goals[0].target), ("summarize", "meeting"))

    def test_meeting_overview_without_nay_is_also_a_summary(self) -> None:
        spec = QueryInterpretationService().interpret("cuộc họp nói về vấn đề gì?", language_hint="vi")

        self.assertEqual(spec.language, "vi")
        self.assertEqual((spec.goals[0].operation, spec.goals[0].target), ("summarize", "meeting"))

    def test_vietnamese_greeting_uses_vietnamese_output_contract(self) -> None:
        spec = QueryInterpretationService().interpret("xin chào", language_hint="vi")

        self.assertEqual(spec.language, "vi")
        self.assertEqual(spec.goals[0].target, "greeting")

    def test_missing_contact_entity_requires_clarification(self) -> None:
        spec = QueryInterpretationService().interpret("Cho tôi email", language_hint="vi")
        self.assertEqual(spec.dependency_mode, "ambiguous")
        self.assertEqual(spec.clarification_reason, "missing_entity")

    def test_verifier_rejects_locked_fact_drift(self) -> None:
        goal = GoalSpec("goal-1", "count", "participant", ("count",), answer_shape="scalar")
        fact = TypedFact("fact:count", "count", 2, "number", "complete", ("ref-1",))
        contract = SynthesisContract("vi", "short", (goal,), (EvidenceBundle("goal-1", "m1", "g1", "sufficient", (fact,)),), (fact,), ("ref-1",))
        result = AnswerVerificationService().verify(
            {"answer": "Có 3 người.", "claims": [{"goalId": "goal-1", "factIds": ["fact:count"], "refs": ["ref-1"]}]},
            contract,
        )
        self.assertFalse(result.passed)
        self.assertIn("locked_fact_value_missing:fact:count", result.errors)

    def test_verifier_derives_refs_from_selected_facts(self) -> None:
        goal = GoalSpec("goal-1", "search", "meeting")
        fact = TypedFact("fact:x", "fact", "approved", "string", "complete", ("ref-1",))
        bundle = EvidenceBundle("goal-1", "m1", "g1", "sufficient", (fact,))
        contract = SynthesisContract("en", "short", (goal,), (bundle,), (fact,), ("ref-1",))
        result = AnswerVerificationService().verify(
            # An obsolete/model-invented refs field has no authority. The
            # verifier derives the citation from fact:x instead.
            {"answer": "approved", "claims": [{"goalId": "goal-1", "factIds": ["fact:x"], "refs": ["bad-ref"]}]},
            contract,
        )
        self.assertTrue(result.passed)
        self.assertEqual(result.verified_refs, ("ref-1",))

    def test_verifier_rejects_wrong_script_for_requested_language(self) -> None:
        goal = GoalSpec("goal-1", "search", "meeting")
        fact = TypedFact("fact:x", "fact", "approved", "string", "complete", ("ref-1",))
        bundle = EvidenceBundle("goal-1", "m1", "g1", "sufficient", (fact,))
        contract = SynthesisContract("vi", "short", (goal,), (bundle,), (fact,), ("ref-1",))

        result = AnswerVerificationService().verify(
            {"answer": "这是已批准的。", "claims": [{"goalId": "goal-1", "factIds": ["fact:x"]}]},
            contract,
        )

        self.assertFalse(result.passed)
        self.assertIn("answer_language_mismatch", result.errors)

    def test_contract_failure_becomes_terminal_control_error_with_trace(self) -> None:
        query = QuerySpec("xin chào", "vi", "standalone", (GoalSpec("goal-1", "direct", "greeting"),))

        class Interpreter:
            def interpret(self, *_args, **_kwargs):
                return query

        class Retrieval:
            def plan(self, *_args):
                return []

            def retrieve(self, meeting_id, _query):
                return (EvidenceBundle("goal-1", meeting_id, "generation-1", "sufficient"),)

        class Synthesis:
            def synthesize(self, *_args, **_kwargs):
                raise SynthesisContractError(VerificationResult(False, ("claim_0_unknown_ref",), ()))

        pipeline = SimpleRAGPipeline.__new__(SimpleRAGPipeline)
        pipeline.settings = type("Settings", (), {
            "rag_chat_turn_timeout_seconds": 150,
            "rag_query_interpretation_timeout_seconds": 15,
            "rag_evidence_retrieval_timeout_seconds": 20,
            "rag_finalization_reserve_seconds": 15,
            "rag_synthesis_primary_timeout_seconds": 60,
            "rag_synthesis_fallback_timeout_seconds": 40,
            "rag_synthesis_contract_retries": 1,
        })()
        pipeline.interpreter = Interpreter()
        pipeline.retrieval = Retrieval()
        pipeline.synthesis = Synthesis()

        result = pipeline.run(meeting_id="m1", question="xin chào")

        self.assertEqual(result.evidence_state, "error")
        self.assertEqual(result.terminal_status, "error")
        stages = {stage["stage"]: stage for stage in result.pipeline_trace["stages"]}
        self.assertEqual(stages["synthesis"]["status"], "failed")
        self.assertEqual(stages["answer_verification"]["details"]["errors"], ["claim_0_unknown_ref"])

    def test_language_comes_from_locale_not_question_keywords(self) -> None:
        spec = QueryInterpretationService().interpret("xin chào", language_hint="en-US")
        self.assertEqual(spec.language, "en")
        self.assertEqual(spec.goals[0].target, "greeting")


if __name__ == "__main__":
    unittest.main()

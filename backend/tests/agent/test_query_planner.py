from __future__ import annotations

import unittest

from backend.services.agent.context_manager import ContextChunk
from backend.services.agent.evidence_verifier import verify_evidence
from backend.services.agent.query_planner import build_query_plan, replan_query


class QueryPlannerTestCase(unittest.TestCase):
    def test_multi_intent_plan_contains_action_and_risk_sections(self) -> None:
        plan = build_query_plan("Ai phụ trách triển khai API, deadline là khi nào và rủi ro gì?")

        self.assertEqual(plan.intent, "multi_intent")
        self.assertIn("action.item", plan.sections)
        self.assertIn("risk.record", plan.sections)
        self.assertIn("action", plan.record_types)
        self.assertIn("owner", plan.required_fields)

    def test_plan_exposes_generic_record_selectors(self) -> None:
        plan = build_query_plan("Có bao nhiêu người tham gia cuộc họp này?")
        self.assertIn("fact", plan.record_types)
        self.assertIn("participant_count", plan.record_subtypes)

    def test_metadata_question_has_metadata_sections(self) -> None:
        plan = build_query_plan("Model và provider nào đã xử lý cuộc họp?")

        self.assertIn("source.processing", plan.sections)
        self.assertIn("provider", plan.required_fields)
        self.assertIn("model", plan.required_fields)

    def test_price_question_routes_to_structured_commercial_evidence(self) -> None:
        plan = build_query_plan("Có bao nhiêu giá tiền và chi phí nào được nhắc đến?")

        self.assertIn("fact.record", plan.sections)
        self.assertIn("decision.record", plan.sections)
        self.assertIn("value", plan.required_fields)

    def test_store_question_routes_to_entity_and_fact_evidence(self) -> None:
        plan = build_query_plan("Tên cửa hàng được nhắc đến là gì?")

        self.assertIn("entity.profile", plan.sections)
        self.assertIn("fact.record", plan.sections)
        self.assertIn("transcript.window", plan.sections)

    def test_participant_plan_does_not_require_missing_role_field(self) -> None:
        plan = build_query_plan("Có bao nhiêu người tham gia và họ là ai?")

        self.assertIn("displayName", plan.required_fields)
        self.assertIn("value", plan.required_fields)
        self.assertNotIn("role", plan.required_fields)

    def test_participant_count_question_requires_only_count_evidence(self) -> None:
        plan = build_query_plan("Có bao nhiêu người tham gia cuộc họp này?")

        self.assertEqual(plan.required_fields, ["value"])
        self.assertIn("fact.participant_count", plan.sections)

    def test_participant_aliases_route_who_joined_and_attendee_questions(self) -> None:
        for question in ("Ai tham gia cuộc họp?", "How many attendees joined?"):
            plan = build_query_plan(question)
            self.assertIn("fact.participant_count", plan.sections)

    def test_verifier_reports_missing_fields(self) -> None:
        plan = build_query_plan("Ai phụ trách việc này và deadline là khi nào?")
        chunks = [ContextChunk("action-1", "Action item. owner: An. status: open.", 0.9, section_type="action.item")]

        result = verify_evidence(plan, chunks)

        self.assertFalse(result.sufficient)
        self.assertIn("dueDate", result.missing_fields)

    def test_verifier_accepts_participant_count_and_names_without_roles(self) -> None:
        plan = build_query_plan("Có bao nhiêu người tham gia và họ là ai?")
        chunks = [
            ContextChunk(
                "participant-count",
                "Fact. type: participant_count. value: 3. unit: people.",
                0.9,
                section_type="fact.participant_count",
            ),
            ContextChunk(
                "participant-profile",
                "Participant profile. display Name: Speaker 1.",
                0.9,
                section_type="participant.profile",
            ),
        ]

        result = verify_evidence(plan, chunks)

        self.assertTrue(result.sufficient)

    def test_replan_focuses_on_missing_fields(self) -> None:
        plan = build_query_plan("Ai phụ trách việc này và deadline là khi nào?")
        revised = replan_query(plan, ["dueDate"])

        self.assertTrue(revised.intent.endswith("_follow_up"))
        self.assertEqual(revised.required_fields, ["dueDate"])

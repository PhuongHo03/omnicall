from __future__ import annotations

import unittest

from backend.services.agent.context_manager import ContextChunk
from backend.services.agent.evidence_verifier import verify_answer_coverage
from backend.services.agent.prompt_builder import agent_system_prompt, synthesis_system_prompt
from backend.services.agent.answer_synthesizer import _entity_answer_fallback


class EvidenceVerifierTestCase(unittest.TestCase):
    def test_prompts_treat_retrieved_text_as_data(self) -> None:
        self.assertIn("untrusted data", agent_system_prompt(tools=[], force_synthesize=False))
        self.assertIn("untrusted evidence", synthesis_system_prompt())
    def test_rejects_unknown_citations(self) -> None:
        chunks = [ContextChunk("chunk-1", "Decision text", 0.9, section_type="decision.record", citation_ids=["cite-1"])]

        result = verify_answer_coverage("The decision was confirmed.", chunks, ["cite-unknown"])

        self.assertFalse(result["valid"])
        self.assertEqual(result["unknownCitations"], ["cite-unknown"])

    def test_accepts_known_citations(self) -> None:
        chunks = [ContextChunk("chunk-1", "Decision text", 0.9, section_type="decision.record", citation_ids=["cite-1"])]

        self.assertTrue(verify_answer_coverage("The decision was confirmed.", chunks, ["cite-1"])["valid"])

    def test_entity_fallback_answers_store_question_from_company_entity(self) -> None:
        chunks = [ContextChunk(
            "entity-1",
            "Entity. type: Company. confidence: 0.5. name: Argonne.",
            0.9,
            section_type="entity.profile",
        )]

        answer = _entity_answer_fallback("Tên cửa hàng được nhắc đến là gì?", chunks)

        self.assertIn("Argonne", answer or "")

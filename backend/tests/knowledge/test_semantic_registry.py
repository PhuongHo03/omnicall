import unittest

from backend.services.knowledge.semantic_registry import (
    CANONICAL_RECORD_TYPES,
    canonical_record_type,
    record_type_definition,
)
from backend.services.knowledge.contract import KNOWLEDGE_SCHEMA_VERSION, build_record, validate_record_shape


class SemanticRegistryTestCase(unittest.TestCase):
    def test_registry_contains_general_record_families(self) -> None:
        self.assertTrue({"participant", "entity", "fact", "event", "action", "risk", "observation"}.issubset(CANONICAL_RECORD_TYPES))

    def test_aliases_normalize_to_canonical_types(self) -> None:
        self.assertEqual(canonical_record_type("action_item"), "action")
        self.assertEqual(canonical_record_type("named entity"), "entity")
        self.assertEqual(canonical_record_type("relation"), "relationship")

    def test_unknown_type_is_retained_as_observation(self) -> None:
        self.assertEqual(canonical_record_type("participant_count", data={"value": 2}), "observation")

    def test_subtype_stays_in_payload_without_expanding_registry(self) -> None:
        self.assertEqual(canonical_record_type("fact", data={"type": "participant_count"}), "fact")
        self.assertEqual(record_type_definition("fact").name, "fact")

    def test_v2_record_envelope_is_stable_and_deduplicated(self) -> None:
        record = build_record(
            record_id="fact-001",
            record_type="fact",
            data={"type": "participant_count", "value": 2},
            evidence_refs=["evidence-1", "evidence-1"],
            source_refs=["window-1"],
            derived_from=["speakers"],
        )
        self.assertEqual(KNOWLEDGE_SCHEMA_VERSION, "meeting-intelligence-result.v2")
        self.assertEqual(record["type"], "fact")
        self.assertEqual(record["subtype"], "participant_count")
        self.assertEqual(record["evidenceRefs"], ["evidence-1"])
        validate_record_shape(record)

    def test_unknown_record_type_is_valid_as_observation(self) -> None:
        record = build_record(record_id="observation-1", record_type="new_llm_type", data={"value": "kept"})
        self.assertEqual(record["type"], "observation")
        validate_record_shape(record)


if __name__ == "__main__":
    unittest.main()

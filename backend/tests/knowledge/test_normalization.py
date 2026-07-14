import unittest

from backend.services.knowledge.normalization import normalize_candidate


class CandidateNormalizationTestCase(unittest.TestCase):
    def test_normalizes_legacy_section_and_keeps_subtype_payload(self) -> None:
        record = normalize_candidate(
            item={"id": "fact-1", "type": "participant_count", "value": 2, "citationIds": ["cite-1"]},
            section="facts",
            record_id="fact-1",
            source_ref="window-1",
            evidence_refs=["cite-1"],
        )
        self.assertEqual(record["type"], "fact")
        self.assertEqual(record["subtype"], "participant_count")
        self.assertEqual(record["data"]["value"], 2)
        self.assertEqual(record["evidenceRefs"], ["cite-1"])

    def test_unknown_section_becomes_observation(self) -> None:
        record = normalize_candidate(
            item={"id": "x", "label": "new concept"},
            section="new_section",
            record_id="observation-1",
            source_ref="window-1",
            evidence_refs=[],
        )
        self.assertEqual(record["type"], "observation")
        self.assertEqual(record["subtype"], "new_section")


if __name__ == "__main__":
    unittest.main()

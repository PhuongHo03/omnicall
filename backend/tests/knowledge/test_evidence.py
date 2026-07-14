import unittest

from backend.services.knowledge.evidence import build_evidence_item, evidence_by_id, evidence_items


class EvidenceContractTestCase(unittest.TestCase):
    def test_builds_transcript_evidence_with_stable_location(self) -> None:
        item = build_evidence_item(
            evidence_id="evidence-001",
            kind="transcript",
            quote="The decision is approved.",
            segment_ids=["seg-001", "seg-001"],
            start_ms=100,
            end_ms=200,
        )
        self.assertEqual(item["segmentIds"], ["seg-001"])
        self.assertEqual(item["startMs"], 100)

    def test_items_are_the_canonical_collection(self) -> None:
        result = {"evidence": {"items": [{"id": "evidence-001", "kind": "structured"}]}}
        self.assertEqual(evidence_items(result)[0]["kind"], "structured")
        self.assertIn("evidence-001", evidence_by_id(result))

    def test_rejects_unknown_evidence_kind(self) -> None:
        with self.assertRaises(ValueError):
            build_evidence_item(evidence_id="bad", kind="random")


if __name__ == "__main__":
    unittest.main()

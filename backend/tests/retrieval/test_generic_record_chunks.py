import unittest

from backend.services.retrieval.chunk_builder import _canonical_record_view
from backend.services.retrieval.section_registry import SECTION_TYPE_SET


class GenericRecordChunkTestCase(unittest.TestCase):
    def test_unknown_record_is_exposed_without_new_section_name(self) -> None:
        view = _canonical_record_view({
            "knowledge": {
                "records": [{
                    "id": "observation-1", "type": "observation", "subtype": "customer_signal",
                    "data": {"label": "customer signal", "value": "urgent"},
                    "evidenceRefs": [], "sourceRefs": [], "confidence": 0.8,
                }]
            }
        })
        self.assertEqual(view["observations"][0]["subtype"], "customer_signal")
        self.assertIn("observation.record", SECTION_TYPE_SET)


if __name__ == "__main__":
    unittest.main()

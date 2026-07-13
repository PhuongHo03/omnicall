from __future__ import annotations

import unittest

from backend.services.retrieval.chunk_builder import SECTION_PRIORITY, _retrieval_view
from backend.services.retrieval.section_registry import SECTION_TYPE_SET


class SectionRegistryTestCase(unittest.TestCase):
    def test_priority_sections_are_registered(self) -> None:
        self.assertTrue(set(SECTION_PRIORITY).issubset(SECTION_TYPE_SET))

    def test_registry_has_metadata_and_quality_sections(self) -> None:
        self.assertIn("source.processing", SECTION_TYPE_SET)
        self.assertIn("quality.warning", SECTION_TYPE_SET)
        self.assertIn("extraction.warning", SECTION_TYPE_SET)

    def test_knowledge_entity_records_are_exposed_to_entity_chunks(self) -> None:
        view = _retrieval_view({
            "knowledge": {
                "records": [
                    {"id": "entity-1", "type": "entity", "data": {"name": "Argonne"}},
                ],
            },
        })

        self.assertEqual(view["entities"][0]["name"], "Argonne")

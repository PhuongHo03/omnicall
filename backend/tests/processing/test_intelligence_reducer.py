import unittest
from types import SimpleNamespace

from backend.providers.transcript_types import TranscriptSegment
from backend.services.processing.intelligence_reducer import reduce_window_results
from backend.services.processing.result_validation import validate_result_json


class IntelligenceReducerTestCase(unittest.TestCase):
    def test_executive_summary_inherits_only_explicit_topic_lineage(self) -> None:
        result = reduce_window_results(
            meeting=SimpleNamespace(id="meeting-001", title="Lineage test"),
            asset=SimpleNamespace(id="asset-001"),
            transcript_segments=[
                TranscriptSegment("seg-001", "Speaker 1", 0, 1000, "Discuss retrieval lineage.", 0.95)
            ],
            windows=[{
                "windowId": "window-001",
                "sequenceNo": 1,
                "startMs": 0,
                "endMs": 1000,
                "segmentIds": ["seg-001"],
            }],
            local_results=[{
                "topics": [{
                    "id": "topic-001",
                    "title": "Retrieval lineage",
                    "summary": "The team discussed citation lineage.",
                    "citationIds": ["cite-local-001"],
                }],
                "summaries": {"executive": {
                    "text": "The call discussed retrieval lineage.",
                    "topicIds": ["topic-001"],
                    "citationIds": [],
                }},
                "evidence": {"citations": [{
                    "id": "cite-local-001",
                    "segmentIds": ["seg-001"],
                }]},
            }],
            provider_name="test-llm",
            provider_model="test-model",
        )

        executive = result["summaries"]["executive"]
        self.assertEqual(executive["evidenceRefs"], ["cite-001"])
        self.assertEqual(executive["lineageStatus"], "verified")

    def test_executive_summary_without_explicit_lineage_is_context_only(self) -> None:
        result = reduce_window_results(
            meeting=SimpleNamespace(id="meeting-001", title="Context-only test"),
            asset=SimpleNamespace(id="asset-001"),
            transcript_segments=[
                TranscriptSegment("seg-001", "Speaker 1", 0, 1000, "Discuss retrieval lineage.", 0.95)
            ],
            windows=[{
                "windowId": "window-001",
                "sequenceNo": 1,
                "startMs": 0,
                "endMs": 1000,
                "segmentIds": ["seg-001"],
            }],
            local_results=[{
                "topics": [{
                    "id": "topic-001",
                    "title": "Retrieval lineage",
                    "summary": "The team discussed citation lineage.",
                    "citationIds": ["cite-local-001"],
                }],
                "summaries": {"executive": {
                    "text": "The call discussed retrieval lineage.",
                    "topicIds": [],
                    "citationIds": [],
                }},
                "evidence": {"citations": [{
                    "id": "cite-local-001",
                    "segmentIds": ["seg-001"],
                }]},
            }],
            provider_name="test-llm",
            provider_model="test-model",
        )

        executive = result["summaries"]["executive"]
        self.assertEqual(executive["evidenceRefs"], [])
        self.assertEqual(executive["lineageStatus"], "context_only")
        self.assertTrue(any(
            "context only" in warning
            for warning in result["quality"]["warnings"]
        ))

    def test_validation_rejects_context_only_summary_with_evidence(self) -> None:
        result = reduce_window_results(
            meeting=SimpleNamespace(id="meeting-001", title="Validation test"),
            asset=SimpleNamespace(id="asset-001"),
            transcript_segments=[
                TranscriptSegment("seg-001", "Speaker 1", 0, 1000, "Discuss citations.", 0.95)
            ],
            windows=[{
                "windowId": "window-001",
                "sequenceNo": 1,
                "startMs": 0,
                "endMs": 1000,
                "segmentIds": ["seg-001"],
            }],
            local_results=[{
                "summaries": {"executive": {
                    "text": "The call discussed citations.",
                    "citationIds": [],
                }},
                "evidence": {"citations": [{
                    "id": "cite-local-001",
                    "segmentIds": ["seg-001"],
                }]},
            }],
            provider_name="test-llm",
            provider_model="test-model",
        )
        result["summaries"]["executive"]["evidenceRefs"] = ["cite-001"]

        with self.assertRaisesRegex(ValueError, "Context-only executive summary"):
            validate_result_json(result)

    def test_global_participant_count_excludes_unknown_and_keeps_fact_ids_isolated(self) -> None:
        segments = [
            TranscriptSegment("seg-001", "Speaker 1", 0, 1000, "The shipping cost is 599 dollars.", 0.94),
            TranscriptSegment("seg-002", "Speaker 2", 1000, 2000, "Yes.", 0.91),
            TranscriptSegment("seg-003", "unknown", 2000, 3000, "Thank you.", 0.88),
        ]
        windows = [
            {
                "windowId": "window-001",
                "sequenceNo": 1,
                "startMs": 0,
                "endMs": 3000,
                "segmentIds": ["seg-001", "seg-002", "seg-003"],
            }
        ]
        local_results = [
            {
                "facts": [
                    {
                        "id": "derived-window-participant-count",
                        "type": "participant_count",
                        "predicate": "has_reliable_speaker_count",
                        "value": 3,
                        "unit": "people",
                        "derivedFrom": "speakers",
                        "citationIds": [],
                    },
                    {
                        "id": "fact-001",
                        "type": "shipping_cost",
                        "predicate": "costs",
                        "value": 599,
                        "unit": "USD",
                        "citationIds": ["cite-local-001"],
                    },
                ],
                "summaries": {
                    "executive": {
                        "text": "The call discussed shipping cost.",
                        "citationIds": ["cite-local-001"],
                    }
                },
                "evidence": {
                    "citations": [
                        {
                            "id": "cite-local-001",
                            "segmentIds": ["seg-001"],
                        }
                    ]
                },
                "quality": {"warnings": []},
                "extraction": {"warnings": []},
            }
        ]

        result = reduce_window_results(
            meeting=SimpleNamespace(id="meeting-001", title="Reducer test"),
            asset=SimpleNamespace(id="asset-001"),
            transcript_segments=segments,
            windows=windows,
            local_results=local_results,
            provider_name="test-llm",
            provider_model="test-model",
        )

        validate_result_json(result)
        self.assertEqual(result["speakers"]["speakerCount"], 2)
        self.assertEqual(result["speakers"]["ignoredSpeakerLabelCount"], 1)
        self.assertEqual(result["speakers"]["ignoredSegmentCount"], 1)
        self.assertEqual(result["speakers"]["reconciledIgnoredSegmentCount"], 1)
        self.assertEqual(result["speakers"]["unresolvedIgnoredSegmentCount"], 0)
        self.assertTrue(result["speakers"]["speakerCountExact"])

        records_by_id = {
            record["id"]: record
            for record in result["knowledge"]["records"]
        }
        self.assertEqual(records_by_id["fact-001"]["subtype"], "shipping_cost")
        self.assertEqual(records_by_id["fact-001"]["data"]["value"], 599)
        self.assertNotIn("ignoredSegmentCount", records_by_id["fact-001"]["data"])

        participant_count = records_by_id["derived-transcript-participant-count"]
        self.assertEqual(participant_count["subtype"], "participant_count")
        self.assertEqual(participant_count["data"]["value"], 2)
        self.assertEqual(participant_count["data"]["unit"], "people")
        self.assertFalse(participant_count["data"]["isLowerBound"])
        self.assertEqual(participant_count["data"]["countCompleteness"], "exact")
        self.assertEqual(participant_count["evidenceRefs"], [])
        self.assertEqual(
            len(participant_count["derivedFrom"]),
            2,
            "Only reliable speaker profiles may contribute to the count.",
        )
        self.assertNotIn("derived-window-participant-count", records_by_id)

    def test_unknown_segment_between_different_speakers_keeps_count_as_lower_bound(self) -> None:
        segments = [
            TranscriptSegment("seg-001", "Speaker 1", 0, 1000, "Hello.", 0.94),
            TranscriptSegment("seg-002", "unknown", 1000, 2000, "Excuse me.", 0.80),
            TranscriptSegment("seg-003", "Speaker 2", 2000, 3000, "Yes.", 0.91),
        ]
        result = reduce_window_results(
            meeting=SimpleNamespace(id="meeting-001", title="Ambiguous speaker test"),
            asset=SimpleNamespace(id="asset-001"),
            transcript_segments=segments,
            windows=[{
                "windowId": "window-001",
                "sequenceNo": 1,
                "startMs": 0,
                "endMs": 3000,
                "segmentIds": ["seg-001", "seg-002", "seg-003"],
            }],
            local_results=[{}],
            provider_name="test-llm",
            provider_model="test-model",
        )

        participant_count = next(
            record
            for record in result["knowledge"]["records"]
            if record.get("subtype") == "participant_count"
        )
        self.assertFalse(result["speakers"]["speakerCountExact"])
        self.assertEqual(result["speakers"]["unresolvedIgnoredSegmentCount"], 1)
        self.assertTrue(participant_count["data"]["isLowerBound"])
        self.assertEqual(participant_count["data"]["countCompleteness"], "lower_bound")

    def test_unknown_only_transcript_omits_global_participant_count(self) -> None:
        result = reduce_window_results(
            meeting=SimpleNamespace(id="meeting-001", title="Unknown speaker test"),
            asset=SimpleNamespace(id="asset-001"),
            transcript_segments=[
                TranscriptSegment("seg-001", "unknown", 0, 1000, "Thank you.", 0.88)
            ],
            windows=[
                {
                    "windowId": "window-001",
                    "sequenceNo": 1,
                    "startMs": 0,
                    "endMs": 1000,
                    "segmentIds": ["seg-001"],
                }
            ],
            local_results=[
                {
                    "facts": [
                        {
                            "id": "derived-window-participant-count",
                            "type": "participant_count",
                            "predicate": "has_reliable_speaker_count",
                            "value": 1,
                            "unit": "people",
                            "derivedFrom": "speakers",
                            "citationIds": [],
                        }
                    ],
                    "summaries": {
                        "executive": {
                            "text": "The transcript contains a closing phrase.",
                            "citationIds": ["cite-local-001"],
                        }
                    },
                    "evidence": {
                        "citations": [
                            {
                                "id": "cite-local-001",
                                "segmentIds": ["seg-001"],
                            }
                        ]
                    },
                }
            ],
            provider_name="test-llm",
            provider_model="test-model",
        )

        validate_result_json(result)
        self.assertEqual(result["speakers"]["speakerCount"], 0)
        self.assertFalse(
            any(
                record.get("subtype") == "participant_count"
                for record in result["knowledge"]["records"]
            )
        )
        self.assertTrue(
            any(
                "Participant count was omitted" in warning
                for warning in result["quality"]["warnings"]
            )
        )


if __name__ == "__main__":
    unittest.main()

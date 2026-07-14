import unittest

from backend.services.processing.result_validation import validate_result_json


def _result() -> dict:
    return {
        "schemaVersion": "meeting-intelligence-result.v2",
        "document": {"meetingId": "meeting-1"},
        "transcript": {"segments": [{"id": "seg-1", "text": "Two people attended."}], "windows": [{"id": "window-1"}]},
        "evidence": {
            "items": [
                {"id": "evidence-1", "kind": "transcript", "segmentIds": ["seg-1"], "startMs": 0, "endMs": 1000, "quote": "Two people attended."},
                {"id": "evidence-2", "kind": "derived", "segmentIds": [], "quote": None},
            ]
        },
        "speakers": {"speakerCount": 2},
        "knowledge": {
            "records": [
                {
                    "id": "fact-1", "type": "fact", "subtype": "participant_count", "data": {"value": 2}, "scope": "meeting",
                    "evidenceRefs": ["evidence-2"], "sourceRefs": [], "derivedFrom": ["speakers"], "confidence": 1.0, "status": "verified",
                }
            ],
            "relationships": [],
        },
        "summaries": {"executive": {"text": "Two people attended."}},
        "quality": {},
        "extraction": {},
    }


class V2ResultValidationTestCase(unittest.TestCase):
    def test_validates_generic_record_and_derived_evidence(self) -> None:
        validate_result_json(_result())

    def test_rejects_structured_evidence_with_transcript_location(self) -> None:
        result = _result()
        result["evidence"]["items"][1]["kind"] = "structured"
        result["evidence"]["items"][1]["segmentIds"] = ["seg-1"]
        with self.assertRaisesRegex(ValueError, "Structured or derived"):
            validate_result_json(result)

    def test_rejects_unknown_record_evidence(self) -> None:
        result = _result()
        result["knowledge"]["records"][0]["evidenceRefs"] = ["missing"]
        with self.assertRaisesRegex(ValueError, "unknown evidence"):
            validate_result_json(result)


if __name__ == "__main__":
    unittest.main()

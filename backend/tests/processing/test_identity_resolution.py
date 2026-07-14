import unittest
from collections import OrderedDict
from types import SimpleNamespace

from backend.services.processing.intelligence_reducer import _infer_identity_relationships


class IdentityResolutionTestCase(unittest.TestCase):
    def test_self_introduction_creates_identity_relationship(self) -> None:
        records = OrderedDict({
            "speaker-profile-speaker-2": {
                "id": "speaker-profile-speaker-2",
                "type": "participant",
                "subtype": "speaker_profile",
                "data": {"displayName": "Speaker 2"},
            },
            "participant-andrew": {
                "id": "participant-andrew",
                "type": "participant",
                "subtype": "participant",
                "data": {"displayName": "Andrew"},
            },
        })
        segment = SimpleNamespace(
            id="seg-1",
            speaker="Speaker 2",
            text="For calling the studio, this is Andrew.",
        )
        relationships = _infer_identity_relationships(
            records,
            [segment],
            [{"id": "cite-1", "segmentIds": ["seg-1"]}],
            [{"id": "window-1"}],
        )

        self.assertEqual(len(relationships), 1)
        relationship = relationships[0]
        self.assertEqual(relationship["subtype"], "identity_resolution")
        self.assertEqual(relationship["data"]["relationType"], "identified_as")
        self.assertEqual(relationship["from"]["id"], "speaker-profile-speaker-2")
        self.assertEqual(relationship["to"]["id"], "participant-andrew")
        self.assertEqual(relationship["evidenceRefs"], ["cite-1"])

    def test_addressed_name_does_not_create_identity_relationship(self) -> None:
        records = OrderedDict({
            "speaker-profile-speaker-1": {
                "id": "speaker-profile-speaker-1",
                "type": "participant",
                "subtype": "speaker_profile",
                "data": {"displayName": "Speaker 1"},
            },
            "participant-mildred": {
                "id": "participant-mildred",
                "type": "participant",
                "subtype": "participant",
                "data": {"displayName": "Mildred Anderson"},
            },
        })
        segment = SimpleNamespace(id="seg-2", speaker="Speaker 1", text="Thanks, Mildred Anderson.")
        self.assertEqual(
            _infer_identity_relationships(records, [segment], [], [{"id": "window-1"}]),
            [],
        )


if __name__ == "__main__":
    unittest.main()

import unittest

from backend.models.meeting_models import MeetingAsset
from backend.providers.text_extraction_provider import DocumentTextExtractionProvider


class FakeStorageProvider:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def get_object_bytes(self, *, object_key: str) -> bytes:
        return self.content


class TextExtractionProviderTestCase(unittest.TestCase):
    def make_asset(self, *, file_name: str = "meeting.txt", content_type: str = "text/plain") -> MeetingAsset:
        return MeetingAsset(
            id="44444444-4444-4444-8444-444444444444",
            owner_user_id="33333333-3333-4333-8333-333333333333",
            meeting_id="11111111-1111-4111-8111-111111111111",
            object_key="workspaces/test/meetings/test/uploads/meeting.txt",
            file_name=file_name,
            content_type=content_type,
            size_bytes=100,
            idempotency_key="upload-test",
        )

    def test_plain_text_transcript_lines_become_segments(self) -> None:
        provider = DocumentTextExtractionProvider(
            FakeStorageProvider(
                b"00:00 Alice: Review the transcript JSON contract.\n"
                b"00:15 Bob: Action item is to add text extraction.\n"
            )
        )

        result = provider.extract(self.make_asset())

        self.assertEqual(len(result.segments), 2)
        self.assertEqual(result.segments[0].id, "seg-001")
        self.assertEqual(result.segments[0].speaker, "Alice")
        self.assertEqual(result.segments[0].start_ms, 0)
        self.assertIn("transcript JSON", result.segments[0].text)
        self.assertEqual(result.segments[1].speaker, "Bob")
        self.assertEqual(result.segments[1].start_ms, 15000)

    def test_vtt_cue_metadata_is_ignored(self) -> None:
        provider = DocumentTextExtractionProvider(
            FakeStorageProvider(
                b"WEBVTT\n\n"
                b"1\n"
                b"00:00:00.000 --> 00:00:02.000\n"
                b"Alice: First cue text.\n"
            )
        )

        result = provider.extract(self.make_asset(file_name="meeting.vtt", content_type="text/vtt"))

        self.assertEqual(len(result.segments), 1)
        self.assertEqual(result.segments[0].speaker, "Alice")
        self.assertEqual(result.segments[0].text, "First cue text.")


if __name__ == "__main__":
    unittest.main()

from backend.models.meeting_models import Meeting, MeetingAsset
from backend.providers.text_extraction_provider import DocumentTextExtractionProvider, get_text_extraction_provider
from backend.providers.transcript_types import TranscriptSegment


class LocalTranscriptionProvider:
    provider_name = "local-placeholder-asr"
    provider_model = "deterministic-v1"
    last_provider_name = provider_name
    last_provider_model = provider_model

    def __init__(self, text_extraction_provider: DocumentTextExtractionProvider | None = None) -> None:
        self.text_extraction_provider = text_extraction_provider

    def transcribe(self, meeting: Meeting, asset: MeetingAsset) -> list[TranscriptSegment]:
        if self.text_extraction_provider is not None and self.text_extraction_provider.can_extract(asset):
            extracted = self.text_extraction_provider.extract(asset)
            if extracted.segments:
                self.last_provider_name = self.text_extraction_provider.provider_name
                self.last_provider_model = self.text_extraction_provider.provider_model
                return extracted.segments

        self.last_provider_name = self.provider_name
        self.last_provider_model = self.provider_model
        text = (
            f"Uploaded meeting asset {asset.file_name} is ready for deeper ASR processing. "
            "This placeholder transcript preserves the processing contract until local ASR is connected."
        )
        return [
            TranscriptSegment(
                id="seg-001",
                speaker="Speaker 1",
                start_ms=0,
                end_ms=max(1000, min(asset.size_bytes * 20, 30000)),
                text=text,
                confidence=0.5,
            )
        ]


def get_transcription_provider() -> LocalTranscriptionProvider:
    return LocalTranscriptionProvider(get_text_extraction_provider())

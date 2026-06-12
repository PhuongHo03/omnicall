import re
from dataclasses import dataclass
from pathlib import Path

from backend.models.meeting_models import MeetingAsset
from backend.providers.storage_provider import ObjectStorageProvider, get_object_storage_provider
from backend.providers.transcript_types import TranscriptSegment


TEXT_TRANSCRIPT_EXTENSIONS = {".txt", ".md", ".vtt", ".srt"}
TEXT_TRANSCRIPT_CONTENT_TYPES = {
    "text/plain",
    "text/markdown",
    "text/vtt",
    "application/x-subrip",
}

_SPEAKER_LINE_RE = re.compile(
    r"^\s*(?:\[?(?P<time>(?:\d{1,2}:)?\d{1,2}:\d{2}(?:[.,]\d{1,3})?)\]?\s+)?"
    r"(?:(?P<speaker>[^:\n]{1,80}):\s*)?"
    r"(?P<text>.+?)\s*$"
)
_CUE_TIME_RE = re.compile(r"^\s*\d{1,2}:\d{2}:\d{2}[.,]\d{1,3}\s+-->\s+")


@dataclass(frozen=True)
class ExtractedTextTranscript:
    segments: list[TranscriptSegment]
    source_kind: str


class DocumentTextExtractionProvider:
    provider_name = "local-text-extraction"
    provider_model = "deterministic-v1"

    def __init__(self, storage_provider: ObjectStorageProvider) -> None:
        self.storage_provider = storage_provider

    def can_extract(self, asset: MeetingAsset) -> bool:
        extension = Path(asset.file_name).suffix.lower()
        return extension in TEXT_TRANSCRIPT_EXTENSIONS or asset.content_type in TEXT_TRANSCRIPT_CONTENT_TYPES

    def extract(self, asset: MeetingAsset) -> ExtractedTextTranscript:
        raw = self.storage_provider.get_object_bytes(object_key=asset.object_key)
        text = raw.decode("utf-8-sig", errors="replace")
        lines = _clean_text_lines(text)
        if not lines:
            return ExtractedTextTranscript(segments=[], source_kind="text")

        segments: list[TranscriptSegment] = []
        fallback_start_ms = 0
        for index, line in enumerate(lines, start=1):
            match = _SPEAKER_LINE_RE.match(line)
            if match is None:
                continue
            body = match.group("text").strip()
            if not body:
                continue
            start_ms = _parse_timestamp_ms(match.group("time")) if match.group("time") else fallback_start_ms
            end_ms = max(start_ms + 1000, start_ms + min(max(len(body) * 45, 2000), 30000))
            fallback_start_ms = end_ms + 500
            segments.append(
                TranscriptSegment(
                    id=f"seg-{len(segments) + 1:03d}",
                    speaker=(match.group("speaker") or "Speaker 1").strip(),
                    start_ms=start_ms,
                    end_ms=end_ms,
                    text=body,
                    confidence=0.95,
                )
            )

        return ExtractedTextTranscript(segments=segments, source_kind="text")


def get_text_extraction_provider() -> DocumentTextExtractionProvider:
    return DocumentTextExtractionProvider(get_object_storage_provider())


def _clean_text_lines(text: str) -> list[str]:
    cleaned: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.upper() == "WEBVTT" or line.isdigit() or _CUE_TIME_RE.match(line):
            continue
        cleaned.append(line)
    return cleaned


def _parse_timestamp_ms(value: str) -> int:
    normalized = value.replace(",", ".")
    parts = normalized.split(":")
    seconds_part = parts[-1]
    if "." in seconds_part:
        seconds_text, millis_text = seconds_part.split(".", 1)
        milliseconds = int(millis_text[:3].ljust(3, "0"))
    else:
        seconds_text = seconds_part
        milliseconds = 0
    seconds = int(seconds_text)
    minutes = int(parts[-2]) if len(parts) >= 2 else 0
    hours = int(parts[-3]) if len(parts) >= 3 else 0
    return ((hours * 3600) + (minutes * 60) + seconds) * 1000 + milliseconds

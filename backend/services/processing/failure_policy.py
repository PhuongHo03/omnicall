from backend.models.enums import MeetingStatus
from backend.providers.transcription_provider import NoRecognizableSpeechError


NO_RECOGNIZABLE_SPEECH_CODE = "NO_RECOGNIZABLE_SPEECH"
NO_RECOGNIZABLE_SPEECH_REASON = "No clear speech was detected in this recording."
PROCESSING_FAILED_CODE = "PROCESSING_FAILED"
PROCESSING_FAILED_REASON = "Meeting processing failed. Please retry later."


def safe_processing_failure(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, NoRecognizableSpeechError):
        return NO_RECOGNIZABLE_SPEECH_CODE, NO_RECOGNIZABLE_SPEECH_REASON
    return PROCESSING_FAILED_CODE, PROCESSING_FAILED_REASON


def processing_failure_code(*, status: MeetingStatus, failure_reason: str | None) -> str | None:
    if status != MeetingStatus.FAILED:
        return None
    if failure_reason == NO_RECOGNIZABLE_SPEECH_REASON:
        return NO_RECOGNIZABLE_SPEECH_CODE
    return PROCESSING_FAILED_CODE

from enum import StrEnum


class MeetingStatus(StrEnum):
    DRAFT = "DRAFT"
    UPLOADED = "UPLOADED"
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    READY = "READY"
    FAILED = "FAILED"


class ProcessingJobStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    RETRYING = "RETRYING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ProcessingJobType(StrEnum):
    MEETING_PROCESSING = "MEETING_PROCESSING"


class MeetingAssetKind(StrEnum):
    UPLOAD = "UPLOAD"
    RECORDING = "RECORDING"
    TRANSCRIPT = "TRANSCRIPT"
    EXPORT = "EXPORT"

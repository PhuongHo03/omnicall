from enum import StrEnum


class MeetingStatus(StrEnum):
    DRAFT = "DRAFT"
    UPLOADED = "UPLOADED"
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    READY = "READY"
    FAILED = "FAILED"


class MeetingAssetKind(StrEnum):
    UPLOAD = "UPLOAD"
    RECORDING = "RECORDING"
    TRANSCRIPT = "TRANSCRIPT"
    EXPORT = "EXPORT"

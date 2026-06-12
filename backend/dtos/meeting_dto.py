from datetime import datetime

from pydantic import BaseModel, Field

from backend.models.enums import MeetingStatus, ProcessingJobStatus


class MeetingCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    language: str | None = Field(default=None, max_length=16)


class MeetingResponse(BaseModel):
    id: str
    workspace_id: str
    title: str
    language: str | None
    status: MeetingStatus
    failure_reason: str | None
    created_at: datetime
    updated_at: datetime


class MeetingListResponse(BaseModel):
    items: list[MeetingResponse]


class MeetingAssetResponse(BaseModel):
    id: str
    meeting_id: str
    object_key: str
    file_name: str
    content_type: str
    size_bytes: int
    created_at: datetime


class ProcessingJobResponse(BaseModel):
    id: str
    meeting_id: str
    status: ProcessingJobStatus
    safe_failure_reason: str | None
    retry_allowed: bool
    created_at: datetime
    updated_at: datetime


class ProcessingStatusResponse(BaseModel):
    meeting: MeetingResponse
    latest_job: ProcessingJobResponse | None


class MeetingChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    session_id: str | None = None
    language: str | None = Field(default=None, max_length=16)


class MeetingChatCitationResponse(BaseModel):
    chunk_id: str
    source_type: str
    section_type: str
    json_pointer: str
    citation_ids: list[str]
    segment_ids: list[str]
    start_ms: int | None
    end_ms: int | None
    text: str


class MeetingChatMessageResponse(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    retrieved_chunk_ids: list[str]
    citations: list[MeetingChatCitationResponse]
    metadata: dict
    created_at: datetime


class MeetingChatResponse(BaseModel):
    session_id: str
    answer: str
    evidence_state: str
    citations: list[MeetingChatCitationResponse]
    message: MeetingChatMessageResponse


class MeetingChatHistoryResponse(BaseModel):
    session_id: str
    meeting_id: str
    title: str
    messages: list[MeetingChatMessageResponse]

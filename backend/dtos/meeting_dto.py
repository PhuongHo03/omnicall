from datetime import datetime

from pydantic import BaseModel, Field

from backend.models.enums import MeetingStatus


class MeetingCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=240)


class MeetingUpdateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=240)


class MeetingResponse(BaseModel):
    id: str
    title: str
    status: MeetingStatus
    failure_reason: str | None
    pending_chat_status: str | None = None
    created_at: datetime
    updated_at: datetime
    latest_asset: "MeetingAssetResponse | None" = None

class MeetingDetailResponse(MeetingResponse):
    latest_asset: "MeetingAssetResponse | None" = None
    retry_allowed: bool = False


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


class MeetingChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


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
    role: str
    content: str
    retrieved_chunk_ids: list[str]
    citations: list[MeetingChatCitationResponse]
    metadata: dict
    created_at: datetime


class MeetingChatResponse(BaseModel):
    answer: str
    evidence_state: str
    citations: list[MeetingChatCitationResponse]
    message: MeetingChatMessageResponse


class MeetingChatAcceptedResponse(BaseModel):
    status: str = "processing"
    message: str = "Question accepted. Answer is being generated."


class MeetingChatHistoryResponse(BaseModel):
    meeting_id: str
    title: str
    messages: list[MeetingChatMessageResponse]

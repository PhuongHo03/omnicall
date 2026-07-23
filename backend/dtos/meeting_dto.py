from datetime import datetime

from typing import Literal

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
    failure_code: str | None = None
    pending_chat_status: str | None = None
    created_at: datetime
    updated_at: datetime
    latest_asset: "MeetingAssetResponse | None" = None
    retry_allowed: bool = False

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
    # BCP 47 client locale, e.g. vi-VN. The backend falls back to its
    # deployment default when an older/non-browser client omits it.
    language: str | None = Field(default=None, max_length=35)


class MeetingChatFeedbackRequest(BaseModel):
    rating: Literal["up", "down", "neutral"]
    expected_revision: int | None = Field(default=None, ge=0)


class MeetingChatFeedbackResponse(BaseModel):
    message_id: str
    rating: Literal["up", "down", "neutral"]
    revision: int = Field(ge=1)
    memory_status: str
    cache_action: str


class MeetingChatCitationResponse(BaseModel):
    citation_id: str
    chunk_id: str
    source_type: str
    section_type: str
    json_pointer: str
    segment_ids: list[str]
    start_ms: int | None
    end_ms: int | None
    quote: str


class MeetingChatMessageResponse(BaseModel):
    id: str
    role: str
    content: str
    retrieved_chunk_ids: list[str]
    citations: list[MeetingChatCitationResponse]
    metadata: dict  # Owner-visible diagnostics; may include explicit raw provider/tool JSON, never hidden reasoning tokens.
    feedback_rating: Literal["up", "down"] | None = None
    feedback_revision: int | None = None
    created_at: datetime


class AgentToolCallResponse(BaseModel):
    """Response schema for a single agent tool call."""
    tool: str
    arguments: dict = Field(default_factory=dict)
    result_count: int = 0


class MeetingChatResponse(BaseModel):
    answer: str
    evidence_state: str
    citations: list[MeetingChatCitationResponse]
    message: MeetingChatMessageResponse
    # Agent metadata (optional for backward compatibility)
    iterations: int | None = None
    toolCalls: list[AgentToolCallResponse] | None = None


class MeetingChatAcceptedResponse(BaseModel):
    status: str = "processing"
    message: str = "Question accepted. Answer is being generated."
    turn_id: str | None = None


class MeetingChatHistoryResponse(BaseModel):
    meeting_id: str
    title: str
    messages: list[MeetingChatMessageResponse]

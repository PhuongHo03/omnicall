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
    metadata: dict  # May include: evidenceState, confidence, provider, model, guardrails,
                    # agentIterations, agentToolCalls, agentThoughts
    created_at: datetime


class AgentToolCallResponse(BaseModel):
    """Response schema for a single agent tool call."""
    tool: str
    arguments: dict = Field(default_factory=dict)
    result_count: int = 0


class AgentThoughtResponse(BaseModel):
    """Response schema for agent thinking step."""
    iteration: int
    decision: str = ""
    reasoning: str = ""
    tools: list[str] = Field(default_factory=list)
    duration_ms: int = 0


class MeetingChatResponse(BaseModel):
    answer: str
    evidence_state: str
    citations: list[MeetingChatCitationResponse]
    message: MeetingChatMessageResponse
    # Agent metadata (optional for backward compatibility)
    iterations: int | None = None
    toolCalls: list[AgentToolCallResponse] | None = None
    agentThoughts: list[AgentThoughtResponse] | None = None


class MeetingChatAcceptedResponse(BaseModel):
    status: str = "processing"
    message: str = "Question accepted. Answer is being generated."


class MeetingChatHistoryResponse(BaseModel):
    meeting_id: str
    title: str
    messages: list[MeetingChatMessageResponse]

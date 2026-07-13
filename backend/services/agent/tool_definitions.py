from dataclasses import dataclass
from enum import Enum
from typing import Any

from backend.models.meeting_models import MeetingChunkRecord


class ToolCategory(str, Enum):
    SEARCH = "search"
    RETRIEVAL = "retrieval"
    SYNTHESIS = "synthesis"


@dataclass(frozen=True)
class ToolParameter:
    name: str
    type: str
    description: str
    required: bool = True
    default: Any = None
    enum: list[str] | None = None


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    category: ToolCategory
    parameters: list[ToolParameter]
    returns: str


@dataclass
class ToolExecutionResult:
    tool_name: str
    success: bool
    data: list[dict[str, Any]] | dict[str, Any] | None = None
    error: str | None = None
    metadata: dict[str, Any] | None = None


def chunk_to_dict(chunk: MeetingChunkRecord) -> dict[str, Any]:
    return {
        "chunkId": chunk.chunk_id,
        "meetingId": chunk.meeting_id,
        "sectionType": chunk.section_type,
        "sourceType": chunk.source_type,
        "text": chunk.text,
        "jsonPointer": chunk.json_pointer,
        "startMs": chunk.start_ms,
        "endMs": chunk.end_ms,
        "citationIds": chunk.citation_ids or [],
        "segmentIds": chunk.segment_ids or [],
        "metadata": chunk.metadata_json or {},
    }

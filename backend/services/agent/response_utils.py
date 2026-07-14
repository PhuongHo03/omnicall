"""Pure chunk, evidence, and fallback helpers for Agentic RAG responses."""

import time
from typing import Any

from backend.services.agent.context_manager import ContextChunk

_VALID_EVIDENCE_STATES = {
    "grounded", "partial", "not_enough_evidence", "fast_path", "blocked", "error",
}


def normalize_chunk(chunk: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(chunk.get("metadata") or {})
    # Retrieval adapters may expose v2 fields at the top level. Keep one
    # canonical projection in metadata so every agent layer consumes the same
    # record/evidence contract.
    for key in ("recordId", "recordType", "subtype", "recordFields", "evidenceRefs", "sourceRefs", "derivedFrom"):
        if key in chunk and key not in metadata:
            metadata[key] = chunk[key]
    return {
        "chunkId": chunk.get("chunkId") or chunk.get("chunk_id") or "",
        "meetingId": chunk.get("meetingId") or chunk.get("meeting_id"),
        "sourceType": chunk.get("sourceType") or chunk.get("source_type") or "",
        "sectionType": chunk.get("sectionType") or chunk.get("section_type") or "",
        "jsonPointer": chunk.get("jsonPointer") or chunk.get("json_pointer") or "",
        "citationIds": list(chunk.get("citationIds") or chunk.get("citation_ids") or []),
        "segmentIds": list(chunk.get("segmentIds") or chunk.get("segment_ids") or []),
        "startMs": chunk.get("startMs") if "startMs" in chunk else chunk.get("start_ms"),
        "endMs": chunk.get("endMs") if "endMs" in chunk else chunk.get("end_ms"),
        "text": str(chunk.get("text") or ""),
        "score": float(chunk.get("score") or 0.0),
        "metadata": metadata,
    }


def to_context_chunk(chunk: dict[str, Any]) -> ContextChunk:
    metadata = dict(chunk.get("metadata") or {})
    metadata.setdefault("jsonPointer", chunk.get("jsonPointer", ""))
    metadata.setdefault("evidenceRefs", list(chunk.get("citationIds") or []))
    return ContextChunk(
        chunk_id=chunk["chunkId"],
        text=chunk.get("text", ""),
        score=float(chunk.get("score") or 0.0),
        source_type=chunk.get("sourceType", ""),
        section_type=chunk.get("sectionType", ""),
        citation_ids=list(chunk.get("citationIds") or []),
        segment_ids=list(chunk.get("segmentIds") or []),
        start_ms=chunk.get("startMs"),
        end_ms=chunk.get("endMs"),
        metadata=metadata,
    )


def fallback_answer_from_context(chunks: list[ContextChunk]) -> str:
    lines = [chunk.text.strip() for chunk in chunks[:3] if chunk.text.strip()]
    if not lines:
        return "Không đủ bằng chứng trong dữ liệu cuộc họp để trả lời câu hỏi này."
    return "Dựa trên dữ liệu cuộc họp: " + " ".join(lines)


def ensure_fact_search_for_precise_participant_attributes(
    tool_calls: list[dict[str, Any]], question: str
) -> list[dict[str, Any]]:
    if not is_precise_participant_attribute_question(question):
        return tool_calls
    if any(call.get("tool") == "search_semantic" for call in tool_calls):
        return tool_calls
    return [{"tool": "search_semantic", "parameters": {"query": question, "limit": 6}}, *tool_calls]


def is_precise_participant_attribute_question(question: str) -> bool:
    normalized = question.lower()
    return any(
        phrase in normalized
        for phrase in ("quốc tịch", "quoc tich", "công dân", "cong dan", "nationality", "citizenship", "citizen")
    )


def evidence_state(value: Any, *, has_context: bool) -> str:
    if value in _VALID_EVIDENCE_STATES:
        return str(value)
    return "grounded" if has_context else "not_enough_evidence"


def confidence(value: Any, *, default: float) -> float:
    if isinstance(value, int | float):
        return max(0.0, min(1.0, float(value)))
    return default


def elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)

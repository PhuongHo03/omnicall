"""Contracts shared by retrieval candidate and answer layers."""

from dataclasses import dataclass

from backend.models.meeting_models import MeetingChunkRecord


@dataclass(frozen=True)
class RetrievedChunk:
    record: MeetingChunkRecord
    score: float

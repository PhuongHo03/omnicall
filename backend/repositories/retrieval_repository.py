from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.models.meeting_models import MeetingChunkRecord


class MeetingChunkRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def replace_for_result(
        self,
        *,
        workspace_id: str,
        meeting_id: str,
        intelligence_result_id: str,
        chunks: list[dict],
    ) -> list[MeetingChunkRecord]:
        self.session.execute(delete(MeetingChunkRecord).where(MeetingChunkRecord.meeting_id == meeting_id))
        records: list[MeetingChunkRecord] = []
        for chunk in chunks:
            record = MeetingChunkRecord(
                workspace_id=workspace_id,
                meeting_id=meeting_id,
                intelligence_result_id=intelligence_result_id,
                chunk_id=chunk["chunkId"],
                source_type=chunk["sourceType"],
                section_type=chunk["sectionType"],
                source_id=chunk.get("sourceId"),
                json_pointer=chunk["jsonPointer"],
                text=chunk["text"],
                citation_ids=chunk.get("citationIds", []),
                segment_ids=chunk.get("segmentIds", []),
                start_ms=chunk.get("startMs"),
                end_ms=chunk.get("endMs"),
                token_count=chunk.get("tokenCount", 0),
                embedding=chunk.get("embedding"),
                visibility=chunk.get("visibility", "workspace"),
                metadata_json=chunk.get("metadata", {}),
            )
            self.session.add(record)
            records.append(record)
        self.session.flush()
        return records

    def list_for_meeting(self, meeting_id: str) -> list[MeetingChunkRecord]:
        statement = select(MeetingChunkRecord).where(MeetingChunkRecord.meeting_id == meeting_id)
        return list(self.session.scalars(statement).all())

    def list_for_workspace_meeting(self, *, workspace_id: str, meeting_id: str) -> list[MeetingChunkRecord]:
        statement = select(MeetingChunkRecord).where(
            MeetingChunkRecord.workspace_id == workspace_id,
            MeetingChunkRecord.meeting_id == meeting_id,
        )
        return list(self.session.scalars(statement).all())

    def list_by_chunk_ids_for_workspace_meeting(
        self,
        *,
        workspace_id: str,
        meeting_id: str,
        chunk_ids: list[str],
    ) -> list[MeetingChunkRecord]:
        if not chunk_ids:
            return []
        statement = select(MeetingChunkRecord).where(
            MeetingChunkRecord.workspace_id == workspace_id,
            MeetingChunkRecord.meeting_id == meeting_id,
            MeetingChunkRecord.chunk_id.in_(chunk_ids),
        )
        records = list(self.session.scalars(statement).all())
        by_chunk_id = {record.chunk_id: record for record in records}
        return [by_chunk_id[chunk_id] for chunk_id in chunk_ids if chunk_id in by_chunk_id]

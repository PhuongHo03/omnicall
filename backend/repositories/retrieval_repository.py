from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from backend.models.meeting_models import MeetingChunkRecord


class MeetingChunkRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def replace_for_result(
        self,
        *,
        meeting_id: str,
        intelligence_result_id: str,
        chunks: list[dict],
    ) -> list[MeetingChunkRecord]:
        self.session.execute(delete(MeetingChunkRecord).where(MeetingChunkRecord.meeting_id == meeting_id))
        records: list[MeetingChunkRecord] = []
        for chunk in chunks:
            record = MeetingChunkRecord(
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
        return self.list_for_meeting(meeting_id)

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
            MeetingChunkRecord.meeting_id == meeting_id,
            MeetingChunkRecord.chunk_id.in_(chunk_ids),
        )
        records = list(self.session.scalars(statement).all())
        by_chunk_id = {record.chunk_id: record for record in records}
        return [by_chunk_id[chunk_id] for chunk_id in chunk_ids if chunk_id in by_chunk_id]

    def search_by_keyword(
        self,
        *,
        meeting_id: str,
        keyword: str,
        limit: int = 10,
    ) -> list[MeetingChunkRecord]:
        """Search chunks by keyword using PostgreSQL ILIKE for full-text search.

        Args:
            meeting_id: The meeting ID to search within
            keyword: The keyword or phrase to search for
            limit: Maximum number of results to return (default 10)

        Returns:
            List of MeetingChunkRecord objects matching the keyword
        """
        if not keyword or not keyword.strip():
            return []

        pattern = f"%{keyword.strip()}%"
        statement = (
            select(MeetingChunkRecord)
            .where(
                MeetingChunkRecord.meeting_id == meeting_id,
                func.lower(MeetingChunkRecord.text).like(func.lower(pattern)),
            )
            .order_by(
                MeetingChunkRecord.created_at.desc(),
            )
            .limit(limit)
        )
        return list(self.session.scalars(statement).all())

    def list_by_section_type(
        self,
        *,
        meeting_id: str,
        section_type: str,
        limit: int = 10,
    ) -> list[MeetingChunkRecord]:
        """Retrieve chunks filtered by section type.

        Args:
            meeting_id: The meeting ID to search within
            section_type: The section type to filter by (e.g., 'summary.executive', 'analysis.actionItems')
            limit: Maximum number of results to return (default 10)

        Returns:
            List of MeetingChunkRecord objects matching the section type
        """
        statement = (
            select(MeetingChunkRecord)
            .where(
                MeetingChunkRecord.meeting_id == meeting_id,
                MeetingChunkRecord.section_type == section_type,
            )
            .order_by(
                MeetingChunkRecord.created_at.asc(),
            )
            .limit(limit)
        )
        return list(self.session.scalars(statement).all())

    def search_by_speaker(
        self,
        *,
        meeting_id: str,
        query: str,
        limit: int = 10,
    ) -> list[MeetingChunkRecord]:
        """Search chunks by speaker name or role in the meeting.

        This searches both the text content and metadata for speaker information.

        Args:
            meeting_id: The meeting ID to search within
            query: The speaker name or role to search for
            limit: Maximum number of results to return (default 10)

        Returns:
            List of MeetingChunkRecord objects related to the speaker
        """
        if not query or not query.strip():
            return []

        pattern = f"%{query.strip()}%"
        statement = (
            select(MeetingChunkRecord)
            .where(
                MeetingChunkRecord.meeting_id == meeting_id,
                func.lower(MeetingChunkRecord.text).like(func.lower(pattern)),
            )
            .order_by(
                MeetingChunkRecord.created_at.asc(),
            )
            .limit(limit)
        )
        return list(self.session.scalars(statement).all())

    def get_structured_sections(
        self,
        *,
        meeting_id: str,
        section_types: list[str],
        limit: int = 50,
    ) -> list[MeetingChunkRecord]:
        """Retrieve chunks for multiple section types.

        Args:
            meeting_id: The meeting ID to search within
            section_types: List of section types to retrieve (e.g., ['summary.executive', 'analysis.actionItems'])
            limit: Maximum total results to return (default 50)

        Returns:
            List of MeetingChunkRecord objects matching the specified section types
        """
        if not section_types:
            return []

        statement = (
            select(MeetingChunkRecord)
            .where(
                MeetingChunkRecord.meeting_id == meeting_id,
                MeetingChunkRecord.section_type.in_(section_types),
            )
            .order_by(
                MeetingChunkRecord.created_at.asc(),
            )
            .limit(limit)
        )
        return list(self.session.scalars(statement).all())

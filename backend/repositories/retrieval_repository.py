import re

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import and_, case, delete, func, or_, select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from backend.models.meeting_models import MeetingChunkRecord, MeetingRetrievalSnapshot


@dataclass(frozen=True)
class RetrievalRepairClaim:
    meeting_id: str
    token: str


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

    def current_index_generation(self, meeting_id: str) -> str | None:
        snapshot = self.session.scalar(
            select(MeetingRetrievalSnapshot)
            .where(MeetingRetrievalSnapshot.meeting_id == meeting_id)
            .execution_options(populate_existing=True)
        )
        if snapshot is not None and snapshot.status == "ready":
            return snapshot.index_generation
        return None

    def current_snapshot(self, meeting_id: str) -> MeetingRetrievalSnapshot | None:
        snapshot = self.session.scalar(
            select(MeetingRetrievalSnapshot)
            .where(MeetingRetrievalSnapshot.meeting_id == meeting_id)
            .execution_options(populate_existing=True)
        )
        return snapshot if snapshot is not None and snapshot.status == "ready" else None

    def current_snapshot_for_update(self, meeting_id: str) -> MeetingRetrievalSnapshot | None:
        snapshot = self.session.scalar(
            select(MeetingRetrievalSnapshot)
            .where(MeetingRetrievalSnapshot.meeting_id == meeting_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return snapshot if snapshot is not None and snapshot.status == "ready" else None

    def upsert_snapshot(
        self,
        *,
        meeting_id: str,
        intelligence_result_id: str,
        index_generation: str,
        embedding_identity: str,
        retrieval_contract: str,
        chunk_count: int,
        status: str = "ready",
        error: str | None = None,
    ) -> MeetingRetrievalSnapshot:
        snapshot = self.session.get(MeetingRetrievalSnapshot, meeting_id)
        if snapshot is None:
            snapshot = MeetingRetrievalSnapshot(meeting_id=meeting_id, index_generation=index_generation)
            self.session.add(snapshot)
        snapshot.intelligence_result_id = intelligence_result_id
        snapshot.index_generation = index_generation
        snapshot.embedding_identity = embedding_identity
        snapshot.retrieval_contract = retrieval_contract
        snapshot.status = status
        snapshot.chunk_count = max(0, int(chunk_count))
        snapshot.indexed_at = datetime.now(UTC) if status == "ready" else snapshot.indexed_at
        snapshot.last_error = error[:160] if error else None
        if error == "vector_repair_pending":
            snapshot.repair_status = "pending"
            snapshot.repair_lease_token = None
            snapshot.repair_lease_expires_at = None
            snapshot.repair_started_at = None
        elif status == "ready" and snapshot.repair_status != "started":
            snapshot.repair_status = "none"
            snapshot.repair_lease_token = None
            snapshot.repair_lease_expires_at = None
            snapshot.repair_started_at = None
        self.session.flush()
        return snapshot

    def claim_repair_for_publish(
        self,
        *,
        meeting_id: str,
        lease_seconds: int,
    ) -> RetrievalRepairClaim | None:
        """Claim newly persisted repair work before publishing its task."""
        snapshot = self.session.scalar(
            select(MeetingRetrievalSnapshot)
            .where(MeetingRetrievalSnapshot.meeting_id == meeting_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if snapshot is None or snapshot.repair_status != "pending":
            return None
        return self._queue_repair_claim(snapshot, lease_seconds=lease_seconds)

    def claim_stale_repairs(
        self,
        *,
        updated_before: datetime,
        limit: int,
        lease_seconds: int,
    ) -> list[RetrievalRepairClaim]:
        """Atomically recover pending or expired repair work.

        ``SKIP LOCKED`` prevents a reconciler from stealing a repair while its
        worker holds the authoritative snapshot row through a rebuild.
        """
        now = datetime.now(UTC)
        snapshots = list(
            self.session.scalars(
                select(MeetingRetrievalSnapshot)
                .where(
                    or_(
                        and_(
                            MeetingRetrievalSnapshot.repair_status == "pending",
                            MeetingRetrievalSnapshot.updated_at < updated_before,
                        ),
                        and_(
                            MeetingRetrievalSnapshot.repair_status.in_(("queued", "started")),
                            or_(
                                MeetingRetrievalSnapshot.repair_lease_expires_at.is_(None),
                                MeetingRetrievalSnapshot.repair_lease_expires_at < now,
                            ),
                        ),
                    )
                )
                .order_by(MeetingRetrievalSnapshot.updated_at.asc(), MeetingRetrievalSnapshot.meeting_id.asc())
                .with_for_update(skip_locked=True)
                .limit(max(1, int(limit)))
                .execution_options(populate_existing=True)
            ).all()
        )
        return [self._queue_repair_claim(snapshot, lease_seconds=lease_seconds) for snapshot in snapshots]

    def restore_repair_pending_if_owned(
        self,
        *,
        meeting_id: str,
        token: str,
        error: str | None = None,
    ) -> bool:
        """Restore a claim after a broker publish failure, fenced by token."""
        snapshot = self._lock_repair_snapshot(meeting_id)
        if (
            snapshot is None
            or snapshot.repair_status != "queued"
            or snapshot.repair_lease_token != token
        ):
            return False
        snapshot.repair_status = "pending"
        snapshot.repair_lease_token = None
        snapshot.repair_lease_expires_at = None
        snapshot.repair_started_at = None
        snapshot.last_error = (error or "vector_repair_pending")[:160]
        self.session.flush()
        return True

    def mark_repair_started_if_owned(
        self,
        *,
        meeting_id: str,
        token: str,
        lease_seconds: int,
    ) -> bool:
        snapshot = self._lock_repair_snapshot(meeting_id)
        if (
            snapshot is None
            or snapshot.repair_status != "queued"
            or snapshot.repair_lease_token != token
        ):
            return False
        now = datetime.now(UTC)
        snapshot.repair_status = "started"
        snapshot.repair_attempt_count += 1
        snapshot.repair_started_at = now
        snapshot.repair_lease_expires_at = now + timedelta(seconds=max(30, int(lease_seconds)))
        self.session.flush()
        return True

    def lock_started_repair_if_owned(
        self,
        *,
        meeting_id: str,
        token: str,
    ) -> MeetingRetrievalSnapshot | None:
        """Hold the snapshot row for the complete authoritative rebuild."""
        snapshot = self._lock_repair_snapshot(meeting_id)
        if (
            snapshot is None
            or snapshot.repair_status != "started"
            or snapshot.repair_lease_token != token
        ):
            return None
        return snapshot

    def requeue_repair_if_owned(
        self,
        *,
        meeting_id: str,
        token: str,
        lease_seconds: int,
        error: str | None = None,
    ) -> bool:
        """Make a failed attempt retryable without invalidating its task token."""
        snapshot = self._lock_repair_snapshot(meeting_id)
        if (
            snapshot is None
            or snapshot.repair_status not in {"queued", "started"}
            or snapshot.repair_lease_token != token
        ):
            return False
        snapshot.repair_status = "queued"
        snapshot.repair_started_at = None
        snapshot.repair_lease_expires_at = datetime.now(UTC) + timedelta(
            seconds=max(30, int(lease_seconds))
        )
        snapshot.last_error = (error or "vector_repair_retry")[:160]
        self.session.flush()
        return True

    def finish_repair_if_owned(
        self,
        *,
        meeting_id: str,
        token: str,
        error: str | None = None,
    ) -> bool:
        """Finish a non-rebuild terminal path such as a deleted source result."""
        snapshot = self._lock_repair_snapshot(meeting_id)
        if (
            snapshot is None
            or snapshot.repair_status != "started"
            or snapshot.repair_lease_token != token
        ):
            return False
        snapshot.repair_status = "none"
        snapshot.repair_lease_token = None
        snapshot.repair_lease_expires_at = None
        snapshot.repair_started_at = None
        snapshot.last_error = error[:160] if error else None
        self.session.flush()
        return True

    def _queue_repair_claim(
        self,
        snapshot: MeetingRetrievalSnapshot,
        *,
        lease_seconds: int,
    ) -> RetrievalRepairClaim:
        token = str(uuid4())
        snapshot.repair_status = "queued"
        snapshot.repair_lease_token = token
        snapshot.repair_lease_expires_at = datetime.now(UTC) + timedelta(
            seconds=max(30, int(lease_seconds))
        )
        snapshot.repair_started_at = None
        snapshot.last_error = "vector_repair_pending"
        self.session.flush()
        return RetrievalRepairClaim(meeting_id=snapshot.meeting_id, token=token)

    def _lock_repair_snapshot(self, meeting_id: str) -> MeetingRetrievalSnapshot | None:
        return self.session.scalar(
            select(MeetingRetrievalSnapshot)
            .where(MeetingRetrievalSnapshot.meeting_id == meeting_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    def list_by_chunk_ids_for_meeting(
        self,
        *,
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

        raw_keyword = keyword.strip()
        pattern = f"%{raw_keyword}%"
        exact_statement = (
            select(MeetingChunkRecord)
            .where(
                MeetingChunkRecord.meeting_id == meeting_id,
                func.lower(MeetingChunkRecord.text).like(func.lower(pattern)),
            )
            .order_by(MeetingChunkRecord.created_at.desc())
            .limit(limit)
        )
        exact_matches = list(self.session.scalars(exact_statement).all())
        if exact_matches:
            return exact_matches

        # Support planner-generated expressions such as "price OR cost OR
        # dollar" and avoid requiring an entire user sentence to occur in a
        # canonical English JSON chunk.
        terms = [term for term in re.findall(r"[\w$]+", raw_keyword.lower()) if len(term) >= 2]
        if not terms:
            return []
        term_predicates = [func.lower(MeetingChunkRecord.text).like(f"%{term}%") for term in terms]
        statement = (
            select(MeetingChunkRecord)
            .where(
                MeetingChunkRecord.meeting_id == meeting_id,
                or_(*term_predicates),
            )
            .order_by(
                MeetingChunkRecord.created_at.desc(),
            )
            .limit(limit)
        )
        return list(self.session.scalars(statement).all())

    def search_by_trigram(
        self,
        *,
        meeting_id: str,
        query: str,
        threshold: float,
        limit: int,
    ) -> list[tuple[MeetingChunkRecord, float]]:
        if not query or not query.strip():
            return []
        similarity = func.similarity(func.lower(MeetingChunkRecord.text), query.strip().lower())
        statement = (
            select(MeetingChunkRecord, similarity.label("similarity"))
            .where(
                MeetingChunkRecord.meeting_id == meeting_id,
                similarity >= threshold,
            )
            .order_by(similarity.desc(), MeetingChunkRecord.created_at.asc())
            .limit(limit)
        )
        try:
            rows = self.session.execute(statement).all()
        except ProgrammingError as exc:
            if "similarity" not in str(exc).lower() and "pg_trgm" not in str(exc).lower():
                raise
            self.session.rollback()
            return []
        return [(record, float(score)) for record, score in rows]

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
            section_type: The section type to filter by (e.g., 'summary.executive', 'action.item')
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
            .order_by(MeetingChunkRecord.created_at.asc())
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
            section_types: List of section types to retrieve (e.g., ['summary.executive', 'action.item'])
            limit: Maximum total results to return (default 50)

        Returns:
            List of MeetingChunkRecord objects matching the specified section types
        """
        if not section_types:
            return []

        section_order = {section_type: index for index, section_type in enumerate(dict.fromkeys(section_types))}
        statement = (
            select(MeetingChunkRecord)
            .where(
                MeetingChunkRecord.meeting_id == meeting_id,
                MeetingChunkRecord.section_type.in_(section_types),
            )
            .order_by(
                case(
                    section_order,
                    value=MeetingChunkRecord.section_type,
                    else_=len(section_order),
                ).asc(),
                MeetingChunkRecord.created_at.asc(),
                MeetingChunkRecord.chunk_id.asc(),
            )
            .limit(limit)
        )
        return list(self.session.scalars(statement).all())

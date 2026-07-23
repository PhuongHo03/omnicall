from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from backend.configs.settings import Settings, get_settings
from backend.models.enums import MeetingStatus
from backend.models.meeting_models import Meeting
from backend.providers.lock_provider import RedisLockProvider, get_redis_lock_provider
from backend.providers.app_metrics_provider import CHAT_TURN_TOTAL
from backend.providers.queue_provider import (
    ChatQueueProvider,
    ProcessingQueueProvider,
    get_chat_queue_provider,
    get_processing_queue_provider,
)
from backend.repositories.chat_repository import ChatTurnRepository
from backend.repositories.meeting_repository import MeetingRepository
from backend.repositories.retrieval_repository import MeetingChunkRepository


class ProcessingReconciliationService:
    lock_key = "lock:processing-meeting-reconciliation"

    def __init__(
        self,
        *,
        session: Session,
        settings: Settings | None = None,
        lock_provider: RedisLockProvider | None = None,
        queue_provider: ProcessingQueueProvider | None = None,
        meetings: MeetingRepository | None = None,
        chat_queue_provider: ChatQueueProvider | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.lock_provider = lock_provider or get_redis_lock_provider()
        self.queue_provider = queue_provider or get_processing_queue_provider()
        self.meetings = meetings or MeetingRepository(session)
        self.chat_queue_provider = chat_queue_provider or get_chat_queue_provider()
        self.chat_turns = ChatTurnRepository(session)
        self.retrieval_snapshots = MeetingChunkRepository(session)

    def reconcile(self) -> dict[str, int | str]:
        lock_ttl = max(self.settings.processing_reconciliation_interval_seconds * 2, 60)
        lock_token = self.lock_provider.acquire(self.lock_key, ttl_seconds=lock_ttl)
        if lock_token is None:
            return {"status": "locked", "scanned": 0, "republished": 0, "failed": 0}

        try:
            now = datetime.now(UTC)
            stale_before = now - timedelta(seconds=self.settings.processing_reconciliation_stale_seconds)
            stale_meetings = self.meetings.list_stale_queued(
                updated_before=stale_before,
                limit=self.settings.processing_reconciliation_batch_size,
            )
            republished = 0
            failed = 0

            for meeting in stale_meetings:
                try:
                    self.queue_provider.enqueue_meeting_processing(
                        meeting_id=meeting.id,
                    )
                except Exception:
                    failed += 1
                    continue

                republished += 1

            self.session.commit()
            chat_result = self.reconcile_chat_work(stale_before=stale_before)
            
            return {
                "status": "completed",
                "scanned": len(stale_meetings),
                "republished": republished,
                "failed": failed,
                "stale_chat_scanned": chat_result["scanned"],
                "stale_chat_republished": chat_result["republished"],
                "retrieval_repair_queued": chat_result["retrieval_repair_queued"],
            }
        finally:
            self.lock_provider.release(self.lock_key, lock_token)

    def reconcile_chat_work(self, *, stale_before: datetime) -> dict[str, int]:
        if not hasattr(self.session, "scalars"):
            return {
                "scanned": 0,
                "republished": 0,
                "retrieval_repair_queued": 0,
            }
        turns = self.chat_turns.list_stale_active(
            updated_before=stale_before,
            limit=self.settings.processing_reconciliation_batch_size,
        )
        turn_ids: list[str] = []
        for turn in turns:
            self.chat_turns.mark_queued(turn, reason="stale_turn_recovery")
            meeting = self.session.get(Meeting, turn.meeting_id)
            if meeting is not None:
                meeting.pending_chat_status = "queued"
            turn_ids.append(turn.id)
        # Commit every locked stale row into a claimable state before any
        # broker publish. No unprocessed row lock is released halfway through
        # the batch, and a fast worker can never observe the old lease.
        self.session.commit()
        republished = 0
        for turn_id in turn_ids:
            try:
                self.chat_queue_provider.enqueue_turn(turn_id=turn_id)
            except Exception:
                continue
            republished += 1
            CHAT_TURN_TOTAL.labels("recovered").inc()

        repair_claims = self.retrieval_snapshots.claim_stale_repairs(
            updated_before=stale_before,
            limit=self.settings.processing_reconciliation_batch_size,
            lease_seconds=self._retrieval_repair_lease_seconds(),
        )
        # Claims must be durable before the broker can expose their tokens.
        self.session.commit()
        retrieval_repair_queued = 0
        for claim in repair_claims:
            try:
                self.queue_provider.enqueue_retrieval_repair(
                    meeting_id=claim.meeting_id,
                    repair_token=claim.token,
                )
            except Exception:
                self.retrieval_snapshots.restore_repair_pending_if_owned(
                    meeting_id=claim.meeting_id,
                    token=claim.token,
                )
                self.session.commit()
                continue
            retrieval_repair_queued += 1
        return {
            "scanned": len(turns),
            "republished": republished,
            "retrieval_repair_queued": retrieval_repair_queued,
        }

    def _retrieval_repair_lease_seconds(self) -> int:
        return max(
            60,
            int(self.settings.redis_processing_lock_ttl_seconds),
            int(self.settings.processing_reconciliation_stale_seconds) * 2,
        )

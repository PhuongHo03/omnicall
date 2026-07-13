from sqlalchemy import delete
from sqlalchemy.orm import Session

from backend.dependencies.auth import CurrentUserContext
from backend.dtos.error_dto import DeleteResponse
from backend.configs.settings import Settings, get_settings
from backend.models.meeting_models import (
    ChatMessage,
    Meeting,
    MeetingChunkRecord,
    MeetingIntelligenceResult,
)
from backend.providers.cache_provider import CacheProviderError, JsonCacheProvider, get_json_cache_provider
from backend.providers.lock_provider import RedisLockProvider, get_redis_lock_provider
from backend.providers.queue_provider import ProcessingQueueProvider, get_processing_queue_provider
from backend.providers.storage_provider import ObjectStorageProvider
from backend.providers.vector_provider import VectorProvider, get_vector_provider
from backend.repositories.auth_repository import AuditEventRepository
from backend.repositories.meeting_repository import MeetingRepository
from backend.services.operational_log_service import OperationalLogService
from backend.utils.exceptions import ApplicationError


class AdminMeetingService:
    def __init__(
        self,
        session: Session,
        storage_provider: ObjectStorageProvider,
        vector_provider: VectorProvider | None = None,
        lock_provider: RedisLockProvider | None = None,
        queue_provider: ProcessingQueueProvider | None = None,
        cache_provider: JsonCacheProvider | None = None,
        operational_logs: OperationalLogService | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.storage_provider = storage_provider
        self.vector_provider = vector_provider or get_vector_provider()
        self.lock_provider = lock_provider or get_redis_lock_provider()
        self.queue_provider = queue_provider or get_processing_queue_provider()
        self.cache_provider = cache_provider or get_json_cache_provider()
        self.operational_logs = operational_logs
        self.settings = settings or get_settings()
        self.meetings = MeetingRepository(session)
        self.audit = AuditEventRepository(session)

    def delete_meeting(
        self,
        context: CurrentUserContext,
        meeting_id: str,
        *,
        require_owner: bool = False,
        use_processing_lock: bool = True,
        commit: bool = True,
    ) -> DeleteResponse:
        lock_key = f"lock:meeting-processing:{meeting_id}"
        lock_token = None
        if use_processing_lock:
            lock_token = self.lock_provider.acquire(lock_key)
            if lock_token is None:
                raise ApplicationError(
                    409,
                    "meeting_processing_in_progress",
                    "Meeting processing is currently running. Please retry deletion after processing finishes.",
                )
        try:
            response = self._delete_meeting_without_lock(context, meeting_id, require_owner=require_owner)
            if commit:
                self.session.commit()
                self._invalidate_admin_metrics_cache()
                self._clear_operational_logs(meeting_id)
            return response
        finally:
            if lock_token is not None:
                self.lock_provider.release(lock_key, lock_token)

    def _clear_operational_logs(self, meeting_id: str) -> None:
        if self.operational_logs is None:
            return
        try:
            self.operational_logs.clear_by_meeting(meeting_id)
        except Exception:
            # Log cleanup is best effort and must not turn a successful deletion into a failure.
            return

    def _delete_meeting_without_lock(
        self,
        context: CurrentUserContext,
        meeting_id: str,
        *,
        require_owner: bool = False,
    ) -> DeleteResponse:
        meeting = (
            self.meetings.get_for_owner(meeting_id, context.user_id)
            if require_owner
            else self.meetings.get(meeting_id)
        )
        if meeting is None:
            self.audit.create(
                event_type="meeting.delete",
                outcome="not_found",
                user_id=context.user_id,
                resource_type="meeting",
                resource_id=meeting_id,
            )
            self.session.commit()
            raise ApplicationError(404, "meeting_not_found", "Meeting was not found.")

        queue_metadata = self.queue_provider.revoke_meeting_processing(meeting_ids=[meeting.id])
        if queue_metadata.get("status") != "requested":
            raise ApplicationError(
                503,
                "processing_queue_unavailable",
                "Processing tasks could not be revoked. Please retry the deletion.",
            )
        object_keys = [asset.object_key for asset in meeting.assets]
        self._delete_vectors(meeting.id)
        self.session.execute(delete(ChatMessage).where(ChatMessage.meeting_id == meeting.id))
        self.session.execute(delete(MeetingChunkRecord).where(MeetingChunkRecord.meeting_id == meeting.id))
        self.session.execute(delete(MeetingIntelligenceResult).where(MeetingIntelligenceResult.meeting_id == meeting.id))
        for asset in list(meeting.assets):
            self.session.delete(asset)
        self.session.delete(meeting)

        for object_key in sorted(set(object_keys)):
            self.storage_provider.remove_object(object_key=object_key)

        self.audit.create(
            event_type="meeting.delete",
            outcome="success",
            user_id=context.user_id,
            resource_type="meeting",
            resource_id=meeting.id,
            metadata={
                "objectCount": len(set(object_keys)),
                
                "queue": queue_metadata,
            },
        )
        return DeleteResponse(id=meeting_id, deleted=True)

    def _delete_vectors(self, meeting_id: str) -> None:
        try:
            self.vector_provider.delete_meeting(meeting_id=meeting_id)
        except Exception as exc:
            raise ApplicationError(
                503,
                "vector_index_unavailable",
                "Meeting vectors could not be removed. Please retry the deletion.",
            ) from exc

    def _invalidate_admin_metrics_cache(self) -> None:
        try:
            self.cache_provider.delete_key(self.settings.admin_metrics_cache_key)
        except CacheProviderError:
            return

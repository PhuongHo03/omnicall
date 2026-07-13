from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.configs.settings import Settings, get_settings
from backend.dependencies.auth import CurrentUserContext
from backend.dtos.admin_dto import AdminAccountListResponse, AdminAccountResponse
from backend.dtos.error_dto import DeleteResponse
from backend.models.meeting_models import Meeting, MeetingAsset
from backend.providers.cache_provider import CacheProviderError, JsonCacheProvider, get_json_cache_provider
from backend.providers.lock_provider import RedisLockProvider, get_redis_lock_provider
from backend.providers.queue_provider import ProcessingQueueProvider, get_processing_queue_provider
from backend.providers.storage_provider import ObjectStorageProvider
from backend.repositories.auth_repository import AuditEventRepository, AuthRepository
from backend.services.admin_meeting_service import AdminMeetingService
from backend.services.operational_log_service import OperationalLogService
from backend.utils.exceptions import ApplicationError


class AdminAccountService:
    def __init__(
        self,
        session: Session,
        storage_provider: ObjectStorageProvider,
        lock_provider: RedisLockProvider | None = None,
        queue_provider: ProcessingQueueProvider | None = None,
        cache_provider: JsonCacheProvider | None = None,
        operational_logs: OperationalLogService | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.storage_provider = storage_provider
        self.lock_provider = lock_provider or get_redis_lock_provider()
        self.queue_provider = queue_provider or get_processing_queue_provider()
        self.cache_provider = cache_provider or get_json_cache_provider()
        self.operational_logs = operational_logs
        self.settings = settings or get_settings()
        self.auth = AuthRepository(session)
        self.audit = AuditEventRepository(session)

    def list_accounts(self, context: CurrentUserContext) -> AdminAccountListResponse:
        return AdminAccountListResponse(
            items=[
                AdminAccountResponse(
                    user_id=user.id,
                    email=user.email,
                    display_name=user.display_name,
                    role=_normalize_product_role(user.role),
                    created_at=user.created_at,
                    can_change_role=user.id != context.user_id,
                )
                for user in self.auth.list_accounts()
            ]
        )

    def update_account_role(self, context: CurrentUserContext, user_id: str, role: str) -> AdminAccountResponse:
        if user_id == context.user_id:
            raise ApplicationError(409, "cannot_change_own_role", "Admins cannot change their own role.")
        user = self.auth.get_user(user_id)
        if user is None:
            raise ApplicationError(404, "account_not_found", "Account was not found.")

        next_role = _normalize_product_role(role)
        previous_role = _normalize_product_role(user.role)
        self.auth.update_user_role(user, next_role)
        self.audit.create(
            event_type="admin.account.role_update",
            outcome="success",
            user_id=context.user_id,
            resource_type="user",
            resource_id=user_id,
            metadata={"previousRole": previous_role, "nextRole": next_role},
        )
        self.session.commit()
        return AdminAccountResponse(
            user_id=user.id,
            email=user.email,
            display_name=user.display_name,
            role=next_role,
            created_at=user.created_at,
            can_change_role=True,
        )

    def delete_account(self, context: CurrentUserContext, user_id: str) -> DeleteResponse:
        if user_id == context.user_id:
            raise ApplicationError(409, "cannot_delete_own_account", "Admins cannot delete their own account.")
        user = self.auth.get_user(user_id)
        if user is None:
            raise ApplicationError(404, "account_not_found", "Account was not found.")

        meeting_ids = list(self.session.scalars(select(Meeting.id).where(Meeting.owner_user_id == user_id)).all())
        acquired_locks = self._acquire_meeting_processing_locks(context, user_id, meeting_ids)
        try:
            meeting_service = AdminMeetingService(
                self.session,
                self.storage_provider,
                lock_provider=self.lock_provider,
                queue_provider=self.queue_provider,
                cache_provider=self.cache_provider,
                operational_logs=self.operational_logs,
                settings=self.settings,
            )
            for meeting_id in meeting_ids:
                meeting_service.delete_meeting(context, meeting_id, use_processing_lock=False, commit=False)

            object_keys = list(
                self.session.scalars(
                    select(MeetingAsset.object_key).where(
                        MeetingAsset.owner_user_id == user_id,
                        MeetingAsset.meeting_id.is_(None),
                    )
                ).all()
            )
            self.session.execute(
                delete(MeetingAsset).where(
                    MeetingAsset.owner_user_id == user_id,
                    MeetingAsset.meeting_id.is_(None),
                )
            )
            for object_key in sorted(set(object_keys)):
                self.storage_provider.remove_object(object_key=object_key)

            self.session.delete(user)
            self.audit.create(
                event_type="admin.account.delete",
                outcome="success",
                user_id=context.user_id,
                resource_type="user",
                resource_id=user_id,
                metadata={
                    "meetingCount": len(meeting_ids),
                    "objectCount": len(set(object_keys)),
                    "processingLocks": len(acquired_locks),
                },
            )
            self.session.commit()
            self._invalidate_admin_metrics_cache()
            if self.operational_logs is not None:
                for meeting_id in meeting_ids:
                    try:
                        self.operational_logs.clear_by_meeting(meeting_id)
                    except Exception:
                        # Log cleanup is best effort and must not turn account deletion into a failure.
                        continue
            return DeleteResponse(id=user_id, deleted=True)
        finally:
            self._release_meeting_processing_locks(acquired_locks)

    def _acquire_meeting_processing_locks(
        self,
        context: CurrentUserContext,
        user_id: str,
        meeting_ids: list[str],
    ) -> list[tuple[str, str]]:
        acquired_locks: list[tuple[str, str]] = []
        for meeting_id in meeting_ids:
            lock_key = f"lock:meeting-processing:{meeting_id}"
            lock_token = self.lock_provider.acquire(lock_key)
            if lock_token is None:
                self._release_meeting_processing_locks(acquired_locks)
                self.audit.create(
                    event_type="admin.account.delete",
                    outcome="blocked",
                    user_id=context.user_id,
                    resource_type="user",
                    resource_id=user_id,
                    metadata={"reason": "meeting_processing_in_progress", "meetingId": meeting_id},
                )
                self.session.commit()
                raise ApplicationError(
                    409,
                    "account_meeting_processing_in_progress",
                    "One or more meetings for this account are currently processing. Please retry account deletion later.",
                )
            acquired_locks.append((lock_key, lock_token))
        return acquired_locks

    def _release_meeting_processing_locks(self, acquired_locks: list[tuple[str, str]]) -> None:
        for lock_key, lock_token in reversed(acquired_locks):
            self.lock_provider.release(lock_key, lock_token)

    def _invalidate_admin_metrics_cache(self) -> None:
        try:
            self.cache_provider.delete_key(self.settings.admin_metrics_cache_key)
        except CacheProviderError:
            return


def _normalize_product_role(role: str) -> str:
    return "Admin" if role == "Admin" else "User"

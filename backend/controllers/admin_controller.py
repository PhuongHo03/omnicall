from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.configs.database import get_db_session
from backend.dependencies.auth import CurrentUserContext, require_admin_context
from backend.configs.settings import get_settings
from backend.dtos.admin_dto import (
    AdminAccountListResponse,
    AdminAccountResponse,
    AdminAccountRoleUpdateRequest,
    AdminMetricsResponse,
    AdminOperationalLogClearResponse,
    AdminOperationalLogListResponse,
)
from backend.dtos.file_dto import DeleteResponse
from backend.providers.storage_provider import ObjectStorageProvider, get_object_storage_provider
from backend.repositories.auth_repository import AuditEventRepository
from backend.services.admin_account_service import AdminAccountService
from backend.services.admin_meeting_service import AdminMeetingService
from backend.services.admin_metrics_service import AdminMetricsService, get_admin_metrics_service
from backend.services.operational_log_service import OperationalLogService, get_operational_log_service

router = APIRouter(prefix="/admin", tags=["admin"])


def get_admin_meeting_service(
    session: Session = Depends(get_db_session),
    storage_provider: ObjectStorageProvider = Depends(get_object_storage_provider),
) -> AdminMeetingService:
    return AdminMeetingService(session, storage_provider)


def get_admin_account_service(
    session: Session = Depends(get_db_session),
    storage_provider: ObjectStorageProvider = Depends(get_object_storage_provider),
) -> AdminAccountService:
    return AdminAccountService(session, storage_provider)


@router.get("/metrics", response_model=AdminMetricsResponse)
def read_admin_metrics(
    context: CurrentUserContext = Depends(require_admin_context),
    service: AdminMetricsService = Depends(get_admin_metrics_service),
    session: Session = Depends(get_db_session),
) -> AdminMetricsResponse:
    response = service.get_metrics()
    AuditEventRepository(session).create(
        event_type="admin.metrics.access",
        outcome="success",
        user_id=context.user_id,
        resource_type="admin_metrics",
    )
    session.commit()
    return response


@router.delete("/meetings/{meeting_id}", response_model=DeleteResponse)
def delete_meeting(
    meeting_id: str,
    context: CurrentUserContext = Depends(require_admin_context),
    service: AdminMeetingService = Depends(get_admin_meeting_service),
) -> DeleteResponse:
    return service.delete_meeting(context, meeting_id)


@router.get("/accounts", response_model=AdminAccountListResponse)
def list_accounts(
    context: CurrentUserContext = Depends(require_admin_context),
    service: AdminAccountService = Depends(get_admin_account_service),
) -> AdminAccountListResponse:
    return service.list_accounts(context)


@router.patch("/accounts/{user_id}/role", response_model=AdminAccountResponse)
def update_account_role(
    user_id: str,
    request: AdminAccountRoleUpdateRequest,
    context: CurrentUserContext = Depends(require_admin_context),
    service: AdminAccountService = Depends(get_admin_account_service),
) -> AdminAccountResponse:
    return service.update_account_role(context, user_id, request.role)


@router.delete("/accounts/{user_id}", response_model=DeleteResponse)
def delete_account(
    user_id: str,
    context: CurrentUserContext = Depends(require_admin_context),
    service: AdminAccountService = Depends(get_admin_account_service),
) -> DeleteResponse:
    return service.delete_account(context, user_id)


@router.get("/logs", response_model=AdminOperationalLogListResponse)
def read_operational_logs(
    limit: int = Query(default=get_settings().operational_log_default_tail, ge=1, le=1000),
    flow: str | None = Query(default=None, pattern="^(processing|rag)$"),
    level: str | None = Query(default=None, pattern="^(info|error)$"),
    search: str | None = Query(default=None, max_length=200),
    _: CurrentUserContext = Depends(require_admin_context),
    service: OperationalLogService = Depends(get_operational_log_service),
) -> AdminOperationalLogListResponse:
    settings = get_settings()
    return AdminOperationalLogListResponse(
        items=service.tail(limit=limit, flow=flow, level=level, search=search),
        limit=limit,
        retained_limit=settings.operational_log_max_length,
    )


@router.delete("/logs", response_model=AdminOperationalLogClearResponse)
def clear_operational_logs(
    _: CurrentUserContext = Depends(require_admin_context),
    service: OperationalLogService = Depends(get_operational_log_service),
) -> AdminOperationalLogClearResponse:
    return AdminOperationalLogClearResponse(cleared=service.clear() > 0)

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.configs.database import get_db_session
from backend.dependencies.auth import CurrentUserContext, require_admin_context
from backend.dtos.admin_dto import AdminMetricsResponse
from backend.dtos.file_dto import DeleteResponse
from backend.providers.storage_provider import ObjectStorageProvider, get_object_storage_provider
from backend.repositories.auth_repository import AuditEventRepository
from backend.services.admin_meeting_service import AdminMeetingService
from backend.services.admin_metrics_service import AdminMetricsService, get_admin_metrics_service

router = APIRouter(prefix="/admin", tags=["admin"])


def get_admin_meeting_service(
    session: Session = Depends(get_db_session),
    storage_provider: ObjectStorageProvider = Depends(get_object_storage_provider),
) -> AdminMeetingService:
    return AdminMeetingService(session, storage_provider)


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
        workspace_id=context.workspace_id,
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

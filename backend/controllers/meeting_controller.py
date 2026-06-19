from uuid import uuid4
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Header, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from backend.configs.database import get_db_session
from backend.configs.settings import get_settings
from backend.dependencies.auth import CurrentUserContext, get_current_context
from backend.dtos.meeting_dto import (
    MeetingChatHistoryResponse,
    MeetingChatRequest,
    MeetingChatResponse,
    MeetingAssetResponse,
    MeetingCreateRequest,
    MeetingListResponse,
    MeetingResponse,
    ProcessingJobResponse,
    ProcessingStatusResponse,
)
from backend.providers.queue_provider import ProcessingQueueProvider, get_processing_queue_provider
from backend.providers.storage_provider import ObjectStorageProvider, get_object_storage_provider
from backend.services.chat_service import MeetingChatService
from backend.services.intelligence_service import IntelligenceService
from backend.services.meeting_service import MeetingService
from backend.services.operational_log_service import OperationalLogService, get_operational_log_service
from backend.utils.exceptions import ApplicationError

router = APIRouter(prefix="/meetings", tags=["meetings"])


def get_meeting_service(
    session: Session = Depends(get_db_session),
    storage_provider: ObjectStorageProvider = Depends(get_object_storage_provider),
    queue_provider: ProcessingQueueProvider = Depends(get_processing_queue_provider),
    operational_logs: OperationalLogService = Depends(get_operational_log_service),
) -> MeetingService:
    return MeetingService(
        session,
        storage_provider,
        queue_provider,
        settings=get_settings(),
        operational_logs=operational_logs,
    )


def get_intelligence_service(session: Session = Depends(get_db_session)) -> IntelligenceService:
    return IntelligenceService(session)


def get_chat_service(
    session: Session = Depends(get_db_session),
    operational_logs: OperationalLogService = Depends(get_operational_log_service),
) -> MeetingChatService:
    return MeetingChatService(session, operational_logs=operational_logs)


def normalize_idempotency_key(idempotency_key: str | None, fallback: str) -> str:
    key = idempotency_key or fallback
    if len(key) > 160:
        raise ApplicationError(400, "idempotency_key_too_long", "Idempotency-Key must be 160 characters or fewer.")
    return key


@router.post("", response_model=MeetingResponse, status_code=status.HTTP_201_CREATED)
def create_meeting(
    request: MeetingCreateRequest,
    context: CurrentUserContext = Depends(get_current_context),
    meeting_service: MeetingService = Depends(get_meeting_service),
) -> MeetingResponse:
    return meeting_service.create_meeting(context, request)


@router.get("", response_model=MeetingListResponse)
def list_meetings(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    context: CurrentUserContext = Depends(get_current_context),
    meeting_service: MeetingService = Depends(get_meeting_service),
) -> MeetingListResponse:
    return MeetingListResponse(items=meeting_service.list_meetings(context, limit=limit, offset=offset))


@router.get("/{meeting_id}", response_model=MeetingResponse)
def get_meeting(
    meeting_id: str,
    context: CurrentUserContext = Depends(get_current_context),
    meeting_service: MeetingService = Depends(get_meeting_service),
) -> MeetingResponse:
    return meeting_service.get_meeting(context, meeting_id)


@router.post("/{meeting_id}/assets", response_model=MeetingAssetResponse, status_code=status.HTTP_201_CREATED)
def upload_meeting_asset(
    meeting_id: str,
    file: UploadFile = File(...),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: CurrentUserContext = Depends(get_current_context),
    meeting_service: MeetingService = Depends(get_meeting_service),
) -> MeetingAssetResponse:
    key = normalize_idempotency_key(idempotency_key, fallback=f"upload:{uuid4()}")
    return meeting_service.upload_asset(context, meeting_id, file, key)


@router.post("/{meeting_id}/process", response_model=ProcessingJobResponse, status_code=status.HTTP_202_ACCEPTED)
def process_meeting(
    meeting_id: str,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: CurrentUserContext = Depends(get_current_context),
    meeting_service: MeetingService = Depends(get_meeting_service),
) -> ProcessingJobResponse:
    key = normalize_idempotency_key(idempotency_key, fallback=f"process:{meeting_id}")
    return meeting_service.queue_processing(context, meeting_id, key)


@router.get("/{meeting_id}/processing-status", response_model=ProcessingStatusResponse)
def get_processing_status(
    meeting_id: str,
    context: CurrentUserContext = Depends(get_current_context),
    meeting_service: MeetingService = Depends(get_meeting_service),
) -> ProcessingStatusResponse:
    return meeting_service.get_processing_status(context, meeting_id)


@router.get("/{meeting_id}/assets/{asset_id}/content")
def get_meeting_asset_content(
    meeting_id: str,
    asset_id: str,
    context: CurrentUserContext = Depends(get_current_context),
    meeting_service: MeetingService = Depends(get_meeting_service),
) -> Response:
    asset_content = meeting_service.get_asset_content(context, meeting_id, asset_id)
    encoded_name = quote(asset_content.file_name)
    return Response(
        content=asset_content.data,
        media_type=asset_content.content_type,
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{encoded_name}"},
    )


@router.get("/{meeting_id}/intelligence-result")
def get_meeting_intelligence_result(
    meeting_id: str,
    context: CurrentUserContext = Depends(get_current_context),
    intelligence_service: IntelligenceService = Depends(get_intelligence_service),
) -> dict:
    return intelligence_service.get_result(context, meeting_id)


@router.post("/{meeting_id}/chat", response_model=MeetingChatResponse)
def ask_meeting_chat(
    meeting_id: str,
    request: MeetingChatRequest,
    context: CurrentUserContext = Depends(get_current_context),
    chat_service: MeetingChatService = Depends(get_chat_service),
) -> MeetingChatResponse:
    return chat_service.ask(context, meeting_id, request)


@router.get("/{meeting_id}/chat", response_model=MeetingChatHistoryResponse)
def get_meeting_chat_history(
    meeting_id: str,
    context: CurrentUserContext = Depends(get_current_context),
    chat_service: MeetingChatService = Depends(get_chat_service),
) -> MeetingChatHistoryResponse:
    return chat_service.get_history(context, meeting_id)

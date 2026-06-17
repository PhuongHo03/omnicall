from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Response, UploadFile, status
from sqlalchemy.orm import Session

from backend.configs.database import get_db_session
from backend.dependencies.auth import CurrentUserContext, get_current_context
from backend.dtos.file_dto import AccountFileListResponse, AccountFileResponse, DeleteResponse
from backend.providers.storage_provider import ObjectStorageProvider, get_object_storage_provider
from backend.services.file_service import AccountFileService

router = APIRouter(prefix="/files", tags=["files"])


def get_account_file_service(
    session: Session = Depends(get_db_session),
    storage_provider: ObjectStorageProvider = Depends(get_object_storage_provider),
) -> AccountFileService:
    return AccountFileService(session, storage_provider)


@router.get("", response_model=AccountFileListResponse)
def list_files(
    context: CurrentUserContext = Depends(get_current_context),
    service: AccountFileService = Depends(get_account_file_service),
) -> AccountFileListResponse:
    return service.list_files(context)


@router.post("", response_model=AccountFileResponse, status_code=status.HTTP_201_CREATED)
def upload_file(
    file: UploadFile = File(...),
    context: CurrentUserContext = Depends(get_current_context),
    service: AccountFileService = Depends(get_account_file_service),
) -> AccountFileResponse:
    return service.upload_file(context, file)


@router.get("/{file_id}/content")
def get_file_content(
    file_id: str,
    context: CurrentUserContext = Depends(get_current_context),
    service: AccountFileService = Depends(get_account_file_service),
) -> Response:
    file_content = service.get_content(context, file_id)
    encoded_name = quote(file_content.file_name)
    return Response(
        content=file_content.data,
        media_type=file_content.content_type,
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{encoded_name}"},
    )


@router.delete("/{file_id}", response_model=DeleteResponse)
def delete_file(
    file_id: str,
    context: CurrentUserContext = Depends(get_current_context),
    service: AccountFileService = Depends(get_account_file_service),
) -> DeleteResponse:
    return service.delete_file(context, file_id)

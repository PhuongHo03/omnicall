from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from backend.configs.database import get_db_session
from backend.dependencies.auth import CurrentUserContext, get_current_context, optional_bearer_token
from backend.dtos.auth_dto import AuthLoginRequest, AuthRegisterRequest, AuthSessionResponse, MeResponse
from backend.services.auth_service import AuthService

router = APIRouter(tags=["auth"])


def get_auth_service(session: Session = Depends(get_db_session)) -> AuthService:
    return AuthService(session)


@router.post("/auth/register", response_model=AuthSessionResponse, status_code=status.HTTP_201_CREATED)
def register(
    request: AuthRegisterRequest,
    service: AuthService = Depends(get_auth_service),
) -> AuthSessionResponse:
    return service.register(request)


@router.post("/auth/login", response_model=AuthSessionResponse)
def login(
    request: AuthLoginRequest,
    service: AuthService = Depends(get_auth_service),
) -> AuthSessionResponse:
    return service.login(request)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    token: str | None = Depends(optional_bearer_token),
    context: CurrentUserContext = Depends(get_current_context),
    service: AuthService = Depends(get_auth_service),
) -> None:
    service.logout(token, context)


@router.get("/me", response_model=MeResponse)
def me(
    context: CurrentUserContext = Depends(get_current_context),
    service: AuthService = Depends(get_auth_service),
) -> MeResponse:
    return service.me(context)

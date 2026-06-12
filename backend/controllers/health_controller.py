from fastapi import APIRouter, Depends

from backend.configs.settings import Settings, get_settings
from backend.dtos.health_dto import HealthResponse
from backend.services.health_service import HealthService, get_health_service

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def read_health(
    settings: Settings = Depends(get_settings),
    health_service: HealthService = Depends(get_health_service),
) -> HealthResponse:
    return health_service.get_status(app_name=settings.app_name)

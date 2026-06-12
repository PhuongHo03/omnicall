from backend.dtos.health_dto import HealthResponse


class HealthService:
    def get_status(self, app_name: str) -> HealthResponse:
        return HealthResponse(app=app_name, status="ok")


def get_health_service() -> HealthService:
    return HealthService()

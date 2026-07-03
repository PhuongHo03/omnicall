from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.configs.settings import get_settings
from backend.controllers.admin_controller import router as admin_router
from backend.controllers.auth_controller import router as auth_router
from backend.controllers.health_controller import router as health_router
from backend.controllers.meeting_controller import router as meeting_router
from backend.controllers.metrics_controller import router as metrics_router
from backend.dtos.error_dto import ErrorResponse
from backend.providers.app_metrics_provider import MetricsMiddleware
from backend.middlewares.request_id_middleware import RequestIdMiddleware
from backend.utils.exceptions import ApplicationError


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name)

    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(MetricsMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(ApplicationError)
    async def application_error_handler(_, exc: ApplicationError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(code=exc.code, message=exc.message).model_dump(),
        )

    app.include_router(health_router, prefix=settings.api_prefix)
    app.include_router(auth_router, prefix=settings.api_prefix)
    app.include_router(admin_router, prefix=settings.api_prefix)
    app.include_router(meeting_router, prefix=settings.api_prefix)
    app.include_router(metrics_router)
    return app


app = create_app()

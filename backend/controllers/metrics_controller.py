from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from starlette.responses import Response

from backend.configs.database import get_db_session
from backend.providers.app_metrics_provider import render_metrics

router = APIRouter(tags=["metrics"])


@router.get("/metrics", include_in_schema=False)
def read_metrics(session: Session = Depends(get_db_session)) -> Response:
    return render_metrics(session)

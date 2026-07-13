from dataclasses import dataclass
import time
from typing import Callable

from backend.providers.analysis import SCHEMA_VERSION
from backend.services.processing.observability import asset_log_context, elapsed_ms


@dataclass(frozen=True)
class PersistenceStageResult:
    result: object
    duration_ms: int


class PersistenceStage:
    def __init__(self, results_repository, emit: Callable[..., None]) -> None:
        self.results = results_repository
        self.emit = emit

    def run(self, *, meeting, asset, result_json: dict, provider_name: str, provider_model: str) -> PersistenceStageResult:
        started = time.perf_counter()
        result = self.results.upsert(
            meeting_id=meeting.id,
            schema_version=SCHEMA_VERSION,
            provider_name=provider_name,
            provider_model=provider_model,
            result_json=result_json,
        )
        duration_ms = elapsed_ms(started)
        self.emit(
            level="info",
            flow="processing",
            stage="result_persistence",
            status="succeeded",
            message="Processed meeting intelligence JSON persisted.",
            workspace_id=meeting.owner_user_id,
            meeting_id=meeting.id,
            meeting_name=meeting.title,
            file=asset_log_context(asset),
            duration_ms=duration_ms,
            details={
                "resultId": result.id,
                "segmentCount": len(result_json["transcript"]["segments"]),
            },
        )
        return PersistenceStageResult(result=result, duration_ms=duration_ms)

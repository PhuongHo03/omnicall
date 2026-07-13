import time


def elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def asset_log_context(asset) -> dict:
    if asset is None:
        return {}
    return {
        "id": asset.id,
        "name": asset.file_name,
        "contentType": asset.content_type,
        "sizeBytes": asset.size_bytes,
        "objectKey": asset.object_key,
    }


def job_log_context(meeting) -> dict:
    return {
        "id": meeting.id,
        "attempt": meeting.attempts,
        "queue": "meeting-processing",
        "taskName": "omnicall.processing.process_meeting",
        "status": str(meeting.status),
    }

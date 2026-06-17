import json
import time
import unittest
from io import BytesIO
from uuid import uuid4
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from sqlalchemy import delete, select
from starlette.datastructures import Headers, UploadFile

from backend.configs.database import SessionLocal
from backend.configs.settings import get_settings
from backend.dependencies.auth import CurrentUserContext
from backend.models.core_models import User, Workspace
from backend.models.enums import MeetingStatus, ProcessingJobStatus
from backend.models.meeting_models import Meeting, MeetingAsset, ProcessingJob
from backend.repositories.auth_repository import AuthRepository
from backend.services.meeting_service import MeetingService
from backend.utils.exceptions import ApplicationError


API_BASE_URL = "http://127.0.0.1:8000/api"


class FakeStorageProvider:
    def __init__(self) -> None:
        self.objects: list[tuple[str, int, str]] = []
        self.bytes_by_key: dict[str, bytes] = {}

    def put_object(self, *, object_key, data, size_bytes, content_type) -> None:
        self.objects.append((object_key, size_bytes, content_type))
        self.bytes_by_key[object_key] = data.read()

    def get_object_bytes(self, *, object_key) -> bytes:
        return self.bytes_by_key[object_key]


class FakeQueueProvider:
    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.calls: list[tuple[str, str]] = []

    def enqueue_meeting_processing(self, *, job_id: str, meeting_id: str) -> None:
        self.calls.append((job_id, meeting_id))
        if self.should_fail:
            raise RuntimeError("queue unavailable")


def request_json(method: str, path: str, headers: dict[str, str] | None = None, payload: dict | None = None) -> tuple[int, dict]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(
        f"{API_BASE_URL}{path}",
        data=body,
        headers={"Content-Type": "application/json", **(headers or {})},
        method=method,
    )
    try:
        with urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode("utf-8"))
        finally:
            exc.close()


def request_multipart_upload(
    path: str,
    headers: dict[str, str],
    *,
    field_name: str,
    file_name: str,
    content_type: str,
    content: bytes,
) -> tuple[int, dict]:
    boundary = f"omnicall-boundary-{uuid4()}"
    body = b"".join(
        [
            f"--{boundary}\r\n".encode(),
            (
                f'Content-Disposition: form-data; name="{field_name}"; '
                f'filename="{file_name}"\r\n'
            ).encode(),
            f"Content-Type: {content_type}\r\n\r\n".encode(),
            content,
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )
    request = Request(
        f"{API_BASE_URL}{path}",
        data=body,
        headers={
            **headers,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode("utf-8"))
        finally:
            exc.close()


class MeetingApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.user_id = str(uuid4())
        self.workspace_id = str(uuid4())
        self.headers = {
            "X-User-ID": self.user_id,
            "X-Workspace-ID": self.workspace_id,
            "X-User-Email": f"{self.user_id}@test.omnicall",
            "X-User-Name": "Test User",
            "X-Workspace-Name": "Test Workspace",
        }

    def tearDown(self) -> None:
        with SessionLocal() as session:
            session.execute(delete(Workspace).where(Workspace.id == self.workspace_id))
            session.execute(delete(User).where(User.id == self.user_id))
            session.commit()

    def create_meeting(self) -> dict:
        status, payload = request_json(
            "POST",
            "/meetings",
            headers=self.headers,
            payload={"title": "Automated test meeting", "language": "vi"},
        )
        self.assertEqual(status, 201, payload)
        self.assertEqual(payload["status"], MeetingStatus.DRAFT)
        return payload

    def upload_wav(self, meeting_id: str, idempotency_key: str = "upload-test") -> dict:
        status, payload = request_multipart_upload(
            f"/meetings/{meeting_id}/assets",
            headers={**self.headers, "Idempotency-Key": idempotency_key},
            field_name="file",
            file_name="meeting.wav",
            content_type="audio/wav",
            content=b"RIFF....WAVEfmt ",
        )
        self.assertEqual(status, 201, payload)
        return payload

    def upload_text_transcript(self, meeting_id: str, idempotency_key: str = "upload-text-test") -> dict:
        status, payload = request_multipart_upload(
            f"/meetings/{meeting_id}/assets",
            headers={**self.headers, "Idempotency-Key": idempotency_key},
            field_name="file",
            file_name="meeting.txt",
            content_type="text/plain",
            content=(
                b"00:00 Alice: The processed JSON should drive chatbot retrieval.\n"
                b"00:30 Bob: Action item is to index transcript-derived sections.\n"
            ),
        )
        self.assertEqual(status, 201, payload)
        return payload

    def wait_for_processed_status(self, meeting_id: str) -> dict:
        latest_payload: dict = {}
        for _ in range(120):
            status, latest_payload = request_json(
                "GET",
                f"/meetings/{meeting_id}/processing-status",
                headers=self.headers,
            )
            self.assertEqual(status, 200, latest_payload)
            if latest_payload["meeting"]["status"] in {MeetingStatus.READY, MeetingStatus.FAILED}:
                return latest_payload
            time.sleep(0.5)
        return latest_payload

    def test_requires_auth_headers(self) -> None:
        status, payload = request_json("GET", "/meetings")

        self.assertEqual(status, 401)
        self.assertEqual(payload["code"], "missing_auth_context")

    def test_meeting_upload_process_flow_persists_records_and_fails_safely_without_local_models(self) -> None:
        meeting = self.create_meeting()

        first_upload = self.upload_wav(meeting["id"], "upload-idempotent")
        second_upload = self.upload_wav(meeting["id"], "upload-idempotent")

        self.assertEqual(first_upload["id"], second_upload["id"])
        self.assertTrue(
            first_upload["object_key"].startswith(
                f"workspaces/{self.workspace_id}/meetings/{meeting['id']}/uploads/"
            )
        )

        first_status, first_process = request_json(
            "POST",
            f"/meetings/{meeting['id']}/process",
            headers={**self.headers, "Idempotency-Key": "process-idempotent"},
        )
        second_status, second_process = request_json(
            "POST",
            f"/meetings/{meeting['id']}/process",
            headers={**self.headers, "Idempotency-Key": "process-idempotent"},
        )

        self.assertEqual(first_status, 202, first_process)
        self.assertEqual(second_status, 202, second_process)
        self.assertEqual(first_process["id"], second_process["id"])
        self.assertEqual(first_process["status"], ProcessingJobStatus.PENDING)

        processing_status = self.wait_for_processed_status(meeting["id"])
        self.assertEqual(processing_status["meeting"]["status"], MeetingStatus.FAILED)
        self.assertEqual(processing_status["latest_job"]["status"], ProcessingJobStatus.FAILED)
        self.assertTrue(processing_status["latest_job"]["retry_allowed"])

        with SessionLocal() as session:
            self.assertIsNotNone(session.scalar(select(Meeting).where(Meeting.id == meeting["id"])))
            self.assertIsNotNone(session.scalar(select(MeetingAsset).where(MeetingAsset.meeting_id == meeting["id"])))
            self.assertIsNotNone(session.scalar(select(ProcessingJob).where(ProcessingJob.meeting_id == meeting["id"])))

    def test_upload_validation_rejects_unsupported_files(self) -> None:
        meeting = self.create_meeting()

        status, payload = request_multipart_upload(
            f"/meetings/{meeting['id']}/assets",
            headers={**self.headers, "Idempotency-Key": "upload-invalid-extension"},
            field_name="file",
            file_name="notes.pdf",
            content_type="application/pdf",
            content=b"%PDF",
        )

        self.assertEqual(status, 400)
        self.assertEqual(payload["code"], "unsupported_file_extension")

    def test_text_transcript_upload_is_accepted_for_processing(self) -> None:
        meeting = self.create_meeting()
        self.upload_text_transcript(meeting["id"], "upload-text-transcript")

        status, process = request_json(
            "POST",
            f"/meetings/{meeting['id']}/process",
            headers={**self.headers, "Idempotency-Key": "process-text-transcript"},
        )
        self.assertEqual(status, 202, process)

        processing_status = self.wait_for_processed_status(meeting["id"])
        self.assertIn(processing_status["meeting"]["status"], {MeetingStatus.READY, MeetingStatus.FAILED})
        self.assertIn(
            processing_status["latest_job"]["status"],
            {ProcessingJobStatus.SUCCEEDED, ProcessingJobStatus.FAILED},
        )
        if processing_status["latest_job"]["status"] == ProcessingJobStatus.FAILED:
            self.assertTrue(processing_status["latest_job"]["retry_allowed"])

    def test_workspace_scope_prevents_cross_workspace_access(self) -> None:
        meeting = self.create_meeting()
        other_headers = {
            **self.headers,
            "X-Workspace-ID": str(uuid4()),
            "X-Workspace-Name": "Other Workspace",
        }

        status, payload = request_json("GET", f"/meetings/{meeting['id']}", headers=other_headers)

        self.assertEqual(status, 404)
        self.assertEqual(payload["code"], "meeting_not_found")


class MeetingServiceRetryTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.user_id = str(uuid4())
        self.workspace_id = str(uuid4())
        self.context = CurrentUserContext(
            user_id=self.user_id,
            workspace_id=self.workspace_id,
            role="owner",
        )

    def tearDown(self) -> None:
        with SessionLocal() as session:
            session.execute(delete(Workspace).where(Workspace.id == self.workspace_id))
            session.execute(delete(User).where(User.id == self.user_id))
            session.commit()

    def test_queue_failure_is_visible_and_retry_can_create_new_job(self) -> None:
        with SessionLocal() as session:
            AuthRepository(session).upsert_dev_context(
                user_id=self.user_id,
                workspace_id=self.workspace_id,
                email=f"{self.user_id}@test.omnicall",
                display_name="Test User",
                workspace_name="Test Workspace",
            )
            session.commit()

            failing_queue = FakeQueueProvider(should_fail=True)
            storage = FakeStorageProvider()
            service = MeetingService(session, storage, failing_queue, get_settings())
            meeting = service.create_meeting(
                self.context,
                request=type("MeetingRequest", (), {"title": "Retry test", "language": "vi"})(),
            )
            upload = UploadFile(
                file=BytesIO(b"RIFF....WAVEfmt "),
                filename="meeting.wav",
                headers=Headers({"content-type": "audio/wav"}),
            )
            service.upload_asset(self.context, meeting.id, upload, "upload-before-failure")

            failed_job = service.queue_processing(self.context, meeting.id, "process-fails")
            self.assertEqual(failed_job.status, ProcessingJobStatus.FAILED)
            self.assertTrue(failed_job.retry_allowed)
            self.assertEqual(
                failed_job.safe_failure_reason,
                "Processing queue is unavailable. Please retry later.",
            )

            recovering_queue = FakeQueueProvider()
            service = MeetingService(session, storage, recovering_queue, get_settings())
            retry_job = service.queue_processing(self.context, meeting.id, "process-recovers")
            self.assertEqual(retry_job.status, ProcessingJobStatus.PENDING)
            self.assertNotEqual(retry_job.id, failed_job.id)
            self.assertEqual(len(recovering_queue.calls), 1)

    def test_meeting_accepts_only_one_uploaded_asset(self) -> None:
        with SessionLocal() as session:
            AuthRepository(session).upsert_dev_context(
                user_id=self.user_id,
                workspace_id=self.workspace_id,
                email=f"{self.user_id}@test.omnicall",
                display_name="Test User",
                workspace_name="Test Workspace",
            )
            session.commit()

            storage = FakeStorageProvider()
            service = MeetingService(session, storage, FakeQueueProvider(), get_settings())
            meeting = service.create_meeting(
                self.context,
                request=type("MeetingRequest", (), {"title": "Single upload", "language": "vi"})(),
            )
            first_upload = UploadFile(
                file=BytesIO(b"RIFF....WAVEfmt "),
                filename="meeting.wav",
                headers=Headers({"content-type": "audio/wav"}),
            )
            first_asset = service.upload_asset(self.context, meeting.id, first_upload, "upload-once")

            idempotent_upload = UploadFile(
                file=BytesIO(b"RIFF....WAVEfmt "),
                filename="same-meeting.wav",
                headers=Headers({"content-type": "audio/wav"}),
            )
            idempotent_asset = service.upload_asset(self.context, meeting.id, idempotent_upload, "upload-once")
            self.assertEqual(first_asset.id, idempotent_asset.id)

            second_upload = UploadFile(
                file=BytesIO(b"RIFF....WAVEfmt "),
                filename="replacement.wav",
                headers=Headers({"content-type": "audio/wav"}),
            )
            with self.assertRaises(ApplicationError) as error:
                service.upload_asset(self.context, meeting.id, second_upload, "upload-replacement")
            self.assertEqual(error.exception.code, "meeting_already_has_asset")

            status = service.get_processing_status(self.context, meeting.id)
            self.assertIsNotNone(status.latest_asset)
            self.assertEqual(status.latest_asset.id, first_asset.id)

    def test_asset_content_is_loaded_through_authorized_meeting(self) -> None:
        with SessionLocal() as session:
            AuthRepository(session).upsert_dev_context(
                user_id=self.user_id,
                workspace_id=self.workspace_id,
                email=f"{self.user_id}@test.omnicall",
                display_name="Test User",
                workspace_name="Test Workspace",
            )
            session.commit()

            storage = FakeStorageProvider()
            service = MeetingService(session, storage, FakeQueueProvider(), get_settings())
            meeting = service.create_meeting(
                self.context,
                request=type("MeetingRequest", (), {"title": "Playback source", "language": "vi"})(),
            )
            upload = UploadFile(
                file=BytesIO(b"RIFF....WAVEfmt playback"),
                filename="meeting.wav",
                headers=Headers({"content-type": "audio/wav"}),
            )
            asset = service.upload_asset(self.context, meeting.id, upload, "upload-playback")

            content = service.get_asset_content(self.context, meeting.id, asset.id)
            self.assertEqual(content.data, b"RIFF....WAVEfmt playback")
            self.assertEqual(content.file_name, "meeting.wav")
            self.assertEqual(content.content_type, "audio/wav")

            other_context = CurrentUserContext(
                user_id=self.user_id,
                workspace_id=str(uuid4()),
                role="owner",
            )
            with self.assertRaises(ApplicationError) as error:
                service.get_asset_content(other_context, meeting.id, asset.id)
            self.assertEqual(error.exception.code, "meeting_not_found")


if __name__ == "__main__":
    unittest.main()

import unittest
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete

from backend.configs.database import SessionLocal
from backend.main import app
from backend.models.core_models import User
from backend.models.enums import MeetingStatus
from backend.models.meeting_models import MeetingAsset
from backend.providers.cache_provider import get_json_cache_provider
from backend.providers.lock_provider import get_redis_lock_provider
from backend.providers.queue_provider import get_processing_queue_provider
from backend.providers.storage_provider import get_object_storage_provider
from backend.providers.vector_provider import get_vector_provider


class FakeStorageProvider:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.removed: list[str] = []

    def put_object(self, *, object_key, data, size_bytes, content_type) -> None:
        self.objects[object_key] = data.read()

    def get_object_bytes(self, *, object_key) -> bytes:
        return self.objects[object_key]

    def remove_object(self, *, object_key) -> None:
        self.removed.append(object_key)
        self.objects.pop(object_key, None)


class FakeLockProvider:
    def acquire(self, key: str, ttl_seconds: int | None = None) -> str:
        return f"lock:{key}"

    def release(self, key: str, token: str) -> None:
        return None


class FakeQueueProvider:
    def revoke_meeting_processing(self, *, job_ids: list[str]) -> dict:
        return {"requested": len(job_ids), "revoked": len(job_ids), "status": "requested"}


class FakeCacheProvider:
    def delete_key(self, key: str) -> None:
        return None


class FakeVectorProvider:
    def delete_meeting(self, *, workspace_id: str, meeting_id: str) -> dict:
        return {"deleted": True}


class MeetingApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.storage = FakeStorageProvider()
        app.dependency_overrides[get_object_storage_provider] = lambda: self.storage
        app.dependency_overrides[get_redis_lock_provider] = lambda: FakeLockProvider()
        app.dependency_overrides[get_processing_queue_provider] = lambda: FakeQueueProvider()
        app.dependency_overrides[get_json_cache_provider] = lambda: FakeCacheProvider()
        app.dependency_overrides[get_vector_provider] = lambda: FakeVectorProvider()
        self.client = TestClient(app)
        self.email = f"meeting-{uuid4().hex[:8]}@test.omnicall"
        response = self.client.post(
            "/api/auth/register",
            json={"email": self.email, "display_name": "Meeting API User", "password": "pw"},
        )
        self.assertEqual(response.status_code, 201, response.text)
        payload = response.json()
        self.user_id = payload["account"]["user_id"]
        self.headers = {"Authorization": f"Bearer {payload['token']}"}

    def tearDown(self) -> None:
        with SessionLocal() as session:
            session.execute(delete(User).where(User.id == self.user_id))
            session.commit()
        app.dependency_overrides.clear()

    def test_meeting_create_list_get_and_upload_use_owner_scope(self) -> None:
        create_response = self.client.post(
            "/api/meetings",
            headers=self.headers,
            json={},
        )
        self.assertEqual(create_response.status_code, 201, create_response.text)
        meeting = create_response.json()
        self.assertEqual(meeting["status"], MeetingStatus.DRAFT)
        self.assertEqual(meeting["title"], meeting["id"])
        self.assertNotIn("language", meeting)
        self.assertNotIn("workspace_id", meeting)

        rename_response = self.client.patch(
            f"/api/meetings/{meeting['id']}",
            headers=self.headers,
            json={"title": "API schema meeting"},
        )
        self.assertEqual(rename_response.status_code, 200, rename_response.text)
        self.assertEqual(rename_response.json()["title"], "API schema meeting")

        list_response = self.client.get("/api/meetings", headers=self.headers)
        self.assertEqual(list_response.status_code, 200, list_response.text)
        self.assertEqual([item["id"] for item in list_response.json()["items"]], [meeting["id"]])

        get_response = self.client.get(f"/api/meetings/{meeting['id']}", headers=self.headers)
        self.assertEqual(get_response.status_code, 200, get_response.text)
        self.assertEqual(get_response.json()["id"], meeting["id"])
        self.assertEqual(get_response.json()["title"], "API schema meeting")

        upload_response = self.client.post(
            f"/api/meetings/{meeting['id']}/assets",
            headers={**self.headers, "Idempotency-Key": "api-upload"},
            files={"file": ("meeting.txt", b"00:00 Alice: Store one JSON result.\n", "text/plain")},
        )
        self.assertEqual(upload_response.status_code, 201, upload_response.text)
        asset = upload_response.json()
        self.assertEqual(asset["meeting_id"], meeting["id"])
        self.assertTrue(asset["object_key"].startswith(f"users/{self.user_id}/meetings/{meeting['id']}/uploads/"))

        with SessionLocal() as session:
            stored_asset = session.get(MeetingAsset, asset["id"])
            self.assertIsNotNone(stored_asset)
            self.assertEqual(stored_asset.owner_user_id, self.user_id)
            self.assertEqual(stored_asset.meeting_id, meeting["id"])

    def test_other_user_cannot_read_meeting(self) -> None:
        create_response = self.client.post(
            "/api/meetings",
            headers=self.headers,
            json={"title": "Private meeting"},
        )
        meeting_id = create_response.json()["id"]

        other = self.client.post(
            "/api/auth/register",
            json={"email": f"other-{uuid4().hex[:8]}@test.omnicall", "display_name": "Other User", "password": "pw"},
        )
        self.assertEqual(other.status_code, 201, other.text)
        other_payload = other.json()
        try:
            response = self.client.get(
                f"/api/meetings/{meeting_id}",
                headers={"Authorization": f"Bearer {other_payload['token']}"},
            )
            self.assertEqual(response.status_code, 404)
        finally:
            with SessionLocal() as session:
                session.execute(delete(User).where(User.id == other_payload["account"]["user_id"]))
                session.commit()

    def test_user_can_delete_owned_meeting(self) -> None:
        create_response = self.client.post(
            "/api/meetings",
            headers=self.headers,
            json={"title": "Owned deletion"},
        )
        self.assertEqual(create_response.status_code, 201, create_response.text)
        meeting_id = create_response.json()["id"]

        upload_response = self.client.post(
            f"/api/meetings/{meeting_id}/assets",
            headers={**self.headers, "Idempotency-Key": "delete-upload"},
            files={"file": ("meeting.txt", b"00:00 Alice: Delete this meeting.\n", "text/plain")},
        )
        self.assertEqual(upload_response.status_code, 201, upload_response.text)
        object_key = upload_response.json()["object_key"]

        delete_response = self.client.delete(f"/api/meetings/{meeting_id}", headers=self.headers)
        self.assertEqual(delete_response.status_code, 200, delete_response.text)
        self.assertEqual(delete_response.json(), {"id": meeting_id, "deleted": True})
        self.assertIn(object_key, self.storage.removed)

        get_response = self.client.get(f"/api/meetings/{meeting_id}", headers=self.headers)
        self.assertEqual(get_response.status_code, 404)

    def test_other_user_cannot_delete_meeting(self) -> None:
        create_response = self.client.post(
            "/api/meetings",
            headers=self.headers,
            json={"title": "Private deletion"},
        )
        self.assertEqual(create_response.status_code, 201, create_response.text)
        meeting_id = create_response.json()["id"]

        other = self.client.post(
            "/api/auth/register",
            json={"email": f"other-delete-{uuid4().hex[:8]}@test.omnicall", "display_name": "Other User", "password": "pw"},
        )
        self.assertEqual(other.status_code, 201, other.text)
        other_payload = other.json()
        try:
            response = self.client.delete(
                f"/api/meetings/{meeting_id}",
                headers={"Authorization": f"Bearer {other_payload['token']}"},
            )
            self.assertEqual(response.status_code, 404)

            owner_response = self.client.get(f"/api/meetings/{meeting_id}", headers=self.headers)
            self.assertEqual(owner_response.status_code, 200, owner_response.text)
        finally:
            with SessionLocal() as session:
                session.execute(delete(User).where(User.id == other_payload["account"]["user_id"]))
                session.commit()


if __name__ == "__main__":
    unittest.main()

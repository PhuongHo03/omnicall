import unittest
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete

from backend.configs.database import SessionLocal
from backend.main import app
from backend.models.core_models import User
from backend.models.enums import MeetingStatus
from backend.models.meeting_models import MeetingAsset


class MeetingApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
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

    def test_meeting_create_list_get_and_upload_use_owner_scope(self) -> None:
        create_response = self.client.post(
            "/api/meetings",
            headers=self.headers,
            json={"title": "API schema meeting", "language": "vi"},
        )
        self.assertEqual(create_response.status_code, 201, create_response.text)
        meeting = create_response.json()
        self.assertEqual(meeting["status"], MeetingStatus.DRAFT)
        self.assertNotIn("workspace_id", meeting)

        list_response = self.client.get("/api/meetings", headers=self.headers)
        self.assertEqual(list_response.status_code, 200, list_response.text)
        self.assertEqual([item["id"] for item in list_response.json()["items"]], [meeting["id"]])

        get_response = self.client.get(f"/api/meetings/{meeting['id']}", headers=self.headers)
        self.assertEqual(get_response.status_code, 200, get_response.text)
        self.assertEqual(get_response.json()["id"], meeting["id"])

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
            json={"title": "Private meeting", "language": "vi"},
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


if __name__ == "__main__":
    unittest.main()

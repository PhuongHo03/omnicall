import unittest
from uuid import uuid4

from sqlalchemy import delete, select

from backend.configs.database import SessionLocal
from backend.dependencies.auth import CurrentUserContext
from backend.dtos.auth_dto import AuthRegisterRequest
from backend.models.core_models import AccountSession, User
from backend.models.enums import MeetingStatus
from backend.models.meeting_models import Meeting, MeetingAsset
from backend.repositories.auth_repository import AuthRepository
from backend.repositories.meeting_repository import MeetingAssetRepository, MeetingRepository
from backend.services.auth_service import AuthService
from backend.services.admin_account_service import AdminAccountService


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
    def acquire(self, lock_key: str) -> str:
        return f"token:{lock_key}"

    def release(self, lock_key: str, token: str) -> None:
        return None


class FakeQueueProvider:
    def revoke_meeting_processing(self, *, meeting_ids: list[str]) -> dict:
        return {"revoked": meeting_ids}


class FakeCacheProvider:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    def delete_key(self, key: str) -> None:
        self.deleted.append(key)


class Phase7AuthFilesTestCase(unittest.TestCase):
    def tearDown(self) -> None:
        with SessionLocal() as session:
            session.execute(delete(User).where(User.email.like("%@phase7.test")))
            session.commit()

    def test_register_creates_user_role_and_account_session(self) -> None:
        email = f"user-{uuid4().hex[:8]}@phase7.test"
        with SessionLocal() as session:
            response = AuthService(session).register(
                AuthRegisterRequest(email=email, display_name="Phase 7 User", password="pw")
            )

            user = AuthRepository(session).get_user(response.account.user_id)
            sessions = list(
                session.scalars(select(AccountSession).where(AccountSession.user_id == response.account.user_id)).all()
            )

        self.assertIsNotNone(user)
        self.assertEqual(response.account.role, "User")
        self.assertEqual(user.role, "User")
        self.assertEqual(len(sessions), 1)

    def test_admin_account_delete_removes_owned_meetings_assets_and_user(self) -> None:
        admin_id = str(uuid4())
        user_id = str(uuid4())
        storage = FakeStorageProvider()
        lock = FakeLockProvider()
        queue = FakeQueueProvider()
        cache = FakeCacheProvider()
        with SessionLocal() as session:
            auth = AuthRepository(session)
            auth.upsert_dev_user(
                user_id=admin_id,
                email=f"{admin_id}@phase7.test",
                display_name="Admin",
                role="Admin",
            )
            auth.upsert_dev_user(
                user_id=user_id,
                email=f"{user_id}@phase7.test",
                display_name="Deleted User",
                role="User",
            )
            meeting = MeetingRepository(session).create(user_id=user_id, title="To delete")
            meeting.status = MeetingStatus.READY
            asset = MeetingAssetRepository(session).create(
                meeting_id=meeting.id,
                user_id=user_id,
                object_key=f"users/{user_id}/meetings/{meeting.id}/uploads/audio.mp3",
                file_name="audio.mp3",
                content_type="audio/mpeg",
                size_bytes=100,
                idempotency_key="upload",
            )
            standalone = MeetingAsset(
                owner_user_id=user_id,
                meeting_id=None,
                object_key=f"users/{user_id}/files/note.txt",
                file_name="note.txt",
                content_type="text/plain",
                size_bytes=10,
            )
            session.add(standalone)
            storage.objects[asset.object_key] = b"audio"
            storage.objects[standalone.object_key] = b"note"
            session.commit()

            response = AdminAccountService(
                session,
                storage,
                lock_provider=lock,
                queue_provider=queue,
                cache_provider=cache,
            ).delete_account(CurrentUserContext(user_id=admin_id, role="Admin"), user_id)

            remaining_user = session.get(User, user_id)
            remaining_meetings = list(session.scalars(select(Meeting).where(Meeting.owner_user_id == user_id)).all())
            remaining_assets = list(session.scalars(select(MeetingAsset).where(MeetingAsset.owner_user_id == user_id)).all())

        self.assertTrue(response.deleted)
        self.assertIsNone(remaining_user)
        self.assertEqual(remaining_meetings, [])
        self.assertEqual(remaining_assets, [])
        self.assertIn(f"users/{user_id}/meetings/{meeting.id}/uploads/audio.mp3", storage.removed)
        self.assertIn(f"users/{user_id}/files/note.txt", storage.removed)


if __name__ == "__main__":
    unittest.main()

import unittest
from uuid import uuid4

from starlette.datastructures import Headers, UploadFile
from sqlalchemy import delete, select

from backend.configs.database import SessionLocal
from backend.dependencies.auth import CurrentUserContext
from backend.dtos.auth_dto import AuthRegisterRequest
from backend.models.core_models import AccountSession, User
from backend.models.enums import MeetingStatus, ProcessingJobStatus
from backend.models.meeting_models import Meeting, MeetingAsset, ProcessingJob
from backend.repositories.auth_repository import AuthRepository
from backend.repositories.meeting_repository import MeetingAssetRepository, MeetingRepository, ProcessingJobRepository
from backend.services.admin_account_service import AdminAccountService
from backend.services.file_service import AccountFileService
from backend.services.auth_service import AuthService
from backend.utils.exceptions import ApplicationError


class MemoryUpload:
    def __init__(self, data: bytes) -> None:
        self._data = data
        self._position = 0

    def tell(self) -> int:
        return self._position

    def seek(self, offset: int, whence: int = 0) -> int:
        if whence == 0:
            self._position = offset
        elif whence == 1:
            self._position += offset
        elif whence == 2:
            self._position = len(self._data) + offset
        return self._position

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self._data) - self._position
        chunk = self._data[self._position : self._position + size]
        self._position += len(chunk)
        return chunk


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
    def revoke_meeting_processing(self, *, job_ids: list[str]) -> dict:
        return {"revoked": job_ids}


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

    def test_file_library_uses_standalone_meeting_asset_rows(self) -> None:
        user_id = str(uuid4())
        storage = FakeStorageProvider()
        with SessionLocal() as session:
            AuthRepository(session).upsert_dev_user(
                user_id=user_id,
                email=f"{user_id}@phase7.test",
                display_name="File User",
                role="User",
            )
            context = CurrentUserContext(user_id=user_id, role="User")
            service = AccountFileService(session, storage)
            upload = UploadFile(
                filename="note.txt",
                file=MemoryUpload(b"00:00 Alice: hello"),
                headers=Headers({"content-type": "text/plain"}),
            )

            created = service.upload_file(context, upload)
            listed = service.list_files(context)
            deleted = service.delete_file(context, created.id)

        self.assertIsNone(created.meeting_id)
        self.assertFalse(created.linked_to_meeting)
        self.assertEqual(len(listed.items), 1)
        self.assertTrue(deleted.deleted)
        self.assertIn(f"users/{user_id}/files/", storage.removed[0])

    def test_linked_meeting_asset_cannot_be_deleted_from_file_library(self) -> None:
        user_id = str(uuid4())
        storage = FakeStorageProvider()
        with SessionLocal() as session:
            AuthRepository(session).upsert_dev_user(
                user_id=user_id,
                email=f"{user_id}@phase7.test",
                display_name="Linked File User",
                role="User",
            )
            meeting = MeetingRepository(session).create(user_id=user_id, title="Linked", language="vi")
            asset = MeetingAssetRepository(session).create(
                meeting_id=meeting.id,
                user_id=user_id,
                object_key=f"users/{user_id}/meetings/{meeting.id}/uploads/linked.txt",
                file_name="linked.txt",
                content_type="text/plain",
                size_bytes=10,
                idempotency_key="linked",
            )
            session.commit()

            with self.assertRaises(ApplicationError) as error:
                AccountFileService(session, storage).delete_file(CurrentUserContext(user_id=user_id, role="User"), asset.id)

        self.assertEqual(error.exception.code, "file_linked_to_meeting")

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
            meeting = MeetingRepository(session).create(user_id=user_id, title="To delete", language="vi")
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
            ProcessingJobRepository(session).create(
                meeting_id=meeting.id,
                idempotency_key="process",
                payload={"meetingId": meeting.id},
                status=ProcessingJobStatus.SUCCEEDED,
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

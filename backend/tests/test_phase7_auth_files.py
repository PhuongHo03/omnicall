import unittest
from io import BytesIO
from uuid import uuid4

from starlette.datastructures import Headers, UploadFile

from backend.configs.database import SessionLocal
from backend.configs.settings import get_settings
from backend.dependencies.auth import CurrentUserContext, require_admin_context
from backend.dtos.auth_dto import AuthRegisterRequest
from backend.dtos.file_dto import DeleteResponse
from backend.dtos.meeting_dto import MeetingCreateRequest
from sqlalchemy import delete

from backend.models.core_models import AccountSession, AuditEvent, User, Workspace, WorkspaceMember
from backend.models.meeting_models import AccountFile
from backend.repositories.auth_repository import AuthRepository
from backend.services.admin_meeting_service import AdminMeetingService
from backend.services.auth_service import AuthService
from backend.services.file_service import AccountFileService
from backend.services.meeting_service import MeetingService
from backend.utils.exceptions import ApplicationError


class FakeStorageProvider:
    def __init__(self) -> None:
        self.bytes_by_key: dict[str, bytes] = {}
        self.removed: list[str] = []

    def put_object(self, *, object_key, data, size_bytes, content_type) -> None:
        self.bytes_by_key[object_key] = data.read()

    def get_object_bytes(self, *, object_key) -> bytes:
        return self.bytes_by_key[object_key]

    def remove_object(self, *, object_key) -> None:
        self.removed.append(object_key)
        self.bytes_by_key.pop(object_key, None)


class FakeQueueProvider:
    def enqueue_meeting_processing(self, *, job_id: str, meeting_id: str) -> None:
        return None


class FakeVectorProvider:
    enabled = True
    provider_name = "fake-vector"

    def __init__(self) -> None:
        self.deleted: list[tuple[str, str]] = []

    def upsert_chunks(self, chunks):
        return {}

    def search_chunk_ids(self, *, workspace_id, meeting_id, query_vector, limit):
        return []

    def delete_meeting(self, *, workspace_id: str, meeting_id: str) -> dict:
        self.deleted.append((workspace_id, meeting_id))
        return {"status": "deleted"}


def upload_file(name: str, content_type: str, content: bytes) -> UploadFile:
    return UploadFile(filename=name, file=BytesIO(content), headers=Headers({"content-type": content_type}))


class Phase7AuthFilesTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.created_user_ids: list[str] = []
        self.created_workspace_ids: list[str] = []

    def tearDown(self) -> None:
        with SessionLocal() as session:
            for user_id in self.created_user_ids:
                session.execute(delete(AccountSession).where(AccountSession.user_id == user_id))
                session.execute(delete(AuditEvent).where(AuditEvent.user_id == user_id))
                session.execute(delete(AccountFile).where(AccountFile.owner_user_id == user_id))
                session.execute(delete(WorkspaceMember).where(WorkspaceMember.user_id == user_id))
            for workspace_id in self.created_workspace_ids:
                workspace = session.get(Workspace, workspace_id)
                if workspace is not None:
                    session.delete(workspace)
            for user_id in self.created_user_ids:
                user = session.get(User, user_id)
                if user is not None:
                    session.delete(user)
            session.commit()

    def register(self, role: str):
        with SessionLocal() as session:
            response = AuthService(session).register(
                AuthRegisterRequest(
                    email=f"{role.lower()}-{uuid4()}@omnicall.test",
                    password="change-me-123",
                    display_name=f"{role} Test",
                    role=role,
                )
            )
            self.created_user_ids.append(response.account.user_id)
            self.created_workspace_ids.append(response.account.workspace_id)
            return response

    def test_auth_roles_are_enforced(self) -> None:
        admin = self.register("Admin")
        user = self.register("User")

        admin_context = CurrentUserContext(
            user_id=admin.account.user_id,
            workspace_id=admin.account.workspace_id,
            role=admin.account.role,
        )
        user_context = CurrentUserContext(
            user_id=user.account.user_id,
            workspace_id=user.account.workspace_id,
            role=user.account.role,
        )

        self.assertEqual(require_admin_context(admin_context), admin_context)
        with self.assertRaises(ApplicationError) as raised:
            require_admin_context(user_context)
        self.assertEqual(raised.exception.status_code, 403)

    def test_file_delete_is_blocked_when_linked_and_session_delete_cleans_file(self) -> None:
        admin = self.register("Admin")
        context = CurrentUserContext(
            user_id=admin.account.user_id,
            workspace_id=admin.account.workspace_id,
            role=admin.account.role,
        )
        storage = FakeStorageProvider()
        vector = FakeVectorProvider()

        with SessionLocal() as session:
            service = MeetingService(session, storage, FakeQueueProvider(), settings=get_settings())
            meeting = service.create_meeting(context, MeetingCreateRequest(title="Phase 7", language="vi"))
            asset = service.upload_asset(
                context,
                meeting.id,
                upload_file("phase7.txt", "text/plain", b"phase 7 linked file"),
                "upload-phase7",
            )

            file_service = AccountFileService(session, storage)
            files = file_service.list_files(context).items
            linked = next(item for item in files if item.asset_id == asset.id)
            self.assertTrue(linked.linked_to_meeting)
            with self.assertRaises(ApplicationError) as raised:
                file_service.delete_file(context, linked.id)
            self.assertEqual(raised.exception.status_code, 409)

            delete_response = AdminMeetingService(session, storage, vector).delete_meeting(context, meeting.id)
            self.assertEqual(delete_response, DeleteResponse(id=meeting.id, deleted=True))
            self.assertIn((context.workspace_id, meeting.id), vector.deleted)
            self.assertFalse(file_service.list_files(context).items)
            self.assertFalse(storage.bytes_by_key)

    def test_unlinked_account_file_can_be_deleted_by_owner(self) -> None:
        user = self.register("User")
        context = CurrentUserContext(
            user_id=user.account.user_id,
            workspace_id=user.account.workspace_id,
            role=user.account.role,
        )
        storage = FakeStorageProvider()

        with SessionLocal() as session:
            service = AccountFileService(session, storage)
            account_file = service.upload_file(
                context,
                upload_file("library.txt", "text/plain", b"unlinked file"),
            )
            self.assertFalse(account_file.linked_to_meeting)
            self.assertTrue(storage.bytes_by_key)

            response = service.delete_file(context, account_file.id)
            self.assertTrue(response.deleted)
            self.assertFalse(storage.bytes_by_key)

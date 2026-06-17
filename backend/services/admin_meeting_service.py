from sqlalchemy import delete
from sqlalchemy.orm import Session

from backend.dependencies.auth import CurrentUserContext
from backend.dtos.file_dto import DeleteResponse
from backend.models.meeting_models import (
    ChatMessage,
    ChatSession,
    Meeting,
    MeetingAsset,
    MeetingChunkRecord,
    MeetingInsightRecord,
    MeetingIntelligenceResult,
    ProcessingJob,
    TranscriptSegmentRecord,
)
from backend.providers.storage_provider import ObjectStorageProvider
from backend.providers.vector_provider import VectorProvider, get_vector_provider
from backend.repositories.auth_repository import AuditEventRepository
from backend.repositories.file_repository import AccountFileRepository
from backend.repositories.meeting_repository import MeetingRepository
from backend.utils.exceptions import ApplicationError


class AdminMeetingService:
    def __init__(
        self,
        session: Session,
        storage_provider: ObjectStorageProvider,
        vector_provider: VectorProvider | None = None,
    ) -> None:
        self.session = session
        self.storage_provider = storage_provider
        self.vector_provider = vector_provider or get_vector_provider()
        self.meetings = MeetingRepository(session)
        self.account_files = AccountFileRepository(session)
        self.audit = AuditEventRepository(session)

    def delete_meeting(self, context: CurrentUserContext, meeting_id: str) -> DeleteResponse:
        meeting = self.meetings.get_for_workspace(meeting_id, context.workspace_id)
        if meeting is None:
            self.audit.create(
                event_type="meeting.delete",
                outcome="not_found",
                workspace_id=context.workspace_id,
                user_id=context.user_id,
                resource_type="meeting",
                resource_id=meeting_id,
            )
            self.session.commit()
            raise ApplicationError(404, "meeting_not_found", "Meeting was not found.")

        object_keys = [asset.object_key for asset in meeting.assets]
        for account_file in self.account_files.list_for_meeting(workspace_id=context.workspace_id, meeting_id=meeting.id):
            object_keys.append(account_file.object_key)
            self.account_files.delete(account_file)

        self._delete_vectors(context.workspace_id, meeting.id)
        self.session.execute(delete(ChatMessage).where(ChatMessage.meeting_id == meeting.id))
        self.session.execute(delete(ChatSession).where(ChatSession.meeting_id == meeting.id))
        self.session.execute(delete(MeetingChunkRecord).where(MeetingChunkRecord.meeting_id == meeting.id))
        self.session.execute(delete(MeetingInsightRecord).where(MeetingInsightRecord.meeting_id == meeting.id))
        self.session.execute(delete(TranscriptSegmentRecord).where(TranscriptSegmentRecord.meeting_id == meeting.id))
        self.session.execute(delete(MeetingIntelligenceResult).where(MeetingIntelligenceResult.meeting_id == meeting.id))
        self.session.execute(delete(ProcessingJob).where(ProcessingJob.meeting_id == meeting.id))
        self.session.execute(delete(MeetingAsset).where(MeetingAsset.meeting_id == meeting.id))
        self.session.delete(meeting)

        for object_key in sorted(set(object_keys)):
            self.storage_provider.remove_object(object_key=object_key)

        self.audit.create(
            event_type="meeting.delete",
            outcome="success",
            workspace_id=context.workspace_id,
            user_id=context.user_id,
            resource_type="meeting",
            resource_id=meeting.id,
            metadata={"objectCount": len(set(object_keys))},
        )
        self.session.commit()
        return DeleteResponse(id=meeting_id, deleted=True)

    def _delete_vectors(self, workspace_id: str, meeting_id: str) -> None:
        try:
            self.vector_provider.delete_meeting(workspace_id=workspace_id, meeting_id=meeting_id)
        except Exception:
            return

from sqlalchemy.orm import Session

from backend.dependencies.auth import CurrentUserContext
from backend.repositories.meeting_repository import MeetingIntelligenceResultRepository, MeetingRepository
from backend.utils.exceptions import ApplicationError


class IntelligenceService:
    def __init__(self, session: Session) -> None:
        self.meetings = MeetingRepository(session)
        self.results = MeetingIntelligenceResultRepository(session)

    def get_result(self, context: CurrentUserContext, meeting_id: str) -> dict:
        meeting = self.meetings.get_for_workspace(meeting_id, context.workspace_id)
        if meeting is None:
            raise ApplicationError(404, "meeting_not_found", "Meeting was not found.")

        result = self.results.get_latest_for_meeting(meeting_id)
        if result is None:
            raise ApplicationError(404, "meeting_intelligence_not_ready", "Meeting intelligence result is not ready.")

        return result.result_json

    def get_transcript(self, context: CurrentUserContext, meeting_id: str) -> dict:
        result = self.get_result(context, meeting_id)
        return {
            "meeting": result["meeting"],
            "transcript": result["transcript"],
            "citations": result["citations"],
            "quality": result["quality"],
        }

    def get_insights(self, context: CurrentUserContext, meeting_id: str) -> dict:
        result = self.get_result(context, meeting_id)
        return {
            "meeting": result["meeting"],
            "summary": result["summary"],
            "analysis": result["analysis"],
            "citations": result["citations"],
            "quality": result["quality"],
        }

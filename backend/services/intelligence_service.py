from sqlalchemy.orm import Session

from backend.dependencies.auth import CurrentUserContext
from backend.repositories.meeting_repository import MeetingIntelligenceResultRepository, MeetingRepository
from backend.utils.exceptions import ApplicationError


class IntelligenceService:
    def __init__(self, session: Session) -> None:
        self.meetings = MeetingRepository(session)
        self.results = MeetingIntelligenceResultRepository(session)

    def get_result(self, context: CurrentUserContext, meeting_id: str) -> dict:
        meeting = self.meetings.get_for_owner(meeting_id, context.user_id)
        if meeting is None:
            raise ApplicationError(404, "meeting_not_found", "Meeting was not found.")

        result = self.results.get_latest_for_meeting(meeting_id)
        if result is None:
            raise ApplicationError(404, "meeting_intelligence_not_ready", "Meeting intelligence result is not ready.")

        return result.result_json

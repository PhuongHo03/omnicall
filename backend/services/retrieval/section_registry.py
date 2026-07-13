"""Canonical retrieval section registry shared by builders and Agent tools."""

SECTION_TYPES = (
    "meeting.metadata", "source.processing", "speaker.stats", "fact.participant_count", "fact.record",
    "participant.overview", "participant.profile", "entity.profile", "action.item", "decision.record",
    "event.timeline", "relationship.edge", "risk.record", "question.record", "topic.summary",
    "summary.executive", "summary.topic", "summary.timeline", "quality.overview", "quality.warning",
    "extraction.overview", "extraction.warning", "evidence.map", "transcript.coverage", "transcript.window",
)

SECTION_TYPE_SET = frozenset(SECTION_TYPES)

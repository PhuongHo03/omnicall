"""Schema-first query planning for meeting-grounded Agentic RAG."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class QuerySubPlan:
    goal: str
    query: str
    sections: list[str]
    required_fields: list[str] = field(default_factory=list)
    limit: int = 5
    record_types: list[str] = field(default_factory=list)
    record_subtypes: list[str] = field(default_factory=list)
    relation_types: list[str] = field(default_factory=list)
    answer_shape: str = "record_list"


@dataclass(frozen=True)
class QueryPlan:
    intent: str
    sub_queries: list[QuerySubPlan]
    sections: list[str]
    required_fields: list[str]
    retrieval_mode: str = "hybrid"
    confidence: float = 0.75
    record_types: list[str] = field(default_factory=list)
    record_subtypes: list[str] = field(default_factory=list)
    relation_types: list[str] = field(default_factory=list)
    answer_shape: str = "record_list"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["subQueries"] = data.pop("sub_queries")
        data["requiredFields"] = data.pop("required_fields")
        data["recordTypes"] = data.pop("record_types")
        data["recordSubtypes"] = data.pop("record_subtypes")
        data["relationTypes"] = data.pop("relation_types")
        data["answerShape"] = data.pop("answer_shape")
        for item in data["subQueries"]:
            item["requiredFields"] = item.pop("required_fields")
            item["recordTypes"] = item.pop("record_types")
            item["recordSubtypes"] = item.pop("record_subtypes")
            item["relationTypes"] = item.pop("relation_types")
            item["answerShape"] = item.pop("answer_shape")
        return data


def build_query_plan(question: str) -> QueryPlan:
    """Build a deterministic, schema-shaped plan from the user's question.

    The planner intentionally describes retrieval requirements instead of
    producing an answer. LLM planning can be added behind this contract later
    without changing retrieval or verification consumers.
    """
    normalized = _normalize(question)
    subplans: list[QuerySubPlan] = []

    if _has_any(normalized, "action", "task", "todo", "follow up", "owner", "deadline", "due", "viec", "nguoi phu trach"):
        fields = ["task", "owner", "dueDate", "status"]
        subplans.append(QuerySubPlan("action ownership and deadline", question, ["action.item", "relationship.edge"], fields))
    if _has_any(normalized, "decision", "decisions", "quyet dinh", "outcome", "ket qua"):
        subplans.append(QuerySubPlan("meeting decisions", question, ["decision.record", "event.timeline"], ["text", "status"]))
    if _has_any(normalized, "risk", "risks", "blocker", "blockers", "rui ro", "tro ngai"):
        subplans.append(QuerySubPlan("risks and blockers", question, ["risk.record", "question.record"], ["text", "severity", "status"]))
    if _has_any(normalized, "participant", "participants", "speaker", "people", "attendee", "attendees", "joined", "join", "nguoi tham gia", "tham gia", "tham du", "ai la"):
        asks_count = _has_participant_count(normalized)
        asks_names = _has_any(normalized, "who", "ai", "name", "names", "display name")
        if asks_count and asks_names:
            required_fields = ["displayName", "value"]
        elif asks_count:
            required_fields = ["value"]
        else:
            required_fields = ["displayName"]
        subplans.append(QuerySubPlan("participants and speaker facts", question, ["fact.participant_count", "participant.overview", "participant.profile", "fact.record"], required_fields))
    if _has_any(normalized, "nationality", "citizenship", "quoc tich", "cong dan", "age", "tuoi", "education", "hoc van", "address", "dia chi", "phone", "telephone", "email", "so dien thoai", "sdt"):
        subplans.append(QuerySubPlan("precise participant attribute", question, ["fact.record", "participant.profile", "entity.profile", "transcript.window"], ["subject", "predicate", "value"]))

    # Do not match standalone "gia": in Vietnamese it is also part of
    # "tham gia" (participate). Require commercial phrases instead.
    if _has_any(normalized, "price", "cost", "money", "amount", "dollar", "discount", "gia tien", "chi phi", "gia ca", "giam gia", "tien bac"):
        subplans.append(QuerySubPlan("prices and commercial terms", question, ["fact.record", "decision.record", "summary.executive", "entity.profile", "transcript.window"], ["text", "value"]))

    if _has_any(normalized, "store", "shop", "merchant", "company", "brand", "cua hang", "ten cua hang", "thuong hieu", "cong ty"):
        subplans.append(QuerySubPlan("business and product entities", question, ["entity.profile", "fact.record", "summary.executive", "transcript.window"], ["text", "displayName"]))
    if _has_any(normalized, "timeline", "date", "time", "deadline", "thoi gian", "ngay", "moc"):
        subplans.append(QuerySubPlan("timeline and dates", question, ["event.timeline", "action.item", "summary.timeline"], ["startMs", "endMs"], answer_shape="timeline"))
    if _has_any(normalized, "provider", "model", "source", "file", "asset", "metadata", "mo hinh", "nguon"):
        subplans.append(QuerySubPlan("processing source metadata", question, ["meeting.metadata", "source.processing", "transcript.coverage"], ["provider", "model", "generatedAt"]))
    if _has_any(normalized, "quality", "confidence", "warning", "coverage", "quality", "chat luong", "canh bao", "thieu"):
        subplans.append(QuerySubPlan("quality and extraction coverage", question, ["quality.overview", "quality.warning", "extraction.overview", "extraction.warning", "transcript.coverage"], ["warnings", "coverage", "unsupportedClaims"]))
    if _has_any(normalized, "summary", "overview", "main", "topic", "tom tat", "noi dung chinh"):
        subplans.append(QuerySubPlan("meeting summary", question, ["summary.executive", "summary.topic", "summary.timeline", "topic.summary"], ["text"]))

    if not subplans:
        subplans.append(QuerySubPlan("general meeting evidence", question, ["summary.executive", "fact.record", "event.timeline", "transcript.window"], ["text"]))

    sections = _unique(section for plan in subplans for section in plan.sections)
    record_types = _unique(value for value in (_record_type_for_section(section) for section in sections) if value)
    # Subtype selectors are global filters in the generic tool. Do not combine
    # `participant_count` with participant records, otherwise a participant
    # name question would filter out every participant profile.
    record_subtypes = _unique(
        "participant_count"
        for section in sections
        if section == "fact.participant_count" and "participant" not in record_types
    )
    if _has_participant_count(normalized) and not _has_any(normalized, "who", "ai", "name", "names", "display name"):
        record_types = [record_type for record_type in record_types if record_type != "participant"]
        record_subtypes = ["participant_count"]
    answer_shape = _answer_shape(normalized, subplans)
    relation_types = _relation_types(normalized)
    if answer_shape == "participant_list":
        record_types = ["participant"]
    elif answer_shape == "actor_target":
        record_types = _unique(record_types + ["participant", "action", "entity"])
    elif answer_shape == "location":
        record_types = _unique(record_types + ["entity", "action", "event"])
    elif answer_shape == "timeline":
        record_types = _unique(record_types + ["event", "action", "fact"])
    fields = _unique(field for plan in subplans for field in plan.required_fields)
    intent = "multi_intent" if len(subplans) > 1 else subplans[0].goal.replace(" ", "_")
    return QueryPlan(intent, subplans, sections, fields, "hybrid", 0.75, record_types, record_subtypes, relation_types, answer_shape)


def replan_query(plan: QueryPlan, missing_fields: list[str]) -> QueryPlan:
    """Narrow a plan toward fields the verifier could not prove."""
    if not missing_fields:
        return plan
    missing = _unique(missing_fields)
    subplans = [
        QuerySubPlan(
            goal=f"follow-up evidence for {', '.join(missing)}",
            query=f"{plan.intent}: {', '.join(missing)}",
            sections=item.sections,
            record_types=item.record_types,
            record_subtypes=item.record_subtypes,
            required_fields=missing,
            limit=item.limit,
            relation_types=plan.relation_types,
            answer_shape=plan.answer_shape,
        )
        for item in plan.sub_queries
        if set(item.sections).intersection(plan.sections)
    ] or [QuerySubPlan(
        goal=f"follow-up evidence for {', '.join(missing)}",
        query=f"{plan.intent}: {', '.join(missing)}",
        sections=plan.sections,
        required_fields=missing,
        record_types=plan.record_types,
        record_subtypes=plan.record_subtypes,
    )]
    return QueryPlan(
        intent=f"{plan.intent}_follow_up",
        sub_queries=subplans,
        sections=plan.sections,
        required_fields=missing,
        retrieval_mode=plan.retrieval_mode,
        confidence=plan.confidence,
        record_types=plan.record_types,
        record_subtypes=plan.record_subtypes,
        relation_types=plan.relation_types,
        answer_shape=plan.answer_shape,
    )


def _answer_shape(normalized: str, subplans: list[QuerySubPlan]) -> str:
    if _has_any(normalized, "where", "location", "venue", "address", "dia diem", "o dau", "ở đâu"):
        return "location"
    if _has_any(normalized, "who booked", "who scheduled", "who owns", "who performed", "ai dat hen", "ai dat lich", "nguoi dat hen", "nguoi phu trach"):
        return "actor_target"
    if any("timeline" in plan.goal for plan in subplans) or _has_any(normalized, "timeline", "thoi gian", "moc"):
        return "timeline"
    if _has_any(normalized, "participant", "participants", "speaker", "people", "attendee", "nguoi tham gia", "ai tham gia", "nhung ai", "ten cua nhung nguoi", "ten cua ho") and not _has_participant_count(normalized):
        return "participant_list"
    if _has_participant_count(normalized):
        return "count"
    return "record_list"


def _relation_types(normalized: str) -> list[str]:
    relations: list[str] = []
    if _has_any(normalized, "who booked", "who scheduled", "ai dat hen", "ai dat lich", "nguoi dat hen"):
        relations.extend(["performed", "actor"])
    if _has_any(normalized, "where", "location", "venue", "address", "dia diem", "o dau", "ở đâu"):
        relations.extend(["targets", "located_at"])
    return _unique(relations)


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.lower())
    value = "".join(char for char in value if not unicodedata.combining(char))
    return value.replace("đ", "d")


def _has_any(value: str, *terms: str) -> bool:
    return any(re.search(rf"\b{re.escape(term)}\b", value) for term in terms)


def _has_participant_count(value: str) -> bool:
    return bool(
        re.search(r"\bhow many\b", value)
        or re.search(r"\bbao nhieu\b", value)
        or re.search(r"\bso (nguoi|luong nguoi|speaker|participants?)\b", value)
        or re.search(r"\b(count|number of) (people|person|speakers?|participants?|attendees?)\b", value)
    )


def _unique(values) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def _record_type_for_section(section: str) -> str:
    return {
        "participant": "participant",
        "participant.overview": "participant",
        "participant.profile": "participant",
        "fact.participant_count": "fact",
        "fact.record": "fact",
        "event.timeline": "event",
        "action.item": "action",
        "decision.record": "decision",
        "risk.record": "risk",
        "question.record": "question",
        "entity.profile": "entity",
        "topic.summary": "topic",
    }.get(section, "")

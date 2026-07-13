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


@dataclass(frozen=True)
class QueryPlan:
    intent: str
    sub_queries: list[QuerySubPlan]
    sections: list[str]
    required_fields: list[str]
    retrieval_mode: str = "hybrid"
    confidence: float = 0.75

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["subQueries"] = data.pop("sub_queries")
        data["requiredFields"] = data.pop("required_fields")
        for item in data["subQueries"]:
            item["requiredFields"] = item.pop("required_fields")
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
    if _has_any(normalized, "participant", "participants", "speaker", "people", "nguoi tham gia", "ai la"):
        subplans.append(QuerySubPlan("participants and speaker facts", question, ["fact.participant_count", "speaker.stats", "participant.overview", "participant.profile", "fact.record"], ["displayName", "value"]))
    if _has_any(normalized, "nationality", "citizenship", "quoc tich", "cong dan", "age", "tuoi", "education", "hoc van", "address", "dia chi", "phone", "telephone", "email", "so dien thoai", "sdt"):
        subplans.append(QuerySubPlan("precise participant attribute", question, ["fact.record", "participant.profile", "entity.profile", "transcript.window"], ["subject", "predicate", "value"]))

    # Do not match standalone "gia": in Vietnamese it is also part of
    # "tham gia" (participate). Require commercial phrases instead.
    if _has_any(normalized, "price", "cost", "money", "amount", "dollar", "discount", "gia tien", "chi phi", "gia ca", "giam gia", "tien bac"):
        subplans.append(QuerySubPlan("prices and commercial terms", question, ["fact.record", "decision.record", "summary.executive", "entity.profile", "transcript.window"], ["text", "value"]))

    if _has_any(normalized, "store", "shop", "merchant", "company", "brand", "cua hang", "ten cua hang", "thuong hieu", "cong ty"):
        subplans.append(QuerySubPlan("business and product entities", question, ["entity.profile", "fact.record", "summary.executive", "transcript.window"], ["text", "displayName"]))
    if _has_any(normalized, "timeline", "date", "time", "deadline", "thoi gian", "ngay", "moc"):
        subplans.append(QuerySubPlan("timeline and dates", question, ["event.timeline", "action.item", "summary.timeline"], ["startMs", "endMs", "dueDate"]))
    if _has_any(normalized, "provider", "model", "source", "file", "asset", "metadata", "mo hinh", "nguon"):
        subplans.append(QuerySubPlan("processing source metadata", question, ["meeting.metadata", "source.processing", "transcript.coverage"], ["provider", "model", "generatedAt"]))
    if _has_any(normalized, "quality", "confidence", "warning", "coverage", "quality", "chat luong", "canh bao", "thieu"):
        subplans.append(QuerySubPlan("quality and extraction coverage", question, ["quality.overview", "quality.warning", "extraction.overview", "extraction.warning", "transcript.coverage"], ["warnings", "coverage", "unsupportedClaims"]))
    if _has_any(normalized, "summary", "overview", "main", "topic", "tom tat", "noi dung chinh"):
        subplans.append(QuerySubPlan("meeting summary", question, ["summary.executive", "summary.topic", "summary.timeline", "topic.summary"], ["text"]))

    if not subplans:
        subplans.append(QuerySubPlan("general meeting evidence", question, ["summary.executive", "fact.record", "event.timeline", "transcript.window"], ["text"]))

    sections = _unique(section for plan in subplans for section in plan.sections)
    fields = _unique(field for plan in subplans for field in plan.required_fields)
    intent = "multi_intent" if len(subplans) > 1 else subplans[0].goal.replace(" ", "_")
    return QueryPlan(intent, subplans, sections, fields)


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
            required_fields=missing,
            limit=item.limit,
        )
        for item in plan.sub_queries
        if set(item.sections).intersection(plan.sections)
    ] or [QuerySubPlan(
        goal=f"follow-up evidence for {', '.join(missing)}",
        query=f"{plan.intent}: {', '.join(missing)}",
        sections=plan.sections,
        required_fields=missing,
    )]
    return QueryPlan(
        intent=f"{plan.intent}_follow_up",
        sub_queries=subplans,
        sections=plan.sections,
        required_fields=missing,
        retrieval_mode=plan.retrieval_mode,
        confidence=plan.confidence,
    )


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.lower())
    return "".join(char for char in value if not unicodedata.combining(char))


def _has_any(value: str, *terms: str) -> bool:
    return any(re.search(rf"\b{re.escape(term)}\b", value) for term in terms)


def _unique(values) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result

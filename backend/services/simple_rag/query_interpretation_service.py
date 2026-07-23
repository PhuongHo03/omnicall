"""One deterministic-first query interpretation authority."""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable

from backend.configs.settings import Settings
from backend.models.meeting_models import ChatMessage
from backend.services.simple_rag.contracts import GoalSpec, QuerySpec, TrustedReference
from backend.services.simple_rag.language_service import ChatLanguageService
from backend.services.simple_rag.query_intent_classifier import QueryIntentClassifier


class QueryInterpretationService:
    def __init__(self, settings: Settings | None = None, *, language_service: ChatLanguageService | None = None, classifier: QueryIntentClassifier | None = None) -> None:
        self.language_service = language_service or ChatLanguageService(settings)
        self.classifier = classifier or QueryIntentClassifier()

    def interpret(self, question: str, history: Iterable[ChatMessage] = (), *, language_hint: str | None = None) -> QuerySpec:
        normalized = _normalize(question)
        language = self.language_service.resolve(language_hint)
        decision = self.classifier.classify(frozenset(normalized.split()))
        if decision.operation == "direct":
            return QuerySpec(
                question=question,
                language=language,
                dependency_mode="standalone",
                goals=(GoalSpec("goal-1", "direct", decision.target, answer_shape=decision.answer_shape),),
            )

        operation, target, fields, shape = decision.operation, decision.target, decision.requested_fields, decision.answer_shape
        anchors: list[TrustedReference] = []
        dependency = "standalone"
        if not decision.standalone and _has_history_reference(normalized):
            anchor = _last_query_anchor(history)
            if anchor is None:
                return QuerySpec(
                    question=question,
                    language=language,
                    dependency_mode="ambiguous",
                    goals=(),
                    clarification_reason="missing_history_anchor",
                )
            dependency = "resolved"
            target = target if target != "meeting" else anchor.target
            if not fields:
                fields = anchor.requested_fields
            anchors.append(TrustedReference(anchor.goal_id, "target", anchor.target))

        if operation in {"lookup", "list"} and target in {"contact", "entity"}:
            entities = _extract_entities(question)
            if not entities:
                return QuerySpec(
                    question=question,
                    language=language,
                    dependency_mode="ambiguous",
                    goals=(),
                    clarification_reason="missing_entity",
                )
        else:
            entities = ()
        return QuerySpec(
            question=question,
            language=language,
            dependency_mode=dependency,
            goals=(GoalSpec("goal-1", operation, target, tuple(fields), entities, answer_shape=shape),),
            trusted_history_anchors=tuple(anchors),
        )
def _has_history_reference(text: str) -> bool:
    return any(term in text.split() for term in ("do", "nay", "them", "it", "that", "those", "more"))


def _last_query_anchor(history: Iterable[ChatMessage]) -> GoalSpec | None:
    for message in reversed(list(history)):
        metadata = message.metadata_json or {}
        raw = metadata.get("querySpec")
        goals = raw.get("goals") if isinstance(raw, dict) else None
        goal = goals[0] if isinstance(goals, list) and goals else None
        if isinstance(goal, dict) and goal.get("target"):
            return GoalSpec(
                str(goal.get("goal_id") or goal.get("goalId") or message.id),
                str(goal.get("operation") or "search"),
                str(goal["target"]),
                tuple(goal.get("requested_fields") or goal.get("requestedFields") or ()),
            )
    return None


def _extract_entities(question: str) -> tuple[str, ...]:
    quoted = re.findall(r'["“”]([^"“”]{2,80})["“”]', question)
    if quoted:
        return tuple(quoted)
    match = re.search(r"(?:cua|of|for)\s+([\wÀ-ỹ][\wÀ-ỹ .'-]{1,80})[?.!]*$", question, re.IGNORECASE)
    return (match.group(1).strip(),) if match else ()


def _normalize(value: str) -> str:
    folded = unicodedata.normalize("NFD", value.casefold())
    return " ".join("".join(char for char in folded if unicodedata.category(char) != "Mn").split())


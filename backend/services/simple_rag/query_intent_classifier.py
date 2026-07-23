"""Deterministic intent classification from reusable language concepts.

This module deliberately does not contain complete user-question strings.  It
maps normalized tokens to product concepts (meeting scope, overview, contact,
and so on); the interpreter turns the resulting decision into ``QuerySpec``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IntentDecision:
    operation: str
    target: str
    requested_fields: tuple[str, ...] = ()
    answer_shape: str = "paragraph"
    standalone: bool = False


# These are language concepts, not question-shaped exceptions.  They are kept
# together so adding a supported locale is a data change rather than another
# branch in QueryInterpretationService.
_CONCEPTS = {
    "meeting": frozenset({"cuoc", "hop", "meeting"}),
    "overview": frozenset({"tom", "tat", "noi", "dung", "chinh", "ban", "ve", "van", "de", "about", "discuss", "summary", "summarize", "main", "points"}),
    "count": frozenset({"bao", "nhieu", "so", "luong", "count", "many"}),
    "participant": frozenset({"nguoi", "tham", "gia", "participant", "participants", "attendee", "attendees", "who"}),
    "email": frozenset({"email"}),
    "phone": frozenset({"phone", "dien", "thoai"}),
    "contact": frozenset({"lien", "he", "contact"}),
    "action": frozenset({"hanh", "dong", "action", "todo", "viec", "lam"}),
    "decision": frozenset({"quyet", "dinh", "decision", "decisions"}),
    "risk": frozenset({"rui", "ro", "risk", "risks"}),
    "date": frozenset({"ngay", "when", "date"}),
    "location": frozenset({"dau", "where", "location"}),
    "greeting": frozenset({"xin", "chao", "hello", "hi", "hey"}),
    "farewell": frozenset({"tam", "biet", "bye", "goodbye"}),
    "identity": frozenset({"ban", "la", "ai", "who", "are", "you"}),
    "capability": frozenset({"lam", "duoc", "gi", "what", "can", "do"}),
}
_DIRECT_TOKEN_PATTERNS = {
    "identity": (frozenset({"ban", "la", "ai"}), frozenset({"who", "are", "you"})),
    "capability": (frozenset({"lam", "duoc", "gi"}), frozenset({"what", "can", "do"})),
}


class QueryIntentClassifier:
    """Classify stable product intents without inspecting conversation state."""

    def classify(self, tokens: frozenset[str]) -> IntentDecision:
        direct = self._direct(tokens)
        if direct is not None:
            return IntentDecision("direct", direct, answer_shape="short", standalone=True)
        if self._has_any(tokens, "overview") and self._has_any(tokens, "meeting"):
            return IntentDecision("summarize", "meeting", answer_shape="paragraph", standalone=True)
        if self._has_any(tokens, "count"):
            target = "participant" if self._has_any(tokens, "participant") else "record"
            return IntentDecision("count", target, ("count",), "scalar")
        if self._has_any(tokens, "email", "phone", "contact"):
            fields = tuple(field for field in ("email", "phone") if self._has_any(tokens, field))
            return IntentDecision("lookup", "contact", fields or ("email", "phone"), "record")
        for target in ("action", "decision", "risk", "participant"):
            if self._has_any(tokens, target):
                return IntentDecision("list", target, answer_shape="list")
        for target in ("date", "location"):
            if self._has_any(tokens, target):
                return IntentDecision("lookup", target, answer_shape="scalar")
        return IntentDecision("search", "meeting")

    def _direct(self, tokens: frozenset[str]) -> str | None:
        # Greeting/farewell require a locale-specific salutation token.  The
        # more general concepts below intentionally require multiple tokens to
        # avoid classifying a factual question containing "who" as identity.
        if self._has_any(tokens, "greeting"):
            return "greeting"
        if self._has_any(tokens, "farewell"):
            return "farewell"
        for intent, patterns in _DIRECT_TOKEN_PATTERNS.items():
            if any(pattern.issubset(tokens) for pattern in patterns):
                return intent
        return None

    def _has_any(self, tokens: frozenset[str], *concepts: str) -> bool:
        return any(tokens.intersection(_CONCEPTS[concept]) for concept in concepts)

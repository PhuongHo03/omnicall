"""Code-owned semantic vocabulary for generalized meeting intelligence.

The LLM may discover attributes and aliases, but it must not invent the
top-level contract consumed by retrieval, tools, or the UI. Unknown concepts
are retained as observations so information is not discarded while the
platform remains queryable through a stable vocabulary.
"""

from dataclasses import dataclass
import re
from typing import Final


@dataclass(frozen=True, slots=True)
class RecordTypeDefinition:
    name: str
    description: str
    aliases: tuple[str, ...] = ()
    temporal: bool = False
    actor_scoped: bool = False


_DEFINITIONS: tuple[RecordTypeDefinition, ...] = (
    RecordTypeDefinition("participant", "A person or speaker involved in or mentioned by the source.", ("person", "attendee", "speaker"), actor_scoped=True),
    RecordTypeDefinition("entity", "A named organization, product, system, location, amount, date, or domain concept.", ("named_entity", "object")),
    RecordTypeDefinition("fact", "An atomic claim with a subject, predicate, and value.", ("attribute", "claim")),
    RecordTypeDefinition("event", "A bounded occurrence or change in the source.", ("occurrence", "milestone"), temporal=True, actor_scoped=True),
    RecordTypeDefinition("topic", "A coherent subject discussed in the source.", ("theme", "subject")),
    RecordTypeDefinition("action", "A task, follow-up, or commitment.", ("action_item", "task", "todo"), temporal=True, actor_scoped=True),
    RecordTypeDefinition("decision", "A choice, approval, rejection, or agreed outcome.", ("resolution", "agreement"), temporal=True, actor_scoped=True),
    RecordTypeDefinition("risk", "A blocker, dependency, uncertainty, or potential negative outcome.", ("issue", "concern", "blocker"), actor_scoped=True),
    RecordTypeDefinition("question", "An explicit or unresolved question.", ("open_question", "unknown"), actor_scoped=True),
    RecordTypeDefinition("relationship", "A typed edge connecting two knowledge records.", ("relation", "edge")),
    RecordTypeDefinition("observation", "A valid extracted observation without a more specific registered type.", ("other", "unclassified")),
)

_BY_NAME: Final = {definition.name: definition for definition in _DEFINITIONS}
_BY_ALIAS: Final = {
    alias: definition.name
    for definition in _DEFINITIONS
    for alias in (definition.name, *definition.aliases)
}
CANONICAL_RECORD_TYPES: Final = frozenset(_BY_NAME)


def canonical_record_type(raw_type: object, *, data: dict | None = None) -> str:
    """Return a stable record type for an LLM or imported candidate.

    A subtype such as ``participant_count`` belongs in the record payload;
    it does not create a new top-level collection. A few legacy names are
    recognized only as aliases and are never exposed as canonical types.
    """

    value = _slug(raw_type)
    if value in _BY_ALIAS:
        return _BY_ALIAS[value]
    if isinstance(data, dict):
        nested = _slug(data.get("recordType") or data.get("kind"))
        if nested in _BY_ALIAS:
            return _BY_ALIAS[nested]
    return "observation"


def record_type_definition(record_type: object) -> RecordTypeDefinition:
    """Return the definition for a canonical type or the observation fallback."""

    return _BY_NAME.get(str(record_type), _BY_NAME["observation"])


def _slug(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")

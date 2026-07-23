"""Mandatory terminal authority for synthesized answers."""

from __future__ import annotations

import unicodedata
from typing import Any

from backend.services.simple_rag.contracts import SynthesisContract, VerificationResult


class AnswerVerificationService:
    def verify(self, payload: dict[str, Any], contract: SynthesisContract) -> VerificationResult:
        errors: list[str] = []
        answer = payload.get("answer")
        claims = payload.get("claims")
        if not isinstance(answer, str) or not answer.strip():
            errors.append("answer_missing")
        elif _contains_non_latin_letters(answer):
            # The currently supported chat locales use Latin script. This is a
            # script policy, not a Vietnamese- or English-specific exception.
            # A future non-Latin locale must add its script profile here.
            errors.append("answer_language_mismatch")
        if not isinstance(claims, list):
            errors.append("claims_must_be_array")
            claims = []
        if contract.bundles and contract.direct_intent is None and not claims:
            errors.append("factual_claims_missing")
        allowed_goals = {goal.goal_id for goal in contract.goals}
        allowed_facts = {fact.fact_id: fact for fact in contract.locked_facts}
        facts_by_goal = {
            bundle.goal_id: {fact.fact_id: fact for fact in bundle.typed_facts}
            for bundle in contract.bundles
        }
        verified_refs: set[str] = set()
        claimed_facts: set[str] = set()
        for index, claim in enumerate(claims):
            if not isinstance(claim, dict):
                errors.append(f"claim_{index}_invalid")
                continue
            goal_id = claim.get("goalId")
            if goal_id not in allowed_goals:
                errors.append(f"claim_{index}_unknown_goal")
            fact_ids = claim.get("factIds") or []
            if not isinstance(fact_ids, list) or not fact_ids or any(fact_id not in allowed_facts for fact_id in fact_ids):
                errors.append(f"claim_{index}_unknown_fact")
            else:
                claimed_facts.update(fact_ids)
                if any(fact_id not in facts_by_goal.get(goal_id, {}) for fact_id in fact_ids):
                    errors.append(f"claim_{index}_cross_goal_fact")
                # Citation IDs are backend-owned bookkeeping.  A model selects
                # facts only; every verified ref is derived from the immutable
                # fact-to-ref mapping in the matching goal bundle.
                for fact_id in fact_ids:
                    fact = allowed_facts[fact_id]
                    if not fact.refs:
                        errors.append(f"claim_{index}_fact_missing_evidence:{fact_id}")
                    verified_refs.update(fact.refs)
        required_locked = {
            fact_id: fact
            for fact_id, fact in allowed_facts.items()
            if fact.value_type in {"number", "string", "list", "email", "phone", "date"}
        }
        if required_locked:
            for fact_id, fact in required_locked.items():
                if fact_id not in claimed_facts:
                    errors.append(f"locked_fact_omitted:{fact_id}")
                values = fact.value if isinstance(fact.value, list) else [fact.value]
                for value in values:
                    scalar = str(value).strip()
                    if scalar and scalar.casefold() not in str(answer or "").casefold():
                        errors.append(f"locked_fact_value_missing:{fact_id}")
        return VerificationResult(not errors, tuple(dict.fromkeys(errors)), tuple(sorted(verified_refs)))


def _contains_non_latin_letters(value: str) -> bool:
    for character in value:
        if not character.isalpha():
            continue
        if "LATIN" not in unicodedata.name(character, ""):
            return True
    return False

"""LLM-only successful answer generation with one contract-only retry."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict
from typing import Any

from backend.configs.settings import Settings, get_settings
from backend.providers.llm import LLMProvider, get_execution_snapshot
from backend.providers.llm.provider import call_with_llm_circuit
from backend.services.simple_rag.answer_verification_service import AnswerVerificationService
from backend.services.simple_rag.contracts import SynthesisContract, VerificationResult


logger = logging.getLogger(__name__)
_ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "goalId": {"type": "string"},
                    "factIds": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["goalId", "factIds"],
            },
        },
    },
    "required": ["answer", "claims"],
}


class SynthesisContractError(RuntimeError):
    def __init__(self, verification: VerificationResult) -> None:
        super().__init__("LLM output violated synthesis-contract.v1")
        self.verification = verification


class AnswerSynthesisService:
    def __init__(self, provider: LLMProvider, settings: Settings | None = None, verifier: AnswerVerificationService | None = None) -> None:
        self.provider = provider
        self.settings = settings or get_settings()
        self.verifier = verifier or AnswerVerificationService()

    def synthesize(self, contract: SynthesisContract, *, total_timeout_seconds: float | None = None) -> tuple[dict[str, Any], VerificationResult, Any, int]:
        system = (
            "You verbalize a locked answer contract naturally. Return JSON only: "
            '{"answer":"...","claims":[{"goalId":"...","factIds":["..."]}]}. '
            "Never add facts, identifiers, people, dates, counts, or refs absent from the contract. "
            "Include every scalar, list, date, and contact locked value exactly. Use text evidence selectively "
            "to answer the requested goals; do not repeat unrelated evidence. Claims must enumerate only the used fact IDs. "
            "Do not return citation IDs: the server derives citations from the selected fact IDs."
        )
        system += (
            f" Write the answer in {_language_name(contract.language)} only, using that language's normal writing system; "
            "never translate it to another language or switch writing systems."
        )
        if contract.disclosure_permissions:
            system += (
                " Disclose personal or contact details only when their field is explicitly present in "
                "disclosurePermissions."
            )
        else:
            system += (
                " This is not a personal-profile lookup: do not include age, contact details, address, "
                "government identifiers, or other personal-profile details unless the user explicitly requested them."
            )
        if contract.direct_intent is not None:
            system += (
                " This is a direct, non-meeting intent: write the natural response, "
                "do not mention meeting evidence, and return exactly an empty claims array: \"claims\": []."
            )
        base = _contract_payload(contract)
        errors: tuple[str, ...] = ()
        attempts = self.settings.rag_synthesis_contract_retries + 1
        synthesis_deadline = time.monotonic() + total_timeout_seconds if total_timeout_seconds is not None else None
        for attempt in range(attempts):
            remaining = synthesis_deadline - time.monotonic() if synthesis_deadline is not None else None
            if remaining is not None and remaining <= 0:
                raise TimeoutError("rag_synthesis_timeout")
            prompt = json.dumps(
                {"contract": base, **({"validationErrors": list(errors)} if errors else {})},
                ensure_ascii=False,
                separators=(",", ":"),
            )
            attempt_system = system
            if "answer_language_mismatch" in errors:
                attempt_system += (
                    f" Your previous answer used the wrong script. Rewrite it entirely in "
                    f"{_language_name(contract.language)} using its normal writing system."
                )
            effective_provider = self.provider
            if attempt > 0 and bool(getattr(self.provider, "last_fallback_used", False)):
                effective_provider = getattr(self.provider, "fallback", self.provider)
            stage_call = getattr(effective_provider, "generate_json_with_stage_timeouts", None)
            if callable(stage_call):
                payload = stage_call(
                    system_prompt=attempt_system,
                    user_prompt=prompt,
                    temperature=0,
                    primary_timeout_seconds=self.settings.rag_synthesis_primary_timeout_seconds,
                    fallback_timeout_seconds=self.settings.rag_synthesis_fallback_timeout_seconds,
                    total_timeout_seconds=remaining,
                    max_output_tokens=512,
                    response_schema=_ANSWER_SCHEMA,
                )
            else:
                payload = call_with_llm_circuit(
                    effective_provider,
                    stage="synthesis",
                    function=lambda: effective_provider.generate_json(
                        system_prompt=attempt_system,
                        user_prompt=prompt,
                        temperature=0,
                        timeout_seconds=min(
                            self.settings.rag_synthesis_fallback_timeout_seconds
                            if effective_provider is not self.provider
                            else self.settings.rag_synthesis_primary_timeout_seconds,
                            remaining,
                        ) if remaining is not None else (
                            self.settings.rag_synthesis_fallback_timeout_seconds
                            if effective_provider is not self.provider
                            else self.settings.rag_synthesis_primary_timeout_seconds
                        ),
                        max_output_tokens=512,
                        response_schema=_ANSWER_SCHEMA,
                    ),
                )
            snapshot = get_execution_snapshot(self.provider)
            verification = self.verifier.verify(payload, contract)
            if verification.passed:
                return payload, verification, snapshot, attempt + 1
            logger.warning(
                "synthesis_contract_invalid attempt=%d keys=%s claims_type=%s errors=%s",
                attempt + 1,
                sorted(str(key) for key in payload.keys()),
                type(payload.get("claims")).__name__,
                list(verification.errors),
            )
            errors = verification.errors
        raise SynthesisContractError(verification)


def _contract_payload(contract: SynthesisContract) -> dict[str, Any]:
    evidence = []
    for bundle in contract.bundles:
        evidence.append({
            "goalId": bundle.goal_id,
            "status": bundle.status,
            "facts": [
                {
                    "factId": fact.fact_id,
                    "field": fact.field,
                    "value": _bounded_value(fact.value),
                    "valueType": fact.value_type,
                    "completeness": fact.completeness,
                    "refs": list(fact.refs),
                }
                for fact in bundle.typed_facts
            ],
        })
    return {
        "version": contract.version,
        "language": contract.language,
        "answerStyle": contract.answer_style,
        "directIntent": contract.direct_intent,
        "goals": [asdict(goal) for goal in contract.goals],
        "lockedFacts": [
            asdict(fact)
            for fact in contract.locked_facts
            if fact.value_type in {"number", "string", "list", "email", "phone", "date"}
        ],
        "evidence": evidence,
        "disclosurePermissions": list(contract.disclosure_permissions),
    }


def _bounded_value(value: Any) -> Any:
    if isinstance(value, str):
        return value[:800]
    if isinstance(value, list):
        return value[:50]
    return value


def _language_name(language: str) -> str:
    return {"vi": "Vietnamese", "en": "English"}.get(language, language)

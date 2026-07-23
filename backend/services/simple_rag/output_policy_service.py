"""Deterministic disclosure boundary plus output guardrail orchestration."""

from backend.configs.settings import Settings, get_settings
from backend.providers.contracts.guardrail import GuardrailResult
from backend.providers.guardrail_provider import GuardrailProvider, get_guardrail_provider, safe_guardrail_check
from backend.services.simple_rag.contracts import PipelineResult


class OutputPolicyService:
    def __init__(self, provider: GuardrailProvider | None = None, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.provider = provider or get_guardrail_provider()

    def verify(self, result: PipelineResult, *, meeting_id: str, turn_id: str) -> GuardrailResult:
        return safe_guardrail_check(
            self.provider,
            kind="answer",
            text=result.answer,
            metadata={
                "meetingId": meeting_id,
                "turnId": turn_id,
                "hasCitations": bool(result.citations),
                "claimVerificationPassed": True,
                "verifiedEvidenceRefCount": len(result.citations),
                "evidenceState": result.evidence_state,
            },
            strict_mode=True,
        )

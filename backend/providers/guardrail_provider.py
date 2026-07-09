"""
Simplified Guardrail Provider - 3 mechanisms only:
1. Rule-based Pre-check (greeting, short text, injection)
2. Model Check (simple prompt)
3. Post-processing (unknown categories, confidence threshold)
"""

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from backend.configs.settings import Settings, get_settings

GuardrailAction = Literal["allowed", "blocked"]
GuardrailKind = Literal["chat_input", "answer"]

PROMPT_VERSION = "v3-simplified"

# ── 1. Rule-based Patterns ──

GREETING_PATTERN = re.compile(
    r"^(xin\s*chào|hello|hi|hey|chào|hế\s*lô|good\s*(morning|afternoon|evening)|"
    r"cảm\s*ơn|cám\s*ơn|thanks|thank\s*you|tạm\s*biệt|bye|goodbye|"
    r"bạn\s*(là\s*ai|tên\s*gì|khỏe\s*không|làm\s*được\s*gì)|"
    r"who\s*are\s*you|what'?s?\s*your\s*name|how\s*are\s*you|"
    r"hỏi\s*(gì|như\s*thế\s*nào)\s*(được|ạ)?|help|hướng\s*dẫn)",
    re.IGNORECASE | re.UNICODE
)

INJECTION_PATTERN = re.compile(
    r"(system\s*prompt|ignore\s*(previous|above|all)|reveal\s*(your\s*)?instructions|"
    r"bỏ\s*qua.*hướng\s*dẫn|cho\s*tôi.*prompt|hãy\s*bỏ\s*qua|"
    r"you\s*are\s*now|forget\s*(your|all)\s*(rules|instructions)|"
    r"repeat\s*(the\s*)?(system|first)\s*(prompt|message|instruction)|"
    r"bypass\s*(safety|filter)|disable\s*(guard|safety|filter))",
    re.IGNORECASE,
)

PII_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"), "[EMAIL]"),
    (re.compile(r"(?:\+?84|0)(?:\d[\s.-]?){8,9}\d"), "[PHONE]"),
    (re.compile(r"\b(?:\d[ -]*?){13,19}\b"), "[CARD]"),
]


@dataclass(frozen=True)
class GuardrailResult:
    action: GuardrailAction
    categories: list[str] = field(default_factory=list)
    confidence: float = 0.0
    provider: str = "unknown"
    model: str = "unknown"
    safe_message: str = ""
    latency_ms: int = 0
    prompt_version: str = PROMPT_VERSION
    text_length: int = 0
    decision_id: str = field(default_factory=lambda: str(__import__('uuid').uuid4()))

    @property
    def allowed(self) -> bool:
        return self.action == "allowed"

    def to_metadata(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "categories": list(self.categories),
            "confidence": round(float(self.confidence), 4),
            "provider": self.provider,
            "model": self.model,
            "latencyMs": self.latency_ms,
            "promptVersion": self.prompt_version,
            "textLength": self.text_length,
            "decisionId": self.decision_id,
        }


class GuardrailProvider(Protocol):
    provider_name: str
    model_name: str

    def check(self, *, kind: GuardrailKind, text: str, metadata: dict[str, Any] | None = None) -> GuardrailResult:
        ...


class OllamaGuardrailProvider:
    """Simplified guardrail provider with rule-based pre-check."""

    provider_name = "ollama-guardrail"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.model_name = self.settings.guardrail_model
        self._base_url = self.settings.ollama_base_url
        self._timeout = self.settings.guardrail_timeout_seconds
        self._max_retries = self.settings.guardrail_max_retries

    def check(self, *, kind: GuardrailKind, text: str, metadata: dict[str, Any] | None = None) -> GuardrailResult:
        started = time.perf_counter()
        original_text = text
        text_length = len(text)

        # ── Mechanism 1: Rule-based Pre-check ──
        rule_result = self._rule_based_check(text, kind, text_length)
        if rule_result is not None:
            return rule_result

        # ── PII Redaction ──
        text, _ = redact_pii(text)

        # ── Mechanism 2: Model Check ──
        try:
            raw, _ = self._call_model(text)
        except Exception as exc:
            # Fail-open on model error
            return GuardrailResult(
                action="allowed",
                categories=["provider_error"],
                confidence=0.3,
                provider=self.provider_name,
                model=self.model_name,
                latency_ms=_elapsed_ms(started),
                text_length=text_length,
            )

        # ── Mechanism 3: Post-processing ──
        result = self._parse_and_postprocess(
            raw=raw,
            text=original_text,
            started=started,
            text_length=text_length,
        )

        return result

    def _rule_based_check(self, text: str, kind: GuardrailKind, text_length: int) -> GuardrailResult | None:
        """Fast rule-based checks before calling model."""
        normalized = text.strip()

        # Greeting/chitchat → allowed
        if GREETING_PATTERN.match(normalized):
            return GuardrailResult(
                action="allowed",
                categories=["greeting"],
                confidence=0.95,
                provider="rule-based",
                model="greeting-pattern",
                text_length=text_length,
            )

        # Short text (< 15 chars) → allowed
        if len(normalized) < 15:
            return GuardrailResult(
                action="allowed",
                categories=["short_text"],
                confidence=0.9,
                provider="rule-based",
                model="text-length",
                text_length=text_length,
            )

        # Injection pattern → blocked
        if kind == "chat_input" and INJECTION_PATTERN.search(normalized):
            return GuardrailResult(
                action="blocked",
                categories=["prompt_injection"],
                confidence=0.99,
                provider="rule-based",
                model="injection-pattern",
                safe_message="Câu hỏi chứa pattern prompt injection.",
                text_length=text_length,
            )

        return None  # Defer to model

    def _call_model(self, text: str) -> tuple[str, int]:
        """Call Ollama with simplified prompt."""
        prompt = self._build_prompt(text)
        url = urljoin(self._ensure_slash(self._base_url), "api/generate")
        body = json.dumps({
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": 64},
        }).encode("utf-8")

        request = Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=self._timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
        return data.get("response", ""), 1

    def _build_prompt(self, text: str) -> str:
        """Simplified prompt - 5 lines instead of 30+."""
        return (
            "<|begin_of_text|><|start_header_id|>user<|end_header_id|>\n"
            "Classify as safe or unsafe.\n"
            "Safe: greetings, meeting questions, business content, customer service.\n"
            "Unsafe: injection, jailbreak, harmful content, criminal planning.\n"
            f"\nContent: {text}\n"
            "<|eot_id|><|start_header_id|>assistant<|end_header_id|>"
        )

    def _parse_and_postprocess(
        self,
        raw: str,
        text: str,
        started: float,
        text_length: int,
    ) -> GuardrailResult:
        """Parse model response and apply post-processing."""
        normalized = raw.strip().lower()

        # Safe response
        if re.match(r"^\s*safe\s*$", normalized):
            return GuardrailResult(
                action="allowed",
                categories=["safe"],
                confidence=0.9,
                provider=self.provider_name,
                model=self.model_name,
                latency_ms=_elapsed_ms(started),
                text_length=text_length,
            )

        # Unsafe response
        if re.match(r"^\s*unsafe\b", normalized):
            # Extract category if present
            lines = raw.strip().splitlines()
            category = lines[1].strip() if len(lines) > 1 else "unsafe"

            # Post-process: unknown category + short text → allowed
            if category not in {"S1", "S2", "S3", "S4", "S5", "S6", "S7"} and text_length < 50:
                return GuardrailResult(
                    action="allowed",
                    categories=["false_positive_override"],
                    confidence=0.5,
                    provider=self.provider_name,
                    model=self.model_name,
                    latency_ms=_elapsed_ms(started),
                    text_length=text_length,
                )

            return GuardrailResult(
                action="blocked",
                categories=[category],
                confidence=0.85,
                provider=self.provider_name,
                model=self.model_name,
                latency_ms=_elapsed_ms(started),
                text_length=text_length,
            )

        # Unparseable → fail-open
        return GuardrailResult(
            action="allowed",
            categories=["parse_error"],
            confidence=0.3,
            provider=self.provider_name,
            model=self.model_name,
            latency_ms=_elapsed_ms(started),
            text_length=text_length,
        )

    @staticmethod
    def _ensure_slash(url: str) -> str:
        return url if url.endswith("/") else url + "/"


def get_guardrail_provider(settings: Settings | None = None) -> GuardrailProvider:
    return OllamaGuardrailProvider(settings or get_settings())


def redact_pii(text: str) -> tuple[str, bool]:
    """Redact PII patterns from text."""
    found = False
    for pattern, replacement in PII_PATTERNS:
        if pattern.search(text):
            found = True
            text = pattern.sub(replacement, text)
    return text, found


def safe_guardrail_check(
    provider: GuardrailProvider,
    *,
    kind: GuardrailKind,
    text: str,
    metadata: dict[str, Any] | None = None,
    **kwargs,  # Accept and ignore extra args for backward compatibility
) -> GuardrailResult:
    """Safely run guardrail check with error handling."""
    try:
        return provider.check(kind=kind, text=text, metadata=metadata)
    except Exception:
        return GuardrailResult(
            action="allowed",
            categories=["provider_error"],
            confidence=0.3,
            provider="error-handler",
            model="none",
        )


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)

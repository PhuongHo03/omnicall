import json
import unittest
from unittest.mock import patch

from backend.configs.settings import Settings
from backend.providers.guardrail_provider import (
    GuardrailProviderError,
    OllamaGuardrailProvider,
    _build_llama_guard_prompt,
    build_guardrail_provider,
    safe_guardrail_check,
)


class BrokenGuardrailProvider:
    provider_name = "broken-guardrail"
    model_name = "broken-model"

    def check(self, *, kind, text, metadata=None):
        raise GuardrailProviderError("provider unavailable")


class FakeOllamaResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class GuardrailProviderTestCase(unittest.TestCase):
    def test_safe_check_fails_open_when_strict_mode_is_disabled(self) -> None:
        result = safe_guardrail_check(
            BrokenGuardrailProvider(),
            kind="chat_input",
            text="normal question",
            strict_mode=False,
        )

        self.assertEqual(result.action, "warn")
        self.assertIn("provider_error", result.categories)
        self.assertGreaterEqual(result.latency_ms, 0)

    def test_safe_check_fails_closed_when_strict_mode_is_enabled(self) -> None:
        result = safe_guardrail_check(
            BrokenGuardrailProvider(),
            kind="chat_input",
            text="normal question",
            strict_mode=True,
        )

        self.assertEqual(result.action, "block")
        self.assertIn("provider_error", result.categories)

    def test_build_ollama_guardrail_provider_uses_local_model_setting(self) -> None:
        provider = build_guardrail_provider(
            Settings(
                GUARDRAIL_MODEL="llama-guard3:1b",
                GUARDRAIL_TIMEOUT_SECONDS=1,
                GUARDRAIL_MAX_RETRIES=0,
            )
        )

        self.assertEqual(provider.provider_name, "ollama-guardrail")
        self.assertEqual(provider.model_name, "llama-guard3:1b")

    def test_ollama_guardrail_provider_normalizes_local_model_response(self) -> None:
        provider = OllamaGuardrailProvider(
            Settings(
                OLLAMA_BASE_URL="http://localhost:11434",
                GUARDRAIL_MODEL="llama-guard3:1b",
                GUARDRAIL_TIMEOUT_SECONDS=1,
                GUARDRAIL_MAX_RETRIES=0,
            )
        )
        provider._call_ollama = lambda prompt: "unsafe\nS1,S2"  # type: ignore[method-assign]

        result = provider.check(kind="chat_input", text="Summarize the action items.")

        self.assertEqual(result.action, "block")
        self.assertEqual(result.categories, ["S1", "S2"])
        self.assertEqual(result.provider, "ollama-guardrail")
        self.assertEqual(result.model, "llama-guard3:1b")

    def test_ollama_guardrail_request_limits_generation_for_local_latency(self) -> None:
        provider = OllamaGuardrailProvider(
            Settings(
                OLLAMA_BASE_URL="http://localhost:11434",
                GUARDRAIL_MODEL="llama-guard3:1b",
                GUARDRAIL_TIMEOUT_SECONDS=1,
                GUARDRAIL_MAX_RETRIES=0,
            )
        )
        captured_payload = {}

        def fake_urlopen(request, timeout):
            captured_payload.update(json.loads(request.data.decode("utf-8")))
            self.assertEqual(timeout, 1)
            return FakeOllamaResponse({"response": "safe"})

        with patch("backend.providers.guardrail_provider.urlopen", fake_urlopen):
            result = provider.check(kind="chat_input", text="normal meeting question")

        self.assertEqual(result.action, "allow")
        self.assertEqual(captured_payload["model"], "llama-guard3:1b")
        self.assertEqual(captured_payload["options"]["num_predict"], 16)
        self.assertEqual(captured_payload["options"]["num_ctx"], 1024)

    def test_long_transcript_guardrail_prompt_is_sampled(self) -> None:
        text = "A" * 2200 + " middle-marker " + "B" * 2200 + " final-marker"
        prompt = _build_llama_guard_prompt(
            kind="transcript",
            text=text,
            metadata={"meetingId": "meeting-1", "ignored": "not stored"},
        )

        self.assertIn("[content omitted before middle sample]", prompt)
        self.assertIn("[content omitted before final sample]", prompt)
        self.assertIn("meeting-1", prompt)
        self.assertNotIn("not stored", prompt)
        self.assertLess(len(prompt), 1400)


if __name__ == "__main__":
    unittest.main()

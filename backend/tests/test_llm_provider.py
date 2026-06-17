import json
import unittest
from unittest.mock import patch
from urllib.error import URLError

from backend.configs.settings import Settings
from backend.providers.llm_provider import (
    FallbackLLMProvider,
    LLMProviderError,
    OpenAICompatibleLLMProvider,
    build_llm_provider,
)


class FakeHTTPResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeHTTPResponse":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class BrokenProvider:
    provider_name = "broken"
    model_name = "broken-model"

    def generate_json(self, *, system_prompt: str, user_prompt: str) -> dict:
        raise LLMProviderError("primary failed")


class StaticProvider:
    provider_name = "static"
    model_name = "static-model"

    def generate_json(self, *, system_prompt: str, user_prompt: str) -> dict:
        return {"ok": True, "userPrompt": user_prompt}


class LLMProviderTestCase(unittest.TestCase):
    def make_settings(self, **overrides) -> Settings:
        defaults = {
            "LLM_PROVIDER": "endpoint",
            "LLM_API_BASE_URL": "http://llm.internal/v1",
            "LLM_API_KEY": "test-key",
            "LLM_MODEL": "private-model",
            "LLM_ENDPOINT_COMPATIBILITY": "openai",
            "LLM_FALLBACK_PROVIDER": "ollama",
            "OLLAMA_BASE_URL": "http://ollama.internal:11434",
            "OLLAMA_MODEL": "qwen2.5:1.5b",
        }
        defaults.update(overrides)
        return Settings(_env_file=None, **defaults)

    def test_endpoint_provider_is_wrapped_with_ollama_fallback(self) -> None:
        provider = build_llm_provider(self.make_settings())

        self.assertIsInstance(provider, FallbackLLMProvider)
        self.assertEqual(provider.primary.provider_name, "openai-compatible")
        self.assertEqual(provider.primary.model_name, "private-model")
        self.assertEqual(provider.fallback.provider_name, "ollama")
        self.assertEqual(provider.fallback.model_name, "qwen2.5:1.5b")

    def test_ollama_provider_can_be_primary_without_extra_fallback_wrapper(self) -> None:
        provider = build_llm_provider(self.make_settings(LLM_PROVIDER="ollama"))

        self.assertEqual(provider.provider_name, "ollama")
        self.assertEqual(provider.model_name, "qwen2.5:1.5b")

    def test_openai_compatible_provider_posts_chat_completion_and_parses_json_content(self) -> None:
        captured = {}

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            captured["headers"] = dict(request.header_items())
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return FakeHTTPResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "content": "{\"summary\":\"done\",\"items\":[1,2]}"
                            }
                        }
                    ]
                }
            )

        provider = OpenAICompatibleLLMProvider(
            config=type(
                "Config",
                (),
                {
                    "base_url": "http://llm.internal/v1",
                    "model": "private-model",
                    "api_key": "secret",
                    "timeout_seconds": 12,
                },
            )()
        )

        with patch("backend.providers.llm_provider.urlopen", side_effect=fake_urlopen):
            result = provider.generate_json(system_prompt="return json", user_prompt="meeting transcript")

        self.assertEqual(result, {"summary": "done", "items": [1, 2]})
        self.assertEqual(captured["url"], "http://llm.internal/v1/chat/completions")
        self.assertEqual(captured["timeout"], 12)
        self.assertEqual(captured["headers"]["Authorization"], "Bearer secret")
        self.assertEqual(captured["body"]["model"], "private-model")
        self.assertEqual(captured["body"]["response_format"], {"type": "json_object"})

    def test_openai_compatible_provider_retries_transient_failures(self) -> None:
        calls = {"count": 0}

        def flaky_urlopen(request, timeout):
            calls["count"] += 1
            if calls["count"] == 1:
                raise URLError("temporary outage")
            return FakeHTTPResponse(
                {"choices": [{"message": {"content": "{\"summary\":\"retried\"}"}}]}
            )

        provider = OpenAICompatibleLLMProvider(
            config=type(
                "Config",
                (),
                {
                    "base_url": "http://llm.internal/v1",
                    "model": "private-model",
                    "api_key": "secret",
                    "timeout_seconds": 12,
                    "max_retries": 1,
                    "retry_backoff_seconds": 0,
                },
            )()
        )

        with patch("backend.providers.llm_provider.urlopen", side_effect=flaky_urlopen):
            result = provider.generate_json(system_prompt="return json", user_prompt="meeting transcript")

        self.assertEqual(result, {"summary": "retried"})
        self.assertEqual(calls["count"], 2)

    def test_fallback_provider_uses_secondary_provider_after_primary_failure(self) -> None:
        provider = FallbackLLMProvider(BrokenProvider(), StaticProvider())

        self.assertEqual(
            provider.generate_json(system_prompt="system", user_prompt="hello"),
            {"ok": True, "userPrompt": "hello"},
        )
        self.assertEqual(provider.last_provider_name, "static")
        self.assertEqual(provider.last_provider_model, "static-model")

    def test_fallback_provider_records_primary_provider_when_primary_succeeds(self) -> None:
        provider = FallbackLLMProvider(StaticProvider(), BrokenProvider())

        self.assertEqual(
            provider.generate_json(system_prompt="system", user_prompt="hello"),
            {"ok": True, "userPrompt": "hello"},
        )
        self.assertEqual(provider.last_provider_name, "static")
        self.assertEqual(provider.last_provider_model, "static-model")


if __name__ == "__main__":
    unittest.main()

import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import patch
from urllib.error import URLError

from backend.configs.settings import Settings
from backend.providers.llm import (
    FallbackLLMProvider,
    FallbackLLMProviderError,
    LLMExecutionTracker,
    LLMProviderError,
    LLMRequestConfig,
    OllamaLLMProvider,
    OpenAICompatibleLLMProvider,
    build_llm_provider,
    generate_json_with_execution,
    get_configured_primary_model_name,
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

    def __init__(self) -> None:
        self.temperatures: list[float] = []

    def generate_json(self, *, system_prompt: str, user_prompt: str, temperature: float = 0) -> dict:
        self.temperatures.append(temperature)
        raise LLMProviderError("primary failed")


class StaticProvider:
    provider_name = "static"
    model_name = "static-model"

    def __init__(self) -> None:
        self.temperatures: list[float] = []

    def generate_json(self, *, system_prompt: str, user_prompt: str, temperature: float = 0) -> dict:
        self.temperatures.append(temperature)
        return {"ok": True, "userPrompt": user_prompt, "temperature": temperature}


class ConditionalProvider(StaticProvider):
    provider_name = "conditional"
    model_name = "conditional-model"

    def generate_json(self, *, system_prompt: str, user_prompt: str, temperature: float = 0) -> dict:
        if user_prompt == "fallback":
            raise LLMProviderError("conditional primary failed")
        return super().generate_json(system_prompt=system_prompt, user_prompt=user_prompt, temperature=temperature)


class BlockingProvider(StaticProvider):
    provider_name = "blocking"
    model_name = "blocking-model"

    def __init__(self, started: Event, release: Event) -> None:
        super().__init__()
        self.started = started
        self.release = release

    def generate_json(self, *, system_prompt: str, user_prompt: str, temperature: float = 0) -> dict:
        self.started.set()
        self.release.wait(timeout=1)
        return super().generate_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
        )


class LLMProviderTestCase(unittest.TestCase):
    def setUp(self) -> None:
        # Circuit state is intentionally process-wide in production. Isolate
        # independent test cases while retaining within-test breaker behavior.
        from backend.providers.llm.provider import _LLM_BREAKERS

        _LLM_BREAKERS.clear()

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
            "OLLAMA_LLM_TIMEOUT_SECONDS": 600,
            "OLLAMA_CONTEXT_LENGTH": 8192,
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
        self.assertEqual(provider.fallback.config.timeout_seconds, 600)
        self.assertEqual(provider.fallback.config.context_length, 8192)
        self.assertEqual(provider.fallback.config.max_output_tokens, 1024)

    def test_ollama_request_bounds_generated_tokens(self) -> None:
        captured = {}

        def fake_urlopen(request, timeout):
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return FakeHTTPResponse({"message": {"content": "{\"ok\":true}"}})

        provider = OllamaLLMProvider(
            LLMRequestConfig(
                base_url="http://ollama.internal:11434",
                model="qwen2.5:1.5b",
                timeout_seconds=600,
                context_length=8192,
                max_output_tokens=1024,
            )
        )
        with patch("backend.providers.llm.transport.urlopen", side_effect=fake_urlopen):
            result = provider.generate_json(system_prompt="system", user_prompt="transcript")

        self.assertEqual(result, {"ok": True})
        self.assertEqual(captured["body"]["options"]["num_ctx"], 8192)
        self.assertEqual(captured["body"]["options"]["num_predict"], 1024)

    def test_ollama_length_termination_is_reported_as_output_exhausted(self) -> None:
        def fake_urlopen(request, timeout):
            return FakeHTTPResponse(
                {
                    "done_reason": "length",
                    "message": {"content": "{\"summary\": \"incomplete\""},
                }
            )

        provider = OllamaLLMProvider(
            LLMRequestConfig(
                base_url="http://ollama.internal:11434",
                model="qwen2.5:1.5b",
                timeout_seconds=60,
            )
        )
        with patch("backend.providers.llm.transport.urlopen", side_effect=fake_urlopen):
            with self.assertRaisesRegex(LLMProviderError, "exhausted its output budget") as raised:
                provider.generate_json(system_prompt="system", user_prompt="transcript")

        self.assertEqual(raised.exception.code, "llm_output_exhausted")

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

        with patch("backend.providers.llm.transport.urlopen", side_effect=fake_urlopen):
            result = provider.generate_json(system_prompt="return json", user_prompt="meeting transcript")

        self.assertEqual(result, {"summary": "done", "items": [1, 2]})
        self.assertEqual(captured["url"], "http://llm.internal/v1/chat/completions")
        self.assertEqual(captured["timeout"], 12)
        self.assertEqual(captured["headers"]["Authorization"], "Bearer secret")
        self.assertEqual(captured["body"]["model"], "private-model")
        self.assertEqual(captured["body"]["response_format"], {"type": "json_object"})
        self.assertEqual(captured["body"]["temperature"], 0)

    def test_openai_compatible_provider_posts_custom_temperature(self) -> None:
        captured = {}

        def fake_urlopen(request, timeout):
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return FakeHTTPResponse(
                {"choices": [{"message": {"content": "{\"summary\":\"done\"}"}}]}
            )

        provider = OpenAICompatibleLLMProvider(
            config=type(
                "Config",
                (),
                {
                    "base_url": "http://llm.internal/v1",
                    "model": "private-model",
                    "api_key": "",
                    "timeout_seconds": 12,
                },
            )()
        )

        with patch("backend.providers.llm.transport.urlopen", side_effect=fake_urlopen):
            provider.generate_json(
                system_prompt="return json",
                user_prompt="hello",
                temperature=0.5,
            )

        self.assertEqual(captured["body"]["temperature"], 0.5)

    def test_openai_compatible_provider_disables_qwen_thinking(self) -> None:
        captured = {}

        def fake_urlopen(request, timeout):
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return FakeHTTPResponse({"choices": [{"finish_reason": "stop", "message": {"content": "{\"ok\":true}"}}]})

        provider = OpenAICompatibleLLMProvider(
            LLMRequestConfig(
                base_url="http://llm.internal/v1",
                model="qwen",
                api_key="",
                timeout_seconds=12,
                reasoning_mode="disabled",
            )
        )
        with patch("backend.providers.llm.transport.urlopen", side_effect=fake_urlopen):
            provider.generate_json(system_prompt="json", user_prompt="hello")

        self.assertEqual(captured["body"]["chat_template_kwargs"], {"enable_thinking": False})

    def test_content_null_at_length_is_output_exhausted(self) -> None:
        provider = OpenAICompatibleLLMProvider(
            LLMRequestConfig(base_url="http://llm.internal/v1", model="qwen", timeout_seconds=12)
        )
        response = FakeHTTPResponse({"choices": [{"finish_reason": "length", "message": {"content": None}}]})
        with patch("backend.providers.llm.transport.urlopen", return_value=response):
            with self.assertRaises(LLMProviderError) as raised:
                provider.generate_json(system_prompt="json", user_prompt="hello")

        self.assertEqual(raised.exception.code, "llm_output_exhausted")

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

        with patch("backend.providers.llm.transport.urlopen", side_effect=flaky_urlopen):
            result = provider.generate_json(system_prompt="return json", user_prompt="meeting transcript")

        self.assertEqual(result, {"summary": "retried"})
        self.assertEqual(calls["count"], 2)

    def test_fallback_provider_uses_secondary_provider_after_primary_failure(self) -> None:
        primary = BrokenProvider()
        fallback = StaticProvider()
        provider = FallbackLLMProvider(primary, fallback)

        self.assertEqual(
            provider.generate_json(system_prompt="system", user_prompt="hello", temperature=0.5),
            {"ok": True, "userPrompt": "hello", "temperature": 0.5},
        )
        self.assertEqual(primary.temperatures, [0.5])
        self.assertEqual(fallback.temperatures, [0.5])
        self.assertEqual(provider.last_provider_name, "static")
        self.assertEqual(provider.last_provider_model, "static-model")
        self.assertTrue(provider.last_fallback_used)
        self.assertEqual(provider.last_primary_error_type, "LLMProviderError")
        self.assertEqual(provider.last_primary_error_message, "primary failed")

    def test_fallback_is_not_started_when_total_budget_is_exhausted(self) -> None:
        primary = BrokenProvider()
        fallback = StaticProvider()
        provider = FallbackLLMProvider(primary, fallback)

        with self.assertRaises(FallbackLLMProviderError) as raised:
            provider.generate_json_with_stage_timeouts(
                system_prompt="system",
                user_prompt="hello",
                temperature=0,
                primary_timeout_seconds=60,
                fallback_timeout_seconds=40,
                total_timeout_seconds=0,
            )

        self.assertEqual(raised.exception.fallback_error.code, "llm_fallback_budget_exhausted")
        self.assertEqual(fallback.temperatures, [])
        self.assertFalse(provider.last_fallback_used)

    def test_fallback_provider_uses_compact_fallback_prompts(self) -> None:
        provider = FallbackLLMProvider(BrokenProvider(), StaticProvider())

        result = provider.generate_json_with_fallback_prompts(
            system_prompt="full system",
            user_prompt="full extraction contract",
            fallback_system_prompt="compact system",
            fallback_user_prompt="compact extraction contract",
        )

        self.assertEqual(result["userPrompt"], "compact extraction contract")

    def test_fallback_provider_exposes_both_failures(self) -> None:
        provider = FallbackLLMProvider(BrokenProvider(), BrokenProvider())

        with self.assertRaises(FallbackLLMProviderError) as raised:
            provider.generate_json(system_prompt="system", user_prompt="transcript")

        self.assertEqual(raised.exception.primary_provider, "broken")
        self.assertEqual(raised.exception.fallback_provider, "broken")

    def test_configured_primary_model_name_ignores_fallback_display_model(self) -> None:
        provider = FallbackLLMProvider(StaticProvider(), BrokenProvider())

        self.assertEqual(get_configured_primary_model_name(provider), "static-model")

    def test_fallback_provider_records_primary_provider_when_primary_succeeds(self) -> None:
        primary = StaticProvider()
        fallback = BrokenProvider()
        provider = FallbackLLMProvider(primary, fallback)

        self.assertEqual(
            provider.generate_json(system_prompt="system", user_prompt="hello"),
            {"ok": True, "userPrompt": "hello", "temperature": 0},
        )
        self.assertEqual(primary.temperatures, [0])
        self.assertEqual(fallback.temperatures, [])
        self.assertEqual(provider.last_provider_name, "static")
        self.assertEqual(provider.last_provider_model, "static-model")
        self.assertFalse(provider.last_fallback_used)
        self.assertIsNone(provider.last_primary_error_message)

    def test_fallback_execution_provenance_is_isolated_per_thread(self) -> None:
        provider = FallbackLLMProvider(ConditionalProvider(), StaticProvider())

        def invoke(prompt: str) -> tuple[str, str, bool, str | None]:
            provider.generate_json(system_prompt="system", user_prompt=prompt)
            return (
                provider.last_provider_name,
                provider.last_provider_model,
                provider.last_fallback_used,
                provider.last_primary_error_message,
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            primary_result, fallback_result = executor.map(invoke, ["primary", "fallback"])

        self.assertEqual(primary_result, ("conditional", "conditional-model", False, None))
        self.assertEqual(fallback_result, ("static", "static-model", True, "conditional primary failed"))

    def test_execution_snapshot_crosses_executor_thread_with_payload(self) -> None:
        provider = FallbackLLMProvider(BrokenProvider(), StaticProvider())

        with ThreadPoolExecutor(max_workers=1) as executor:
            payload, execution = executor.submit(
                generate_json_with_execution,
                provider,
                system_prompt="system",
                user_prompt="fallback",
            ).result()

        self.assertEqual(payload["userPrompt"], "fallback")
        self.assertEqual(execution.provider_name, "static")
        self.assertEqual(execution.model_name, "static-model")
        self.assertTrue(execution.fallback_used)
        self.assertEqual(execution.primary_error_type, "LLMProviderError")
        self.assertEqual(execution.primary_error_message, "primary failed")

    def test_tracker_exposes_fallback_before_local_call_completes(self) -> None:
        started = Event()
        release = Event()
        tracker = LLMExecutionTracker()
        provider = FallbackLLMProvider(
            BrokenProvider(),
            BlockingProvider(started, release),
        )

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                generate_json_with_execution,
                provider,
                system_prompt="system",
                user_prompt="fallback",
                execution_tracker=tracker,
            )
            self.assertTrue(started.wait(timeout=0.5))
            execution = tracker.snapshot()
            self.assertIsNotNone(execution)
            self.assertEqual(execution.provider_name, "blocking")
            self.assertEqual(execution.model_name, "blocking-model")
            self.assertTrue(execution.fallback_used)
            self.assertEqual(execution.primary_error_type, "LLMProviderError")
            release.set()
            future.result(timeout=1)


if __name__ == "__main__":
    unittest.main()

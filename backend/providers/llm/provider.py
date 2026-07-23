import json
import time
import inspect
import logging
from threading import Lock, Semaphore, local
from typing import Any
from backend.configs.settings import Settings, get_settings
from backend.providers.contracts.llm import (
    LLMExecutionSnapshot,
    LLMExecutionTracker,
    LLMProvider,
    LLMProviderError,
    LLMRequestConfig,
)
from backend.providers.llm.transport import parse_json_content, post_json
from backend.providers.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError


logger = logging.getLogger(__name__)
_LLM_BREAKERS: dict[str, CircuitBreaker] = {}
_LLM_BREAKERS_LOCK = Lock()


class OpenAICompatibleLLMProvider:
    provider_name = "openai-compatible"

    def __init__(self, config: LLMRequestConfig) -> None:
        self.config = config
        self.model_name = config.model
        self.last_provider_name = self.provider_name
        self.last_provider_model = self.model_name

    def generate_json(self, *, system_prompt: str, user_prompt: str, temperature: float = 0, timeout_seconds: float | None = None, max_output_tokens: int | None = None, response_schema: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": temperature,
        }
        if getattr(self.config, "reasoning_mode", "disabled") == "disabled":
            # vLLM/Qwen-compatible way to disable hidden thinking so the JSON
            # answer is emitted in message.content within the output budget.
            payload["chat_template_kwargs"] = {"enable_thinking": False}
        if max_output_tokens is not None:
            payload["max_tokens"] = max(1, max_output_tokens)
        response = self._post_json("chat/completions", payload, timeout_seconds=timeout_seconds)
        choice = response.get("choices", [{}])[0]
        self.last_finish_reason = str(choice.get("finish_reason") or "unknown")
        content = choice.get("message", {}).get("content")
        if not isinstance(content, str) or not content.strip():
            finish_reason = self.last_finish_reason
            code = "llm_output_exhausted" if finish_reason == "length" else "llm_empty_content"
            raise LLMProviderError(
                f"OpenAI-compatible response did not include message content (finish_reason={finish_reason}).",
                retryable=finish_reason == "length",
                code=code,
            )
        return parse_json_content(content)

    def _post_json(self, path: str, payload: dict[str, Any], *, timeout_seconds: float | None = None) -> dict[str, Any]:
        return post_json(
            base_url=self.config.base_url,
            path=path,
            payload=payload,
            api_key=self.config.api_key,
            timeout_seconds=min(self.config.timeout_seconds, timeout_seconds) if timeout_seconds is not None else self.config.timeout_seconds,
            max_retries=getattr(self.config, "max_retries", 1),
            retry_backoff_seconds=getattr(self.config, "retry_backoff_seconds", 0.2),
        )


class CustomJSONEndpointLLMProvider:
    provider_name = "custom-json-endpoint"

    def __init__(self, config: LLMRequestConfig) -> None:
        self.config = config
        self.model_name = config.model
        self.last_provider_name = self.provider_name
        self.last_provider_model = self.model_name

    def generate_json(self, *, system_prompt: str, user_prompt: str, temperature: float = 0, timeout_seconds: float | None = None, max_output_tokens: int | None = None, response_schema: dict[str, Any] | None = None) -> dict[str, Any]:
        response = post_json(
            base_url=self.config.base_url,
            path="generate-json",
            payload={
                "model": self.config.model,
                "systemPrompt": system_prompt,
                "userPrompt": user_prompt,
                "responseFormat": "json",
                "temperature": temperature,
                **({"maxOutputTokens": max(1, max_output_tokens)} if max_output_tokens is not None else {}),
            },
            api_key=self.config.api_key,
            timeout_seconds=min(self.config.timeout_seconds, timeout_seconds) if timeout_seconds is not None else self.config.timeout_seconds,
            max_retries=getattr(self.config, "max_retries", 1),
            retry_backoff_seconds=getattr(self.config, "retry_backoff_seconds", 0.2),
        )
        if isinstance(response.get("json"), dict):
            return response["json"]
        if isinstance(response.get("content"), str):
            return parse_json_content(response["content"])
        if isinstance(response.get("result"), dict):
            return response["result"]
        raise LLMProviderError("Custom JSON endpoint response did not include a JSON result.")


class OllamaLLMProvider:
    provider_name = "ollama"

    def __init__(self, config: LLMRequestConfig) -> None:
        self.config = config
        self.model_name = config.model
        self.last_provider_name = self.provider_name
        self.last_provider_model = self.model_name

    def generate_json(self, *, system_prompt: str, user_prompt: str, temperature: float = 0, timeout_seconds: float | None = None, max_output_tokens: int | None = None, response_schema: dict[str, Any] | None = None) -> dict[str, Any]:
        options: dict[str, Any] = {"temperature": temperature}
        if self.config.context_length:
            options["num_ctx"] = self.config.context_length
        output_limit = max_output_tokens if max_output_tokens is not None else getattr(self.config, "max_output_tokens", None)
        if output_limit:
            options["num_predict"] = max(1, output_limit)
        response = post_json(
            base_url=self.config.base_url,
            path="api/chat",
            payload={
                "model": self.config.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "format": response_schema or "json",
                "stream": False,
                "options": options,
            },
            timeout_seconds=min(self.config.timeout_seconds, timeout_seconds) if timeout_seconds is not None else self.config.timeout_seconds,
            max_retries=getattr(self.config, "max_retries", 1),
            retry_backoff_seconds=getattr(self.config, "retry_backoff_seconds", 0.2),
        )
        self.last_finish_reason = str(response.get("done_reason") or "unknown")
        content = response.get("message", {}).get("content")
        if not isinstance(content, str) or not content.strip():
            code = "llm_output_exhausted" if self.last_finish_reason == "length" else "llm_empty_content"
            raise LLMProviderError(
                f"Ollama response did not include message content (done_reason={self.last_finish_reason}).",
                retryable=self.last_finish_reason == "length",
                code=code,
            )
        try:
            return parse_json_content(content)
        except LLMProviderError as exc:
            if self.last_finish_reason == "length":
                raise LLMProviderError(
                    "Ollama response exhausted its output budget before completing JSON.",
                    retryable=True,
                    code="llm_output_exhausted",
                ) from exc
            raise


class FallbackLLMProviderError(LLMProviderError):
    def __init__(
        self,
        *,
        primary: LLMProvider,
        fallback: LLMProvider,
        primary_error: LLMProviderError,
        fallback_error: LLMProviderError,
    ) -> None:
        super().__init__(
            f"Primary and fallback LLM providers failed; fallback error: {fallback_error}",
            retryable=fallback_error.retryable,
        )
        self.primary_provider = primary.provider_name
        self.primary_model = primary.model_name
        self.primary_error = primary_error
        self.fallback_provider = fallback.provider_name
        self.fallback_model = fallback.model_name
        self.fallback_error = fallback_error


class FallbackLLMProvider:
    provider_name = "fallback"

    def __init__(self, primary: LLMProvider, fallback: LLMProvider) -> None:
        self.primary = primary
        self.fallback = fallback
        self.model_name = f"{primary.provider_name}:{primary.model_name}|{fallback.provider_name}:{fallback.model_name}"
        self._execution = local()
        # Ollama commonly exposes one inference slot. Serialize fallback calls
        # before opening the HTTP request so queued windows receive their own
        # complete timeout instead of timing out behind another generation.
        self._fallback_slot = Semaphore(1)
        self.last_provider_name = primary.provider_name
        self.last_provider_model = primary.model_name
        self.last_fallback_used = False
        self.last_primary_error_type: str | None = None
        self.last_primary_error_message: str | None = None

    @property
    def last_provider_name(self) -> str:
        return getattr(self._execution, "provider_name", self.primary.provider_name)

    @last_provider_name.setter
    def last_provider_name(self, value: str) -> None:
        self._execution.provider_name = value

    @property
    def last_provider_model(self) -> str:
        return getattr(self._execution, "provider_model", self.primary.model_name)

    @last_provider_model.setter
    def last_provider_model(self, value: str) -> None:
        self._execution.provider_model = value

    @property
    def last_fallback_used(self) -> bool:
        return bool(getattr(self._execution, "fallback_used", False))

    @last_fallback_used.setter
    def last_fallback_used(self, value: bool) -> None:
        self._execution.fallback_used = bool(value)

    @property
    def last_primary_error_type(self) -> str | None:
        return getattr(self._execution, "primary_error_type", None)

    @last_primary_error_type.setter
    def last_primary_error_type(self, value: str | None) -> None:
        self._execution.primary_error_type = value

    @property
    def last_primary_error_message(self) -> str | None:
        return getattr(self._execution, "primary_error_message", None)

    @last_primary_error_message.setter
    def last_primary_error_message(self, value: str | None) -> None:
        self._execution.primary_error_message = value

    def generate_json(self, *, system_prompt: str, user_prompt: str, temperature: float = 0, timeout_seconds: float | None = None, max_output_tokens: int | None = None, response_schema: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.generate_json_with_fallback_prompts(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            fallback_system_prompt=system_prompt,
            fallback_user_prompt=user_prompt,
            temperature=temperature,
            timeout_seconds=timeout_seconds,
            max_output_tokens=max_output_tokens,
            response_schema=response_schema,
        )

    def generate_json_with_fallback_prompts(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        fallback_system_prompt: str,
        fallback_user_prompt: str,
        temperature: float = 0,
        timeout_seconds: float | None = None,
        max_output_tokens: int | None = None,
        response_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        started = time.monotonic()
        primary_timeout = timeout_seconds
        fallback_timeout = timeout_seconds
        if timeout_seconds is not None:
            fallback_timeout = max(0.1, timeout_seconds - (time.monotonic() - started))
        return self._generate_chain(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            fallback_system_prompt=fallback_system_prompt,
            fallback_user_prompt=fallback_user_prompt,
            temperature=temperature,
            primary_timeout_seconds=primary_timeout,
            fallback_timeout_seconds=fallback_timeout,
            max_output_tokens=max_output_tokens,
            response_schema=response_schema,
        )

    def generate_json_with_stage_timeouts(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        primary_timeout_seconds: float,
        fallback_timeout_seconds: float,
        total_timeout_seconds: float | None = None,
        max_output_tokens: int | None = None,
        response_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Give each provider its explicit synthesis budget without a hidden cap."""
        return self._generate_chain(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            fallback_system_prompt=system_prompt,
            fallback_user_prompt=user_prompt,
            temperature=temperature,
            primary_timeout_seconds=primary_timeout_seconds,
            fallback_timeout_seconds=fallback_timeout_seconds,
            max_output_tokens=max_output_tokens,
            response_schema=response_schema,
            total_timeout_seconds=total_timeout_seconds,
        )

    def _generate_chain(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        fallback_system_prompt: str,
        fallback_user_prompt: str,
        temperature: float,
        primary_timeout_seconds: float | None,
        fallback_timeout_seconds: float | None,
        max_output_tokens: int | None,
        response_schema: dict[str, Any] | None,
        total_timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        chain_started = time.monotonic()
        self.last_fallback_used = False
        self.last_primary_error_type = None
        self.last_primary_error_message = None
        self._publish_execution_snapshot()
        try:
            result = call_with_llm_circuit(
                self.primary,
                stage="synthesis",
                function=lambda: _generate_with_optional_budget(
                    self.primary,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=temperature,
                    timeout_seconds=primary_timeout_seconds,
                    max_output_tokens=max_output_tokens,
                    response_schema=response_schema,
                ),
            )
            self.last_provider_name = getattr(self.primary, "last_provider_name", self.primary.provider_name)
            self.last_provider_model = getattr(self.primary, "last_provider_model", self.primary.model_name)
            return result
        except LLMProviderError as exc:
            effective_fallback_timeout = fallback_timeout_seconds
            if total_timeout_seconds is not None:
                remaining = total_timeout_seconds - (time.monotonic() - chain_started)
                effective_fallback_timeout = min(fallback_timeout_seconds or remaining, remaining)
            if effective_fallback_timeout is not None and effective_fallback_timeout <= 0:
                fallback_exc = LLMProviderError(
                    "No synthesis budget remains for fallback.",
                    retryable=True,
                    code="llm_fallback_budget_exhausted",
                )
                raise FallbackLLMProviderError(
                    primary=self.primary,
                    fallback=self.fallback,
                    primary_error=exc,
                    fallback_error=fallback_exc,
                ) from fallback_exc
            self.last_fallback_used = True
            self.last_primary_error_type = type(exc).__name__
            self.last_primary_error_message = str(exc)
            self.last_provider_name = self.fallback.provider_name
            self.last_provider_model = self.fallback.model_name
            self._publish_execution_snapshot()
            try:
                with self._fallback_slot:
                    result = call_with_llm_circuit(
                        self.fallback,
                        stage="synthesis",
                        function=lambda: _generate_with_optional_budget(
                            self.fallback,
                            system_prompt=fallback_system_prompt,
                            user_prompt=fallback_user_prompt,
                            temperature=temperature,
                            timeout_seconds=effective_fallback_timeout,
                            max_output_tokens=max_output_tokens,
                            response_schema=response_schema,
                        ),
                    )
            except LLMProviderError as fallback_exc:
                raise FallbackLLMProviderError(
                    primary=self.primary,
                    fallback=self.fallback,
                    primary_error=exc,
                    fallback_error=fallback_exc,
                ) from fallback_exc
            self.last_provider_name = getattr(self.fallback, "last_provider_name", self.fallback.provider_name)
            self.last_provider_model = getattr(self.fallback, "last_provider_model", self.fallback.model_name)
            self._publish_execution_snapshot()
            return result

    def _set_execution_tracker(self, tracker: LLMExecutionTracker | None) -> None:
        self._execution.tracker = tracker

    def _publish_execution_snapshot(self) -> None:
        tracker = getattr(self._execution, "tracker", None)
        if isinstance(tracker, LLMExecutionTracker):
            tracker.record(get_execution_snapshot(self))


def _generate_with_optional_budget(
    provider: LLMProvider,
    *,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    timeout_seconds: float | None,
    max_output_tokens: int | None,
    response_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Call legacy-compatible adapters without requiring the new keywords."""
    generate = provider.generate_json
    try:
        parameters = inspect.signature(generate).parameters
    except (TypeError, ValueError):
        parameters = {}
    kwargs: dict[str, Any] = {
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "temperature": temperature,
    }
    if "timeout_seconds" in parameters:
        kwargs["timeout_seconds"] = timeout_seconds
    if "max_output_tokens" in parameters:
        kwargs["max_output_tokens"] = max_output_tokens
    if "response_schema" in parameters:
        kwargs["response_schema"] = response_schema
    return generate(**kwargs)


def call_with_llm_circuit(provider: LLMProvider, *, stage: str, function):
    """Isolate provider health by stage, provider and model."""
    key = f"llm:{stage}:{provider.provider_name}:{provider.model_name}"
    with _LLM_BREAKERS_LOCK:
        breaker = _LLM_BREAKERS.get(key)
        if breaker is None:
            settings = get_settings()
            breaker = CircuitBreaker(
                key,
                failure_threshold=settings.circuit_breaker_failure_threshold,
                recovery_seconds=settings.circuit_breaker_recovery_seconds,
                enabled=settings.circuit_breaker_enabled,
            )
            _LLM_BREAKERS[key] = breaker
    started = time.perf_counter()
    try:
        result = breaker.call(function)
    except CircuitBreakerOpenError as exc:
        logger.warning("llm_call stage=%s provider=%s model=%s error=circuit_open", stage, provider.provider_name, provider.model_name)
        raise LLMProviderError(str(exc), retryable=True, code="llm_circuit_open") from exc
    except Exception as exc:
        logger.warning(
            "llm_call stage=%s provider=%s model=%s latency_ms=%d error=%s",
            stage,
            provider.provider_name,
            provider.model_name,
            round((time.perf_counter() - started) * 1000),
            type(exc).__name__,
        )
        raise
    logger.info(
        "llm_call stage=%s provider=%s model=%s latency_ms=%d finish_reason=%s",
        stage,
        provider.provider_name,
        provider.model_name,
        round((time.perf_counter() - started) * 1000),
        getattr(provider, "last_finish_reason", "unknown"),
    )
    return result


def get_effective_provider_name(provider: LLMProvider) -> str:
    return getattr(provider, "last_provider_name", provider.provider_name)


def get_effective_model_name(provider: LLMProvider) -> str:
    return getattr(provider, "last_provider_model", provider.model_name)


def get_configured_primary_model_name(provider: LLMProvider) -> str:
    primary = getattr(provider, "primary", None)
    if primary is not None:
        return getattr(primary, "model_name", provider.model_name)
    return provider.model_name


def get_execution_snapshot(provider: LLMProvider) -> LLMExecutionSnapshot:
    """Capture provenance in the same thread that executed the provider call."""
    return LLMExecutionSnapshot(
        provider_name=get_effective_provider_name(provider),
        model_name=get_effective_model_name(provider),
        fallback_used=bool(getattr(provider, "last_fallback_used", False)),
        primary_error_type=getattr(provider, "last_primary_error_type", None),
        primary_error_message=getattr(provider, "last_primary_error_message", None),
    )


def generate_json_with_execution(
    provider: LLMProvider,
    *,
    system_prompt: str,
    user_prompt: str,
    temperature: float | None = 0,
    execution_tracker: LLMExecutionTracker | None = None,
) -> tuple[dict[str, Any], LLMExecutionSnapshot]:
    """Return the payload and its request-scoped execution provenance together."""
    tracker = execution_tracker or LLMExecutionTracker()
    bind_tracker = getattr(provider, "_set_execution_tracker", None)
    if callable(bind_tracker):
        bind_tracker(tracker)
    tracker.record(get_execution_snapshot(provider))
    try:
        payload = (
            provider.generate_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
            if temperature is None
            else provider.generate_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=temperature,
            )
        )
        snapshot = get_execution_snapshot(provider)
        tracker.record(snapshot)
        return payload, snapshot
    finally:
        tracker.record(get_execution_snapshot(provider))
        if callable(bind_tracker):
            bind_tracker(None)


def build_llm_provider(settings: Settings) -> LLMProvider:
    primary = _build_primary_provider(settings)
    fallback_name = settings.llm_fallback_provider.strip().lower()
    if primary.provider_name == "ollama" or fallback_name != "ollama":
        return primary
    return FallbackLLMProvider(primary, _build_ollama_provider(settings))


def get_llm_provider() -> LLMProvider:
    return build_llm_provider(get_settings())


def _build_primary_provider(settings: Settings) -> LLMProvider:
    provider_name = settings.llm_provider.strip().lower()
    if provider_name == "ollama":
        return _build_ollama_provider(settings)
    if provider_name in {"api", "endpoint"}:
        return _build_http_provider(settings)
    raise LLMProviderError(f"Unsupported LLM_PROVIDER: {settings.llm_provider}")


def _build_http_provider(settings: Settings) -> LLMProvider:
    model = settings.llm_model or "default"
    config = LLMRequestConfig(
        base_url=settings.llm_api_base_url,
        model=model,
        api_key=settings.llm_api_key,
        timeout_seconds=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
        retry_backoff_seconds=settings.llm_retry_backoff_seconds,
        reasoning_mode=settings.llm_reasoning_mode,
    )
    compatibility = settings.llm_endpoint_compatibility.strip().lower()
    if compatibility == "openai":
        return OpenAICompatibleLLMProvider(config)
    if compatibility in {"custom", "custom-json"}:
        return CustomJSONEndpointLLMProvider(config)
    raise LLMProviderError(f"Unsupported LLM_ENDPOINT_COMPATIBILITY: {settings.llm_endpoint_compatibility}")


def _build_ollama_provider(settings: Settings) -> OllamaLLMProvider:
    return OllamaLLMProvider(
        LLMRequestConfig(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            timeout_seconds=settings.ollama_llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
            retry_backoff_seconds=settings.llm_retry_backoff_seconds,
            context_length=settings.ollama_context_length,
            max_output_tokens=settings.ollama_max_output_tokens,
            reasoning_mode=settings.llm_reasoning_mode,
        )
    )

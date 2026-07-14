import json
from typing import Any
from backend.configs.settings import Settings, get_settings
from backend.providers.contracts.llm import LLMProvider, LLMProviderError, LLMRequestConfig
from backend.providers.llm.transport import parse_json_content, post_json


class OpenAICompatibleLLMProvider:
    provider_name = "openai-compatible"

    def __init__(self, config: LLMRequestConfig) -> None:
        self.config = config
        self.model_name = config.model
        self.last_provider_name = self.provider_name
        self.last_provider_model = self.model_name

    def generate_json(self, *, system_prompt: str, user_prompt: str, temperature: float = 0) -> dict[str, Any]:
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": temperature,
        }
        response = self._post_json("chat/completions", payload)
        content = (
            response.get("choices", [{}])[0]
            .get("message", {})
            .get("content")
        )
        if not isinstance(content, str) or not content.strip():
            raise LLMProviderError("OpenAI-compatible response did not include message content.")
        return parse_json_content(content)

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return post_json(
            base_url=self.config.base_url,
            path=path,
            payload=payload,
            api_key=self.config.api_key,
            timeout_seconds=self.config.timeout_seconds,
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

    def generate_json(self, *, system_prompt: str, user_prompt: str, temperature: float = 0) -> dict[str, Any]:
        response = post_json(
            base_url=self.config.base_url,
            path="generate-json",
            payload={
                "model": self.config.model,
                "systemPrompt": system_prompt,
                "userPrompt": user_prompt,
                "responseFormat": "json",
                "temperature": temperature,
            },
            api_key=self.config.api_key,
            timeout_seconds=self.config.timeout_seconds,
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

    def generate_json(self, *, system_prompt: str, user_prompt: str, temperature: float = 0) -> dict[str, Any]:
        options: dict[str, Any] = {"temperature": temperature}
        if self.config.context_length:
            options["num_ctx"] = self.config.context_length
        response = post_json(
            base_url=self.config.base_url,
            path="api/chat",
            payload={
                "model": self.config.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "format": "json",
                "stream": False,
                "options": options,
            },
            timeout_seconds=self.config.timeout_seconds,
            max_retries=getattr(self.config, "max_retries", 1),
            retry_backoff_seconds=getattr(self.config, "retry_backoff_seconds", 0.2),
        )
        content = response.get("message", {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise LLMProviderError("Ollama response did not include message content.")
        return parse_json_content(content)

class FallbackLLMProvider:
    provider_name = "fallback"

    def __init__(self, primary: LLMProvider, fallback: LLMProvider) -> None:
        self.primary = primary
        self.fallback = fallback
        self.model_name = f"{primary.provider_name}:{primary.model_name}|{fallback.provider_name}:{fallback.model_name}"
        self.last_provider_name = primary.provider_name
        self.last_provider_model = primary.model_name
        self.last_fallback_used = False
        self.last_primary_error_type: str | None = None
        self.last_primary_error_message: str | None = None

    def generate_json(self, *, system_prompt: str, user_prompt: str, temperature: float = 0) -> dict[str, Any]:
        self.last_fallback_used = False
        self.last_primary_error_type = None
        self.last_primary_error_message = None
        try:
            result = self.primary.generate_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=temperature,
            )
            self.last_provider_name = getattr(self.primary, "last_provider_name", self.primary.provider_name)
            self.last_provider_model = getattr(self.primary, "last_provider_model", self.primary.model_name)
            return result
        except LLMProviderError as exc:
            self.last_fallback_used = True
            self.last_primary_error_type = type(exc).__name__
            self.last_primary_error_message = str(exc)
            result = self.fallback.generate_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=temperature,
            )
            self.last_provider_name = getattr(self.fallback, "last_provider_name", self.fallback.provider_name)
            self.last_provider_model = getattr(self.fallback, "last_provider_model", self.fallback.model_name)
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
        )
    )

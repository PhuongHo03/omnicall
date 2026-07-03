import json
import time
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from backend.configs.settings import Settings, get_settings


class LLMProviderError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class LLMProvider(Protocol):
    provider_name: str
    model_name: str

    def generate_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        ...

    def generate_stream_json(self, *, system_prompt: str, user_prompt: str, on_token: Any = None) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class LLMRequestConfig:
    base_url: str
    model: str
    api_key: str = ""
    timeout_seconds: float = 60.0
    max_retries: int = 1
    retry_backoff_seconds: float = 0.2
    context_length: int | None = None


class OpenAICompatibleLLMProvider:
    provider_name = "openai-compatible"

    def __init__(self, config: LLMRequestConfig) -> None:
        self.config = config
        self.model_name = config.model
        self.last_provider_name = self.provider_name
        self.last_provider_model = self.model_name

    def generate_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
        }
        response = self._post_json("chat/completions", payload)
        content = (
            response.get("choices", [{}])[0]
            .get("message", {})
            .get("content")
        )
        if not isinstance(content, str) or not content.strip():
            raise LLMProviderError("OpenAI-compatible response did not include message content.")
        return _parse_json_content(content)

    def generate_stream_json(self, *, system_prompt: str, user_prompt: str, on_token: Any = None) -> dict[str, Any]:
        if on_token is None:
            return self.generate_json(system_prompt=system_prompt, user_prompt=user_prompt)
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
            "stream": True,
        }
        url = urljoin(_ensure_trailing_slash(self.config.base_url), "chat/completions")
        body = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        request = Request(url, data=body, headers=headers, method="POST")
        collected = ""
        answer_buffer = ""
        answer_key = '"answer"'
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                for raw_line in response:
                    line = raw_line.decode("utf-8").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[len("data:"):].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if not content:
                        continue
                    collected += content
                    answer_chunk = _extract_answer_stream(collected, answer_key)
                    if len(answer_chunk) > len(answer_buffer):
                        new_text = answer_chunk[len(answer_buffer):]
                        answer_buffer = answer_chunk
                        if new_text:
                            on_token(new_text)
        except (HTTPError, URLError, TimeoutError) as exc:
            raise LLMProviderError(
                f"OpenAI-compatible streaming request failed: {exc}", retryable=True
            ) from exc
        if not collected.strip():
            raise LLMProviderError("OpenAI-compatible streaming response was empty.")
        return _parse_json_content(collected)

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return _post_json(
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

    def generate_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        response = _post_json(
            base_url=self.config.base_url,
            path="generate-json",
            payload={
                "model": self.config.model,
                "systemPrompt": system_prompt,
                "userPrompt": user_prompt,
                "responseFormat": "json",
            },
            api_key=self.config.api_key,
            timeout_seconds=self.config.timeout_seconds,
            max_retries=getattr(self.config, "max_retries", 1),
            retry_backoff_seconds=getattr(self.config, "retry_backoff_seconds", 0.2),
        )
        if isinstance(response.get("json"), dict):
            return response["json"]
        if isinstance(response.get("content"), str):
            return _parse_json_content(response["content"])
        if isinstance(response.get("result"), dict):
            return response["result"]
        raise LLMProviderError("Custom JSON endpoint response did not include a JSON result.")

    def generate_stream_json(self, *, system_prompt: str, user_prompt: str, on_token: Any = None) -> dict[str, Any]:
        if on_token is None:
            return self.generate_json(system_prompt=system_prompt, user_prompt=user_prompt)
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
            "stream": True,
        }
        url = urljoin(_ensure_trailing_slash(self.config.base_url), "chat/completions")
        body = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        request = Request(url, data=body, headers=headers, method="POST")
        collected = ""
        answer_buffer = ""
        answer_key = '"answer"'
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                for raw_line in response:
                    line = raw_line.decode("utf-8").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[len("data:"):].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if not content:
                        continue
                    collected += content
                    answer_chunk = _extract_answer_stream(collected, answer_key)
                    if len(answer_chunk) > len(answer_buffer):
                        new_text = answer_chunk[len(answer_buffer):]
                        answer_buffer = answer_chunk
                        if new_text:
                            on_token(new_text)
        except (HTTPError, URLError, TimeoutError) as exc:
            raise LLMProviderError(
                f"OpenAI-compatible streaming request failed: {exc}", retryable=True
            ) from exc
        if not collected.strip():
            raise LLMProviderError("OpenAI-compatible streaming response was empty.")
        return _parse_json_content(collected)


class OllamaLLMProvider:
    provider_name = "ollama"

    def __init__(self, config: LLMRequestConfig) -> None:
        self.config = config
        self.model_name = config.model
        self.last_provider_name = self.provider_name
        self.last_provider_model = self.model_name

    def generate_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        options: dict[str, Any] = {"temperature": 0}
        if self.config.context_length:
            options["num_ctx"] = self.config.context_length
        response = _post_json(
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
        return _parse_json_content(content)

    def generate_stream_json(self, *, system_prompt: str, user_prompt: str, on_token: Any = None) -> dict[str, Any]:
        options: dict[str, Any] = {"temperature": 0}
        if self.config.context_length:
            options["num_ctx"] = self.config.context_length
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "format": "json",
            "stream": True,
            "options": options,
        }
        url = urljoin(_ensure_trailing_slash(self.config.base_url), "api/chat")
        body = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        request = Request(url, data=body, headers=headers, method="POST")
        collected = ""
        answer_buffer = ""
        in_answer = False
        answer_key = '"answer"'
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                for raw_line in response:
                    line = raw_line.decode("utf-8").strip()
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    token = chunk.get("message", {}).get("content", "")
                    if not token:
                        continue
                    collected += token
                    if on_token is not None:
                        answer_chunk = _extract_answer_stream(collected, answer_key)
                        if len(answer_chunk) > len(answer_buffer):
                            new_text = answer_chunk[len(answer_buffer):]
                            answer_buffer = answer_chunk
                            if new_text:
                                on_token(new_text)
        except (HTTPError, URLError, TimeoutError) as exc:
            raise LLMProviderError(f"Ollama streaming request failed: {exc}", retryable=True) from exc
        if not collected.strip():
            raise LLMProviderError("Ollama streaming response was empty.")
        return _parse_json_content(collected)


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

    def generate_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        self.last_fallback_used = False
        self.last_primary_error_type = None
        self.last_primary_error_message = None
        try:
            result = self.primary.generate_json(system_prompt=system_prompt, user_prompt=user_prompt)
            self.last_provider_name = getattr(self.primary, "last_provider_name", self.primary.provider_name)
            self.last_provider_model = getattr(self.primary, "last_provider_model", self.primary.model_name)
            return result
        except LLMProviderError as exc:
            self.last_fallback_used = True
            self.last_primary_error_type = type(exc).__name__
            self.last_primary_error_message = str(exc)
            result = self.fallback.generate_json(system_prompt=system_prompt, user_prompt=user_prompt)
            self.last_provider_name = getattr(self.fallback, "last_provider_name", self.fallback.provider_name)
            self.last_provider_model = getattr(self.fallback, "last_provider_model", self.fallback.model_name)
            return result

    def generate_stream_json(self, *, system_prompt: str, user_prompt: str, on_token: Any = None) -> dict[str, Any]:
        self.last_fallback_used = False
        self.last_primary_error_type = None
        self.last_primary_error_message = None
        try:
            result = self.primary.generate_stream_json(system_prompt=system_prompt, user_prompt=user_prompt, on_token=on_token)
            self.last_provider_name = getattr(self.primary, "last_provider_name", self.primary.provider_name)
            self.last_provider_model = getattr(self.primary, "last_provider_model", self.primary.model_name)
            return result
        except LLMProviderError as exc:
            self.last_fallback_used = True
            self.last_primary_error_type = type(exc).__name__
            self.last_primary_error_message = str(exc)
            result = self.fallback.generate_stream_json(system_prompt=system_prompt, user_prompt=user_prompt, on_token=on_token)
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


def _post_json(
    *,
    base_url: str,
    path: str,
    payload: dict[str, Any],
    timeout_seconds: float,
    max_retries: int,
    retry_backoff_seconds: float,
    api_key: str = "",
) -> dict[str, Any]:
    url = urljoin(_ensure_trailing_slash(base_url), path)
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = Request(url, data=body, headers=headers, method="POST")
    attempts = max(1, max_retries + 1)
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            retryable = exc.code >= 500 or exc.code == 429
            last_error = exc
            if not retryable or attempt >= attempts:
                raise LLMProviderError(f"LLM provider request failed: HTTP {exc.code}", retryable=retryable) from exc
        except (URLError, TimeoutError) as exc:
            last_error = exc
            if attempt >= attempts:
                raise LLMProviderError(f"LLM provider request failed: {exc}", retryable=True) from exc
        except json.JSONDecodeError as exc:
            raise LLMProviderError("LLM provider response was not valid JSON.", retryable=False) from exc
        time.sleep(retry_backoff_seconds * attempt)
    raise LLMProviderError(f"LLM provider request failed: {last_error}", retryable=True)


def _parse_json_content(content: str) -> dict[str, Any]:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise LLMProviderError("LLM provider response was not valid JSON.", retryable=False) from exc
    if not isinstance(parsed, dict):
        raise LLMProviderError("LLM provider response JSON must be an object.", retryable=False)
    return parsed


def _ensure_trailing_slash(value: str) -> str:
    return value if value.endswith("/") else f"{value}/"


def _extract_answer_stream(collected: str, answer_key: str) -> str:
    idx = collected.find(answer_key)
    if idx < 0:
        return ""
    rest = collected[idx + len(answer_key):]
    rest = rest.lstrip()
    if rest.startswith(':'):
        rest = rest[1:].lstrip()
    if not rest.startswith('"'):
        return ""
    rest = rest[1:]
    result = []
    i = 0
    while i < len(rest):
        ch = rest[i]
        if ch == '"':
            break
        if ch == '\\' and i + 1 < len(rest):
            next_ch = rest[i + 1]
            if next_ch == '"':
                result.append('"')
            elif next_ch == '\\':
                result.append('\\')
            elif next_ch == 'n':
                result.append('\n')
            elif next_ch == 't':
                result.append('\t')
            else:
                result.append(next_ch)
            i += 2
            continue
        result.append(ch)
        i += 1
    return "".join(result)


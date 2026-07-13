"""HTTP and JSON transport helpers shared by LLM adapters."""

import json
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from backend.providers.contracts.llm import LLMProviderError


def post_json(*, base_url: str, path: str, payload: dict[str, Any], timeout_seconds: float, max_retries: int, retry_backoff_seconds: float, api_key: str = "") -> dict[str, Any]:
    url = urljoin(ensure_trailing_slash(base_url), path)
    request = Request(url, data=json.dumps(payload).encode("utf-8"), headers=_headers(api_key), method="POST")
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


def parse_json_content(content: str) -> dict[str, Any]:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise LLMProviderError("LLM provider response was not valid JSON.", retryable=False) from exc
    if not isinstance(parsed, dict):
        raise LLMProviderError("LLM provider response JSON must be an object.", retryable=False)
    return parsed


def ensure_trailing_slash(value: str) -> str:
    return value if value.endswith("/") else f"{value}/"


def extract_answer_stream(collected: str, answer_key: str) -> str:
    idx = collected.find(answer_key)
    if idx < 0:
        return ""
    rest = collected[idx + len(answer_key):].lstrip()
    if rest.startswith(":"):
        rest = rest[1:].lstrip()
    if not rest.startswith('"'):
        return ""
    rest = rest[1:]
    result: list[str] = []
    i = 0
    while i < len(rest):
        ch = rest[i]
        if ch == '"':
            break
        if ch == "\\" and i + 1 < len(rest):
            next_ch = rest[i + 1]
            result.append({"\"": '"', "\\": "\\", "n": "\n", "t": "\t"}.get(next_ch, next_ch))
            i += 2
            continue
        result.append(ch)
        i += 1
    return "".join(result)


def _headers(api_key: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers

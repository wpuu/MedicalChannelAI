from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Protocol


DEFAULT_BASE_URL = "https://apihub.agnes-ai.com/v1"
DEFAULT_MODEL = "agnes-2.5-flash"
OFFICIAL_BASE_HOSTS = {
    "apihub.agnes-ai.com",
    "apihub.agnes-ai.cn",
    "api.agnes-ai.cn",
}
MAX_RESPONSE_BYTES = 1024 * 1024

SYSTEM_PROMPT = """You are the constrained decision component of MedicalChannelAI.
All procurement facts in the user payload were locked outside the model.
Return exactly one JSON object and no markdown or free-text wrapper.
Choose action_type, reason_codes, and risk_codes only from the supplied allowlists.
Reference only supplied grounded fact_ids and allowed confirmed profile paths.
Do not create, infer, complete, correct, or guess procurement facts, dates, budgets, brands, suppliers, hospital relationships, project stages, or attachment contents.
If evidence is insufficient for a strong action, choose a conservative allowed action such as MONITOR or NO_ACTION and cite only supplied evidence."""


class AgnesTransport(Protocol):
    def __call__(self, request: urllib.request.Request, timeout: float) -> tuple[int, bytes]: ...


@dataclass(frozen=True)
class AgnesClientError(RuntimeError):
    error_class: str
    message: str
    retryable: bool
    status_code: int | None = None

    def __str__(self) -> str:
        return self.message


def validate_base_url(base_url: str) -> str:
    value = (base_url or "").strip().rstrip("/")
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme != "https":
        raise ValueError("Agnes base_url must use https")
    if (parsed.hostname or "").lower() not in OFFICIAL_BASE_HOSTS:
        raise ValueError("Agnes base_url host is not an allowlisted official endpoint")
    if parsed.port not in (None, 443):
        raise ValueError("Agnes base_url cannot use a custom port")
    if parsed.path != "/v1" or parsed.query or parsed.fragment:
        raise ValueError("Agnes base_url must be an exact official /v1 endpoint")
    return value


def _default_transport(request: urllib.request.Request, timeout: float) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                raise AgnesClientError("RESPONSE_TOO_LARGE", "Agnes response exceeded byte limit", False)
            return int(response.status), body
    except urllib.error.HTTPError as exc:
        # Do not include response bodies: they may contain provider/account details.
        status = int(exc.code)
        if status == 429:
            raise AgnesClientError("HTTP_429", "Agnes rate limit response", True, status) from exc
        if 500 <= status <= 599:
            raise AgnesClientError("HTTP_5XX", f"Agnes server error HTTP {status}", True, status) from exc
        if status == 408:
            raise AgnesClientError("HTTP_408", "Agnes request timeout response", True, status) from exc
        raise AgnesClientError("HTTP_4XX", f"Agnes request rejected HTTP {status}", False, status) from exc
    except urllib.error.URLError as exc:
        raise AgnesClientError("NETWORK_ERROR", f"Agnes network request failed: {type(exc.reason).__name__}", True) from exc


def _output_prompt(model_input: dict[str, Any]) -> str:
    payload = {
        "locked_model_input": model_input,
        "required_output": {
            "schema_version": "0.1",
            "opportunity_id": model_input.get("opportunity_id"),
            "action_type": "<one allowed_action_type>",
            "reason_codes": ["<one or more allowed_reason_codes>"],
            "risk_codes": ["<zero or more allowed_risk_codes>"],
            "supporting_fact_ids": ["<one or more supplied grounded fact_ids>"],
            "supporting_profile_paths": ["<zero or more allowed confirmed profile paths>"],
            "requires_human_confirmation": True,
        },
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class AgnesChatClient:
    """Small deployment adapter for the official Agnes OpenAI-compatible gateway.

    Route selection is explicit. The client never rotates an API key to another
    regional endpoint after auth/quota errors. API keys are constructor-only and are
    never serialized into repository configuration or returned from this object.
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout_seconds: float = 60.0,
        transport: AgnesTransport | None = None,
    ) -> None:
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("Agnes api_key is required")
        if model != DEFAULT_MODEL:
            raise ValueError("Today Actions v0.1 only permits agnes-2.5-flash")
        if timeout_seconds <= 0 or timeout_seconds > 180:
            raise ValueError("timeout_seconds must be within 0..180")
        self._api_key = api_key
        self.base_url = validate_base_url(base_url)
        self.model = model
        self.timeout_seconds = float(timeout_seconds)
        self._transport = transport or _default_transport

    def build_request(self, model_input: dict[str, Any]) -> urllib.request.Request:
        if not isinstance(model_input, dict) or model_input.get("schema_version") != "0.1":
            raise ValueError("locked model_input schema_version must be 0.1")
        body = json.dumps(
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": _output_prompt(model_input)},
                ],
                "temperature": 0,
                "max_tokens": 600,
                "stream": False,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        return urllib.request.Request(
            self.base_url + "/chat/completions",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "MedicalChannelAI-TodayActions/0.1",
            },
        )

    def __call__(self, model_input: dict[str, Any]) -> dict[str, Any]:
        request = self.build_request(model_input)
        try:
            status, body = self._transport(request, self.timeout_seconds)
        except AgnesClientError:
            raise
        except Exception as exc:
            raise AgnesClientError("NETWORK_ERROR", f"Agnes transport failed: {type(exc).__name__}", True) from exc
        if status != 200:
            if status == 429:
                raise AgnesClientError("HTTP_429", "Agnes rate limit response", True, status)
            if 500 <= status <= 599:
                raise AgnesClientError("HTTP_5XX", f"Agnes server error HTTP {status}", True, status)
            if status == 408:
                raise AgnesClientError("HTTP_408", "Agnes request timeout response", True, status)
            raise AgnesClientError("HTTP_4XX", f"Agnes request rejected HTTP {status}", False, status)
        if len(body) > MAX_RESPONSE_BYTES:
            raise AgnesClientError("RESPONSE_TOO_LARGE", "Agnes response exceeded byte limit", False)
        try:
            envelope = json.loads(body.decode("utf-8"))
            content = envelope["choices"][0]["message"]["content"]
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise AgnesClientError("RESPONSE_INVALID", "Agnes response envelope is invalid", False) from exc
        if not isinstance(content, str):
            raise AgnesClientError("RESPONSE_INVALID", "Agnes response content is not text", False)
        value = content.strip()
        if value.startswith("```"):
            # A fenced response violates the prompt contract; do not silently massage it
            # into trusted JSON in the production worker.
            raise AgnesClientError("MODEL_JSON_INVALID", "Agnes returned a fenced/non-exact JSON response", False)
        try:
            output = json.loads(value)
        except json.JSONDecodeError as exc:
            raise AgnesClientError("MODEL_JSON_INVALID", "Agnes model content is not exact JSON", False) from exc
        if not isinstance(output, dict):
            raise AgnesClientError("MODEL_JSON_INVALID", "Agnes model content must be one JSON object", False)
        return output

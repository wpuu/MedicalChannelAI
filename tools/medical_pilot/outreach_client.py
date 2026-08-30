from __future__ import annotations

import json
import urllib.request
from typing import Any

from .agnes_client import (
    AgnesClientError,
    AgnesTransport,
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    MAX_RESPONSE_BYTES,
    _default_transport,
    validate_base_url,
)


OUTREACH_SYSTEM_PROMPT = """You are the constrained outreach-strategy selector of MedicalChannelAI.
The procurement facts and customer-private context in the user payload are locked outside the model.
Return exactly one JSON object and no markdown or free-text wrapper.
Do not write customer-facing prose.
Choose strategy_code, question_codes, positioning_code only from supplied allowlists.
Reference only supplied grounded fact_ids and allowed confirmed profile paths.
Do not create, infer, complete, correct or guess procurement facts, dates, budgets, brands, suppliers, hospital relationships, stages, contacts or attachment contents.
The final Chinese outreach wording is rendered outside the model from validated codes and locked inputs."""


def _prompt(model_input: dict[str, Any]) -> str:
    payload = {
        "locked_outreach_input": model_input,
        "required_output": {
            "schema_version": "0.1",
            "opportunity_id": model_input.get("opportunity_id"),
            "strategy_code": "<one allowed_strategy_code>",
            "question_codes": ["<1 to 3 allowed_question_codes>"],
            "positioning_code": "<one allowed_positioning_code>",
            "supporting_fact_ids": ["<supplied grounded fact_ids including buyer_name and project_name>"],
            "supporting_profile_paths": ["<zero or more allowed_profile_paths required by positioning>"],
        },
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class AgnesOutreachClient:
    """Official Agnes JSON-only adapter for outreach strategy selection.

    API key stays in server memory only. This client never serializes provider or key
    data into browser/public responses.
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
            raise ValueError("outreach v0.1 only permits agnes-2.5-flash")
        if timeout_seconds <= 0 or timeout_seconds > 180:
            raise ValueError("timeout_seconds must be within 0..180")
        self._api_key = api_key
        self.base_url = validate_base_url(base_url)
        self.model = model
        self.timeout_seconds = float(timeout_seconds)
        self._transport = transport or _default_transport

    def build_request(self, model_input: dict[str, Any]) -> urllib.request.Request:
        if not isinstance(model_input, dict) or model_input.get("task_type") != "GROUNDED_OUTREACH_STRATEGY":
            raise ValueError("locked outreach model_input task_type is invalid")
        body = json.dumps(
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": OUTREACH_SYSTEM_PROMPT},
                    {"role": "user", "content": _prompt(model_input)},
                ],
                "temperature": 0,
                "max_tokens": 400,
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
                "User-Agent": "MedicalChannelAI-Outreach/0.1",
            },
        )

    def __call__(self, model_input: dict[str, Any]) -> dict[str, Any]:
        request = self.build_request(model_input)
        try:
            status, body = self._transport(request, self.timeout_seconds)
        except AgnesClientError:
            raise
        except Exception as exc:
            raise AgnesClientError("NETWORK_ERROR", f"Agnes outreach transport failed: {type(exc).__name__}", True) from exc
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
            raise AgnesClientError("RESPONSE_INVALID", "Agnes outreach response envelope is invalid", False) from exc
        if not isinstance(content, str):
            raise AgnesClientError("RESPONSE_INVALID", "Agnes outreach response content is not text", False)
        value = content.strip()
        if value.startswith("```"):
            raise AgnesClientError("MODEL_JSON_INVALID", "Agnes returned fenced/non-exact outreach JSON", False)
        try:
            output = json.loads(value)
        except json.JSONDecodeError as exc:
            raise AgnesClientError("MODEL_JSON_INVALID", "Agnes outreach content is not exact JSON", False) from exc
        if not isinstance(output, dict):
            raise AgnesClientError("MODEL_JSON_INVALID", "Agnes outreach content must be one JSON object", False)
        return output

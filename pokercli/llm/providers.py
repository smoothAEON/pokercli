from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import httpx

from pokercli import __version__
from pokercli.config import APP_DISPLAY_NAME, APP_REPOSITORY_URL


APP_USER_AGENT = f"{APP_DISPLAY_NAME}/{__version__}"


class LLMProviderError(RuntimeError):
    """Raised when an LLM provider request fails."""

    def __init__(
        self,
        message: str,
        *,
        provider_request: "ProviderRequestDebug | None" = None,
        provider_response: "ProviderResponseDebug | None" = None,
        latency_ms: int | None = None,
    ) -> None:
        super().__init__(message)
        self.provider_request = provider_request
        self.provider_response = provider_response
        self.latency_ms = latency_ms


@dataclass(slots=True)
class ProviderRequestDebug:
    url: str
    body: dict[str, Any]
    headers: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"url": self.url, "headers": self.headers, "body": self.body}


@dataclass(slots=True)
class ProviderResponseDebug:
    status_code: int | None
    body: Any

    def to_dict(self) -> dict[str, Any]:
        return {"status_code": self.status_code, "body": self.body}


@dataclass(slots=True)
class ProviderProfile:
    name: str
    provider: str
    model: str
    api_key_env: str
    base_url: str | None = None
    timeout_s: float = 30.0
    temperature: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "provider": self.provider,
            "model": self.model,
            "api_key_env": self.api_key_env,
            "base_url": self.base_url,
            "timeout_s": self.timeout_s,
            "temperature": self.temperature,
        }


@dataclass(slots=True)
class LLMTurnRequest:
    system_prompt: str
    user_prompt: str
    response_schema: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "system_prompt": self.system_prompt,
            "user_prompt": self.user_prompt,
            "response_schema": self.response_schema,
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class LLMTurnResponse:
    provider: str
    model: str
    content: str
    raw_payload: Any
    latency_ms: int
    provider_request: ProviderRequestDebug | None = None
    provider_response: ProviderResponseDebug | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "content": self.content,
            "raw_payload": self.raw_payload,
            "latency_ms": self.latency_ms,
            "provider_request": self.provider_request.to_dict() if self.provider_request is not None else None,
            "provider_response": self.provider_response.to_dict() if self.provider_response is not None else None,
        }


class ProviderAdapter(ABC):
    def __init__(self, profile: ProviderProfile, api_key: str) -> None:
        self.profile = profile
        self.api_key = api_key

    @abstractmethod
    def complete_turn(self, request: LLMTurnRequest) -> LLMTurnResponse:
        """Return a normalized text completion for a seat decision."""


class _ChatCompletionsProvider(ProviderAdapter):
    provider_name = ""
    default_base_url = ""
    extra_headers: dict[str, str] = {}
    require_base_url = False

    def _resolved_base_url(self) -> str:
        if self.profile.base_url:
            return self.profile.base_url
        if self.require_base_url:
            raise LLMProviderError(f"{self.profile.provider} providers require base_url")
        return self.default_base_url

    def complete_turn(self, request: LLMTurnRequest) -> LLMTurnResponse:
        url = self._resolved_base_url().rstrip("/") + "/chat/completions"
        payload = {
            "model": self.profile.model,
            "temperature": self.profile.temperature,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
            "response_format": {"type": "json_object"},
        }
        return _post_json(
            provider_name=self.provider_name,
            model=self.profile.model,
            url=url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                **self.extra_headers,
            },
            payload=payload,
            timeout=self.profile.timeout_s,
            content_getter=lambda body: body["choices"][0]["message"]["content"],
        )


class OpenAIProvider(_ChatCompletionsProvider):
    provider_name = "openai"
    default_base_url = "https://api.openai.com/v1"


class OpenAICompatibleProvider(_ChatCompletionsProvider):
    provider_name = "openai-compatible"
    require_base_url = True


class OpenRouterProvider(_ChatCompletionsProvider):
    provider_name = "openrouter"
    default_base_url = "https://openrouter.ai/api/v1"
    extra_headers = {
        "HTTP-Referer": APP_REPOSITORY_URL,
        "X-OpenRouter-Title": APP_DISPLAY_NAME,
    }


class NVIDIAProvider(_ChatCompletionsProvider):
    provider_name = "nvidia"
    default_base_url = "https://integrate.api.nvidia.com/v1"


class AnthropicProvider(ProviderAdapter):
    def complete_turn(self, request: LLMTurnRequest) -> LLMTurnResponse:
        url = (self.profile.base_url or "https://api.anthropic.com").rstrip("/") + "/v1/messages"
        payload = {
            "model": self.profile.model,
            "max_tokens": 512,
            "temperature": self.profile.temperature,
            "system": request.system_prompt,
            "messages": [{"role": "user", "content": request.user_prompt}],
        }
        return _post_json(
            provider_name="anthropic",
            model=self.profile.model,
            url=url,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
            payload=payload,
            timeout=self.profile.timeout_s,
            content_getter=lambda body: "".join(
                block.get("text", "") for block in body.get("content", []) if block.get("type") == "text"
            ),
        )


def _post_json(
    provider_name: str,
    model: str,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: float,
    content_getter,
) -> LLMTurnResponse:
    started = time.perf_counter()
    request_headers = {
        "Content-Type": "application/json",
        "User-Agent": APP_USER_AGENT,
        **headers,
    }
    request_debug = ProviderRequestDebug(url=url, headers=_redact_request_headers(request_headers), body=payload)
    response: httpx.Response | None = None
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(url, headers=request_headers, json=payload)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        error_response = exc.response if getattr(exc, "response", None) is not None else response
        raise LLMProviderError(
            str(exc),
            provider_request=request_debug,
            provider_response=_provider_response_debug(error_response, fallback_body=str(exc)),
            latency_ms=latency_ms,
        ) from exc
    latency_ms = int((time.perf_counter() - started) * 1000)
    try:
        body = response.json()
    except ValueError as exc:
        raise LLMProviderError(
            "Provider returned invalid JSON.",
            provider_request=request_debug,
            provider_response=ProviderResponseDebug(status_code=response.status_code, body=response.text or None),
            latency_ms=latency_ms,
        ) from exc
    response_debug = ProviderResponseDebug(status_code=response.status_code, body=body)
    try:
        content = content_getter(body)
    except Exception as exc:  # pragma: no cover - defensive normalization
        raise LLMProviderError(
            f"Unexpected provider response shape: {json.dumps(body)}",
            provider_request=request_debug,
            provider_response=response_debug,
            latency_ms=latency_ms,
        ) from exc
    if not content:
        raise LLMProviderError(
            "Provider returned empty/null content (possible refusal or tool call).",
            provider_request=request_debug,
            provider_response=response_debug,
            latency_ms=latency_ms,
        )
    return LLMTurnResponse(
        provider=provider_name,
        model=model,
        content=content,
        raw_payload=body,
        latency_ms=latency_ms,
        provider_request=request_debug,
        provider_response=response_debug,
    )


def _provider_response_debug(response: httpx.Response | None, *, fallback_body: Any) -> ProviderResponseDebug:
    if response is None:
        return ProviderResponseDebug(status_code=None, body=fallback_body)
    try:
        body = response.json()
    except ValueError:
        body = response.text or fallback_body
    return ProviderResponseDebug(status_code=response.status_code, body=body)


def _redact_request_headers(headers: dict[str, str]) -> dict[str, str]:
    return {
        key: value
        for key, value in headers.items()
        if key.lower() not in {"authorization", "x-api-key"}
    }


def provider_from_profile(profile: ProviderProfile, api_key: str) -> ProviderAdapter:
    provider = profile.provider.lower()
    if provider == "openai":
        return OpenAIProvider(profile, api_key)
    if provider == "anthropic":
        return AnthropicProvider(profile, api_key)
    if provider == "openrouter":
        return OpenRouterProvider(profile, api_key)
    if provider == "nvidia":
        return NVIDIAProvider(profile, api_key)
    if provider in {"openai-compatible", "compatible"}:
        return OpenAICompatibleProvider(profile, api_key)
    raise LLMProviderError(f"Unsupported provider: {profile.provider}")

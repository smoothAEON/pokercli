import json
from dataclasses import dataclass

import httpx
import pytest

from pokercli.agents import LLMController, LiveLLMSeatError
from pokercli.engine import ActionType, LegalAction, PublicTableState, SeatView, Street
from pokercli.engine.cards import Card
from pokercli.llm import LLMTurnRequest, LLMTurnResponse, ProviderProfile, ProviderRequestDebug, ProviderResponseDebug
from pokercli.llm.providers import LLMProviderError, NVIDIAProvider, OpenAIProvider, OpenRouterProvider, provider_from_profile


def make_view() -> SeatView:
    return SeatView(
        seat=0,
        player_name="Seat 1",
        session_id="session-1",
        hand_no=3,
        hole_cards=(Card.from_code("As"), Card.from_code("Kd")),
        stack=1_000,
        to_call=0,
        legal_actions=[LegalAction(ActionType.CHECK), LegalAction(ActionType.BET, min_total=100, max_total=1_000)],
        table=PublicTableState(
            street=Street.FLOP,
            board=(Card.from_code("2c"), Card.from_code("7d"), Card.from_code("Jh")),
            pot=300,
            current_bet=0,
            button_seat=1,
            visible_stacks={0: 1_000, 1: 1_000},
            actions=[],
        ),
        session_memory=[],
    )


@dataclass
class StubProvider:
    responses: list[str]

    def __post_init__(self) -> None:
        self.profile = ProviderProfile(
            name="stub",
            provider="openai",
            model="stub-model",
            api_key_env="TEST_KEY",
        )
        self.calls = 0

    def complete_turn(self, request):
        self.calls += 1
        content = self.responses.pop(0)
        return LLMTurnResponse(
            provider="stub",
            model="stub-model",
            content=content,
            raw_payload={"content": content},
            latency_ms=1,
            provider_request=ProviderRequestDebug(
                url="https://example.invalid/v1/chat/completions",
                body={"messages": [{"role": "user", "content": request.user_prompt}]},
            ),
            provider_response=ProviderResponseDebug(status_code=200, body={"content": content}),
        )


class RaisingProvider:
    def __init__(self) -> None:
        self.profile = ProviderProfile(
            name="stub",
            provider="openai",
            model="stub-model",
            api_key_env="TEST_KEY",
        )
        self.calls = 0

    def complete_turn(self, request):
        self.calls += 1
        raise LLMProviderError(
            "boom",
            provider_request=ProviderRequestDebug(
                url="https://example.invalid/v1/chat/completions",
                body={"messages": [{"role": "user", "content": request.user_prompt}]},
            ),
            provider_response=ProviderResponseDebug(status_code=503, body={"error": "boom"}),
            latency_ms=7,
        )


def test_llm_controller_retries_malformed_json_once() -> None:
    controller = LLMController(
        seat_name="Seat 1",
        provider=StubProvider(
            responses=[
                "not-json",
                '{"action":"check","amount":null,"reason":"fine"}',
            ]
        ),
    )
    decision = controller.act(make_view())
    assert decision.normalized_action() == ActionType.CHECK
    assert controller.provider.calls == 2
    assert len(controller.turn_logs) == 2
    assert controller.turn_logs[0].request_kind == "initial"
    assert controller.turn_logs[0].outcome == "invalid_json"
    assert controller.turn_logs[0].provider_request["body"]["messages"][0]["role"] == "user"
    assert controller.turn_logs[0].provider_response["body"]["content"] == "not-json"
    assert controller.turn_logs[1].request_kind == "retry"
    assert controller.turn_logs[1].outcome == "accepted"
    assert controller.turn_logs[1].turn_response == {
        "provider": "stub",
        "model": "stub-model",
        "content": '{"action":"check","amount":null,"reason":"fine"}',
    }


def test_llm_controller_disables_after_repeated_failures() -> None:
    provider = RaisingProvider()
    controller = LLMController(seat_name="Seat 1", provider=provider)
    first = controller.act(make_view())
    second = controller.act(make_view())
    third = controller.act(make_view())
    assert first.normalized_action() == ActionType.CHECK
    assert second.normalized_action() in {ActionType.CHECK, ActionType.BET}
    assert third.normalized_action() in {ActionType.CHECK, ActionType.BET}
    assert controller.disabled is True
    assert provider.calls == 2


def test_seat_view_prompt_payload_omits_bankroll() -> None:
    payload = make_view().to_prompt_payload()
    assert "bankroll" not in payload


def test_llm_controller_raises_in_live_mode() -> None:
    provider = RaisingProvider()
    controller = LLMController(seat_name="Seat 1", provider=provider, failure_mode="raise")
    with pytest.raises(LiveLLMSeatError) as exc_info:
        controller.act(make_view())
    assert "boom" in str(exc_info.value)
    assert provider.calls == 1


def test_llm_controller_logs_provider_failure_debug_payloads() -> None:
    provider = RaisingProvider()
    controller = LLMController(seat_name="Seat 1", provider=provider)
    decision = controller.act(make_view())
    assert decision.normalized_action() in {ActionType.CHECK, ActionType.BET}
    assert len(controller.turn_logs) == 1
    log = controller.turn_logs[0]
    assert log.outcome == "provider_error"
    assert log.provider_request["url"] == "https://example.invalid/v1/chat/completions"
    assert log.provider_response == {"status_code": 503, "body": {"error": "boom"}}
    assert "Authorization" not in json.dumps(log.to_dict())


def test_openai_provider_error_exposes_debug_payloads_without_auth_header(monkeypatch) -> None:
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    response = httpx.Response(status_code=401, request=request, json={"error": "bad key"})

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, headers, json):
            return response

    monkeypatch.setattr("pokercli.llm.providers.httpx.Client", FakeClient)
    profile = ProviderProfile(
        name="openai",
        provider="openai",
        model="gpt-5.4-mini",
        api_key_env="OPENAI_API_KEY",
    )
    provider = OpenAIProvider(profile, "secret-key")
    turn_request = LLMTurnRequest(system_prompt="system", user_prompt="user")
    with pytest.raises(LLMProviderError) as exc_info:
        provider.complete_turn(turn_request)
    error = exc_info.value
    assert error.provider_request is not None
    assert error.provider_response is not None
    assert error.provider_request.to_dict()["url"] == "https://api.openai.com/v1/chat/completions"
    assert error.provider_request.to_dict()["headers"]["User-Agent"] == "PokerCLI/0.1.0"
    assert error.provider_response.to_dict() == {"status_code": 401, "body": {"error": "bad key"}}
    assert "Authorization" not in json.dumps(error.provider_request.to_dict())
    assert "secret-key" not in json.dumps(error.provider_request.to_dict())


def test_provider_factory_supports_openrouter() -> None:
    profile = ProviderProfile(
        name="router",
        provider="openrouter",
        model="openai/gpt-4o",
        api_key_env="OPENROUTER_API_KEY",
        base_url="https://openrouter.ai/api/v1",
    )
    provider = provider_from_profile(profile, "secret")
    assert isinstance(provider, OpenRouterProvider)


def test_openrouter_provider_sets_app_attribution_headers(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, headers, json):
            captured["url"] = url
            captured["headers"] = headers
            request = httpx.Request("POST", url)
            return httpx.Response(
                status_code=200,
                request=request,
                json={"choices": [{"message": {"content": '{"action":"check","amount":null,"reason":"ok"}'}}]},
            )

    monkeypatch.setattr("pokercli.llm.providers.httpx.Client", FakeClient)
    profile = ProviderProfile(
        name="router",
        provider="openrouter",
        model="openai/gpt-4o",
        api_key_env="OPENROUTER_API_KEY",
        base_url="https://openrouter.ai/api/v1",
    )
    provider = OpenRouterProvider(profile, "secret-key")
    response = provider.complete_turn(LLMTurnRequest(system_prompt="system", user_prompt="user"))

    assert captured["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert captured["headers"]["HTTP-Referer"] == "https://github.com/smoothaeon/pokercli"
    assert captured["headers"]["X-OpenRouter-Title"] == "PokerCLI"
    assert captured["headers"]["User-Agent"] == "PokerCLI/0.1.0"
    assert response.provider_request is not None
    assert response.provider_request.to_dict()["headers"] == {
        "Content-Type": "application/json",
        "User-Agent": "PokerCLI/0.1.0",
        "HTTP-Referer": "https://github.com/smoothaeon/pokercli",
        "X-OpenRouter-Title": "PokerCLI",
    }
    assert "Authorization" not in response.provider_request.to_dict()["headers"]


def test_provider_factory_supports_nvidia() -> None:
    profile = ProviderProfile(
        name="nvidia",
        provider="nvidia",
        model="nvidia/llama-3.1-nemotron-nano-8b-v1",
        api_key_env="NVIDIA_API_KEY",
        base_url="https://integrate.api.nvidia.com/v1",
    )
    provider = provider_from_profile(profile, "secret")
    assert isinstance(provider, NVIDIAProvider)


class PromptCapturingProvider:
    def __init__(self, response: str = '{"action":"check","amount":null,"reason":"fine"}'):
        self.profile = ProviderProfile(
            name="stub", provider="openai", model="stub-model", api_key_env="TEST_KEY",
        )
        self.captured_prompts: list[str] = []
        self._response = response

    def complete_turn(self, request):
        self.captured_prompts.append(request.system_prompt)
        return LLMTurnResponse(
            provider="stub", model="stub-model", content=self._response,
            raw_payload={"content": self._response}, latency_ms=1,
            provider_request=ProviderRequestDebug(url="https://x", body={}),
            provider_response=ProviderResponseDebug(status_code=200, body={}),
        )


def test_llm_controller_injects_identity_into_system_prompt() -> None:
    provider = PromptCapturingProvider()
    controller = LLMController(seat_name="Nina Tight", provider=provider, identity="nina")
    controller.act(make_view())
    prompt = provider.captured_prompts[0]
    assert "Nina" in prompt
    assert "tight-aggressive" in prompt
    assert "premium hands" in prompt


def test_llm_controller_without_identity_uses_generic_prompt() -> None:
    provider = PromptCapturingProvider()
    controller = LLMController(seat_name="Bot 2", provider=provider, identity=None)
    controller.act(make_view())
    prompt = provider.captured_prompts[0]
    assert "poker seat controller" in prompt
    assert "tight-aggressive" not in prompt


def test_llm_controller_with_unknown_identity_falls_back_to_generic() -> None:
    provider = PromptCapturingProvider()
    controller = LLMController(seat_name="Mystery", provider=provider, identity="nonexistent")
    controller.act(make_view())
    prompt = provider.captured_prompts[0]
    assert "poker seat controller" in prompt
    assert "Mystery" not in prompt


def test_lookup_identity_returns_none_for_unknown_key() -> None:
    from pokercli.identities import lookup_identity
    assert lookup_identity("nonesuch") is None
    assert lookup_identity(None) is None
    assert lookup_identity("") is None
    assert lookup_identity("nina").name == "Nina Tight"

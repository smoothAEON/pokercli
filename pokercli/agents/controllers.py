from __future__ import annotations

import json
import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import mean
from typing import Any, Protocol

import questionary

from pokercli.engine import ActionDecision, ActionType, LegalAction, SeatView, evaluate_cards
from pokercli.identities import lookup_identity
from pokercli.llm import LLMProviderError, LLMTurnRequest, LLMTurnResponse, ProviderAdapter


class SeatController(Protocol):
    def act(self, view: SeatView) -> ActionDecision:
        """Return a poker action for the current seat."""


class LiveLLMSeatError(RuntimeError):
    def __init__(self, seat_name: str, reason: str) -> None:
        super().__init__(reason)
        self.seat_name = seat_name
        self.reason = reason


def _legal_map(view: SeatView) -> dict[ActionType, LegalAction]:
    return {action.action: action for action in view.legal_actions}


def _decision_is_legal(view: SeatView, decision: ActionDecision) -> bool:
    legal = _legal_map(view)
    action_type = decision.normalized_action()
    if action_type not in legal:
        return action_type == ActionType.ALL_IN and ActionType.ALL_IN in legal
    bounds = legal[action_type]
    if bounds.min_total is None or bounds.max_total is None:
        return True
    if decision.amount is None:
        return False
    return bounds.min_total <= decision.amount <= bounds.max_total


class HumanController:
    def act(self, view: SeatView) -> ActionDecision:
        prompt = self._prompt_text(view)
        while True:
            raw = questionary.text(prompt).ask()
            if raw is None:
                return self._fallback(view)
            try:
                decision = self._parse(raw)
            except ValueError as exc:
                print(str(exc))
                continue
            try:
                decision.normalized_action()
            except ValueError:
                print("Command not allowed.")
                continue
            if _decision_is_legal(view, decision):
                return decision
            print("Illegal action for the current state.")

    def _prompt_text(self, view: SeatView) -> str:
        options = []
        for action in view.legal_actions:
            if action.min_total is not None and action.max_total is not None:
                options.append(f"{action.action.value} {action.min_total}-{action.max_total}")
            else:
                options.append(action.action.value)
        return f"Seat {view.seat + 1} action [{', '.join(options)}]"

    def _parse(self, raw: str) -> ActionDecision:
        parts = raw.strip().lower().split()
        if not parts:
            raise ValueError("Enter an action, for example 'c', 'r 300', or 'all'.")
        if len(parts) == 1:
            return ActionDecision(parts[0], raw_input=raw, source="human")
        if len(parts) == 2 and parts[0] in {"b", "bet", "r", "raise"}:
            return ActionDecision(parts[0], amount=int(parts[1]), raw_input=raw, source="human")
        raise ValueError("Unsupported action format.")

    def _fallback(self, view: SeatView) -> ActionDecision:
        legal = _legal_map(view)
        if ActionType.CHECK in legal:
            return ActionDecision(ActionType.CHECK, source="human")
        return ActionDecision(ActionType.FOLD, source="human")


class RuleBotController:
    def __init__(self, name: str = "rule-bot", seed: int | None = None) -> None:
        self.name = name
        self.random = random.Random(seed)

    def act(self, view: SeatView) -> ActionDecision:
        legal = _legal_map(view)
        strength = self._strength(view)
        if ActionType.CHECK in legal and view.to_call == 0:
            if strength >= 0.82 and ActionType.BET in legal:
                bet = legal[ActionType.BET]
                return ActionDecision(ActionType.BET, amount=self._sized_total(bet, view), source=self.name)
            if strength >= 0.88 and ActionType.RAISE in legal:
                raise_action = legal[ActionType.RAISE]
                return ActionDecision(ActionType.RAISE, amount=self._sized_total(raise_action, view), source=self.name)
            return ActionDecision(ActionType.CHECK, source=self.name)
        if ActionType.RAISE in legal and strength >= 0.78:
            raise_action = legal[ActionType.RAISE]
            return ActionDecision(ActionType.RAISE, amount=self._sized_total(raise_action, view), source=self.name)
        if ActionType.ALL_IN in legal and strength >= 0.92:
            return ActionDecision(ActionType.ALL_IN, source=self.name)
        if ActionType.CALL in legal:
            pot_odds = view.to_call / max(1, view.table.pot + view.to_call)
            if strength >= max(0.34, pot_odds * 0.9):
                return ActionDecision(ActionType.CALL, source=self.name)
        if ActionType.CHECK in legal:
            return ActionDecision(ActionType.CHECK, source=self.name)
        return ActionDecision(ActionType.FOLD, source=self.name)

    def _strength(self, view: SeatView) -> float:
        hole = sorted((card.rank for card in view.hole_cards), reverse=True)
        if not view.table.board:
            pair_bonus = 0.18 if hole[0] == hole[1] else 0.0
            suited_bonus = 0.05 if view.hole_cards[0].suit == view.hole_cards[1].suit else 0.0
            connectivity = 0.04 if abs(hole[0] - hole[1]) <= 2 else 0.0
            broadway = mean(rank / 14 for rank in hole)
            return min(0.99, broadway * 0.7 + pair_bonus + suited_bonus + connectivity)
        rank_tuple = evaluate_cards((*view.hole_cards, *view.table.board))
        category = rank_tuple[0]
        if category >= 6:
            return 0.97
        if category == 5:
            return 0.9
        if category == 4:
            return 0.82
        if category == 3:
            return 0.78
        if category == 2:
            return 0.7
        if category == 1:
            return 0.55
        return 0.25 + sum(card.rank for card in view.hole_cards) / 100

    def _sized_total(self, action: LegalAction, view: SeatView) -> int:
        assert action.min_total is not None and action.max_total is not None
        target = max(action.min_total, min(action.max_total, view.table.current_bet + max(view.table.pot // 2, 1)))
        if target == action.max_total or target == action.min_total:
            return target
        choices = [action.min_total, target, action.max_total]
        return self.random.choice(choices)


LLM_ACTION_VALUES = (
    ActionType.FOLD.value,
    ActionType.CHECK.value,
    ActionType.CALL.value,
    ActionType.BET.value,
    ActionType.RAISE.value,
    ActionType.ALL_IN.value,
)


@dataclass(slots=True)
class ParsedLLMDecision:
    action_decision: ActionDecision
    log_payload: dict[str, Any]


@dataclass(slots=True)
class LLMTurnLog:
    timestamp: str
    session_id: str
    hand_no: int
    seat: int
    seat_name: str
    attempt: int
    request_kind: str
    provider: str
    model: str
    success: bool
    outcome: str
    latency_ms: int | None
    turn_request: dict[str, Any]
    provider_request: dict[str, Any]
    turn_response: dict[str, Any] | None
    provider_response: dict[str, Any]
    decision: dict[str, Any] | None = None
    error: str | None = None

    def request_payload(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "session_id": self.session_id,
            "hand_no": self.hand_no,
            "seat": self.seat,
            "seat_name": self.seat_name,
            "attempt": self.attempt,
            "request_kind": self.request_kind,
            "turn_request": self.turn_request,
            "provider_request": self.provider_request,
        }

    def response_payload(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "success": self.success,
            "outcome": self.outcome,
            "error": self.error,
            "latency_ms": self.latency_ms,
            "decision": self.decision,
            "turn_response": self.turn_response,
            "provider_response": self.provider_response,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.request_payload(),
            **self.response_payload(),
        }


@dataclass(slots=True)
class LLMStatusEvent:
    seat: int
    seat_name: str
    provider: str
    model: str
    status: str
    note: str = ""


class LLMController:
    def __init__(
        self,
        seat_name: str,
        provider: ProviderAdapter,
        fallback: SeatController | None = None,
        max_failures: int = 2,
        failure_mode: str = "fallback",
        status_callback: Callable[[LLMStatusEvent], None] | None = None,
        identity: str | None = None,
    ) -> None:
        self.seat_name = seat_name
        self.provider = provider
        self.fallback = fallback or RuleBotController(name=f"{seat_name}-fallback")
        self.max_failures = max_failures
        self.failure_mode = failure_mode
        self.status_callback = status_callback
        self.identity = identity
        self._identity_data = lookup_identity(identity)
        self.failure_count = 0
        self.disabled = False
        self.last_error: str | None = None
        self.turn_logs: list[LLMTurnLog] = []

    def act(self, view: SeatView) -> ActionDecision:
        if self.disabled:
            self._emit_status(view, "failed", self.last_error or "LLM seat is disabled.")
            if self.failure_mode == "raise":
                raise LiveLLMSeatError(self.seat_name, self.last_error or "LLM seat is disabled.")
            return self.fallback.act(view)
        base_request = self._build_request(view)
        try:
            request = base_request
            for attempt in range(2):
                request_kind = "initial" if attempt == 0 else "retry"
                self._emit_status(view, "requesting" if attempt == 0 else "retrying", f"attempt {attempt + 1}")
                try:
                    response = self.provider.complete_turn(request)
                except LLMProviderError as exc:
                    self.turn_logs.append(
                        self._build_log_entry(
                            view,
                            request,
                            attempt=attempt + 1,
                            request_kind=request_kind,
                            success=False,
                            outcome="provider_error",
                            error=str(exc),
                            provider_error=exc,
                        )
                    )
                    raise
                try:
                    parsed_decision = self._parse_response(response.content)
                except (TypeError, ValueError, json.JSONDecodeError) as exc:
                    error = f"Malformed JSON: {exc}"
                    self.turn_logs.append(
                        self._build_log_entry(
                            view,
                            request,
                            attempt=attempt + 1,
                            request_kind=request_kind,
                            success=False,
                            outcome="invalid_json",
                            error=error,
                            response=response,
                        )
                    )
                else:
                    decision = parsed_decision.action_decision
                    decision_payload = {
                        **parsed_decision.log_payload,
                        "engine_hand_strength": view.hand_strength.to_dict(),
                    }
                    if _decision_is_legal(view, decision):
                        self.failure_count = 0
                        self.turn_logs.append(
                            self._build_log_entry(
                                view,
                                request,
                                attempt=attempt + 1,
                                request_kind=request_kind,
                                success=True,
                                outcome="accepted",
                                error=None,
                                response=response,
                                decision=decision_payload,
                            )
                        )
                        self.last_error = None
                        self._emit_status(view, "responded", decision.normalized_action().value)
                        return decision
                    error = "Illegal action for the current state."
                    self.turn_logs.append(
                        self._build_log_entry(
                            view,
                            request,
                            attempt=attempt + 1,
                            request_kind=request_kind,
                            success=False,
                            outcome="illegal_action",
                            error=error,
                            response=response,
                            decision=decision_payload,
                        )
                    )
                if attempt == 0:
                    request = self._build_retry_request(view, response.content, error)
                    continue
                raise LLMProviderError("Provider returned an invalid action twice.")
        except (LLMProviderError, ValueError, json.JSONDecodeError) as exc:
            self.failure_count += 1
            self.last_error = str(exc)
            if self.failure_count >= self.max_failures:
                self.disabled = True
            self._emit_status(view, "failed", str(exc))
            if self.failure_mode == "raise":
                raise LiveLLMSeatError(self.seat_name, str(exc)) from exc
            return self._fallback_decision(view)

    def reset_failures(self) -> None:
        self.failure_count = 0
        self.disabled = False
        self.last_error = None

    def set_provider(self, provider: ProviderAdapter) -> None:
        self.provider = provider
        self.reset_failures()

    def _emit_status(self, view: SeatView, status: str, note: str = "") -> None:
        if self.status_callback is None:
            return
        self.status_callback(
            LLMStatusEvent(
                seat=view.seat,
                seat_name=self.seat_name,
                provider=self.provider.profile.provider,
                model=self.provider.profile.model,
                status=status,
                note=note,
            )
        )

    def _build_request(self, view: SeatView) -> LLMTurnRequest:
        payload = json.dumps(view.to_prompt_payload(), indent=2)
        base = (
            "You are a poker seat controller for No-Limit Texas Hold'em. "
            "Never invent hidden cards. Respond with strict JSON only: "
            '{"action":"fold|check|call|bet|raise|all-in","amount":number|null,'
            '"confidence":0.0,"hand_strength":"string","draws":"string","pot_odds":"string",'
            '"spr":"string","reasoning_summary":"short reason","risk_flag":"string"}. '
            "Set amount to null for non-sizing actions. Use \"none\" for draws when no draw is present. "
            "Compute spr as your current stack divided by the pot before acting."
        )
        if self._identity_data is not None:
            system = f"{self._identity_data.description}\n\n{base}"
        else:
            system = base
        user = f"Seat view:\n{payload}\nChoose one legal action."
        return LLMTurnRequest(
            system_prompt=system,
            user_prompt=user,
            response_schema={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": list(LLM_ACTION_VALUES)},
                    "amount": {"type": ["integer", "null"]},
                    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    "hand_strength": {"type": "string"},
                    "draws": {"type": "string"},
                    "pot_odds": {"type": "string"},
                    "spr": {"type": "string"},
                    "reasoning_summary": {"type": "string"},
                    "risk_flag": {"type": "string"},
                },
                "required": [
                    "action",
                    "amount",
                    "confidence",
                    "hand_strength",
                    "draws",
                    "pot_odds",
                    "spr",
                    "reasoning_summary",
                    "risk_flag",
                ],
                "additionalProperties": False,
            },
            metadata={"seat": view.seat, "player_name": view.player_name},
        )

    def _build_retry_request(self, view: SeatView, prior_response: str, error: str) -> LLMTurnRequest:
        retry = self._build_request(view)
        retry.user_prompt += f"\nYour previous response was invalid: {prior_response}\nError: {error}"
        return retry

    def _parse_response(self, content: str) -> ParsedLLMDecision:
        if not content:
            raise ValueError("LLM returned empty content")
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise ValueError("LLM response must be a JSON object")
        action = self._require_action(parsed, "action")
        amount = self._require_int_or_none(parsed, "amount")
        confidence = self._require_confidence(parsed, "confidence")
        hand_strength = self._require_string(parsed, "hand_strength")
        draws = self._require_string(parsed, "draws")
        pot_odds = self._require_string(parsed, "pot_odds")
        spr = self._require_string(parsed, "spr")
        reasoning_summary = self._require_string(parsed, "reasoning_summary")
        risk_flag = self._require_string(parsed, "risk_flag")
        action_decision = ActionDecision(
            action,
            amount=amount,
            raw_input=content,
            source=self.provider.profile.name,
        )
        action_decision.normalized_action()
        return ParsedLLMDecision(
            action_decision=action_decision,
            log_payload={
                "action": action,
                "amount": amount,
                "confidence": confidence,
                "hand_strength": hand_strength,
                "draws": draws,
                "pot_odds": pot_odds,
                "spr": spr,
                "reasoning_summary": reasoning_summary,
                "risk_flag": risk_flag,
            },
        )

    def _require_action(self, payload: dict[str, Any], field_name: str) -> str:
        action = self._require_string(payload, field_name)
        if action not in LLM_ACTION_VALUES:
            raise ValueError(f"Field '{field_name}' must be one of: {', '.join(LLM_ACTION_VALUES)}")
        return action

    def _require_string(self, payload: dict[str, Any], field_name: str) -> str:
        if field_name not in payload:
            raise ValueError(f"Missing required field '{field_name}'")
        value = payload[field_name]
        if not isinstance(value, str):
            raise ValueError(f"Field '{field_name}' must be a string")
        return value

    def _require_int_or_none(self, payload: dict[str, Any], field_name: str) -> int | None:
        if field_name not in payload:
            raise ValueError(f"Missing required field '{field_name}'")
        value = payload[field_name]
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"Field '{field_name}' must be an integer or null")
        return value

    def _require_confidence(self, payload: dict[str, Any], field_name: str) -> float:
        if field_name not in payload:
            raise ValueError(f"Missing required field '{field_name}'")
        value = payload[field_name]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"Field '{field_name}' must be a number")
        confidence = float(value)
        if not 0.0 <= confidence <= 1.0:
            raise ValueError(f"Field '{field_name}' must be between 0 and 1")
        return confidence

    def _fallback_decision(self, view: SeatView) -> ActionDecision:
        legal = _legal_map(view)
        if ActionType.CHECK in legal:
            return ActionDecision(ActionType.CHECK, source="llm-fallback")
        if ActionType.CALL in legal and view.to_call == 0:
            return ActionDecision(ActionType.CALL, source="llm-fallback")
        if self.disabled:
            return self.fallback.act(view)
        return ActionDecision(ActionType.FOLD, source="llm-fallback")

    def _build_log_entry(
        self,
        view: SeatView,
        request: LLMTurnRequest,
        *,
        attempt: int,
        request_kind: str,
        success: bool,
        outcome: str,
        error: str | None,
        response: LLMTurnResponse | None = None,
        provider_error: LLMProviderError | None = None,
        decision: dict[str, Any] | None = None,
    ) -> LLMTurnLog:
        provider = self.provider.profile.provider
        model = self.provider.profile.model
        latency_ms: int | None = None
        turn_response: dict[str, Any] | None = None
        provider_request = {"url": None, "body": None}
        provider_response = {"status_code": None, "body": None}
        if response is not None:
            provider = response.provider
            model = response.model
            latency_ms = response.latency_ms
            turn_response = {
                "provider": response.provider,
                "model": response.model,
                "content": response.content,
            }
            if response.provider_request is not None:
                provider_request = response.provider_request.to_dict()
            if response.provider_response is not None:
                provider_response = response.provider_response.to_dict()
        if provider_error is not None:
            latency_ms = provider_error.latency_ms
            if provider_error.provider_request is not None:
                provider_request = provider_error.provider_request.to_dict()
            if provider_error.provider_response is not None:
                provider_response = provider_error.provider_response.to_dict()
        return LLMTurnLog(
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            session_id=view.session_id,
            hand_no=view.hand_no,
            seat=view.seat,
            seat_name=self.seat_name,
            attempt=attempt,
            request_kind=request_kind,
            provider=provider,
            model=model,
            success=success,
            outcome=outcome,
            latency_ms=latency_ms,
            turn_request=request.to_dict(),
            provider_request=provider_request,
            turn_response=turn_response,
            provider_response=provider_response,
            decision=decision,
            error=error,
        )

from __future__ import annotations

from unittest.mock import MagicMock

from pokercli.agents import HumanController
from pokercli.engine import ActionType, LegalAction, PublicTableState, SeatView, Street
from pokercli.engine.cards import Card


def make_view(
    legal_actions: list[LegalAction] | None = None,
    to_call: int = 200,
) -> SeatView:
    if legal_actions is None:
        legal_actions = [LegalAction(ActionType.CHECK), LegalAction(ActionType.BET, min_total=100, max_total=1_000)]
    return SeatView(
        seat=0,
        player_name="Seat 1",
        session_id="session-1",
        hand_no=3,
        hole_cards=(Card.from_code("As"), Card.from_code("Kd")),
        stack=1_000,
        to_call=to_call,
        legal_actions=legal_actions,
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


def _mock_questionary(monkeypatch, inputs: list[str]) -> None:
    """Patch questionary.text so successive .ask() calls return the given inputs."""

    class StubQuestion:
        def __init__(self, value: str) -> None:
            self._value = value

        def ask(self) -> str:
            return self._value

    items = iter(inputs)
    mock_text = MagicMock()
    mock_text.side_effect = lambda prompt: StubQuestion(next(items))
    monkeypatch.setattr("pokercli.agents.controllers.questionary.text", mock_text)


def test_human_rejects_unknown_command_and_retries(monkeypatch, capsys) -> None:
    """Unknown command 'x' prints 'Command not allowed.' and loops until valid input."""
    _mock_questionary(monkeypatch, ["x", "check"])
    controller = HumanController()
    view = make_view(to_call=0)

    decision = controller.act(view)

    assert decision.normalized_action() == ActionType.CHECK

    captured = capsys.readouterr()
    assert "Command not allowed." in captured.out


def test_human_rejects_illegal_action_and_retries(monkeypatch, capsys) -> None:
    """Recognized-but-illegal 'call' prints 'Illegal action for the current state.' and loops."""
    _mock_questionary(monkeypatch, ["call", "check"])
    controller = HumanController()
    view = make_view(
        legal_actions=[LegalAction(ActionType.CHECK), LegalAction(ActionType.ALL_IN)],
        to_call=0,
    )

    decision = controller.act(view)

    assert decision.normalized_action() == ActionType.CHECK

    captured = capsys.readouterr()
    assert "Illegal action for the current state." in captured.out

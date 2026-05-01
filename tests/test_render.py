from pokercli.analytics import compute_seat_analytics
from pokercli.engine import ActionRecord, ActionType, GameConfig, LegalAction, PublicTableState, SeatView, Street
from pokercli.engine.models import HandHistory, PotAward, PotSlice, SeatSnapshot
from pokercli.render import format_card_code, render_hand_history, render_session_report, render_table

from tests.conftest import cards


def _showdown_history(*, winner_seats: tuple[int, ...], second_revealed: bool) -> HandHistory:
    return HandHistory(
        session_id="session-1",
        hand_no=1,
        button_seat=0,
        blind_seats={"small_blind": 0, "big_blind": 1},
        board=cards(["As", "Kd", "Qc", "Jc", "Td"]),
        burned=cards(["2h"]),
        actions=[
            ActionRecord(
                index=0,
                street=Street.PRE_FLOP,
                seat=0,
                player_name="Seat 1",
                action=ActionType.CALL,
                contribution=100,
                street_total=100,
                pot_before=150,
                pot_after=250,
                stack_after=900,
                to_call_before=100,
                all_in=False,
            ),
            ActionRecord(
                index=1,
                street=Street.PRE_FLOP,
                seat=1,
                player_name="Seat 2",
                action=ActionType.CHECK,
                contribution=0,
                street_total=100,
                pot_before=250,
                pot_after=250,
                stack_after=900,
                to_call_before=0,
                all_in=False,
            ),
        ],
        pots=[PotSlice(index=0, amount=250, eligible_seats=(0, 1))],
        awards=[
            PotAward(
                pot_index=0,
                seat=seat,
                amount=125 if len(winner_seats) > 1 else 250,
                reason="showdown",
            )
            for seat in winner_seats
        ],
        seat_results={
            0: SeatSnapshot(
                seat=0,
                name="Seat 1",
                stack_start=1_000,
                stack_end=1_250 if len(winner_seats) == 1 else 1_125,
                commitment=100,
                winnings=250 if len(winner_seats) == 1 else 125,
                folded=False,
                all_in=False,
                hole_cards=cards(["Jh", "Td"]),
                revealed=True,
                hand_rank=(7, 14, 13) if len(winner_seats) == 1 else (4, 14),
            ),
            1: SeatSnapshot(
                seat=1,
                name="Seat 2",
                stack_start=1_000,
                stack_end=750 if len(winner_seats) == 1 else 1_125,
                commitment=100,
                winnings=0 if len(winner_seats) == 1 else 125,
                folded=False,
                all_in=False,
                hole_cards=cards(["9s", "9c"]),
                revealed=second_revealed,
                hand_rank=(6, 14, 13) if len(winner_seats) == 1 else (4, 14),
            ),
        },
        street_reached=Street.SHOWDOWN,
        winner_seats=winner_seats,
    )


def test_render_table_uses_suit_symbols() -> None:
    view = SeatView(
        seat=0,
        player_name="Seat 1",
        session_id="session-1",
        hand_no=1,
        hole_cards=cards(["As", "Kd"]),
        stack=1_000,
        bankroll=0,
        to_call=0,
        legal_actions=[LegalAction(ActionType.CHECK), LegalAction(ActionType.BET, min_total=100, max_total=1_000)],
        table=PublicTableState(
            street=Street.FLOP,
            board=cards(["2c", "7d", "Jh"]),
            pot=300,
            current_bet=0,
            button_seat=1,
            visible_stacks={0: 1_000, 1: 1_000},
            actions=[],
        ),
        session_memory=[],
    )

    rendered = render_table(view)
    assert "Board:" in rendered
    assert "+----+ +----+ +----+" in rendered
    assert "♠" in rendered
    assert "♦" in rendered


def test_render_hand_history_adds_result_labels_and_keeps_hidden_loser_hidden() -> None:
    history = _showdown_history(winner_seats=(0,), second_revealed=False)

    rendered = render_hand_history(history)
    serialized = history.to_dict()

    assert "result=won" in rendered
    assert "hand=Four of a Kind, Aces" in rendered
    assert "Seat 2 Seat 2: start=1000 end=750 net=-250 result=lost cards=[hidden]" in rendered
    assert "Full House" not in rendered
    assert serialized["board"] == ["AS", "KD", "QC", "JC", "TD"]
    assert serialized["seat_results"][0]["hole_cards"] == ["JH", "TD"]
    assert format_card_code(serialized["board"][0]) == "A♠"


def test_render_hand_history_marks_split_pot_winners_as_draw() -> None:
    history = _showdown_history(winner_seats=(0, 1), second_revealed=True)

    rendered = render_hand_history(history)

    assert rendered.count("result=draw") == 2
    assert rendered.count("hand=Straight, Ace-high") == 2


def test_render_session_report_includes_summary_actions_awards_and_full_cards() -> None:
    history = _showdown_history(winner_seats=(0,), second_revealed=False)
    seat_metrics = compute_seat_analytics([history], 100)

    report = render_session_report(
        session_id="session-1",
        histories=[history],
        seat_metrics=seat_metrics,
        game_config=GameConfig(seat_count=2, small_blind=50, big_blind=100, starting_stack=1_000, max_hands=5),
        end_reason="user-stopped",
        final_stacks={0: 1_250, 1: 750},
        seat_names={0: "Seat 1", 1: "Seat 2"},
    )

    assert "PokerCLI Session Report" in report
    assert "End reason: user-stopped" in report
    assert "Seat Summary:" in report
    assert "final_stack=1250 pnl=250" in report
    assert "Hand Details:" in report
    assert "Actions:" in report
    assert "Awards:" in report
    assert "cards=9♠ 9♣ hand=Full House, Aces full of Kings" in report

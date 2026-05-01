from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

from pokercli.engine import ActionType, HandHistory


@dataclass(slots=True)
class SeatAnalytics:
    seat: int
    player_name: str
    hands: int
    pnl: int
    bb_per_100: float
    vpip: float
    pfr: float
    three_bet_rate: float
    showdown_win_rate: float
    max_drawdown: int
    volatility: float
    risk_of_ruin: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "seat": self.seat,
            "player_name": self.player_name,
            "hands": self.hands,
            "pnl": self.pnl,
            "bb_per_100": self.bb_per_100,
            "vpip": self.vpip,
            "pfr": self.pfr,
            "three_bet_rate": self.three_bet_rate,
            "showdown_win_rate": self.showdown_win_rate,
            "max_drawdown": self.max_drawdown,
            "volatility": self.volatility,
            "risk_of_ruin": self.risk_of_ruin,
        }


def compute_seat_analytics(histories: list[HandHistory], big_blind: int) -> dict[int, SeatAnalytics]:
    if not histories:
        return {}
    seat_ids = sorted({seat for history in histories for seat in history.seat_results})
    metrics: dict[int, SeatAnalytics] = {}
    for seat in seat_ids:
        played_histories = [history for history in histories if seat in history.seat_results]
        if not played_histories:
            continue
        name = played_histories[0].seat_results[seat].name
        hand_nets = [
            history.seat_results[seat].stack_end - history.seat_results[seat].stack_start
            for history in played_histories
        ]
        pnl = sum(hand_nets)
        hands = len(hand_nets)
        vpip_count = 0
        pfr_count = 0
        three_bet_count = 0
        three_bet_opportunities = 0
        showdown_hands = 0
        showdown_wins = 0
        curve = []
        running = 0
        for history in played_histories:
            preflop_actions = [action for action in history.actions if action.street.value == "preflop"]
            voluntary = False
            raised = False
            prior_raises = 0
            seat_acted_after_raise = False
            for action in preflop_actions:
                if action.action == ActionType.POST_BLIND:
                    continue
                if action.action in {ActionType.BET, ActionType.RAISE, ActionType.ALL_IN} and action.street_total > 0:
                    if action.seat == seat:
                        raised = True
                        if prior_raises >= 1:
                            three_bet_count += 1
                    prior_raises += 1
                if action.seat == seat:
                    if action.action in {ActionType.CALL, ActionType.BET, ActionType.RAISE, ActionType.ALL_IN}:
                        voluntary = True
                    if prior_raises >= 1:
                        seat_acted_after_raise = True
            vpip_count += int(voluntary)
            pfr_count += int(raised)
            if seat_acted_after_raise:
                three_bet_opportunities += 1
            showdown = any(snapshot.revealed for snapshot in history.seat_results.values())
            if showdown:
                showdown_hands += 1
                if seat in history.winner_seats:
                    showdown_wins += 1
            running += history.seat_results[seat].stack_end - history.seat_results[seat].stack_start
            curve.append(running)
        drawdown = _max_drawdown(curve)
        volatility = pstdev(hand_nets) / big_blind if len(hand_nets) > 1 else 0.0
        risk = _risk_of_ruin(
            bankroll=max(1, played_histories[0].seat_results[seat].stack_start),
            returns=[net / big_blind for net in hand_nets],
        )
        metrics[seat] = SeatAnalytics(
            seat=seat,
            player_name=name,
            hands=hands,
            pnl=pnl,
            bb_per_100=(pnl / big_blind) * 100 / max(1, hands),
            vpip=vpip_count / max(1, hands),
            pfr=pfr_count / max(1, hands),
            three_bet_rate=three_bet_count / max(1, three_bet_opportunities),
            showdown_win_rate=showdown_wins / max(1, showdown_hands),
            max_drawdown=drawdown,
            volatility=volatility,
            risk_of_ruin=risk,
        )
    return metrics


def _max_drawdown(curve: list[int]) -> int:
    peak = 0
    max_drawdown = 0
    for value in curve:
        peak = max(peak, value)
        max_drawdown = max(max_drawdown, peak - value)
    return max_drawdown


def _risk_of_ruin(bankroll: int, returns: list[float]) -> float:
    if not returns:
        return 0.0
    edge = mean(returns)
    if edge <= 0:
        return 1.0
    variance = pstdev(returns) ** 2 if len(returns) > 1 else 0.0
    if variance == 0:
        return 0.0
    estimate = math.exp((-2 * edge * (bankroll)) / variance)
    return max(0.0, min(1.0, estimate))


def analytics_summary(histories: list[HandHistory], big_blind: int) -> dict[str, Any]:
    seat_metrics = compute_seat_analytics(histories, big_blind)
    return {
        "hands": len(histories),
        "seats": {seat: metric.to_dict() for seat, metric in seat_metrics.items()},
    }


def write_summary_json(path: str | Path, summary: dict[str, Any]) -> None:
    target = Path(path)
    target.write_text(json.dumps(summary, indent=2), encoding="utf-8")


def write_summary_csv(path: str | Path, seat_metrics: dict[int, SeatAnalytics]) -> None:
    target = Path(path)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "seat",
                "player_name",
                "hands",
                "pnl",
                "bb_per_100",
                "vpip",
                "pfr",
                "three_bet_rate",
                "showdown_win_rate",
                "max_drawdown",
                "volatility",
                "risk_of_ruin",
            ],
        )
        writer.writeheader()
        for metric in seat_metrics.values():
            writer.writerow(metric.to_dict())

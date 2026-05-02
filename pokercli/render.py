from __future__ import annotations

from dataclasses import dataclass
from textwrap import shorten
from typing import Any, Iterable, Mapping, Sequence

from rich.table import Table

from pokercli.engine import Card, GameConfig, HandHistory, SeatView, describe_rank

SUIT_SYMBOLS = {
    "s": "♠",
    "h": "♥",
    "d": "♦",
    "c": "♣",
}


@dataclass(slots=True)
class LLMStatusRow:
    seat: int
    name: str
    provider: str
    model: str
    status: str
    note: str = ""


def format_card(card: Card) -> str:
    return f"{card.code[0].upper()}{SUIT_SYMBOLS[card.suit]}"


def format_card_code(code: str) -> str:
    normalized = code.strip()
    if len(normalized) != 2:
        return code
    return f"{normalized[0].upper()}{SUIT_SYMBOLS.get(normalized[1].lower(), normalized[1])}"


def format_cards_inline(cards: Iterable[Card]) -> str:
    return " ".join(format_card(card) for card in cards)


def format_card_codes_inline(codes: Iterable[str]) -> str:
    return " ".join(format_card_code(code) for code in codes)


def result_label_for_seat(seat: int, *, folded: bool, winner_seats: Sequence[int]) -> str:
    if folded:
        return "folded"
    if seat in winner_seats:
        return "draw" if len(winner_seats) > 1 else "won"
    return "lost"


def describe_hand_rank_value(rank: Sequence[int] | None) -> str | None:
    if rank is None:
        return None
    return describe_rank(tuple(rank))


def render_card(card: Card) -> list[str]:
    rank = card.code[0].upper()
    suit = SUIT_SYMBOLS[card.suit]
    return [
        "+----+",
        f"|{rank:<2}  |",
        f"| {suit:^2} |",
        f"|  {rank:>2}|",
        "+----+",
    ]


def render_cards(cards: tuple[Card, ...] | list[Card]) -> str:
    if not cards:
        return "[no cards]"
    blocks = [render_card(card) for card in cards]
    return "\n".join(" ".join(parts[row] for parts in blocks) for row in range(5))


def render_table(view: SeatView) -> str:
    lines = []
    lines.append(f"Seat {view.seat + 1}: {view.player_name}")
    lines.append(f"Street: {view.table.street.value}    Pot: {view.table.pot}    To call: {view.to_call}")
    lines.append("Board:")
    lines.append(render_cards(view.table.board))
    lines.append(f"Your stack: {view.stack}")
    lines.append("Hole cards:")
    lines.append(render_cards(view.hole_cards))
    lines.append("Stacks:")
    for seat, stack in sorted(view.table.visible_stacks.items()):
        lines.append(f"  Seat {seat + 1}: {stack}")
    lines.append("Recent actions:")
    recent = view.table.actions[-8:]
    if not recent:
        lines.append("  [none]")
    else:
        for action in recent:
            label = f"{action.player_name} {action.action.value}"
            if action.contribution:
                label += f" {action.street_total}"
            lines.append(f"  {shorten(label, width=76, placeholder='...')}")
    lines.append("Legal actions:")
    for action in view.legal_actions:
        if action.min_total is not None and action.max_total is not None:
            lines.append(f"  {action.action.value}: {action.min_total} to {action.max_total}")
        elif action.call_amount:
            lines.append(f"  {action.action.value}: {action.call_amount}")
        else:
            lines.append(f"  {action.action.value}")
    lines.append("Hand strength:")
    current = view.hand_strength.current_label
    if view.hand_strength.current_rank is not None:
        current += f" {view.hand_strength.current_rank}"
    lines.append(f"  Current: {current}")
    lines.append("  By river:")
    for bucket, probability in view.hand_strength.potential_by_river.items():
        lines.append(f"    {bucket.replace('_', ' ').title()}: {probability:.2%}")
    return "\n".join(lines)


def render_hand_history(history: HandHistory) -> str:
    lines = [
        f"Session {history.session_id} Hand {history.hand_no}",
        f"Button: Seat {history.button_seat + 1}",
        f"Board: {format_cards_inline(history.board) or '-'}",
        "Actions:",
    ]
    for action in history.actions:
        label = f"  {action.player_name}: {action.action.value}"
        if action.contribution:
            label += f" {action.street_total}"
        lines.append(label)
    lines.append("Results:")
    for seat, snapshot in sorted(history.seat_results.items()):
        result = result_label_for_seat(seat, folded=snapshot.folded, winner_seats=history.winner_seats)
        reveal = format_cards_inline(snapshot.hole_cards) if snapshot.revealed else "[hidden]"
        label = (
            f"  Seat {seat + 1} {snapshot.name}: start={snapshot.stack_start} "
            f"end={snapshot.stack_end} net={snapshot.stack_end - snapshot.stack_start} "
            f"result={result} cards={reveal}"
        )
        hand_description = describe_hand_rank_value(snapshot.hand_rank) if snapshot.revealed else None
        if hand_description is not None:
            label += f" hand={hand_description}"
        lines.append(label)
    return "\n".join(lines)


def render_stored_hand_history(hand: dict[str, Any]) -> str:
    lines = [
        f"Session {hand['session_id']} Hand {hand['hand_no']}",
        f"Button: Seat {hand['button_seat'] + 1}",
        f"Board: {format_card_codes_inline(hand['board']) or '-'}",
        "Actions:",
    ]
    for action in hand["actions"]:
        label = f"  {action['player_name']}: {action['action']}"
        if action["contribution"]:
            label += f" {action['street_total']}"
        lines.append(label)
    lines.append("Results:")
    for seat_key, snapshot in sorted(hand["seat_results"].items(), key=lambda item: int(item[0])):
        seat = int(seat_key)
        result = result_label_for_seat(seat, folded=snapshot["folded"], winner_seats=hand["winner_seats"])
        cards = format_card_codes_inline(snapshot["hole_cards"]) if snapshot["revealed"] else "[hidden]"
        label = (
            f"  Seat {seat + 1} {snapshot['name']}: start={snapshot['stack_start']} "
            f"end={snapshot['stack_end']} net={snapshot['stack_end'] - snapshot['stack_start']} "
            f"result={result} cards={cards}"
        )
        hand_description = describe_hand_rank_value(snapshot["hand_rank"]) if snapshot["revealed"] else None
        if hand_description is not None:
            label += f" hand={hand_description}"
        lines.append(label)
    return "\n".join(lines)


def render_session_report(
    *,
    session_id: str,
    histories: list[HandHistory],
    seat_metrics: Mapping[int, Any],
    game_config: GameConfig,
    end_reason: str,
    final_stacks: Mapping[int, int],
    seat_names: Mapping[int, str],
    seat_identities: Mapping[int, Mapping[str, str]] | None = None,
) -> str:
    lines = [
        "PokerCLI Session Report",
        f"Session ID: {session_id}",
        f"Hands completed: {len(histories)}",
        f"Blinds: {game_config.small_blind}/{game_config.big_blind}",
        f"Starting stack: {game_config.starting_stack}",
        f"End reason: {end_reason}",
        "",
        "Seat Summary:",
    ]
    for seat in sorted(seat_names):
        metric = seat_metrics.get(seat)
        final_stack = final_stacks.get(seat, game_config.starting_stack)
        pnl = metric.pnl if metric is not None else final_stack - game_config.starting_stack
        hands = metric.hands if metric is not None else 0
        bb_per_100 = metric.bb_per_100 if metric is not None else 0.0
        vpip = metric.vpip if metric is not None else 0.0
        pfr = metric.pfr if metric is not None else 0.0
        three_bet_rate = metric.three_bet_rate if metric is not None else 0.0
        showdown_win_rate = metric.showdown_win_rate if metric is not None else 0.0
        max_drawdown = metric.max_drawdown if metric is not None else 0
        volatility = metric.volatility if metric is not None else 0.0
        risk_of_ruin = metric.risk_of_ruin if metric is not None else 0.0
        personality = ""
        if seat_identities is not None and seat in seat_identities:
            identity = seat_identities[seat]
            personality = f" personality={identity['name']} ({identity['style']})"
        lines.append(
            f"  Seat {seat + 1} {seat_names[seat]}: final_stack={final_stack} pnl={pnl} "
            f"hands={hands} bb_per_100={bb_per_100:.2f} vpip={vpip:.2%} pfr={pfr:.2%} "
            f"three_bet={three_bet_rate:.2%} showdown_win={showdown_win_rate:.2%} "
            f"max_drawdown={max_drawdown} volatility={volatility:.2f} risk_of_ruin={risk_of_ruin:.2%}"
            f"{personality}"
        )
    lines.append("")
    lines.append("Hand Details:")
    if not histories:
        lines.append("  No completed hands.")
        return "\n".join(lines)
    for history in histories:
        winner_labels = ", ".join(
            f"Seat {seat + 1} {history.seat_results.get(seat).name if seat in history.seat_results else seat_names.get(seat, f'Seat {seat + 1}')}"
            for seat in history.winner_seats
        ) or "-"
        lines.extend(
            [
                f"Hand {history.hand_no}",
                f"  Button: Seat {history.button_seat + 1}",
                f"  Street reached: {history.street_reached.value}",
                f"  Board: {format_cards_inline(history.board) or '-'}",
                f"  Winners: {winner_labels}",
                "  Actions:",
            ]
        )
        if history.actions:
            for action in history.actions:
                label = f"    {action.street.value} {action.player_name}: {action.action.value}"
                if action.contribution:
                    label += f" {action.street_total}"
                lines.append(label)
        else:
            lines.append("    [none]")
        lines.append("  Awards:")
        if history.awards:
            for award in history.awards:
                winner_name = history.seat_results.get(award.seat).name if award.seat in history.seat_results else seat_names.get(award.seat, f"Seat {award.seat + 1}")
                lines.append(
                    f"    pot={award.pot_index} seat={award.seat + 1} {winner_name} amount={award.amount} reason={award.reason}"
                )
        else:
            lines.append("    [none]")
        lines.append("  Results:")
        for seat, snapshot in sorted(history.seat_results.items()):
            result = result_label_for_seat(seat, folded=snapshot.folded, winner_seats=history.winner_seats)
            hand_description = describe_hand_rank_value(snapshot.hand_rank) or "-"
            lines.append(
                f"    Seat {seat + 1} {snapshot.name}: result={result} start={snapshot.stack_start} "
                f"end={snapshot.stack_end} net={snapshot.stack_end - snapshot.stack_start} "
                f"commitment={snapshot.commitment} winnings={snapshot.winnings} "
                f"cards={format_cards_inline(snapshot.hole_cards)} hand={hand_description}"
            )
        lines.append("")
    if lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def render_llm_status_table(rows: list[LLMStatusRow]) -> Table:
    table = Table(title="LLM Status")
    table.add_column("Seat")
    table.add_column("Name")
    table.add_column("Provider")
    table.add_column("Model")
    table.add_column("Status")
    table.add_column("Note")
    for row in sorted(rows, key=lambda item: item.seat):
        table.add_row(
            str(row.seat + 1),
            row.name,
            row.provider,
            row.model,
            row.status,
            row.note,
        )
    return table

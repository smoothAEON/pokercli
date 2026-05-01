from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from pokercli.engine.cards import Card


class Street(str, Enum):
    SETUP = "setup"
    PRE_FLOP = "preflop"
    FLOP = "flop"
    TURN = "turn"
    RIVER = "river"
    SHOWDOWN = "showdown"
    SETTLEMENT = "settlement"
    COMPLETE = "complete"


class ActionType(str, Enum):
    FOLD = "fold"
    CHECK = "check"
    CALL = "call"
    BET = "bet"
    RAISE = "raise"
    ALL_IN = "all-in"
    POST_BLIND = "post-blind"


@dataclass(slots=True)
class GameConfig:
    seat_count: int = 6
    small_blind: int = 50
    big_blind: int = 100
    starting_stack: int = 10_000
    max_hands: int = 100
    seed: int | None = None
    controller_lineup: tuple[str, ...] = ()
    timeouts: dict[str, float] = field(default_factory=dict)
    session_memory_hands: int = 5

    def __post_init__(self) -> None:
        if not 2 <= self.seat_count <= 6:
            raise ValueError("seat_count must be between 2 and 6")
        if self.small_blind <= 0 or self.big_blind <= 0:
            raise ValueError("blinds must be positive")
        if self.small_blind >= self.big_blind:
            raise ValueError("small_blind must be less than big_blind")
        if self.starting_stack < self.big_blind:
            raise ValueError("starting_stack must cover at least one big blind")
        if self.max_hands <= 0:
            raise ValueError("max_hands must be positive")


@dataclass(slots=True)
class LegalAction:
    action: ActionType
    min_total: int | None = None
    max_total: int | None = None
    call_amount: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "min_total": self.min_total,
            "max_total": self.max_total,
            "call_amount": self.call_amount,
        }


@dataclass(slots=True)
class ActionDecision:
    action: ActionType | str
    amount: int | None = None
    raw_input: str | None = None
    source: str | None = None

    def normalized_action(self) -> ActionType:
        if isinstance(self.action, ActionType):
            return self.action
        normalized = self.action.strip().lower()
        aliases = {
            "f": ActionType.FOLD,
            "fold": ActionType.FOLD,
            "k": ActionType.CHECK,
            "check": ActionType.CHECK,
            "c": ActionType.CALL,
            "call": ActionType.CALL,
            "b": ActionType.BET,
            "bet": ActionType.BET,
            "r": ActionType.RAISE,
            "raise": ActionType.RAISE,
            "all": ActionType.ALL_IN,
            "all-in": ActionType.ALL_IN,
            "allin": ActionType.ALL_IN,
        }
        if normalized not in aliases:
            raise ValueError(f"Unknown action: {self.action}")
        return aliases[normalized]


@dataclass(slots=True)
class ActionRecord:
    index: int
    street: Street
    seat: int
    player_name: str
    action: ActionType
    contribution: int
    street_total: int
    pot_before: int
    pot_after: int
    stack_after: int
    to_call_before: int
    all_in: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "street": self.street.value,
            "seat": self.seat,
            "player_name": self.player_name,
            "action": self.action.value,
            "contribution": self.contribution,
            "street_total": self.street_total,
            "pot_before": self.pot_before,
            "pot_after": self.pot_after,
            "stack_after": self.stack_after,
            "to_call_before": self.to_call_before,
            "all_in": self.all_in,
        }


@dataclass(slots=True)
class PotSlice:
    index: int
    amount: int
    eligible_seats: tuple[int, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "amount": self.amount,
            "eligible_seats": list(self.eligible_seats),
        }


@dataclass(slots=True)
class PotAward:
    pot_index: int
    seat: int
    amount: int
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "pot_index": self.pot_index,
            "seat": self.seat,
            "amount": self.amount,
            "reason": self.reason,
        }


@dataclass(slots=True)
class SeatSnapshot:
    seat: int
    name: str
    stack_start: int
    stack_end: int
    commitment: int
    winnings: int
    folded: bool
    all_in: bool
    hole_cards: tuple[Card, Card]
    revealed: bool
    hand_rank: tuple[int, ...] | None

    def projection(self, viewer_seat: int | None = None) -> dict[str, Any]:
        hole_cards = None
        if viewer_seat == self.seat or self.revealed:
            hole_cards = [str(card) for card in self.hole_cards]
        return {
            "seat": self.seat,
            "name": self.name,
            "stack_start": self.stack_start,
            "stack_end": self.stack_end,
            "commitment": self.commitment,
            "winnings": self.winnings,
            "folded": self.folded,
            "all_in": self.all_in,
            "hole_cards": hole_cards,
            "revealed": self.revealed or viewer_seat == self.seat,
            "hand_rank": self.hand_rank if hole_cards is not None else None,
        }


@dataclass(slots=True)
class HandHistory:
    session_id: str
    hand_no: int
    button_seat: int
    blind_seats: dict[str, int]
    board: tuple[Card, ...]
    burned: tuple[Card, ...]
    actions: list[ActionRecord]
    pots: list[PotSlice]
    awards: list[PotAward]
    seat_results: dict[int, SeatSnapshot]
    street_reached: Street
    winner_seats: tuple[int, ...]

    def public_projection(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "hand_no": self.hand_no,
            "button_seat": self.button_seat,
            "blind_seats": self.blind_seats,
            "board": [str(card) for card in self.board],
            "actions": [action.to_dict() for action in self.actions],
            "pots": [pot.to_dict() for pot in self.pots],
            "awards": [award.to_dict() for award in self.awards],
            "seat_results": {
                seat: snapshot.projection()
                for seat, snapshot in self.seat_results.items()
            },
            "street_reached": self.street_reached.value,
            "winner_seats": list(self.winner_seats),
        }

    def seat_projection(self, seat: int) -> dict[str, Any]:
        public = self.public_projection()
        public["seat_results"] = {
            target_seat: snapshot.projection(viewer_seat=seat)
            for target_seat, snapshot in self.seat_results.items()
        }
        return public

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "hand_no": self.hand_no,
            "button_seat": self.button_seat,
            "blind_seats": self.blind_seats,
            "board": [str(card) for card in self.board],
            "burned": [str(card) for card in self.burned],
            "actions": [action.to_dict() for action in self.actions],
            "pots": [pot.to_dict() for pot in self.pots],
            "awards": [award.to_dict() for award in self.awards],
            "seat_results": {
                seat: {
                    **snapshot.projection(viewer_seat=seat),
                    "hole_cards": [str(card) for card in snapshot.hole_cards],
                    "revealed": snapshot.revealed,
                    "hand_rank": snapshot.hand_rank,
                }
                for seat, snapshot in self.seat_results.items()
            },
            "street_reached": self.street_reached.value,
            "winner_seats": list(self.winner_seats),
        }


@dataclass(slots=True)
class PublicTableState:
    street: Street
    board: tuple[Card, ...]
    pot: int
    current_bet: int
    button_seat: int
    visible_stacks: dict[int, int]
    actions: list[ActionRecord]

    def to_dict(self) -> dict[str, Any]:
        return {
            "street": self.street.value,
            "board": [str(card) for card in self.board],
            "pot": self.pot,
            "current_bet": self.current_bet,
            "button_seat": self.button_seat,
            "visible_stacks": self.visible_stacks,
            "actions": [action.to_dict() for action in self.actions],
        }


@dataclass(slots=True)
class SeatView:
    seat: int
    player_name: str
    session_id: str
    hand_no: int
    hole_cards: tuple[Card, Card]
    stack: int
    to_call: int
    legal_actions: list[LegalAction]
    table: PublicTableState
    session_memory: list[str]

    def to_prompt_payload(self) -> dict[str, Any]:
        return {
            "seat": self.seat,
            "player_name": self.player_name,
            "hole_cards": [str(card) for card in self.hole_cards],
            "stack": self.stack,
            "to_call": self.to_call,
            "legal_actions": [action.to_dict() for action in self.legal_actions],
            "table": self.table.to_dict(),
            "session_memory": list(self.session_memory),
        }


@dataclass(slots=True)
class BankrollEvent:
    seat: int
    event_type: str
    amount: int
    hand_no: int | None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "seat": self.seat,
            "event_type": self.event_type,
            "amount": self.amount,
            "hand_no": self.hand_no,
            "meta": self.meta,
        }


@dataclass(slots=True)
class BankrollLedger:
    events: list[BankrollEvent] = field(default_factory=list)

    def record(self, event: BankrollEvent) -> None:
        self.events.append(event)

    def seat_events(self, seat: int) -> list[BankrollEvent]:
        return [event for event in self.events if event.seat == seat]

    def to_dict(self) -> list[dict[str, Any]]:
        return [event.to_dict() for event in self.events]


@dataclass(slots=True)
class PlayerState:
    seat: int
    name: str
    controller: str
    stack: int
    hole_cards: tuple[Card, Card] | None = None
    folded: bool = False
    all_in: bool = False
    street_commitment: int = 0
    total_commitment: int = 0
    stack_at_hand_start: int = 0
    has_acted: bool = False
    bet_faced: int = 0

    def reset_for_hand(self) -> None:
        self.hole_cards = None
        self.folded = False
        self.all_in = False
        self.street_commitment = 0
        self.total_commitment = 0
        self.stack_at_hand_start = self.stack
        self.has_acted = False
        self.bet_faced = 0


@dataclass(slots=True)
class RefereeState:
    session_id: str
    hand_no: int
    street: Street
    button_seat: int
    small_blind_seat: int
    big_blind_seat: int
    seats: dict[int, PlayerState]
    board: list[Card] = field(default_factory=list)
    burned: list[Card] = field(default_factory=list)
    deck: list[Card] = field(default_factory=list)
    current_bet: int = 0
    last_full_raise_size: int = 0
    pending_to_act: list[int] = field(default_factory=list)
    actions: list[ActionRecord] = field(default_factory=list)
    hand_complete: bool = False

    @property
    def pot(self) -> int:
        return sum(seat.total_commitment for seat in self.seats.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "hand_no": self.hand_no,
            "street": self.street.value,
            "button_seat": self.button_seat,
            "small_blind_seat": self.small_blind_seat,
            "big_blind_seat": self.big_blind_seat,
            "board": [str(card) for card in self.board],
            "burned": [str(card) for card in self.burned],
            "current_bet": self.current_bet,
            "last_full_raise_size": self.last_full_raise_size,
            "pending_to_act": list(self.pending_to_act),
            "actions": [action.to_dict() for action in self.actions],
        }


def dataclass_to_dict(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    return value

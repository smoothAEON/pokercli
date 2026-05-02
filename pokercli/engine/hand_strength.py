from __future__ import annotations

import hashlib
import random
from collections import Counter
from functools import lru_cache
from typing import Sequence

from pokercli.engine.cards import Card
from pokercli.engine.evaluator import describe_rank, evaluate_cards
from pokercli.engine.models import HandStrength
from pokercli.vendor.holdem_calc import holdem_functions

HAND_STRENGTH_BUCKETS = (
    "high_card",
    "one_pair",
    "two_pair",
    "three_of_a_kind",
    "straight",
    "flush",
    "full_house",
    "four_of_a_kind",
    "straight_flush",
)

_RANK_NAME = {
    14: "Ace",
    13: "King",
    12: "Queen",
    11: "Jack",
    10: "Ten",
    9: "Nine",
    8: "Eight",
    7: "Seven",
    6: "Six",
    5: "Five",
    4: "Four",
    3: "Three",
    2: "Two",
}
_RANK_NAME_PLURAL = {
    14: "Aces",
    13: "Kings",
    12: "Queens",
    11: "Jacks",
    10: "Tens",
    9: "Nines",
    8: "Eights",
    7: "Sevens",
    6: "Sixes",
    5: "Fives",
    4: "Fours",
    3: "Threes",
    2: "Twos",
}
_VENDORED_BUCKET_BY_RANK = {
    0: "high_card",
    1: "one_pair",
    2: "two_pair",
    3: "three_of_a_kind",
    4: "straight",
    5: "flush",
    6: "full_house",
    7: "four_of_a_kind",
    8: "straight_flush",
    9: "straight_flush",
}
_LOCAL_BUCKET_BY_RANK = {
    0: "high_card",
    1: "one_pair",
    2: "two_pair",
    3: "three_of_a_kind",
    4: "straight",
    5: "flush",
    6: "full_house",
    7: "four_of_a_kind",
    8: "straight_flush",
}
_MONTE_CARLO_SAMPLES_BY_BOARD_SIZE = {
    0: 20_000,
    3: 10_000,
}


def compute_hand_strength(hole_cards: tuple[Card, Card], board: Sequence[Card]) -> HandStrength:
    current_rank, current_label, potential_items = _compute_hand_strength_cached(
        tuple(card.code for card in hole_cards),
        tuple(card.code for card in board),
    )
    return HandStrength(
        current_rank=current_rank,
        current_label=current_label,
        potential_by_river=dict(potential_items),
    )


@lru_cache(maxsize=2048)
def _compute_hand_strength_cached(
    hole_codes: tuple[str, str],
    board_codes: tuple[str, ...],
) -> tuple[tuple[int, ...] | None, str, tuple[tuple[str, float], ...]]:
    hole_cards = tuple(Card.from_code(code) for code in hole_codes)
    board_cards = tuple(Card.from_code(code) for code in board_codes)
    current_rank = _current_rank(hole_cards, board_cards)
    current_label = _current_label(hole_cards, board_cards, current_rank)
    potential = _potential_by_river(hole_cards, board_cards, current_rank)
    return current_rank, current_label, tuple(potential.items())


def _current_rank(hole_cards: tuple[Card, Card], board: tuple[Card, ...]) -> tuple[int, ...] | None:
    if len(hole_cards) + len(board) < 5:
        return None
    return evaluate_cards((*hole_cards, *board))


def _current_label(
    hole_cards: tuple[Card, Card],
    board: tuple[Card, ...],
    current_rank: tuple[int, ...] | None,
) -> str:
    if current_rank is None:
        return _describe_hole_cards(hole_cards)
    return describe_rank(current_rank)


def _describe_hole_cards(hole_cards: tuple[Card, Card]) -> str:
    high, low = sorted((hole_cards[0].rank, hole_cards[1].rank), reverse=True)
    if high == low:
        return f"Pocket {_RANK_NAME_PLURAL[high]}"
    suited_suffix = "suited" if hole_cards[0].suit == hole_cards[1].suit else "offsuit"
    return f"{_RANK_NAME[high]}-{_RANK_NAME[low]} {suited_suffix}"


def _potential_by_river(
    hole_cards: tuple[Card, Card],
    board: tuple[Card, ...],
    current_rank: tuple[int, ...] | None,
) -> dict[str, float]:
    if len(board) == 5:
        assert current_rank is not None
        return _one_hot_bucket(_LOCAL_BUCKET_BY_RANK[current_rank[0]])
    vendor_hole_cards = tuple(holdem_functions.Card(card.code) for card in hole_cards)
    vendor_board = [holdem_functions.Card(card.code) for card in board]
    deck = holdem_functions.generate_deck((vendor_hole_cards,), vendor_board or None)
    remaining_cards = 5 - len(board)
    counts: Counter[str] = Counter()
    total = 0
    if len(board) == 4:
        board_iter = holdem_functions.generate_exhaustive_boards(deck, 1, len(board))
    else:
        samples = _MONTE_CARLO_SAMPLES_BY_BOARD_SIZE[len(board)]
        rng = random.Random(_seed_for(hole_cards, board))
        board_iter = (tuple(rng.sample(list(deck), remaining_cards)) for _ in range(samples))
    for remaining_board in board_iter:
        total += 1
        full_board = list(vendor_board)
        full_board.extend(remaining_board)
        suit_histogram, histogram, max_suit = holdem_functions.preprocess_board(full_board)
        result = holdem_functions.detect_hand(vendor_hole_cards, full_board, suit_histogram, histogram, max_suit)
        counts[_VENDORED_BUCKET_BY_RANK[result[0]]] += 1
    return {
        bucket: counts[bucket] / total
        for bucket in HAND_STRENGTH_BUCKETS
    }


def _seed_for(hole_cards: tuple[Card, Card], board: tuple[Card, ...]) -> int:
    payload = "|".join([*(card.code for card in hole_cards), *(card.code for card in board)])
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _one_hot_bucket(bucket: str) -> dict[str, float]:
    return {name: 1.0 if name == bucket else 0.0 for name in HAND_STRENGTH_BUCKETS}

from __future__ import annotations

from collections import Counter
from itertools import combinations
from typing import Iterable, Sequence

from pokercli.engine.cards import Card

HAND_CLASS_NAMES = {
    8: "Straight Flush",
    7: "Four of a Kind",
    6: "Full House",
    5: "Flush",
    4: "Straight",
    3: "Three of a Kind",
    2: "Two Pair",
    1: "One Pair",
    0: "High Card",
}


def _straight_high(ranks: Iterable[int]) -> int | None:
    unique = sorted(set(ranks), reverse=True)
    if 14 in unique:
        unique.append(1)
    run = 1
    best = None
    for index in range(1, len(unique)):
        if unique[index - 1] - 1 == unique[index]:
            run += 1
            if run >= 5:
                best = unique[index - 4]
        elif unique[index - 1] != unique[index]:
            run = 1
    return best


def evaluate_five(cards: Sequence[Card]) -> tuple[int, ...]:
    if len(cards) != 5:
        raise ValueError("evaluate_five expects exactly five cards")
    ranks = sorted((card.rank for card in cards), reverse=True)
    counts = Counter(ranks)
    by_count = sorted(counts.items(), key=lambda item: (item[1], item[0]), reverse=True)
    is_flush = len({card.suit for card in cards}) == 1
    straight_high = _straight_high(ranks)
    if is_flush and straight_high is not None:
        return (8, straight_high)
    if by_count[0][1] == 4:
        quad_rank = by_count[0][0]
        kicker = max(rank for rank in ranks if rank != quad_rank)
        return (7, quad_rank, kicker)
    if by_count[0][1] == 3 and by_count[1][1] == 2:
        return (6, by_count[0][0], by_count[1][0])
    if is_flush:
        return (5, *ranks)
    if straight_high is not None:
        return (4, straight_high)
    if by_count[0][1] == 3:
        trip_rank = by_count[0][0]
        kickers = sorted((rank for rank in ranks if rank != trip_rank), reverse=True)
        return (3, trip_rank, *kickers)
    if by_count[0][1] == 2 and by_count[1][1] == 2:
        high_pair, low_pair = sorted((by_count[0][0], by_count[1][0]), reverse=True)
        kicker = max(rank for rank in ranks if rank not in (high_pair, low_pair))
        return (2, high_pair, low_pair, kicker)
    if by_count[0][1] == 2:
        pair_rank = by_count[0][0]
        kickers = sorted((rank for rank in ranks if rank != pair_rank), reverse=True)
        return (1, pair_rank, *kickers)
    return (0, *ranks)


def evaluate_cards(cards: Sequence[Card]) -> tuple[int, ...]:
    if not 5 <= len(cards) <= 7:
        raise ValueError("evaluate_cards expects between five and seven cards")
    best = None
    for combo in combinations(cards, 5):
        rank = evaluate_five(combo)
        if best is None or rank > best:
            best = rank
    assert best is not None
    return best


_RANK_NAME: dict[int, str] = {
    14: "Ace", 13: "King", 12: "Queen", 11: "Jack", 10: "Ten",
    9: "Nine", 8: "Eight", 7: "Seven", 6: "Six", 5: "Five", 4: "Four", 3: "Three", 2: "Two",
}
_RANK_NAME_PLURAL: dict[int, str] = {
    14: "Aces", 13: "Kings", 12: "Queens", 11: "Jacks", 10: "Tens",
    9: "Nines", 8: "Eights", 7: "Sevens", 6: "Sixes", 5: "Fives", 4: "Fours", 3: "Threes", 2: "Twos",
}


def describe_rank(rank: tuple[int, ...]) -> str:
    hand_class = rank[0]
    if hand_class not in HAND_CLASS_NAMES:
        raise ValueError(f"Unknown hand class: {hand_class}")
    base = HAND_CLASS_NAMES[hand_class]

    if hand_class == 0:  # High Card
        return f"{base}, {_RANK_NAME.get(rank[1], '?')}-high"
    if hand_class == 1:  # One Pair
        return f"{base}, {_RANK_NAME_PLURAL.get(rank[1], '?')}"
    if hand_class == 2:  # Two Pair
        return f"{base}, {_RANK_NAME_PLURAL.get(rank[1], '?')} and {_RANK_NAME_PLURAL.get(rank[2], '?')}"
    if hand_class == 3:  # Three of a Kind
        return f"{base}, {_RANK_NAME_PLURAL.get(rank[1], '?')}"
    if hand_class == 4:  # Straight
        return f"{base}, {_RANK_NAME.get(rank[1], '?')}-high"
    if hand_class == 5:  # Flush
        return f"{base}, {_RANK_NAME.get(rank[1], '?')}-high"
    if hand_class == 6:  # Full House
        return f"{base}, {_RANK_NAME_PLURAL.get(rank[1], '?')} full of {_RANK_NAME_PLURAL.get(rank[2], '?')}"
    if hand_class == 7:  # Four of a Kind
        return f"{base}, {_RANK_NAME_PLURAL.get(rank[1], '?')}"
    if hand_class == 8:  # Straight Flush
        return f"{base}, {_RANK_NAME.get(rank[1], '?')}-high"
    return base

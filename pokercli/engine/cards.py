from __future__ import annotations

from dataclasses import dataclass

RANK_TO_VALUE = {
    "2": 2,
    "3": 3,
    "4": 4,
    "5": 5,
    "6": 6,
    "7": 7,
    "8": 8,
    "9": 9,
    "T": 10,
    "J": 11,
    "Q": 12,
    "K": 13,
    "A": 14,
}
VALUE_TO_RANK = {value: rank for rank, value in RANK_TO_VALUE.items()}
SUITS = ("s", "h", "d", "c")


@dataclass(frozen=True, slots=True, order=True)
class Card:
    rank: int
    suit: str

    def __post_init__(self) -> None:
        if self.rank not in VALUE_TO_RANK:
            raise ValueError(f"Invalid rank: {self.rank}")
        if self.suit not in SUITS:
            raise ValueError(f"Invalid suit: {self.suit}")

    @property
    def code(self) -> str:
        return f"{VALUE_TO_RANK[self.rank]}{self.suit}"

    def __str__(self) -> str:
        return self.code.upper()

    @classmethod
    def from_code(cls, code: str) -> "Card":
        normalized = code.strip().lower()
        if len(normalized) != 2:
            raise ValueError(f"Invalid card code: {code}")
        rank_code, suit = normalized[0].upper(), normalized[1]
        if rank_code not in RANK_TO_VALUE:
            raise ValueError(f"Invalid card rank: {code}")
        return cls(rank=RANK_TO_VALUE[rank_code], suit=suit)


def standard_deck() -> list[Card]:
    return [Card(rank=rank, suit=suit) for suit in SUITS for rank in range(2, 15)]

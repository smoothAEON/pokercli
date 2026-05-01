from __future__ import annotations

import random
import secrets
from abc import ABC, abstractmethod
from typing import MutableSequence, TypeVar

T = TypeVar("T")


class DealerRNG(ABC):
    @abstractmethod
    def shuffle(self, items: MutableSequence[T]) -> None:
        """Shuffle the deck in place."""

    @property
    @abstractmethod
    def seed_value(self) -> int | None:
        """Return the seed when the RNG is reproducible."""


class SystemDealerRNG(DealerRNG):
    def __init__(self) -> None:
        self._rng = secrets.SystemRandom()

    def shuffle(self, items: MutableSequence[T]) -> None:
        self._rng.shuffle(items)

    @property
    def seed_value(self) -> int | None:
        return None


class SeededDealerRNG(DealerRNG):
    def __init__(self, seed: int) -> None:
        self._seed = seed
        self._rng = random.Random(seed)

    def shuffle(self, items: MutableSequence[T]) -> None:
        self._rng.shuffle(items)

    @property
    def seed_value(self) -> int | None:
        return self._seed

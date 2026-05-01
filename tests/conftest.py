from __future__ import annotations

from typing import Iterable

from pokercli.engine.cards import Card


def cards(codes: Iterable[str]) -> tuple[Card, ...]:
    return tuple(Card.from_code(code) for code in codes)

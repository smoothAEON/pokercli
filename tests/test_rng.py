from pokercli.engine import SeededDealerRNG
from pokercli.engine.cards import standard_deck


def test_deck_has_52_unique_cards() -> None:
    deck = standard_deck()
    assert len(deck) == 52
    assert len({card.code for card in deck}) == 52


def test_seeded_rng_is_reproducible() -> None:
    deck_one = standard_deck()
    deck_two = standard_deck()
    SeededDealerRNG(42).shuffle(deck_one)
    SeededDealerRNG(42).shuffle(deck_two)
    assert [card.code for card in deck_one] == [card.code for card in deck_two]

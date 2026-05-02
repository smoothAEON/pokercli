from pokercli.engine import HAND_STRENGTH_BUCKETS, compute_hand_strength

from tests.conftest import cards


def test_preflop_pocket_aces_have_null_current_rank_and_set_making_potential() -> None:
    strength = compute_hand_strength(tuple(cards(["As", "Ah"])), ())

    assert strength.current_rank is None
    assert strength.current_label == "Pocket Aces"
    assert strength.potential_by_river["three_of_a_kind"] > 0
    assert strength.potential_by_river["four_of_a_kind"] > 0
    assert sum(strength.potential_by_river.values()) == 1.0


def test_preflop_suited_connectors_report_suited_label_and_draw_potential() -> None:
    strength = compute_hand_strength(tuple(cards(["7s", "6s"])), ())

    assert strength.current_rank is None
    assert strength.current_label == "Seven-Six suited"
    assert strength.potential_by_river["straight"] > 0
    assert strength.potential_by_river["flush"] > 0
    assert set(strength.potential_by_river) == set(HAND_STRENGTH_BUCKETS)


def test_river_strength_is_one_hot_and_matches_current_rank_bucket() -> None:
    strength = compute_hand_strength(tuple(cards(["As", "Ks"])), tuple(cards(["Qs", "Js", "Ts", "2d", "3c"])))

    assert strength.current_rank == (8, 14)
    assert strength.current_label == "Straight Flush, Ace-high"
    assert strength.potential_by_river["straight_flush"] == 1.0
    assert sum(strength.potential_by_river.values()) == 1.0

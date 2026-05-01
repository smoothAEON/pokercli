"""Comprehensive tests for straights, flushes, royal flushes, straight flushes.

Covers 5-card evaluation, 7-card best-five selection, edge cases, and
rank ordering between hand classes.
"""

import pytest

from pokercli.engine import evaluate_cards
from tests.conftest import cards


# ---------------------------------------------------------------------------
# Royal Flush
# ---------------------------------------------------------------------------

def test_royal_flush_all_suits() -> None:
    """Royal flush (Ace-high straight flush) in every suit."""
    assert evaluate_cards(cards(["As", "Ks", "Qs", "Js", "Ts"])) == (8, 14)
    assert evaluate_cards(cards(["Ah", "Kh", "Qh", "Jh", "Th"])) == (8, 14)
    assert evaluate_cards(cards(["Ad", "Kd", "Qd", "Jd", "Td"])) == (8, 14)
    assert evaluate_cards(cards(["Ac", "Kc", "Qc", "Jc", "Tc"])) == (8, 14)


# ---------------------------------------------------------------------------
# Straight Flush (non-royal) – every possible high card
# ---------------------------------------------------------------------------

def test_straight_flush_king_high() -> None:
    assert evaluate_cards(cards(["Ks", "Qs", "Js", "Ts", "9s"])) == (8, 13)


def test_straight_flush_queen_high() -> None:
    assert evaluate_cards(cards(["Qh", "Jh", "Th", "9h", "8h"])) == (8, 12)


def test_straight_flush_jack_high() -> None:
    assert evaluate_cards(cards(["Jd", "Td", "9d", "8d", "7d"])) == (8, 11)


def test_straight_flush_ten_high() -> None:
    assert evaluate_cards(cards(["Tc", "9c", "8c", "7c", "6c"])) == (8, 10)


def test_straight_flush_nine_high() -> None:
    assert evaluate_cards(cards(["9s", "8s", "7s", "6s", "5s"])) == (8, 9)


def test_straight_flush_eight_high() -> None:
    assert evaluate_cards(cards(["8h", "7h", "6h", "5h", "4h"])) == (8, 8)


def test_straight_flush_seven_high() -> None:
    assert evaluate_cards(cards(["7d", "6d", "5d", "4d", "3d"])) == (8, 7)


def test_straight_flush_six_high() -> None:
    assert evaluate_cards(cards(["6c", "5c", "4c", "3c", "2c"])) == (8, 6)


def test_straight_flush_wheel() -> None:
    """Wheel straight flush: Ace-2-3-4-5 all same suit, 5-high."""
    assert evaluate_cards(cards(["Ac", "2c", "3c", "4c", "5c"])) == (8, 5)


# ---------------------------------------------------------------------------
# Straight Flush from 7 cards
# ---------------------------------------------------------------------------

def test_straight_flush_from_seven_cards() -> None:
    """Straight flush available from 7 cards."""
    # Wheel straight flush: Ah 2h in hole, 3h 4h 5h on board + two bricks
    hand = cards(["Ah", "2h", "3h", "4h", "5h", "9d", "Kc"])
    assert evaluate_cards(hand) == (8, 5)


def test_royal_flush_from_seven_cards() -> None:
    """Royal flush via 5 board cards, ignoring hole cards."""
    hand = cards(["2d", "7c", "As", "Ks", "Qs", "Js", "Ts"])
    assert evaluate_cards(hand) == (8, 14)


def test_straight_flush_beats_regular_flush_in_seven() -> None:
    """When both a straight flush and a regular flush are possible, pick SF."""
    # Board: 6h 7h 8h 9h Ks  → 4 hearts to a straight flush
    # Hole: 5h (completes SF 5-9) + 2h (just a 5th heart for a regular flush)
    # The 5h-6h-7h-8h-9h straight flush (9-high) should be chosen over
    # the junk flush 2h-6h-7h-8h-9h.
    hand = cards(["5h", "2h", "6h", "7h", "8h", "9h", "Ks"])
    assert evaluate_cards(hand) == (8, 9)  # 9-high straight flush


def test_straight_flush_beats_straight_in_seven() -> None:
    """When both a straight flush and a regular straight exist, pick SF."""
    # Board: 6s 7s 8s 9s Td  → 4 spades to a straight flush + Td (part of 7-J straight)
    # Hole: 5s (completes SF 5-9) + Jc (completes straight 7-J)
    hand = cards(["5s", "Jc", "6s", "7s", "8s", "9s", "Td"])
    assert evaluate_cards(hand) == (8, 9)  # 9-high straight flush


# ---------------------------------------------------------------------------
# Straight Flush tie-breaking
# ---------------------------------------------------------------------------

def test_straight_flush_tie_breaker() -> None:
    """Higher straight flush beats lower straight flush."""
    royal = evaluate_cards(cards(["As", "Ks", "Qs", "Js", "Ts"]))
    king_high = evaluate_cards(cards(["Ks", "Qs", "Js", "Ts", "9s"]))
    wheel = evaluate_cards(cards(["Ah", "2h", "3h", "4h", "5h"]))
    assert royal > king_high > wheel


def test_same_straight_flush_different_suits_tie() -> None:
    """Same straight flush in different suits should rank equal."""
    sf_hearts = evaluate_cards(cards(["Ah", "Kh", "Qh", "Jh", "Th"]))
    sf_spades = evaluate_cards(cards(["As", "Ks", "Qs", "Js", "Ts"]))
    assert sf_hearts == sf_spades


# ---------------------------------------------------------------------------
# Flush – various high cards and tie-breaking
# ---------------------------------------------------------------------------

def test_flush_ace_high() -> None:
    assert evaluate_cards(cards(["As", "Ks", "Qs", "Js", "9s"])) == (5, 14, 13, 12, 11, 9)


def test_flush_king_high() -> None:
    assert evaluate_cards(cards(["Kh", "Qh", "Jh", "9h", "8h"])) == (5, 13, 12, 11, 9, 8)


def test_flush_low() -> None:
    assert evaluate_cards(cards(["7d", "5d", "4d", "3d", "2d"])) == (5, 7, 5, 4, 3, 2)


def test_flush_kicker_tie_breaker() -> None:
    """Higher kicker wins flush vs flush."""
    flush_ace_high = evaluate_cards(cards(["As", "Ks", "Qs", "Js", "9s"]))
    flush_king_high = evaluate_cards(cards(["As", "Ks", "Qs", "Js", "8s"]))
    flush_weaker_kicker = evaluate_cards(cards(["As", "Ks", "Qs", "Ts", "9s"]))
    assert flush_ace_high > flush_king_high
    assert flush_ace_high > flush_weaker_kicker


def test_flush_from_seven_cards() -> None:
    """Pick the best flush (highest 5 cards of the suit)."""
    # Board: As 2s 4s 8c Kd
    # Hole: Js Qs → 4 spades on board + 2 in hole = flush
    # But only best 5 count
    hand = cards(["Js", "Qs", "As", "Ks", "Ts", "8c", "Kd"])
    assert evaluate_cards(hand) == (8, 14)  # royal flush!


# ---------------------------------------------------------------------------
# Straight – every high card, including wheel and broadway
# ---------------------------------------------------------------------------

def test_straight_broadway() -> None:
    """Ace-high straight (Broadway)."""
    assert evaluate_cards(cards(["As", "Kd", "Qc", "Jh", "Ts"])) == (4, 14)


def test_straight_king_high() -> None:
    assert evaluate_cards(cards(["Ks", "Qd", "Jc", "Th", "9s"])) == (4, 13)


def test_straight_queen_high() -> None:
    assert evaluate_cards(cards(["Qs", "Jd", "Tc", "9h", "8s"])) == (4, 12)


def test_straight_jack_high() -> None:
    assert evaluate_cards(cards(["Js", "Td", "9c", "8h", "7s"])) == (4, 11)


def test_straight_ten_high() -> None:
    assert evaluate_cards(cards(["Ts", "9d", "8c", "7h", "6s"])) == (4, 10)


def test_straight_nine_high() -> None:
    assert evaluate_cards(cards(["9s", "8d", "7c", "6h", "5s"])) == (4, 9)


def test_straight_eight_high() -> None:
    assert evaluate_cards(cards(["8s", "7d", "6c", "5h", "4s"])) == (4, 8)


def test_straight_seven_high() -> None:
    assert evaluate_cards(cards(["7s", "6d", "5c", "4h", "3s"])) == (4, 7)


def test_straight_six_high() -> None:
    assert evaluate_cards(cards(["6s", "5d", "4c", "3h", "2s"])) == (4, 6)


def test_straight_wheel() -> None:
    """Wheel straight: A-2-3-4-5, 5-high."""
    assert evaluate_cards(cards(["As", "2d", "3c", "4h", "5s"])) == (4, 5)


def test_straight_wheel_no_gap() -> None:
    """Another wheel representation: 5-4-3-2-A."""
    assert evaluate_cards(cards(["5h", "4d", "3c", "2s", "Ah"])) == (4, 5)


def test_ace_cannot_wrap_queen_king_ace_two_three() -> None:
    """Q-K-A-2-3 is NOT a straight (Ace doesn't wrap both ways)."""
    hand = cards(["Qd", "Ks", "Ah", "2c", "3d"])
    result = evaluate_cards(hand)
    assert result[0] != 4  # Not a straight


# ---------------------------------------------------------------------------
# Straight from 7 cards
# ---------------------------------------------------------------------------

def test_straight_from_seven_cards() -> None:
    """Straight extracted from 7 cards."""
    # Hole: 6s 7d, Board: 8h 9c Ts 2d Kc → 10-high straight
    hand = cards(["6s", "7d", "8h", "9c", "Ts", "2d", "Kc"])
    assert evaluate_cards(hand) == (4, 10)


def test_wheel_straight_from_seven_cards() -> None:
    """Wheel straight from 7 cards."""
    # Hole: Ah 2s, Board: 3h 4d 5c 9s Kd
    hand = cards(["Ah", "2s", "3h", "4d", "5c", "9s", "Kd"])
    assert evaluate_cards(hand) == (4, 5)


def test_broadway_from_seven_cards() -> None:
    """Broadway straight from 7 cards."""
    # Board: Ah Kd Qc Jh 2s, Hole: Ts 3d
    hand = cards(["Ts", "3d", "Ah", "Kd", "Qc", "Jh", "2s"])
    assert evaluate_cards(hand) == (4, 14)


def test_multiple_straights_picks_highest() -> None:
    """When 7 cards contain multiple possible straights, pick highest."""
    # Board: 4h 5d 6c 7s 8d (8-high straight, all different suits)
    # Hole: 9d Tc (10-high straight also possible: 6-7-8-9-T)
    # Should pick the ten-high straight
    hand = cards(["9d", "Tc", "4h", "5d", "6c", "7s", "8d"])
    assert evaluate_cards(hand) == (4, 10)


# ---------------------------------------------------------------------------
# Straight tie-breaking
# ---------------------------------------------------------------------------

def test_straight_tie_breaker() -> None:
    """Higher straight beats lower straight."""
    broadway = evaluate_cards(cards(["As", "Kd", "Qc", "Jh", "Ts"]))
    king_high = evaluate_cards(cards(["Ks", "Qd", "Jc", "Th", "9s"]))
    wheel = evaluate_cards(cards(["As", "2d", "3c", "4h", "5s"]))
    assert broadway > king_high > wheel


def test_same_straight_different_suits_tie() -> None:
    """Same straight with different suits ranks equal."""
    straight_a = evaluate_cards(cards(["As", "Kd", "Qc", "Jh", "Ts"]))
    straight_b = evaluate_cards(cards(["Ah", "Ks", "Qd", "Jc", "Th"]))
    assert straight_a == straight_b


# ---------------------------------------------------------------------------
# Hand class ordering (flush vs straight, etc.)
# ---------------------------------------------------------------------------

def test_flush_beats_straight() -> None:
    """A flush beats a straight of any rank."""
    flush = evaluate_cards(cards(["2s", "4s", "6s", "8s", "Ts"]))  # Ten-high flush
    straight = evaluate_cards(cards(["As", "Kd", "Qc", "Jh", "Ts"]))  # Broadway
    assert flush > straight


def test_straight_flush_beats_flush() -> None:
    """A straight flush beats a regular flush."""
    straight_flush = evaluate_cards(cards(["2s", "3s", "4s", "5s", "6s"]))  # 6-high SF
    flush = evaluate_cards(cards(["As", "Ks", "Qs", "Js", "9s"]))  # Ace-high flush
    assert straight_flush > flush


def test_royal_flush_is_highest_hand() -> None:
    """Royal flush beats every other hand class."""
    royal = evaluate_cards(cards(["As", "Ks", "Qs", "Js", "Ts"]))
    quads = evaluate_cards(cards(["As", "Ad", "Ac", "Ah", "Kd"]))
    boat = evaluate_cards(cards(["As", "Ad", "Ac", "Kh", "Kd"]))
    flush = evaluate_cards(cards(["As", "Ks", "Qs", "Js", "9s"]))
    straight = evaluate_cards(cards(["As", "Kd", "Qc", "Jh", "Ts"]))
    assert royal > quads > boat > flush > straight


# ---------------------------------------------------------------------------
# Wheel (A-2-3-4-5) edge cases
# ---------------------------------------------------------------------------

def test_wheel_not_confused_with_broadway() -> None:
    """Wheel should be 5-high, not 14-high."""
    wheel = evaluate_cards(cards(["As", "2s", "3s", "4s", "5s"]))
    assert wheel == (8, 5)  # 5-high straight flush, NOT 14-high


def test_wheel_straight_vs_wheel_straight_flush() -> None:
    """Wheel straight flush beats wheel straight."""
    wheel_sf = evaluate_cards(cards(["As", "2s", "3s", "4s", "5s"]))
    wheel_straight = evaluate_cards(cards(["As", "2d", "3c", "4h", "5s"]))
    assert wheel_sf > wheel_straight


# ---------------------------------------------------------------------------
# Boundary / Edge Cases
# ---------------------------------------------------------------------------

def test_no_straight_when_four_in_a_row() -> None:
    """Four sequential cards + gap is NOT a straight."""
    hand = cards(["5s", "6d", "7c", "8h", "Ts"])  # 5-6-7-8-T, missing 9
    result = evaluate_cards(hand)
    assert result[0] != 4


def test_no_straight_with_paired_board() -> None:
    """A paired board with a gap does not make a straight."""
    hand = cards(["5s", "5d", "6c", "7h", "8s"])  # pair of 5s + 5-6-7-8
    result = evaluate_cards(hand)
    # This is one pair (5s), not a straight (only 4 distinct ranks)
    assert result[0] == 1


def test_flush_beats_straight_even_low_flush() -> None:
    """Even the lowest possible flush beats the highest straight."""
    low_flush = evaluate_cards(cards(["2s", "3s", "4s", "5s", "7s"]))  # 7-high flush
    broadway = evaluate_cards(cards(["As", "Kd", "Qc", "Jh", "Ts"]))  # Ace-high straight
    assert low_flush > broadway


def test_straight_flush_beats_quads() -> None:
    """Straight flush beats four of a kind."""
    sf = evaluate_cards(cards(["2s", "3s", "4s", "5s", "6s"]))
    quads = evaluate_cards(cards(["As", "Ad", "Ac", "Ah", "Kd"]))
    assert sf > quads


def test_straight_flush_on_board_only() -> None:
    """Straight flush entirely on the board, hole cards irrelevant."""
    hand = cards(["2d", "7c", "As", "Ks", "Qs", "Js", "Ts"])
    assert evaluate_cards(hand) == (8, 14)  # royal flush from board


def test_royal_flush_is_ace_high_straight_flush() -> None:
    """Royal flush IS a straight flush (Ace-high). No separate class."""
    royal = evaluate_cards(cards(["As", "Ks", "Qs", "Js", "Ts"]))
    assert royal[0] == 8  # class: Straight Flush
    assert royal[1] == 14  # high card: Ace


@pytest.mark.parametrize(
    "hole,board,expected",
    [
        # Broadway straight flush (royal)
        (["As", "Ks"], ["Qs", "Js", "Ts", "2d", "3c"], (8, 14)),
        # King-high straight flush
        (["Ks", "Qs"], ["Js", "Ts", "9s", "2d", "3c"], (8, 13)),
        # Wheel straight flush
        (["Ah", "2h"], ["3h", "4h", "5h", "9d", "Kc"], (8, 5)),
        # Ten-high straight: hole 6-7, board 8-9-T
        (["6s", "7d"], ["8h", "9c", "Ts", "2d", "Kc"], (4, 10)),
        # Broadway straight: using 4 board + 1 hole
        (["Ts", "3d"], ["Ah", "Kd", "Qc", "Jh", "2s"], (4, 14)),
        # Wheel straight: A-2 hole, 3-4-5 board
        (["Ah", "2s"], ["3h", "4d", "5c", "9s", "Kd"], (4, 5)),
        # Ace-high flush
        (["As", "Ks"], ["Qs", "Js", "2s", "3d", "4c"], (5, 14, 13, 12, 11, 2)),
    ],
)
def test_holdem_hand_combinations(hole, board, expected) -> None:
    """Texas Hold'em style: 2 hole cards + 5 board cards."""
    hand = cards(hole + board)
    assert evaluate_cards(hand) == expected

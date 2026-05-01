from pokercli.engine import evaluate_cards

from tests.conftest import cards


def test_evaluate_known_hand_classes() -> None:
    assert evaluate_cards(cards(["Ac", "Kc", "Qc", "Jc", "Tc"])) == (8, 14)
    assert evaluate_cards(cards(["As", "Ad", "Ac", "Ah", "Kd"])) == (7, 14, 13)
    assert evaluate_cards(cards(["As", "Ad", "Ac", "Kh", "Kd"])) == (6, 14, 13)
    assert evaluate_cards(cards(["As", "Js", "9s", "4s", "2s"])) == (5, 14, 11, 9, 4, 2)
    assert evaluate_cards(cards(["As", "2d", "3c", "4h", "5s"])) == (4, 5)
    assert evaluate_cards(cards(["As", "Ad", "Ac", "Kh", "Qd"])) == (3, 14, 13, 12)
    assert evaluate_cards(cards(["As", "Ad", "Kh", "Kd", "Qd"])) == (2, 14, 13, 12)
    assert evaluate_cards(cards(["As", "Ad", "Kh", "Qd", "9c"])) == (1, 14, 13, 12, 9)
    assert evaluate_cards(cards(["As", "Kd", "Qc", "9h", "4d"])) == (0, 14, 13, 12, 9, 4)


def test_evaluate_seven_cards_chooses_best_five() -> None:
    rank = evaluate_cards(cards(["As", "Ad", "Ac", "Kh", "Kd", "2c", "3d"]))
    assert rank == (6, 14, 13)

from pokercli.engine import ActionDecision, ActionType, GameConfig, PokerGame, Street

from tests.conftest import cards


def _assert_all_in_seat_is_skipped(target_seat: int, expected_pending_on_flop: list[int]) -> None:
    game = PokerGame(GameConfig(seat_count=3, small_blind=50, big_blind=100, starting_stack=500))
    if target_seat in {0, 1}:
        game.seats[target_seat].stack = 150
    else:
        game.seats[target_seat].stack = 250
    game.start_hand()

    if target_seat == 0:
        game.apply_action(0, ActionDecision(ActionType.ALL_IN))
        game.apply_action(1, ActionDecision(ActionType.CALL))
        game.apply_action(2, ActionDecision(ActionType.CALL))
    elif target_seat == 1:
        game.apply_action(0, ActionDecision(ActionType.CALL))
        game.apply_action(1, ActionDecision(ActionType.ALL_IN))
        game.apply_action(2, ActionDecision(ActionType.CALL))
        game.apply_action(0, ActionDecision(ActionType.CALL))
    else:
        game.apply_action(0, ActionDecision(ActionType.RAISE, amount=300))
        game.apply_action(1, ActionDecision(ActionType.CALL))
        game.apply_action(2, ActionDecision(ActionType.CALL))

    state = game.require_state()
    assert state.street == Street.FLOP
    assert state.pending_to_act == expected_pending_on_flop
    assert game.seats[target_seat].all_in is True
    assert game.legal_actions_for(target_seat) == []

    while not state.hand_complete:
        if not state.pending_to_act:
            game._auto_advance_if_no_decisions()  # noqa: SLF001
        else:
            acting_seat = state.pending_to_act[0]
            assert acting_seat != target_seat
            game.apply_action(acting_seat, ActionDecision(ActionType.CHECK))
        state = game.require_state()

    assert game.hand_histories[-1].street_reached == Street.SHOWDOWN


def test_heads_up_blind_order_and_preflop_order() -> None:
    game = PokerGame(GameConfig(seat_count=2, small_blind=50, big_blind=100, starting_stack=1_000))
    state = game.start_hand()
    assert state.button_seat == 0
    assert state.small_blind_seat == 0
    assert state.big_blind_seat == 1
    assert state.pending_to_act == [0, 1]


def test_call_call_check_advances_to_flop() -> None:
    game = PokerGame(GameConfig(seat_count=3, small_blind=50, big_blind=100, starting_stack=1_000))
    state = game.start_hand()
    assert state.pending_to_act == [0, 1, 2]
    game.apply_action(0, ActionDecision(ActionType.CALL))
    game.apply_action(1, ActionDecision(ActionType.CALL))
    game.apply_action(2, ActionDecision(ActionType.CHECK))
    state = game.require_state()
    assert state.street == Street.FLOP
    assert len(state.board) == 3
    assert state.current_bet == 0


def test_heads_up_all_in_runs_to_showdown_when_no_seat_has_live_stack() -> None:
    game = PokerGame(GameConfig(seat_count=2, small_blind=50, big_blind=100, starting_stack=1_000))
    state = game.start_hand()
    state.seats[0].hole_cards = cards(["As", "Ad"])
    state.seats[1].hole_cards = cards(["Ks", "Kd"])
    state.deck[:] = list(cards(["5c", "2c", "7d", "9h", "6d", "Jc", "8s", "3s"]))

    game.apply_action(0, ActionDecision(ActionType.RAISE, amount=1_000))
    game.apply_action(1, ActionDecision(ActionType.CALL))

    state = game.require_state()
    history = game.hand_histories[-1]
    assert state.hand_complete is True
    assert history.board == cards(["2c", "7d", "9h", "Jc", "3s"])
    assert history.street_reached == Street.SHOWDOWN
    assert history.winner_seats == (0,)
    assert game.seats[0].stack == 2_000
    assert game.seats[1].stack == 0


def test_all_in_seat_zero_is_skipped_for_future_actions() -> None:
    _assert_all_in_seat_is_skipped(0, [1, 2])


def test_all_in_seat_one_is_skipped_for_future_actions() -> None:
    _assert_all_in_seat_is_skipped(1, [2, 0])


def test_all_in_seat_two_is_skipped_for_future_actions() -> None:
    _assert_all_in_seat_is_skipped(2, [1, 0])


def test_short_all_in_does_not_reopen_betting() -> None:
    game = PokerGame(GameConfig(seat_count=3, small_blind=50, big_blind=100, starting_stack=500))
    game.seats[2].stack = 350
    game.start_hand()
    game.apply_action(0, ActionDecision(ActionType.RAISE, amount=300))
    game.apply_action(1, ActionDecision(ActionType.CALL))
    game.apply_action(2, ActionDecision(ActionType.ALL_IN))
    legal_actions = {action.action for action in game.legal_actions_for(0)}
    assert legal_actions == {ActionType.FOLD, ActionType.CALL}


def test_side_pot_settlement_awards_correct_winners() -> None:
    game = PokerGame(GameConfig(seat_count=3, starting_stack=1_000))
    state = game.start_hand()
    state.board[:] = list(cards(["Kc", "Kh", "2d", "3s", "4c"]))
    state.seats[0].hole_cards = cards(["As", "Ad"])
    state.seats[1].hole_cards = cards(["Qs", "Qd"])
    state.seats[2].hole_cards = cards(["5d", "6d"])
    state.seats[0].stack = 700
    state.seats[1].stack = 800
    state.seats[2].stack = 900
    state.seats[0].total_commitment = 300
    state.seats[1].total_commitment = 200
    state.seats[2].total_commitment = 100
    settlement = game._settle()  # noqa: SLF001
    assert settlement.winners == (0, 2)
    assert state.seats[0].stack == 1_000
    assert state.seats[1].stack == 800
    assert state.seats[2].stack == 1_200


def test_odd_chip_goes_left_of_button() -> None:
    game = PokerGame(GameConfig(seat_count=3, starting_stack=100))
    state = game.start_hand()
    state.button_seat = 2
    state.board[:] = list(cards(["As", "Kd", "Qc", "Jh", "9d"]))
    state.seats[0].hole_cards = cards(["Tc", "2c"])
    state.seats[1].hole_cards = cards(["Ts", "3d"])
    state.seats[2].hole_cards = cards(["2h", "2d"])
    for seat in range(3):
        state.seats[seat].stack = 95
        state.seats[seat].total_commitment = 5
        state.seats[seat].folded = False
    settlement = game._settle()  # noqa: SLF001
    awards = {(award.seat, award.amount, award.reason) for award in settlement.awards}
    assert (0, 7, "showdown") in awards
    assert (1, 7, "showdown") in awards
    assert (0, 1, "odd-chip") in awards


def test_odd_chip_goes_left_of_button_when_all_players_are_all_in() -> None:
    game = PokerGame(GameConfig(seat_count=3, starting_stack=100))
    state = game.start_hand()
    state.button_seat = 2
    state.board[:] = list(cards(["As", "Kd", "Qc", "Jh", "9d"]))
    state.seats[0].hole_cards = cards(["Tc", "2c"])
    state.seats[1].hole_cards = cards(["Ts", "3d"])
    state.seats[2].hole_cards = cards(["2h", "2d"])
    for seat in range(3):
        state.seats[seat].stack = 0
        state.seats[seat].total_commitment = 5
        state.seats[seat].folded = False
        state.seats[seat].all_in = True
    settlement = game._settle()  # noqa: SLF001
    awards = {(award.seat, award.amount, award.reason) for award in settlement.awards}
    assert settlement.winners == (0, 1)
    assert (0, 7, "showdown") in awards
    assert (1, 7, "showdown") in awards
    assert (0, 1, "odd-chip") in awards
    assert state.seats[0].stack == 8
    assert state.seats[1].stack == 7
    assert state.seats[2].stack == 0


def test_busted_player_stale_state_does_not_leak_into_next_hand() -> None:
    game = PokerGame(GameConfig(seat_count=3, starting_stack=500))
    game.start_hand()
    game.seats[1].stack = 0
    game.seats[1].total_commitment = 8450
    game.seats[1].street_commitment = 8450
    game.seats[1].all_in = True
    game.seats[1].hole_cards = cards(["9c", "9s"])
    game.seats[1].stack_at_hand_start = 8450
    game.seats[1].folded = False

    state2 = game.start_hand()

    assert game.seats[1].hole_cards is None
    assert game.seats[1].total_commitment == 0
    assert game.seats[1].street_commitment == 0
    assert game.seats[1].all_in is False
    assert game.seats[1].stack_at_hand_start == 0

    pots = game._side_pots()  # noqa: SLF001
    for pot in pots:
        assert 1 not in pot.eligible_seats, f"busted seat 1 should not be in pot {pot.index}"

    contenders = [s for s, p in state2.seats.items() if p.hole_cards is not None and not p.folded]
    assert 1 not in contenders


def test_can_start_hand_false_when_fewer_than_two_live() -> None:
    from pokercli.engine.game import PokerRuleError

    game = PokerGame(GameConfig(seat_count=3, starting_stack=500))
    game.seats[1].stack = 0
    game.seats[2].stack = 0
    assert game.can_start_hand() is False
    try:
        game.start_hand()
        raise AssertionError("Expected PokerRuleError")
    except PokerRuleError:
        pass


def test_live_seats_excludes_busted_players() -> None:
    game = PokerGame(GameConfig(seat_count=3, starting_stack=500))
    assert game.live_seats() == [0, 1, 2]
    game.seats[1].stack = 0
    assert game.live_seats() == [0, 2]
    game.seats[0].stack = 0
    assert game.live_seats() == [2]


def test_start_hand_resets_all_players_not_just_live_ones() -> None:
    game = PokerGame(GameConfig(seat_count=3, starting_stack=500))
    game.seats[1].stack = 0
    game.seats[1].hole_cards = cards(["As", "Ad"])
    game.seats[1].all_in = True
    game.seats[1].total_commitment = 500
    game.seats[1].street_commitment = 500
    game.seats[1].stack_at_hand_start = 8450
    game.seats[1].folded = False

    game.start_hand()

    assert game.seats[1].hole_cards is None
    assert game.seats[1].all_in is False
    assert game.seats[1].total_commitment == 0
    assert game.seats[1].street_commitment == 0
    assert game.seats[1].stack_at_hand_start == 0
    assert game.seats[1].folded is False

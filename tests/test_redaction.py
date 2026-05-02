from pokercli.engine import GameConfig, PokerGame


def test_public_projection_hides_unrevealed_hole_cards() -> None:
    game = PokerGame(GameConfig(seat_count=2, starting_stack=1_000))
    state = game.start_hand()
    state.seats[1].folded = True
    game._complete_hand()  # noqa: SLF001
    history = game.hand_histories[-1]
    public = history.public_projection()
    seat_zero_view = history.seat_projection(0)
    # Winner's cards are revealed (last-player-standing counts as revealed)
    assert public["seat_results"][0]["hole_cards"] is not None
    # Folded non-winner's cards remain hidden in public view
    assert public["seat_results"][1]["hole_cards"] is None
    # Seat 0 can always see their own cards
    assert seat_zero_view["seat_results"][0]["hole_cards"] is not None
    # Seat 0 cannot see folded opponent's cards
    assert seat_zero_view["seat_results"][1]["hole_cards"] is None


def test_private_seat_view_includes_only_own_hand_strength() -> None:
    game = PokerGame(GameConfig(seat_count=2, starting_stack=1_000, seed=7))
    game.start_hand()
    seat_zero_view = game.build_seat_view(0).to_prompt_payload()
    seat_one_view = game.build_seat_view(1).to_prompt_payload()

    assert "hand_strength" in seat_zero_view
    assert "hand_strength" in seat_one_view
    assert "hole_cards" not in seat_zero_view["table"]
    assert "hand_strength" not in seat_zero_view["table"]
    assert seat_zero_view["hand_strength"] != seat_one_view["hand_strength"]

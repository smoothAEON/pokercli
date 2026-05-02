from __future__ import annotations

import time

from pokercli.vendor.holdem_calc import holdem_argparser, holdem_functions


def main() -> None:
    hole_cards, num, exact, board, file_name = holdem_argparser.parse_args()
    run(hole_cards, num, exact, board, file_name, True)


def calculate(board, exact, num, input_file, hole_cards, verbose):
    args = holdem_argparser.LibArgs(board, exact, num, input_file, hole_cards)
    hole_cards, n, e, board, filename = holdem_argparser.parse_lib_args(args)
    return run(hole_cards, n, e, board, filename, verbose)


def run(hole_cards, num, exact, board, file_name, verbose):
    if file_name:
        with open(file_name, "r", encoding="utf-8") as input_file:
            for line in input_file:
                if line is not None and len(line.strip()) == 0:
                    continue
                hole_cards, board = holdem_argparser.parse_file_args(line)
                deck = holdem_functions.generate_deck(hole_cards, board)
                run_simulation(hole_cards, num, exact, board, deck, verbose)
                print("-----------------------------------")
        return None
    deck = holdem_functions.generate_deck(hole_cards, board)
    return run_simulation(hole_cards, num, exact, board, deck, verbose)


def run_simulation(hole_cards, num, exact, given_board, deck, verbose):
    num_players = len(hole_cards)
    result_histograms, winner_list = [], [0] * (num_players + 1)
    for _ in range(num_players):
        result_histograms.append([0] * len(holdem_functions.hand_rankings))
    board_length = 0 if given_board is None else len(given_board)
    if exact or given_board is not None:
        generate_boards = holdem_functions.generate_exhaustive_boards
    else:
        generate_boards = holdem_functions.generate_random_boards
    if (None, None) in hole_cards:
        hole_cards_list = list(hole_cards)
        unknown_index = hole_cards.index((None, None))
        for filler_hole_cards in holdem_functions.generate_hole_cards(deck):
            hole_cards_list[unknown_index] = filler_hole_cards
            deck_list = list(deck)
            deck_list.remove(filler_hole_cards[0])
            deck_list.remove(filler_hole_cards[1])
            holdem_functions.find_winner(
                generate_boards,
                tuple(deck_list),
                tuple(hole_cards_list),
                num,
                board_length,
                given_board,
                winner_list,
                result_histograms,
            )
    else:
        holdem_functions.find_winner(generate_boards, deck, hole_cards, num, board_length, given_board, winner_list, result_histograms)
    if verbose:
        holdem_functions.print_results(hole_cards, winner_list, result_histograms)
    return holdem_functions.find_winning_percentage(winner_list)


if __name__ == "__main__":
    start = time.time()
    main()
    print("\nTime elapsed(seconds): ", time.time() - start)

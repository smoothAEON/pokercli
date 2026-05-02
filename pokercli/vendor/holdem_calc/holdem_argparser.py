from __future__ import annotations

import argparse
import re

from pokercli.vendor.holdem_calc import holdem_functions


class LibArgs:
    def __init__(self, board, exact, num, input_file, hole_cards) -> None:
        self.board = board
        self.cards = hole_cards
        self.n = num
        self.input = input_file
        self.exact = exact


def parse_lib_args(args):
    error_check_arguments(args)
    hole_cards, board = None, None
    if not args.input:
        hole_cards, board = parse_cards(args.cards, args.board)
    return hole_cards, args.n, args.exact, board, args.input


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Find the odds that a Texas Hold'em hand will win. Cards must be given "
            "in the following format: As, Jc, Td, 3h."
        )
    )
    parser.add_argument("cards", nargs="*", type=str, metavar="hole card", help="Hole cards you want to find the odds for.")
    parser.add_argument("-b", "--board", nargs="*", type=str, metavar="card", help="Add board cards")
    parser.add_argument("-e", "--exact", action="store_true", help="Find exact odds by enumerating every possible board")
    parser.add_argument("-n", type=int, default=100000, help="Run N Monte Carlo simulations")
    parser.add_argument(
        "-i",
        "--input",
        type=str,
        help="Read hole cards and boards from an input file. Commandline arguments for hole cards and board will be ignored",
    )
    args = parser.parse_args()
    error_check_arguments(args)
    hole_cards, board = None, None
    if not args.input:
        hole_cards, board = parse_cards(args.cards, args.board)
    return hole_cards, args.n, args.exact, board, args.input


def parse_file_args(line):
    if line is None or len(line) == 0:
        raise SystemExit("Invalid format")
    values = line.split("|")
    if len(values) > 2 or len(values) < 1:
        raise SystemExit("Invalid format")
    hole_cards = values[0].split()
    all_cards = list(hole_cards)
    board = None
    if len(values) == 2:
        board = values[1].split()
        all_cards.extend(board)
    error_check_cards(all_cards)
    return parse_cards(hole_cards, board)


def parse_cards(cards, board):
    hole_cards = create_hole_cards(cards)
    if board:
        board = parse_board(board)
    return hole_cards, board


def error_check_arguments(args):
    if args.n <= 0:
        raise SystemExit("Number of Monte Carlo simulations must be positive.")
    if args.input:
        file_name = args.input
        try:
            with open(file_name, "r", encoding="utf-8"):
                pass
        except OSError as exc:
            raise SystemExit(f"Error opening file {file_name}") from exc
    all_cards = list(args.cards)
    if args.board:
        all_cards.extend(args.board)
    error_check_cards(all_cards)


def error_check_cards(all_cards):
    card_re = re.compile(r"[AKQJT98765432][scdh]")
    for card in all_cards:
        if card != "?" and not card_re.match(card):
            raise SystemExit("Invalid card given.")
        if all_cards.count(card) != 1 and card != "?":
            raise SystemExit("The cards given must be unique.")


def create_hole_cards(raw_hole_cards):
    if raw_hole_cards is None or len(raw_hole_cards) < 2 or len(raw_hole_cards) % 2:
        raise SystemExit("You must provide a non-zero even number of hole cards")
    hole_cards, current_hole_cards = [], []
    for hole_card in raw_hole_cards:
        if hole_card != "?":
            current_card = holdem_functions.Card(hole_card)
            current_hole_cards.append(current_card)
        else:
            current_hole_cards.append(None)
        if len(current_hole_cards) == 2:
            if None in current_hole_cards and (current_hole_cards[0] is not None or current_hole_cards[1] is not None):
                raise SystemExit("Unknown hole cards must come in pairs")
            hole_cards.append((current_hole_cards[0], current_hole_cards[1]))
            current_hole_cards = []
    if hole_cards.count((None, None)) > 1:
        raise SystemExit("Can only have one set of unknown hole cards")
    return tuple(hole_cards)


def parse_board(board):
    if len(board) > 5 or len(board) < 3:
        raise SystemExit("Board must have a length of 3, 4, or 5.")
    if "?" in board:
        raise SystemExit("Board cannot have unknown cards")
    return create_cards(board)


def create_cards(card_strings):
    return [holdem_functions.Card(arg) for arg in card_strings]

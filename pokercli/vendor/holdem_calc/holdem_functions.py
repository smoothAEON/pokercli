from __future__ import annotations

import itertools
import random
import time

suit_index_dict = {"s": 0, "c": 1, "h": 2, "d": 3}
reverse_suit_index = ("s", "c", "h", "d")
val_string = "AKQJT98765432"
hand_rankings = (
    "High Card",
    "Pair",
    "Two Pair",
    "Three of a Kind",
    "Straight",
    "Flush",
    "Full House",
    "Four of a Kind",
    "Straight Flush",
    "Royal Flush",
)
suit_value_dict = {"T": 10, "J": 11, "Q": 12, "K": 13, "A": 14}
for num in range(2, 10):
    suit_value_dict[str(num)] = num


class Card:
    def __init__(self, card_string: str) -> None:
        value, self.suit = card_string[0], card_string[1]
        self.value = suit_value_dict[value.upper()]
        self.suit_index = suit_index_dict[self.suit]

    def __str__(self) -> str:
        return val_string[14 - self.value] + self.suit

    def __repr__(self) -> str:
        return val_string[14 - self.value] + self.suit

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Card):
            return False
        return self.value == other.value and self.suit == other.suit

    def __hash__(self) -> int:
        return hash((self.value, self.suit))


def generate_deck(hole_cards, board):
    deck = []
    for suit in reverse_suit_index:
        for value in val_string:
            deck.append(Card(value + suit))
    taken_cards = []
    for hole_card in hole_cards:
        for card in hole_card:
            if card is not None:
                taken_cards.append(card)
    if board and len(board) > 0:
        taken_cards.extend(board)
    for taken_card in taken_cards:
        deck.remove(taken_card)
    return tuple(deck)


def generate_hole_cards(deck):
    return itertools.combinations(deck, 2)


def generate_random_boards(deck, num_iterations, board_length):
    rng = random.Random(time.time())
    for _ in range(num_iterations):
        yield rng.sample(list(deck), 5 - board_length)


def generate_exhaustive_boards(deck, num_iterations, board_length):
    return itertools.combinations(deck, 5 - board_length)


def generate_suit_board(flat_board, flush_index):
    histogram = [card.value for card in flat_board if card.suit_index == flush_index]
    histogram.sort(reverse=True)
    return histogram


def preprocess(histogram):
    return [(14 - index, frequency) for index, frequency in enumerate(histogram) if frequency]


def preprocess_board(flat_board):
    suit_histogram, histogram = [0] * 4, [0] * 13
    for card in flat_board:
        histogram[14 - card.value] += 1
        suit_histogram[card.suit_index] += 1
    return suit_histogram, histogram, max(suit_histogram)


def detect_straight_flush(suit_board):
    contiguous_length, fail_index = 1, len(suit_board) - 5
    for index, elem in enumerate(suit_board[:-1]):
        current_val, next_val = elem, suit_board[index + 1]
        if next_val == current_val - 1:
            contiguous_length += 1
            if contiguous_length == 5:
                return True, current_val + 3
        else:
            if index >= fail_index:
                if index == fail_index and next_val == 5 and suit_board[0] == 14:
                    return True, 5
                break
            contiguous_length = 1
    return (False,)


def detect_highest_quad_kicker(histogram_board):
    for elem in histogram_board:
        if elem[1] < 4:
            return elem[0]
    return None


def detect_straight(histogram_board):
    contiguous_length, fail_index = 1, len(histogram_board) - 5
    for index, elem in enumerate(histogram_board[:-1]):
        current_val, next_val = elem[0], histogram_board[index + 1][0]
        if next_val == current_val - 1:
            contiguous_length += 1
            if contiguous_length == 5:
                return True, current_val + 3
        else:
            if index >= fail_index:
                if index == fail_index and next_val == 5 and histogram_board[0][0] == 14:
                    return True, 5
                break
            contiguous_length = 1
    return (False,)


def detect_three_of_a_kind_kickers(histogram_board):
    kicker1 = -1
    for elem in histogram_board:
        if elem[1] != 3:
            if kicker1 == -1:
                kicker1 = elem[0]
            else:
                return kicker1, elem[0]
    return None


def detect_highest_kicker(histogram_board):
    for elem in histogram_board:
        if elem[1] == 1:
            return elem[0]
    return None


def detect_pair_kickers(histogram_board):
    kicker1, kicker2 = -1, -1
    for elem in histogram_board:
        if elem[1] != 2:
            if kicker1 == -1:
                kicker1 = elem[0]
            elif kicker2 == -1:
                kicker2 = elem[0]
            else:
                return kicker1, kicker2, elem[0]
    return None


def get_high_cards(histogram_board):
    return histogram_board[:5]


def detect_hand(hole_cards, given_board, suit_histogram, full_histogram, max_suit):
    if max_suit >= 3:
        flush_index = suit_histogram.index(max_suit)
        adjusted_max_suit = max_suit
        for hole_card in hole_cards:
            if hole_card.suit_index == flush_index:
                adjusted_max_suit += 1
        if adjusted_max_suit >= 5:
            flat_board = list(given_board)
            flat_board.extend(hole_cards)
            suit_board = generate_suit_board(flat_board, flush_index)
            result = detect_straight_flush(suit_board)
            if result[0]:
                return (8, result[1]) if result[1] != 14 else (9,)
            return 5, get_high_cards(suit_board)

    full_histogram = full_histogram[:]
    for hole_card in hole_cards:
        full_histogram[14 - hole_card.value] += 1
    histogram_board = preprocess(full_histogram)

    current_max, max_val, second_max, second_max_val = 0, 0, 0, 0
    for item in histogram_board:
        val, frequency = item[0], item[1]
        if frequency > current_max:
            second_max, second_max_val = current_max, max_val
            current_max, max_val = frequency, val
        elif frequency > second_max:
            second_max, second_max_val = frequency, val

    if current_max == 4:
        return 7, max_val, detect_highest_quad_kicker(histogram_board)
    if current_max == 3 and second_max >= 2:
        return 6, max_val, second_max_val
    if len(histogram_board) >= 5:
        result = detect_straight(histogram_board)
        if result[0]:
            return 4, result[1]
    if current_max == 3:
        return 3, max_val, detect_three_of_a_kind_kickers(histogram_board)
    if current_max == 2:
        if second_max == 2:
            return 2, max_val, second_max_val, detect_highest_kicker(histogram_board)
        return 1, max_val, detect_pair_kickers(histogram_board)
    return 0, get_high_cards(histogram_board)


def compare_hands(result_list):
    best_hand = max(result_list)
    winning_player_index = result_list.index(best_hand) + 1
    if best_hand in result_list[winning_player_index:]:
        return 0
    return winning_player_index


def print_results(hole_cards, winner_list, result_histograms):
    float_iterations = float(sum(winner_list))
    print("Winning Percentages:")
    for index, hole_card in enumerate(hole_cards):
        winning_percentage = float(winner_list[index + 1]) / float_iterations
        if hole_card == (None, None):
            print("(?, ?) : ", winning_percentage)
        else:
            print(f"{hole_card} : ", winning_percentage)
    print("Ties: ", float(winner_list[0]) / float_iterations, "\n")
    for player_index, histogram in enumerate(result_histograms):
        print(f"Player{player_index + 1} Histogram: ")
        for index, elem in enumerate(histogram):
            print(hand_rankings[index], ": ", float(elem) / float_iterations)
        print()


def find_winning_percentage(winner_list):
    float_iterations = float(sum(winner_list))
    percentages = []
    for num_wins in winner_list:
        winning_percentage = float(num_wins) / float_iterations
        percentages.append(winning_percentage)
    return percentages


def find_winner(generate_boards, deck, hole_cards, num, board_length, given_board, winner_list, result_histograms):
    result_list = [None] * len(hole_cards)
    for remaining_board in generate_boards(deck, num, board_length):
        if given_board:
            board = given_board[:]
            board.extend(remaining_board)
        else:
            board = remaining_board
        suit_histogram, histogram, max_suit = preprocess_board(board)
        for index, hole_card in enumerate(hole_cards):
            result_list[index] = detect_hand(hole_card, board, suit_histogram, histogram, max_suit)
        winner_index = compare_hands(result_list)
        winner_list[winner_index] += 1
        for index, result in enumerate(result_list):
            result_histograms[index][result[0]] += 1

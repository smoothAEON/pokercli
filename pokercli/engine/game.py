from __future__ import annotations

from dataclasses import dataclass
from itertools import cycle
from typing import Iterable, Sequence
from uuid import uuid4

from pokercli.engine.cards import Card, standard_deck
from pokercli.engine.evaluator import evaluate_cards
from pokercli.engine.hand_strength import compute_hand_strength
from pokercli.engine.models import (
    ActionDecision,
    ActionRecord,
    ActionType,
    BankrollEvent,
    BankrollLedger,
    GameConfig,
    HandHistory,
    LegalAction,
    PlayerState,
    PotAward,
    PotSlice,
    PublicTableState,
    RefereeState,
    SeatSnapshot,
    SeatView,
    Street,
)
from pokercli.engine.rng import DealerRNG, SeededDealerRNG, SystemDealerRNG


class PokerRuleError(ValueError):
    """Raised when an invalid action is applied."""


@dataclass(slots=True)
class HandSettlement:
    pots: list[PotSlice]
    awards: list[PotAward]
    winners: tuple[int, ...]
    revealed_seats: set[int]


class PokerGame:
    def __init__(
        self,
        config: GameConfig,
        seat_names: Sequence[str] | None = None,
        controllers: Sequence[str] | None = None,
        rng: DealerRNG | None = None,
        session_id: str | None = None,
    ) -> None:
        self.config = config
        self.session_id = session_id or str(uuid4())
        self.rng = rng or (SeededDealerRNG(config.seed) if config.seed is not None else SystemDealerRNG())
        seat_names = seat_names or [f"Seat {seat + 1}" for seat in range(config.seat_count)]
        controllers = controllers or ["rule-bot" for _ in range(config.seat_count)]
        if len(seat_names) != config.seat_count or len(controllers) != config.seat_count:
            raise ValueError("seat_names and controllers must match config.seat_count")
        self.seats = {
            seat: PlayerState(
                seat=seat,
                name=seat_names[seat],
                controller=controllers[seat],
                stack=config.starting_stack,
            )
            for seat in range(config.seat_count)
        }
        self.button_seat = -1
        self.hand_no = 0
        self.state: RefereeState | None = None
        self.hand_histories: list[HandHistory] = []
        self.bankroll_ledger = BankrollLedger()
        self.session_memory: dict[int, list[str]] = {seat: [] for seat in self.seats}
        for seat in self.seats:
            self.bankroll_ledger.record(
                BankrollEvent(
                    seat=seat,
                    event_type="buy-in",
                    amount=-config.starting_stack,
                    hand_no=None,
                    meta={"stack": config.starting_stack},
                )
            )

    def live_seats(self) -> list[int]:
        return [seat for seat, state in self.seats.items() if state.stack > 0]

    def can_start_hand(self) -> bool:
        return len(self.live_seats()) >= 2 and self.hand_no < self.config.max_hands

    def _ordered_seats_from(self, start_seat: int, seats: Iterable[int]) -> list[int]:
        ordered_seats = set(seats)
        if not ordered_seats:
            return []
        return [seat for seat in range(start_seat, self.config.seat_count) if seat in ordered_seats] + [
            seat for seat in range(0, start_seat) if seat in ordered_seats
        ]

    def _ordered_live_seats_from(self, start_seat: int) -> list[int]:
        return self._ordered_seats_from(start_seat, self.live_seats())

    def _ordered_live_after(self, seat: int) -> list[int]:
        return self._ordered_live_seats_from((seat + 1) % self.config.seat_count)

    def _next_live_after(self, seat: int) -> int:
        ordered = self._ordered_live_after(seat)
        if not ordered:
            raise PokerRuleError("No live seats remain")
        return ordered[0]

    def _active_seats(self, include_all_in: bool = True) -> list[int]:
        state = self.require_state()
        active = []
        for seat, player in state.seats.items():
            if player.hole_cards is None or player.folded:
                continue
            if not include_all_in and player.all_in:
                continue
            active.append(seat)
        return active

    def start_hand(self) -> RefereeState:
        if not self.can_start_hand():
            raise PokerRuleError("Not enough live seats to start a hand")
        self.hand_no += 1
        self.button_seat = self._next_live_after(self.button_seat)
        for player in self.seats.values():
            player.reset_for_hand()
        live = self.live_seats()
        if len(live) == 2:
            small_blind_seat = self.button_seat
            big_blind_seat = self._next_live_after(self.button_seat)
        else:
            small_blind_seat = self._next_live_after(self.button_seat)
            big_blind_seat = self._next_live_after(small_blind_seat)
        deck = standard_deck()
        self.rng.shuffle(deck)
        dealing_order = self._ordered_live_after(self.button_seat)
        for _ in range(2):
            for seat in dealing_order:
                player = self.seats[seat]
                player.hole_cards = tuple((*(player.hole_cards or ()), deck.pop(0)))  # type: ignore[assignment]
        for player in self.seats.values():
            if player.stack > 0 and player.hole_cards is None:
                raise PokerRuleError("Failed to deal hole cards")
        normalized_hole_cards = {
            seat: tuple(cards) for seat, cards in ((seat, player.hole_cards) for seat, player in self.seats.items()) if cards
        }
        for seat, cards in normalized_hole_cards.items():
            self.seats[seat].hole_cards = cards
        state = RefereeState(
            session_id=self.session_id,
            hand_no=self.hand_no,
            street=Street.PRE_FLOP,
            button_seat=self.button_seat,
            small_blind_seat=small_blind_seat,
            big_blind_seat=big_blind_seat,
            seats=self.seats,
            deck=deck,
            current_bet=0,
            last_full_raise_size=self.config.big_blind,
        )
        self.state = state
        self._post_blind(small_blind_seat, self.config.small_blind)
        self._post_blind(big_blind_seat, self.config.big_blind)
        state.current_bet = max(player.street_commitment for player in self.seats.values())
        first_actor = self._next_live_after(big_blind_seat)
        state.pending_to_act = [
            seat
            for seat in self._ordered_live_seats_from(first_actor)
            if self._can_take_action(seat)
        ]
        self._auto_advance_if_no_decisions()
        return state

    def require_state(self) -> RefereeState:
        if self.state is None:
            raise PokerRuleError("No active hand")
        return self.state

    def _post_blind(self, seat: int, amount: int) -> None:
        state = self.require_state()
        player = state.seats[seat]
        blind_amount = min(player.stack, amount)
        pot_before = state.pot
        player.stack -= blind_amount
        player.street_commitment += blind_amount
        player.total_commitment += blind_amount
        player.all_in = player.stack == 0
        state.actions.append(
            ActionRecord(
                index=len(state.actions),
                street=state.street,
                seat=seat,
                player_name=player.name,
                action=ActionType.POST_BLIND,
                contribution=blind_amount,
                street_total=player.street_commitment,
                pot_before=pot_before,
                pot_after=pot_before + blind_amount,
                stack_after=player.stack,
                to_call_before=0,
                all_in=player.all_in,
            )
        )

    def _can_take_action(self, seat: int) -> bool:
        state = self.require_state()
        player = state.seats[seat]
        return player.hole_cards is not None and not player.folded and not player.all_in and player.stack >= 0

    def build_public_state(self) -> PublicTableState:
        state = self.require_state()
        return PublicTableState(
            street=state.street,
            board=tuple(state.board),
            pot=state.pot,
            current_bet=state.current_bet,
            button_seat=state.button_seat,
            visible_stacks={seat: player.stack for seat, player in state.seats.items()},
            actions=list(state.actions),
        )

    def build_seat_view(self, seat: int) -> SeatView:
        state = self.require_state()
        player = state.seats[seat]
        if player.hole_cards is None:
            raise PokerRuleError("Seat is not active in this hand")
        return SeatView(
            seat=seat,
            player_name=player.name,
            session_id=state.session_id,
            hand_no=state.hand_no,
            hole_cards=player.hole_cards,
            stack=player.stack,
            to_call=max(0, state.current_bet - player.street_commitment),
            legal_actions=self.legal_actions_for(seat),
            table=self.build_public_state(),
            session_memory=list(self.session_memory[seat]),
            hand_strength=compute_hand_strength(player.hole_cards, tuple(state.board)),
        )

    def legal_actions_for(self, seat: int) -> list[LegalAction]:
        state = self.require_state()
        player = state.seats[seat]
        if not self._can_take_action(seat):
            return []
        to_call = max(0, state.current_bet - player.street_commitment)
        max_total = player.street_commitment + player.stack
        raise_reopened = (not player.has_acted) or (
            state.current_bet - player.bet_faced >= state.last_full_raise_size
        )
        actions: list[LegalAction] = []
        if to_call > 0:
            actions.append(LegalAction(ActionType.FOLD))
            actions.append(LegalAction(ActionType.CALL, call_amount=min(to_call, player.stack)))
        else:
            actions.append(LegalAction(ActionType.CHECK))
        if player.stack == 0:
            return actions
        if to_call == 0:
            if state.current_bet == 0:
                min_total = self.config.big_blind
                if max_total >= min_total:
                    actions.append(LegalAction(ActionType.BET, min_total=min_total, max_total=max_total))
                else:
                    actions.append(LegalAction(ActionType.ALL_IN, min_total=max_total, max_total=max_total))
            elif raise_reopened:
                min_total = state.current_bet + state.last_full_raise_size
                if max_total >= min_total:
                    actions.append(LegalAction(ActionType.RAISE, min_total=min_total, max_total=max_total))
                elif max_total > state.current_bet:
                    actions.append(LegalAction(ActionType.ALL_IN, min_total=max_total, max_total=max_total))
        else:
            if player.stack > to_call:
                if raise_reopened:
                    min_total = state.current_bet + state.last_full_raise_size
                    if max_total >= min_total:
                        actions.append(LegalAction(ActionType.RAISE, min_total=min_total, max_total=max_total))
                actions.append(LegalAction(ActionType.ALL_IN, min_total=max_total, max_total=max_total))
        return actions

    def _order_from_after(self, seat: int) -> list[int]:
        return [target for target in self._ordered_live_after(seat) if target != seat]

    def _ensure_pending_for_underraise(self, acting_seat: int) -> None:
        state = self.require_state()
        ordered = self._order_from_after(acting_seat)
        for seat in ordered:
            player = state.seats[seat]
            if not self._can_take_action(seat):
                continue
            if player.street_commitment < state.current_bet and seat not in state.pending_to_act:
                state.pending_to_act.append(seat)

    def _reset_pending_after_raise(self, acting_seat: int) -> None:
        state = self.require_state()
        state.pending_to_act = [
            seat for seat in self._order_from_after(acting_seat) if self._can_take_action(seat)
        ]

    def apply_action(self, seat: int, decision: ActionDecision) -> None:
        state = self.require_state()
        if not state.pending_to_act or state.pending_to_act[0] != seat:
            raise PokerRuleError(f"It is not seat {seat}'s turn")
        player = state.seats[seat]
        legal = self.legal_actions_for(seat)
        legal_by_type = {item.action: item for item in legal}
        action_type = decision.normalized_action()
        if action_type not in legal_by_type and not (
            action_type == ActionType.ALL_IN and ActionType.ALL_IN in legal_by_type
        ):
            raise PokerRuleError(f"Illegal action {action_type.value} for seat {seat}")
        to_call = max(0, state.current_bet - player.street_commitment)
        pot_before = state.pot
        contribution = 0
        new_total = player.street_commitment
        full_raise = False
        if action_type == ActionType.FOLD:
            player.folded = True
        elif action_type == ActionType.CHECK:
            if to_call != 0:
                raise PokerRuleError("Cannot check when facing a bet")
        elif action_type == ActionType.CALL:
            contribution = min(to_call, player.stack)
            new_total = player.street_commitment + contribution
        elif action_type == ActionType.BET:
            requested_total = decision.amount
            if requested_total is None:
                raise PokerRuleError("Bet amount is required")
            bounds = legal_by_type[ActionType.BET]
            if bounds.min_total is None or bounds.max_total is None or not bounds.min_total <= requested_total <= bounds.max_total:
                raise PokerRuleError("Bet amount is outside legal bounds")
            contribution = requested_total - player.street_commitment
            new_total = requested_total
            full_raise = requested_total >= self.config.big_blind
        elif action_type == ActionType.RAISE:
            requested_total = decision.amount
            if requested_total is None:
                raise PokerRuleError("Raise amount is required")
            bounds = legal_by_type[ActionType.RAISE]
            if bounds.min_total is None or bounds.max_total is None or not bounds.min_total <= requested_total <= bounds.max_total:
                raise PokerRuleError("Raise amount is outside legal bounds")
            contribution = requested_total - player.street_commitment
            new_total = requested_total
            full_raise = requested_total - state.current_bet >= state.last_full_raise_size
        elif action_type == ActionType.ALL_IN:
            new_total = player.street_commitment + player.stack
            contribution = player.stack
            if new_total > state.current_bet:
                full_raise = (
                    (state.current_bet == 0 and new_total >= self.config.big_blind)
                    or (new_total - state.current_bet >= state.last_full_raise_size)
                )
        else:
            raise PokerRuleError(f"Unsupported action {action_type.value}")
        if contribution > player.stack:
            raise PokerRuleError("Contribution exceeds player stack")
        current_bet_before = state.current_bet
        player.stack -= contribution
        player.street_commitment += contribution
        player.total_commitment += contribution
        player.all_in = player.stack == 0
        player.has_acted = True
        if state.pending_to_act and state.pending_to_act[0] == seat:
            state.pending_to_act.pop(0)
        if new_total > state.current_bet:
            raise_size = new_total - state.current_bet
            state.current_bet = new_total
            if full_raise:
                state.last_full_raise_size = raise_size if current_bet_before > 0 else max(new_total, self.config.big_blind)
                self._reset_pending_after_raise(seat)
            else:
                self._ensure_pending_for_underraise(seat)
        player.bet_faced = max(current_bet_before, new_total)
        action_record = ActionRecord(
            index=len(state.actions),
            street=state.street,
            seat=seat,
            player_name=player.name,
            action=action_type,
            contribution=contribution,
            street_total=player.street_commitment,
            pot_before=pot_before,
            pot_after=state.pot,
            stack_after=player.stack,
            to_call_before=to_call,
            all_in=player.all_in,
        )
        state.actions.append(action_record)
        self._auto_advance_if_no_decisions()

    def _only_one_not_folded(self) -> bool:
        state = self.require_state()
        remaining = [seat for seat, player in state.seats.items() if player.hole_cards is not None and not player.folded]
        return len(remaining) <= 1

    def _players_able_to_act(self) -> list[int]:
        state = self.require_state()
        return [seat for seat in self._active_seats(include_all_in=False) if self._can_take_action(seat)]

    def _auto_advance_if_no_decisions(self) -> None:
        state = self.require_state()
        while not state.hand_complete:
            if self._only_one_not_folded():
                self._complete_hand()
                return
            if state.pending_to_act:
                return
            if state.street == Street.RIVER:
                state.street = Street.SHOWDOWN
                self._complete_hand()
                return
            self._advance_street()
            if not state.pending_to_act and state.street in {Street.FLOP, Street.TURN, Street.RIVER}:
                if len(self._players_able_to_act()) == 0:
                    continue
            if state.pending_to_act:
                return

    def _advance_street(self) -> None:
        state = self.require_state()
        if state.street == Street.PRE_FLOP:
            state.street = Street.FLOP
            self._burn(1)
            self._deal_board(3)
        elif state.street == Street.FLOP:
            state.street = Street.TURN
            self._burn(1)
            self._deal_board(1)
        elif state.street == Street.TURN:
            state.street = Street.RIVER
            self._burn(1)
            self._deal_board(1)
        else:
            raise PokerRuleError(f"Cannot advance street from {state.street.value}")
        for player in state.seats.values():
            player.street_commitment = 0
            player.has_acted = False
            player.bet_faced = 0
        state.current_bet = 0
        state.last_full_raise_size = self.config.big_blind
        state.pending_to_act = [
            seat
            for seat in self._ordered_seats_from((state.button_seat + 1) % self.config.seat_count, state.seats)
            if self._can_take_action(seat)
        ]

    def _burn(self, count: int) -> None:
        state = self.require_state()
        for _ in range(count):
            state.burned.append(state.deck.pop(0))

    def _deal_board(self, count: int) -> None:
        state = self.require_state()
        for _ in range(count):
            state.board.append(state.deck.pop(0))

    def _side_pots(self) -> list[PotSlice]:
        state = self.require_state()
        contributions = {seat: player.total_commitment for seat, player in state.seats.items() if player.total_commitment > 0}
        if not contributions:
            return []
        levels = sorted(set(contributions.values()))
        previous = 0
        pots: list[PotSlice] = []
        for index, level in enumerate(levels):
            contributors = [seat for seat, amount in contributions.items() if amount >= level]
            pot_amount = (level - previous) * len(contributors)
            eligible = tuple(
                seat
                for seat in contributors
                if not state.seats[seat].folded and state.seats[seat].hole_cards is not None
            )
            pots.append(PotSlice(index=index, amount=pot_amount, eligible_seats=eligible))
            previous = level
        return pots

    def _winner_order_left_of_button(self) -> list[int]:
        state = self.require_state()
        return self._ordered_seats_from((state.button_seat + 1) % self.config.seat_count, state.seats)

    def _settle(self) -> HandSettlement:
        state = self.require_state()
        contenders = [
            seat
            for seat, player in state.seats.items()
            if player.hole_cards is not None and not player.folded
        ]
        pots = self._side_pots()
        awards: list[PotAward] = []
        revealed: set[int] = set(contenders)
        if len(contenders) == 1:
            winner = contenders[0]
            if pots:
                for pot in pots:
                    awards.append(
                        PotAward(
                            pot_index=pot.index,
                            seat=winner,
                            amount=pot.amount,
                            reason="last-player-standing",
                        )
                    )
            else:
                awards.append(PotAward(pot_index=0, seat=winner, amount=state.pot, reason="last-player-standing"))
            state.seats[winner].stack += sum(award.amount for award in awards if award.seat == winner)
            return HandSettlement(
                pots=pots or [PotSlice(index=0, amount=state.pot, eligible_seats=(winner,))],
                awards=awards,
                winners=(winner,),
                revealed_seats=revealed,
            )
        board_cards = tuple(state.board)
        ranks = {
            seat: evaluate_cards((*state.seats[seat].hole_cards, *board_cards))  # type: ignore[misc]
            for seat in contenders
        }
        winnings = {seat: 0 for seat in contenders}
        order = self._winner_order_left_of_button()
        for pot in pots:
            eligible = [seat for seat in pot.eligible_seats if seat in ranks]
            if not eligible:
                continue
            best_rank = max(ranks[seat] for seat in eligible)
            winners = [seat for seat in eligible if ranks[seat] == best_rank]
            split = pot.amount // len(winners)
            remainder = pot.amount % len(winners)
            for winner in winners:
                winnings[winner] += split
                awards.append(
                    PotAward(
                        pot_index=pot.index,
                        seat=winner,
                        amount=split,
                        reason="showdown",
                    )
                )
            if remainder:
                odd_chip_order = [seat for seat in order if seat in winners]
                odd_chip_winner = odd_chip_order[0]
                winnings[odd_chip_winner] += remainder
                awards.append(
                    PotAward(
                        pot_index=pot.index,
                        seat=odd_chip_winner,
                        amount=remainder,
                        reason="odd-chip",
                    )
                )
        for seat, amount in winnings.items():
            state.seats[seat].stack += amount
        winner_seats = tuple(sorted((seat for seat, amount in winnings.items() if amount > 0)))
        return HandSettlement(pots=pots, awards=awards, winners=winner_seats, revealed_seats=revealed)

    def _complete_hand(self) -> None:
        state = self.require_state()
        while len(state.board) < 5 and len(self._active_seats()) > 1:
            if state.street == Street.PRE_FLOP:
                self._advance_street()
            elif state.street == Street.FLOP:
                self._advance_street()
            elif state.street == Street.TURN:
                self._advance_street()
            elif state.street == Street.RIVER:
                break
        resolved_street = Street.SHOWDOWN if len(self._active_seats()) > 1 else state.street
        settlement = self._settle()
        state.street = Street.SETTLEMENT
        state.hand_complete = True
        seat_results = {}
        for seat, player in state.seats.items():
            if player.hole_cards is None:
                continue
            net = player.stack - player.stack_at_hand_start
            self.bankroll_ledger.record(
                BankrollEvent(
                    seat=seat,
                    event_type="hand-result",
                    amount=net,
                    hand_no=state.hand_no,
                    meta={"stack_end": player.stack},
                )
            )
            seat_results[seat] = SeatSnapshot(
                seat=seat,
                name=player.name,
                stack_start=player.stack_at_hand_start,
                stack_end=player.stack,
                commitment=player.total_commitment,
                winnings=player.stack - (player.stack_at_hand_start - player.total_commitment),
                folded=player.folded,
                all_in=player.all_in,
                hole_cards=player.hole_cards,
                revealed=seat in settlement.revealed_seats,
                hand_rank=evaluate_cards((*player.hole_cards, *state.board)) if not player.folded and len(state.board) == 5 else None,
            )
        history = HandHistory(
            session_id=state.session_id,
            hand_no=state.hand_no,
            button_seat=state.button_seat,
            blind_seats={"small_blind": state.small_blind_seat, "big_blind": state.big_blind_seat},
            board=tuple(state.board),
            burned=tuple(state.burned),
            actions=list(state.actions),
            pots=settlement.pots,
            awards=settlement.awards,
            seat_results=seat_results,
            street_reached=resolved_street,
            winner_seats=settlement.winners,
        )
        self.hand_histories.append(history)
        self._update_session_memory(history)

    def _update_session_memory(self, history: HandHistory) -> None:
        public_summary = (
            f"Hand {history.hand_no}: board={' '.join(str(card) for card in history.board) or '-'} "
            f"winners={','.join(str(seat) for seat in history.winner_seats)}"
        )
        for seat, snapshot in history.seat_results.items():
            entry = public_summary
            own_cards = " ".join(str(card) for card in snapshot.hole_cards)
            entry = f"{entry}; your_cards={own_cards}; net={snapshot.stack_end - snapshot.stack_start}"
            self.session_memory[seat].append(entry)
            self.session_memory[seat] = self.session_memory[seat][-self.config.session_memory_hands :]

    def play_hand(self, controllers: dict[int, object]) -> HandHistory:
        self.start_hand()
        state = self.require_state()
        while not state.hand_complete:
            if not state.pending_to_act:
                self._auto_advance_if_no_decisions()
                continue
            acting_seat = state.pending_to_act[0]
            controller = controllers[acting_seat]
            if not hasattr(controller, "act"):
                raise PokerRuleError(f"Controller for seat {acting_seat} has no act() method")
            view = self.build_seat_view(acting_seat)
            decision = controller.act(view)
            if not isinstance(decision, ActionDecision):
                raise PokerRuleError("Controllers must return ActionDecision")
            self.apply_action(acting_seat, decision)
        return self.hand_histories[-1]

    def chip_totals(self) -> dict[int, int]:
        return {seat: player.stack for seat, player in self.seats.items()}

"""Main Texas Hold'em game loop."""

from __future__ import annotations

from random import random

from cards import Deck
from evaluator import HandEvaluator
from player import Player
from table import Table
from ui import ConsoleUI


class TexasHoldemGame:
    def __init__(self, players: list[Player], small_blind: int = 5, big_blind: int = 10) -> None:
        if len(players) < 2:
            raise ValueError("Texas Hold'em requires at least 2 players")
        self.players = players
        self.small_blind = small_blind
        self.big_blind = big_blind
        self.table = Table()
        self.evaluator = HandEvaluator()
        self.ui = ConsoleUI()

    def play_hand(self) -> None:
        deck = Deck()
        self.table.reset()
        for player in self.players:
            player.reset_for_hand()

        for player in self.players:
            if player.chips > 0:
                player.receive(deck.draw(2))

        self._post_blinds()
        self._show_human_cards()
        self._betting_round("Pre-Flop")

        if not self._only_one_player_left():
            for player in self.players:
                player.current_bet = 0
            self._deal_community(deck, 3, "Flop")
            self._betting_round("Flop")

        if not self._only_one_player_left():
            for player in self.players:
                player.current_bet = 0
            self._deal_community(deck, 1, "Turn")
            self._betting_round("Turn")

        if not self._only_one_player_left():
            for player in self.players:
                player.current_bet = 0
            self._deal_community(deck, 1, "River")
            self._betting_round("River")

        self._showdown()

    def _post_blinds(self) -> None:
        if len(self.players) < 2:
            return

        small_player = self.players[0]
        big_player = self.players[1]

        small_amount = min(self.small_blind, small_player.chips)
        big_amount = min(self.big_blind, big_player.chips)

        small_player.bet(small_amount)
        big_player.bet(big_amount)
        self.table.add_to_pot(small_amount + big_amount)

        self.ui.show_message(
            f"{small_player.name} posts {small_amount}; {big_player.name} posts {big_amount}"
        )

    def _show_human_cards(self) -> None:
        for player in self.players:
            if player.is_human and player.active:
                self.ui.show_message(f"{player.name}: {self.ui.format_cards(player.hole_cards)}")

    def _deal_community(self, deck: Deck, count: int, street: str) -> None:
        if self._only_one_player_left():
            return
        self.table.community_cards.extend(deck.draw(count))
        self.ui.show_message(f"\n-- {street} --")
        self.ui.show_table(self.table.community_cards, self.table.pot)

    def _betting_round(self, street: str) -> None:
        if self._only_one_player_left():
            return

        self.ui.show_message(f"\n{street} betting round")
        self.ui.show_table(self.table.community_cards, self.table.pot)

        current_bet = max(player.current_bet for player in self.players if player.active)
        acted: set[str] = set()
        position = 2 if street == "Pre-Flop" and len(self.players) > 2 else 0

        while True:
            if self._only_one_player_left():
                return

            actionable = [p for p in self.players if p.active and p.chips > 0]
            if not actionable:
                return

            if all(p.current_bet == current_bet for p in actionable) and all(
                p.name in acted for p in actionable
            ):
                return

            player = self.players[position % len(self.players)]
            position += 1

            if not player.active or player.chips == 0:
                continue

            call_amount = max(0, current_bet - player.current_bet)
            if player.is_human:
                action = self.ui.ask_action(player, call_amount)
            else:
                action = self._bot_action(player, call_amount)

            if action == "fold":
                player.folded = True
                acted.add(player.name)
                self.ui.show_message(f"{player.name} folds")
                continue

            if action == "check":
                if call_amount > 0:
                    action = "call"
                else:
                    acted.add(player.name)
                    self.ui.show_message(f"{player.name} checks")
                    continue

            if action == "call":
                contribution = min(call_amount, player.chips)
                player.bet(contribution)
                self.table.add_to_pot(contribution)
                acted.add(player.name)
                if contribution < call_amount:
                    self.ui.show_message(f"{player.name} calls all-in for {contribution}")
                else:
                    self.ui.show_message(f"{player.name} calls {contribution}")
                continue

            if action == "raise":
                max_total = player.current_bet + player.chips
                min_total = current_bet + self.big_blind
                if max_total <= current_bet:
                    contribution = min(call_amount, player.chips)
                    player.bet(contribution)
                    self.table.add_to_pot(contribution)
                    acted.add(player.name)
                    self.ui.show_message(f"{player.name} calls {contribution}")
                    continue

                if player.is_human:
                    raise_to = self.ui.ask_raise_amount(
                        minimum=min(min_total, max_total), maximum=max_total
                    )
                else:
                    raise_to = min(min_total, max_total)

                if raise_to <= current_bet:
                    contribution = min(call_amount, player.chips)
                    player.bet(contribution)
                    self.table.add_to_pot(contribution)
                    acted.add(player.name)
                    self.ui.show_message(f"{player.name} calls {contribution}")
                    continue

                contribution = raise_to - player.current_bet
                player.bet(contribution)
                self.table.add_to_pot(contribution)
                current_bet = player.current_bet
                acted = {player.name}
                self.ui.show_message(f"{player.name} raises to {raise_to}")

    def _bot_action(self, player: Player, call_amount: int) -> str:
        if call_amount == 0:
            if player.chips >= self.big_blind * 2 and random() < 0.25:
                return "raise"
            return "check"
        if call_amount > player.chips:
            return "call"
        if call_amount >= int(player.chips * 0.5):
            return "fold"
        if call_amount <= int(player.chips * 0.15):
            if player.chips > call_amount + self.big_blind and random() < 0.2:
                return "raise"
            return "call"
        return "call"

    def _showdown(self) -> None:
        remaining = [player for player in self.players if player.active]
        if len(remaining) == 1:
            winner = remaining[0]
            winner.chips += self.table.pot
            self.ui.show_message(f"{winner.name} wins {self.table.pot} (everyone else folded)")
            self.table.pot = 0
            return

        ranked: list[tuple[Player, object]] = []
        for player in remaining:
            rank = self.evaluator.best_rank(player.hole_cards + self.table.community_cards)
            ranked.append((player, rank))
            self.ui.show_message(
                f"{player.name}: {self.ui.format_cards(player.hole_cards)} ({rank.category_name})"
            )

        best_rank = max(rank for _, rank in ranked)
        winners = [player for player, rank in ranked if rank == best_rank]
        share = self.table.pot // len(winners)
        remainder = self.table.pot % len(winners)

        for i, winner in enumerate(winners):
            payout = share + (1 if i < remainder else 0)
            winner.chips += payout

        winner_names = ", ".join(winner.name for winner in winners)
        self.ui.show_message(f"Winner: {winner_names} ({best_rank.category_name})")
        self.ui.show_message(f"Pot distributed: {self.table.pot}")
        self.table.pot = 0

    def _only_one_player_left(self) -> bool:
        return sum(1 for player in self.players if player.active) <= 1

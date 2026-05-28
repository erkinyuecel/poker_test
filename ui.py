"""Console input/output helpers."""

from __future__ import annotations

from cards import Card
from player import Player


class ConsoleUI: 
    def show_table(self, community_cards: list[Card], pot: int) -> None:
        cards_text = self.format_cards(community_cards) if community_cards else "(empty board)"
        print(f"Board: {cards_text} | Pot: {pot}")

    def show_player(self, player: Player) -> None:
        cards_text = self.format_cards(player.hole_cards)
        print(f"{player.name}: {cards_text} | Chips: {player.chips}")
    
    def ask_action(self, player: Player, call_amount: int) -> str:
        action_label = f"call {call_amount}" if call_amount > 0 else "check"
        while True:
            raw = input(f"{player.name}, choose [{action_label}/raise/fold]: ").strip().lower()
            if raw in {"c", "call"} and call_amount > 0:
                return "call"
            if raw in {"c", "check"} and call_amount == 0:
                return "check"
            if raw in {"r", "raise"}:
                return "raise"
            if raw in {"f", "fold"}:
                return "fold"
            print("Invalid action. Try again.")

    def ask_raise_amount(self, minimum: int, maximum: int) -> int:
        while True:
            raw = input(f"Enter total raise amount ({minimum}-{maximum}): ").strip()
            try:
                value = int(raw)
            except ValueError:
                print("Please enter a valid integer.")
                continue
            if minimum <= value <= maximum:
                return value
            print("Amount out of range.")

    def show_message(self, message: str) -> None:
        print(message)
    
    def format_cards(self, cards: list[Card]) -> str:
        return " ".join(str(card) for card in cards) if cards else "-"

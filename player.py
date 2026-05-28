"""Player model for the poker table."""

from __future__ import annotations

from dataclasses import dataclass, field

from cards import Card


@dataclass
class Player:
    name: str
    chips: int = 0
    is_human: bool = False
    hole_cards: list[Card] = field(default_factory=list)
    current_bet: int = 0
    folded: bool = False

    def reset_for_hand(self) -> None:
        self.hole_cards.clear()
        self.current_bet = 0
        self.folded = False

    def receive(self, cards: list[Card]) -> None:
        self.hole_cards.extend(cards)

    def bet(self, amount: int) -> int:
        if amount < 0:
            raise ValueError("bet amount cannot be negative")
        if amount > self.chips:
            raise ValueError("not enough chips")
        self.chips -= amount
        self.current_bet += amount
        return amount

    @property
    def active(self) -> bool:
        return not self.folded and bool(self.hole_cards)

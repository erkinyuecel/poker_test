"""Shared table state for a Hold'em hand."""

from __future__ import annotations

from dataclasses import dataclass, field

from cards import Card


@dataclass
class Table:
    community_cards: list[Card] = field(default_factory=list)
    pot: int = 0

    def reset(self) -> None:
        self.community_cards.clear()
        self.pot = 0

    def add_to_pot(self, amount: int) -> None:
        if amount < 0:
            raise ValueError("pot contribution cannot be negative")
        self.pot += amount


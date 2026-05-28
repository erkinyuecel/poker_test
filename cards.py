"""Card and deck primitives for Texas Hold'em."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from random import shuffle


class Suit(IntEnum):
    CLUBS = 0
    DIAMONDS = 1
    HEARTS = 2
    SPADES = 3

    @property
    def code(self) -> str:
        return {
            Suit.CLUBS: "C",
            Suit.DIAMONDS: "D",
            Suit.HEARTS: "H",
            Suit.SPADES: "S",
        }[self]

    @property
    def symbol(self) -> str:
        return {
            Suit.CLUBS: "♣",
            Suit.DIAMONDS: "♦",
            Suit.HEARTS: "♥",
            Suit.SPADES: "♠",
        }[self]


class Rank(IntEnum):
    TWO = 2
    THREE = 3
    FOUR = 4
    FIVE = 5
    SIX = 6
    SEVEN = 7
    EIGHT = 8
    NINE = 9
    TEN = 10
    JACK = 11
    QUEEN = 12
    KING = 13
    ACE = 14

    @property
    def label(self) -> str:
        return {
            Rank.TWO: "2",
            Rank.THREE: "3",
            Rank.FOUR: "4",
            Rank.FIVE: "5",
            Rank.SIX: "6",
            Rank.SEVEN: "7",
            Rank.EIGHT: "8",
            Rank.NINE: "9",
            Rank.TEN: "T",
            Rank.JACK: "J",
            Rank.QUEEN: "Q",
            Rank.KING: "K",
            Rank.ACE: "A",
        }[self]


@dataclass(frozen=True)
class Card:
    rank: Rank
    suit: Suit

    @property
    def code(self) -> str:
        return f"{self.rank.label}{self.suit.code}"

    def __str__(self) -> str:
        return f"{self.rank.label}{self.suit.symbol}"


class Deck:
    def __init__(self) -> None:
        self._cards = [Card(rank=rank, suit=suit) for suit in Suit for rank in Rank]
        shuffle(self._cards)

    def draw(self, count: int = 1) -> list[Card]:
        if count < 1:
            raise ValueError("count must be at least 1")
        if count > len(self._cards):
            raise ValueError("not enough cards left in deck")
        drawn = self._cards[-count:]
        del self._cards[-count:]
        return drawn

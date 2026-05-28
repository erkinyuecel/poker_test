"""Five-card hand evaluator used to rank Texas Hold'em showdowns."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import IntEnum
from itertools import combinations

from cards import Card


class HandCategory(IntEnum):
    HIGH_CARD = 1
    ONE_PAIR = 2
    TWO_PAIR = 3
    THREE_OF_A_KIND = 4
    STRAIGHT = 5
    FLUSH = 6
    FULL_HOUSE = 7
    FOUR_OF_A_KIND = 8
    STRAIGHT_FLUSH = 9


@dataclass(frozen=True, order=True)
class HandRank:
    category: HandCategory
    tiebreakers: tuple[int, ...]

    @property
    def category_name(self) -> str:
        return self.category.name.replace("_", " ").title()


class HandEvaluator:
    def best_rank(self, cards: list[Card]) -> HandRank:
        if len(cards) < 5:
            raise ValueError("at least 5 cards are required to evaluate a hand")

        best: HandRank | None = None
        for combo in combinations(cards, 5):
            rank = self._rank_five(list(combo))
            if best is None or rank > best:
                best = rank
        assert best is not None
        return best

    def _rank_five(self, cards: list[Card]) -> HandRank:
        ranks = sorted((int(card.rank) for card in cards), reverse=True)
        counts = Counter(ranks)
        groups = sorted(counts.items(), key=lambda item: (item[1], item[0]), reverse=True)
        is_flush = len({card.suit for card in cards}) == 1
        straight_high = self._straight_high(ranks)

        if is_flush and straight_high:
            return HandRank(HandCategory.STRAIGHT_FLUSH, (straight_high,))

        if groups[0][1] == 4:
            four_rank = groups[0][0]
            kicker = max(rank for rank in ranks if rank != four_rank)
            return HandRank(HandCategory.FOUR_OF_A_KIND, (four_rank, kicker))

        if groups[0][1] == 3 and groups[1][1] == 2:
            return HandRank(HandCategory.FULL_HOUSE, (groups[0][0], groups[1][0]))

        if is_flush:
            return HandRank(HandCategory.FLUSH, tuple(ranks))

        if straight_high:
            return HandRank(HandCategory.STRAIGHT, (straight_high,))

        if groups[0][1] == 3:
            trips = groups[0][0]
            kickers = tuple(sorted((rank for rank in ranks if rank != trips), reverse=True))
            return HandRank(HandCategory.THREE_OF_A_KIND, (trips, *kickers))

        if groups[0][1] == 2 and groups[1][1] == 2:
            high_pair = max(groups[0][0], groups[1][0])
            low_pair = min(groups[0][0], groups[1][0])
            kicker = max(rank for rank in ranks if rank not in (high_pair, low_pair))
            return HandRank(HandCategory.TWO_PAIR, (high_pair, low_pair, kicker))

        if groups[0][1] == 2:
            pair_rank = groups[0][0]
            kickers = tuple(sorted((rank for rank in ranks if rank != pair_rank), reverse=True))
            return HandRank(HandCategory.ONE_PAIR, (pair_rank, *kickers))

        return HandRank(HandCategory.HIGH_CARD, tuple(ranks))

    def _straight_high(self, ranks: list[int]) -> int | None:
        unique = sorted(set(ranks), reverse=True)
        if len(unique) < 5:
            return None

        # Wheel straight (A-2-3-4-5)
        if {14, 5, 4, 3, 2}.issubset(unique):
            return 5

        for i in range(len(unique) - 4):
            window = unique[i : i + 5]
            if window[0] - window[4] == 4 and len(window) == 5:
                return window[0]
        return None

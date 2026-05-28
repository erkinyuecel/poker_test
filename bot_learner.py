"""Q-Learning based adaptive bot that learns from poker games."""

from __future__ import annotations

import json
from pathlib import Path
from random import random


class BotLearner:
    """Simple Q-Learning agent for poker with personality."""

    def __init__(self, name: str, learning_rate: float = 0.1, discount: float = 0.95, epsilon: float = 0.25, 
                 tightness: float = 0.5, aggression: float = 0.5, bluff_rate: float = 0.2):
        self.name = name
        self.alpha = learning_rate
        self.gamma = discount
        self.epsilon = epsilon
        self.tightness = tightness  # 0=loose (play many hands), 1=tight (fold often)
        self.aggression = aggression  # 0=passive (check/call), 1=aggressive (raise often)
        self.bluff_rate = bluff_rate  # Probability to bluff (0-1)
        self.q_table: dict[tuple, float] = {}

        self.hand_states: list[tuple[tuple, str]] = []

    @staticmethod
    def discretize_state(hand_strength: float, pot_odds: float, stack_pressure: float) -> tuple[int, int, int]:
        hs_bin = int(max(0, min(9, hand_strength * 10)))
        po_bin = int(max(0, min(9, pot_odds * 10)))
        sp_bin = int(max(0, min(9, stack_pressure * 10)))
        return hs_bin, po_bin, sp_bin

    def get_action(self, state: tuple, valid_actions: list[str]) -> str:
        if random() < self.epsilon:
            return valid_actions[int(random() * len(valid_actions))]

        best_q = -float("inf")
        best_action = valid_actions[0]
        for action in valid_actions:
            q_val = self.q_table.get((state, action), 0.0)
            if q_val > best_q:
                best_q = q_val
                best_action = action

        return best_action

    def record_action(self, state: tuple, action: str) -> None:
        self.hand_states.append((state, action))

    def learn_from_result(self, reward: float) -> None:
        for state, action in reversed(self.hand_states):
            old_q = self.q_table.get((state, action), 0.0)
            self.q_table[(state, action)] = old_q + self.alpha * (reward - old_q)
            reward *= self.gamma

        self.hand_states = []

    def save(self, filepath: Path) -> None:
        serialized = {}
        for (state, action), q_val in self.q_table.items():
            key = f"{state}:{action}"
            serialized[key] = q_val
        filepath.write_text(json.dumps(serialized, indent=2))

    def load(self, filepath: Path) -> None:
        if not filepath.exists():
            return
        data = json.loads(filepath.read_text())
        for k_str, v in data.items():
            state_str, action = k_str.rsplit(":", 1)
            state = tuple(int(x) for x in state_str.strip("()").split(", "))
            self.q_table[(state, action)] = v

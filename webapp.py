"""Flask web app for single-player Texas Hold'em against bots."""

from __future__ import annotations

from pathlib import Path
from random import random
from uuid import uuid4

from flask import Flask, redirect, render_template_string, request, session, url_for

from bot_learner import BotLearner
from cards import Deck
from evaluator import HandCategory, HandEvaluator
from game_stats import init_db, save_game_result, get_player_stats, get_leaderboard
from player import Player
from table import Table

STARTING_CHIPS = 1_000
MIN_PLAYERS = 2
MAX_PLAYERS = 5
BOT_PROFILES = [
    ("Ada (Conservative)", "Ada", 0.7, 0.3, 0.1),
    ("Grace (Aggressive)", "Grace", 0.2, 0.9, 0.4),
    ("Charlie (Balanced)", "Charlie", 0.5, 0.6, 0.2),
    ("Zara (Bluffer)", "Zara", 0.1, 0.8, 0.5),
]
GAMES: dict[str, "WebPokerGame"] = {}
BOTS_DIR = Path("bots_data")
BOTS_DIR.mkdir(exist_ok=True)

try:
    init_db()
except Exception as e:
    print(f"⚠️ Database initialization warning: {e}")
    print("Tables might not exist. Will attempt to create on first request.")


def _normalize_player_count(raw: int | str | None) -> int:
    if raw is None:
        return MAX_PLAYERS
    try:
        count = int(raw)
    except (TypeError, ValueError):
        return MAX_PLAYERS
    return max(MIN_PLAYERS, min(count, MAX_PLAYERS))


class WebPokerGame:
    def __init__(self, small_blind: int = 5, big_blind: int = 10, num_players: int = 5) -> None:
        num_players = _normalize_player_count(num_players)
        self.small_blind = small_blind
        self.big_blind = big_blind
        self.players = [Player("You", chips=STARTING_CHIPS, is_human=True)]
        self.bot_learners: list[BotLearner | None] = [None]
        for player_name, learner_name, tightness, aggression, bluff_rate in BOT_PROFILES[
            : max(0, num_players - 1)
        ]:
            self.players.append(Player(player_name, chips=STARTING_CHIPS))
            self.bot_learners.append(
                BotLearner(
                    learner_name,
                    tightness=tightness,
                    aggression=aggression,
                    bluff_rate=bluff_rate,
                )
            )

        for learner in self.bot_learners[1:]:
            if learner is None:
                continue
            name = learner.name.lower()
            learner.load(BOTS_DIR / f"{name}_bot.json")

        self.table = Table()
        self.evaluator = HandEvaluator()
        self.deck: Deck | None = None

        self.dealer_index = -1
        self.current_turn_index = 0
        self.current_bet = 0
        self.acted_this_round: set[int] = set()
        self.street = "waiting"
        self.hand_number = 0
        self.hand_over = True
        self.awaiting_human = False
        self.game_over = False
        self.messages: list[str] = []
        self.hand_initial_chips = [p.chips for p in self.players]

    def add_message(self, message: str) -> None:
        self.messages.append(message)
        self.messages = self.messages[-15:]

    def start_hand(self) -> None:
        if self.game_over:
            return

        active_seats = self._live_seats()
        if len(active_seats) < 2:
            self.hand_over = True
            self.awaiting_human = False
            self.game_over = True
            self.add_message("Game over: not enough players with chips.")
            return

        self.hand_initial_chips = [p.chips for p in self.players]

        self.hand_number += 1
        self.street = "preflop"
        self.hand_over = False
        self.awaiting_human = False
        self.current_bet = 0
        self.acted_this_round = set()
        self.table.reset()
        self.deck = Deck()

        for player in self.players:
            player.reset_for_hand()

        for seat in active_seats:
            self.players[seat].receive(self.deck.draw(2))

        self.dealer_index = self._next_seat(self.dealer_index, active_seats)
        small_blind_seat = self._next_seat(self.dealer_index, active_seats)
        big_blind_seat = self._next_seat(small_blind_seat, active_seats)

        small_amount = self._post_blind(small_blind_seat, self.small_blind)
        big_amount = self._post_blind(big_blind_seat, self.big_blind)
        self.current_bet = max(
            self.players[small_blind_seat].current_bet, self.players[big_blind_seat].current_bet
        )

        self.add_message(
            f"Hand {self.hand_number}: dealer {self.players[self.dealer_index].name}"
        )
        self.add_message(
            f"{self.players[small_blind_seat].name} posts {small_amount}; "
            f"{self.players[big_blind_seat].name} posts {big_amount}"
        )

        actionable = self._actionable_seats()
        self.current_turn_index = (
            self._next_seat(big_blind_seat, actionable) if actionable else big_blind_seat
        )
        self._run_until_human()

    def take_human_action(self, action: str, raise_to: int | None = None) -> None:
        if self.hand_over:
            raise ValueError("the hand is already over")
        if not self.awaiting_human:
            raise ValueError("it is not your turn")

        seat = self.current_turn_index
        player = self.players[seat]
        if not player.is_human:
            raise ValueError("current turn does not belong to the human player")

        self._apply_action(seat, action, raise_to)
        self.awaiting_human = False
        if not self.hand_over:
            self._advance_round_or_turn(seat)
            self._run_until_human()

    def human_options(self) -> dict[str, int | bool] | None:
        if not self.awaiting_human or self.hand_over:
            return None
        player = self.players[self.current_turn_index]
        call_amount = max(0, self.current_bet - player.current_bet)
        max_total = player.current_bet + player.chips
        min_total = self.current_bet + self.big_blind
        can_raise = max_total >= min_total and max_total > self.current_bet
        return {
            "call_amount": call_amount,
            "can_check": call_amount == 0,
            "can_raise": can_raise,
            "min_raise": min_total,
            "max_raise": max_total,
        }

    def _run_until_human(self) -> None:
        while not self.hand_over:
            if len(self._active_seats()) <= 1:
                self._finish_by_fold()
                return

            if self._round_complete():
                self._advance_street()
                continue

            actionable = self._actionable_seats()
            if not actionable:
                self._advance_street()
                continue

            if self.current_turn_index not in actionable:
                self.current_turn_index = self._next_seat(self.current_turn_index, actionable)

            seat = self.current_turn_index
            player = self.players[seat]
            call_amount = max(0, self.current_bet - player.current_bet)

            if player.is_human:
                self.awaiting_human = True
                return

            action, raise_to = self._bot_decision(player, call_amount)
            self._apply_action(seat, action, raise_to)
            if not self.hand_over:
                self._advance_round_or_turn(seat)

    def _apply_action(self, seat: int, action: str, raise_to: int | None = None) -> None:
        player = self.players[seat]
        call_amount = max(0, self.current_bet - player.current_bet)

        if action == "fold":
            player.folded = True
            self.acted_this_round.add(seat)
            self.add_message(f"{player.name} folds")
            return

        if action == "check":
            if call_amount > 0:
                raise ValueError("cannot check when facing a bet")
            self.acted_this_round.add(seat)
            self.add_message(f"{player.name} checks")
            return

        if action == "call":
            contribution = min(call_amount, player.chips)
            player.bet(contribution)
            self.table.add_to_pot(contribution)
            self.acted_this_round.add(seat)
            if call_amount == 0:
                self.add_message(f"{player.name} checks")
            elif contribution < call_amount:
                self.add_message(f"{player.name} calls all-in for {contribution}")
            else:
                self.add_message(f"{player.name} calls {contribution}")
            return

        if action == "raise":
            max_total = player.current_bet + player.chips
            min_total = self.current_bet + self.big_blind
            if raise_to is None:
                raise ValueError("raise amount is required")
            if raise_to < min_total:
                raise ValueError(f"raise must be at least {min_total}")
            if raise_to > max_total:
                raise ValueError(f"raise cannot exceed {max_total}")

            contribution = raise_to - player.current_bet
            player.bet(contribution)
            self.table.add_to_pot(contribution)
            self.current_bet = player.current_bet
            self.acted_this_round = {seat}
            self.add_message(f"{player.name} raises to {raise_to}")
            return

        raise ValueError("unknown action")

    def _advance_round_or_turn(self, acted_seat: int) -> None:
        if self.hand_over:
            return
        if len(self._active_seats()) <= 1:
            self._finish_by_fold()
            return
        if self._round_complete():
            self._advance_street()
            return

        actionable = self._actionable_seats()
        if not actionable:
            self._advance_street()
            return
        self.current_turn_index = self._next_seat(acted_seat, actionable)

    def _advance_street(self) -> None:
        if self.hand_over:
            return

        if self.street == "preflop":
            self._deal_community(3, "Flop")
            self.street = "flop"
        elif self.street == "flop":
            self._deal_community(1, "Turn")
            self.street = "turn"
        elif self.street == "turn":
            self._deal_community(1, "River")
            self.street = "river"
        else:
            self._showdown()
            return

        for player in self.players:
            player.current_bet = 0
        self.current_bet = 0
        self.acted_this_round = set()

        actionable = self._actionable_seats()
        if actionable:
            self.current_turn_index = self._next_seat(self.dealer_index, actionable)

    def _deal_community(self, count: int, label: str) -> None:
        if not self.deck:
            raise RuntimeError("deck is not initialized")
        self.table.community_cards.extend(self.deck.draw(count))
        self.add_message(f"-- {label} -- {' '.join(str(card) for card in self.table.community_cards)}")

    def _showdown(self) -> None:
        active = self._active_seats()
        if len(active) == 1:
            self._finish_by_fold()
            return

        results: list[tuple[int, object]] = []
        for seat in active:
            player = self.players[seat]
            rank = self.evaluator.best_rank(player.hole_cards + self.table.community_cards)
            results.append((seat, rank))
            self.add_message(f"{player.name}: {self._cards_text(player.hole_cards)} ({rank.category_name})")

        best_rank = max(rank for _, rank in results)
        winners = [seat for seat, rank in results if rank == best_rank]
        split = self.table.pot // len(winners)
        remainder = self.table.pot % len(winners)

        for i, seat in enumerate(winners):
            payout = split + (1 if i < remainder else 0)
            self.players[seat].chips += payout

        winner_names = ", ".join(self.players[seat].name for seat in winners)
        self.add_message(f"Winner: {winner_names} ({best_rank.category_name})")
        self.table.pot = 0

        self._learn_from_hand(winners)
        self._save_hand_stats(winners)

        self.hand_over = True
        self.awaiting_human = False
        self.street = "finished"
        self._update_game_over()

    def _finish_by_fold(self) -> None:
        active = self._active_seats()
        if not active:
            self.hand_over = True
            self.awaiting_human = False
            self.street = "finished"
            self._update_game_over()
            return
        winner = self.players[active[0]]
        winner.chips += self.table.pot
        self.add_message(f"{winner.name} wins {self.table.pot} (everyone else folded)")
        self.table.pot = 0

        self._learn_from_hand(active)
        self._save_hand_stats(active)

        self.hand_over = True
        self.awaiting_human = False
        self.street = "finished"
        self._update_game_over()

    def _update_game_over(self) -> None:
        live = self._live_seats()
        human = self.players[0]
        if human.chips <= 0:
            self.game_over = True
            self.add_message("You are out of chips. Start a new game to continue.")
            return
        if not live:
            self.game_over = True
            self.add_message("Match ended without remaining chips.")
            return
        if len(live) == 1:
            self.game_over = True
            winner = self.players[live[0]]
            self.add_message(f"{winner.name} wins the match.")

    def _bot_decision(self, player: Player, call_amount: int) -> tuple[str, int | None]:
        seat = self.players.index(player)
        learner = self.bot_learners[seat]

        strength = self._estimate_strength(player)
        
        # Apply personality to strength
        strength -= (learner.tightness * 0.15)  # Tight bots fold weaker hands
        strength += (learner.aggression * 0.1)  # Aggressive bots play stronger hands
        strength = max(0.0, min(1.0, strength))
        
        # Bluff chance
        if random() < learner.bluff_rate:
            strength = max(strength, 0.4 + random() * 0.3)
        
        pot_odds = call_amount / max(self.table.pot + call_amount, 1)
        stack_pressure = call_amount / max(player.chips, 1)

        state = learner.discretize_state(strength, pot_odds, stack_pressure)
        valid_actions = ["fold", "call", "raise"] if call_amount > 0 else ["check", "raise"]

        action = learner.get_action(state, valid_actions)
        learner.record_action(state, action)

        if action == "fold":
            return "fold", None
        if action == "check":
            return "check", None

        if action == "raise":
            if call_amount == 0:
                if strength > 0.5 - (learner.tightness * 0.2) and player.chips >= self.big_blind:
                    raise_amount = max(self.big_blind, int(self.big_blind * (0.5 + learner.aggression)))
                    raise_to = min(player.current_bet + player.chips, self.current_bet + raise_amount)
                    if raise_to > self.current_bet:
                        return "raise", raise_to
                return "check", None

            if strength > 0.6 - (learner.tightness * 0.2) and player.chips >= call_amount + self.big_blind:
                raise_amount = max(call_amount, int(self.big_blind * (1.0 + learner.aggression)))
                raise_to = min(player.current_bet + player.chips, self.current_bet + raise_amount)
                if raise_to > self.current_bet:
                    return "raise", raise_to

        return "call", None

    def _estimate_strength(self, player: Player) -> float:
        if self.street == "preflop":
            first, second = sorted((int(card.rank) for card in player.hole_cards), reverse=True)
            suited_bonus = 0.05 if player.hole_cards[0].suit == player.hole_cards[1].suit else 0.0
            connected_bonus = 0.04 if abs(first - second) == 1 else 0.0
            if first == second:
                return min(0.95, 0.45 + first / 20)
            return min(0.85, (first + second) / 32 + suited_bonus + connected_bonus)

        rank = self.evaluator.best_rank(player.hole_cards + self.table.community_cards)
        base = {
            HandCategory.HIGH_CARD: 0.2,
            HandCategory.ONE_PAIR: 0.35,
            HandCategory.TWO_PAIR: 0.5,
            HandCategory.THREE_OF_A_KIND: 0.62,
            HandCategory.STRAIGHT: 0.72,
            HandCategory.FLUSH: 0.78,
            HandCategory.FULL_HOUSE: 0.88,
            HandCategory.FOUR_OF_A_KIND: 0.95,
            HandCategory.STRAIGHT_FLUSH: 0.99,
        }[rank.category]
        return min(0.99, base + (rank.tiebreakers[0] / 100))

    def _learn_from_hand(self, winners: list[int]) -> None:
        for seat in range(1, len(self.players)):
            learner = self.bot_learners[seat]
            if learner is None:
                continue
            if seat in winners:
                reward = (self.players[seat].chips - self.hand_initial_chips[seat]) / 100.0
                reward = max(1.0, min(reward, 10.0))
            else:
                reward = (self.players[seat].chips - self.hand_initial_chips[seat]) / 100.0
                reward = min(-0.1, max(reward, -5.0))

            learner.learn_from_result(reward)

            learner.save(BOTS_DIR / f"{learner.name.lower()}_bot.json")

    def _save_player_stats(
        self, player: Player, is_winner: bool, chips_change: int | None = None
    ) -> None:
        resolved_change = chips_change if chips_change is not None else (player.chips - STARTING_CHIPS)
        save_game_result(player.name, is_winner, resolved_change)

    def _save_hand_stats(self, winners: list[int]) -> None:
        human = self.players[0]
        chips_change = human.chips - self.hand_initial_chips[0]
        is_human_winner = 0 in winners
        self._save_player_stats(human, is_human_winner, chips_change)

    def _post_blind(self, seat: int, blind_amount: int) -> int:
        player = self.players[seat]
        amount = min(player.chips, blind_amount)
        player.bet(amount)
        self.table.add_to_pot(amount)
        return amount

    def _round_complete(self) -> bool:
        actionable = self._actionable_seats()
        if not actionable:
            return True
        return all(
            seat in self.acted_this_round and self.players[seat].current_bet == self.current_bet
            for seat in actionable
        )

    def _live_seats(self) -> list[int]:
        return [i for i, player in enumerate(self.players) if player.chips > 0]

    def _active_seats(self) -> list[int]:
        return [i for i, player in enumerate(self.players) if player.active]

    def _actionable_seats(self) -> list[int]:
        return [i for i, player in enumerate(self.players) if player.active and player.chips > 0]

    def _next_seat(self, from_seat: int, candidates: list[int]) -> int:
        if not candidates:
            raise ValueError("candidate list cannot be empty")
        ordered = sorted(candidates)
        if from_seat not in ordered:
            for seat in ordered:
                if seat > from_seat:
                    return seat
            return ordered[0]
        pos = ordered.index(from_seat)
        return ordered[(pos + 1) % len(ordered)]

    def _cards_text(self, cards: list) -> str:
        return " ".join(str(card) for card in cards) if cards else "-"

    def format_hole_cards(self, player: Player) -> str:
        if player.is_human:
            return self._cards_text(player.hole_cards)
        if self.hand_over or player.folded:
            return self._cards_text(player.hole_cards)
        return "?? ??"

    def visible_board_cards(self) -> list[tuple[str, str]]:
        return [(card.code, str(card)) for card in self.table.community_cards]

    def visible_hole_cards(self, player: Player) -> list[tuple[str, str]]:
        if player.is_human or self.hand_over or player.folded:
            return [(card.code, str(card)) for card in player.hole_cards]
        if player.hole_cards:
            return [("back", "🂠")] * len(player.hole_cards)
        return []


TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Poker Web App</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 24px; background: #10151f; color: #e8eefc; }
    .card { background: #1a2333; border: 1px solid #2d3a52; border-radius: 10px; padding: 16px; margin-bottom: 16px; }
    table { border-collapse: collapse; width: 100%; margin-top: 10px; }
    td, th { border: 1px solid #2d3a52; padding: 8px; text-align: left; }
    button { padding: 8px 12px; margin-right: 8px; }
    input[type=number] { padding: 6px; width: 110px; }
    select { padding: 6px; }
    .muted { color: #9fb0d8; }
    .stack { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; }
    ul { max-height: 260px; overflow: auto; }
    .cards-row { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 8px; }
    .card-slot { position: relative; width: 56px; height: 78px; display: inline-flex; }
    .card-img, .card-fallback {
      width: 56px; height: 78px; border-radius: 7px; border: 1px solid #2d3a52;
      background: #0b1322; display: inline-flex; align-items: center; justify-content: center;
      font-weight: 700; letter-spacing: 0.3px;
    }
    .card-img { object-fit: cover; }
    .card-fallback { color: #ffffff; font-size: 16px; }
  </style>
</head>
<body>
  <h1>Texas Hold'em — Web (Single Player + Bots)</h1>

  {% macro render_cards(card_entries) -%}
    <div class="cards-row">
      {% for code, label in card_entries %}
        <span class="card-slot">
          <img
            class="card-img"
            src="{{ url_for('static', filename='cards/' ~ code ~ '.png') }}"
            alt="{{ label }}"
            onerror="this.style.display='none'; this.nextElementSibling.style.display='inline-flex';"
          />
          <span class="card-fallback" style="display:none;">{{ label }}</span>
        </span>
      {% endfor %}
      {% if not card_entries %}
        <span class="muted">-</span>
      {% endif %}
    </div>
  {%- endmacro %}

  {% if not game %}
    <div class="card">
      <h2>Start Game</h2>
      <form method="post" action="{{ url_for('new_game') }}">
        <label for="player-count"><strong>Players</strong> (including you)</label><br />
        <select id="player-count" name="player_count">
          {% for count in player_counts %}
            <option value="{{ count }}" {% if count == selected_count %}selected{% endif %}>
              {{ count }}
            </option>
          {% endfor %}
        </select>
        <button type="submit">Start New Game</button>
      </form>
      <p class="muted">
        You will play against {{ selected_count - 1 }} bot{{ '' if selected_count - 1 == 1 else 's' }}.
      </p>
    </div>
  {% else %}
    <div class="card">
      <div><strong>Hand:</strong> {{ game.hand_number }} | <strong>Street:</strong> {{ game.street|upper }} | <strong>Pot:</strong> {{ game.table.pot }}</div>
      <div class="muted"><strong>Board:</strong></div>
      {{ render_cards(game.visible_board_cards()) }}
    </div>

    <div class="card">
      <strong>Players</strong>
      <table>
        <thead><tr><th>Name</th><th>Chips</th><th>Current Bet</th><th>Status</th><th>Cards</th></tr></thead>
        <tbody>
        {% for player in game.players %}
          <tr>
            <td>{{ player.name }}</td>
            <td>{{ player.chips }}</td>
            <td>{{ player.current_bet }}</td>
            <td>
              {% if player.folded %}Folded{% elif player.chips <= 0 and not player.hole_cards %}Out{% else %}Active{% endif %}
            </td>
            <td>{{ render_cards(game.visible_hole_cards(player)) }}</td>
          </tr>
        {% endfor %}
        </tbody>
      </table>
    </div>

    <div class="card">
      <strong>Actions</strong>
      {% if game.awaiting_human and options %}
        <div class="stack" style="margin-top: 10px;">
          <form method="post" action="{{ url_for('action') }}">
            <input type="hidden" name="action" value="{{ 'check' if options.can_check else 'call' }}" />
            <button type="submit">{{ 'Check' if options.can_check else 'Call ' ~ options.call_amount }}</button>
          </form>

          <form method="post" action="{{ url_for('action') }}">
            <input type="hidden" name="action" value="fold" />
            <button type="submit">Fold</button>
          </form>

          {% if options.can_raise %}
            <form method="post" action="{{ url_for('action') }}">
              <input type="hidden" name="action" value="raise" />
              <input type="number" name="raise_to" min="{{ options.min_raise }}" max="{{ options.max_raise }}" required />
              <button type="submit">Raise ({{ options.min_raise }} - {{ options.max_raise }})</button>
            </form>
          {% else %}
            <span class="muted">Raise unavailable.</span>
          {% endif %}
        </div>
      {% elif game.hand_over %}
        <div class="stack" style="margin-top: 10px;">
          {% if not game.game_over %}
            <form method="post" action="{{ url_for('next_hand') }}">
              <button type="submit">Play Next Hand</button>
            </form>
          {% endif %}
          <form method="post" action="{{ url_for('new_game') }}">
            <button type="submit">Start New Game</button>
          </form>
        </div>
      {% else %}
        <p class="muted">Bots are acting...</p>
      {% endif %}
    </div>

    <div class="card">
      <strong>Hand Log</strong>
      <ul>
        {% for message in game.messages|reverse %}
          <li>{{ message }}</li>
        {% endfor %}
      </ul>
    </div>
  {% endif %}
</body>
</html>
"""

app = Flask(__name__)
app.secret_key = "poker-workshop-secret"


def _get_current_game() -> WebPokerGame | None:
    game_id = session.get("game_id")
    if not game_id:
        return None
    return GAMES.get(game_id)


@app.get("/")
def index():
    game = _get_current_game()
    options = game.human_options() if game else None
    selected_count = _normalize_player_count(session.get("player_count"))
    return render_template_string(
        TEMPLATE,
        game=game,
        options=options,
        player_counts=range(MIN_PLAYERS, MAX_PLAYERS + 1),
        selected_count=selected_count,
    )


@app.post("/new-game")
def new_game():
    raw_count = request.form.get("player_count") or session.get("player_count")
    player_count = _normalize_player_count(raw_count)
    session["player_count"] = player_count
    game = WebPokerGame(num_players=player_count)
    game_id = str(uuid4())
    GAMES[game_id] = game
    session["game_id"] = game_id
    game.start_hand()
    return redirect(url_for("index"))


@app.post("/next-hand")
def next_hand():
    game = _get_current_game()
    if game and game.hand_over and not game.game_over:
        game.start_hand()
    return redirect(url_for("index"))


@app.post("/action")
def action():
    game = _get_current_game()
    if not game:
        return redirect(url_for("index"))

    selected_action = request.form.get("action", "")
    raise_to_raw = request.form.get("raise_to")
    raise_to: int | None = None
    if raise_to_raw:
        try:
            raise_to = int(raise_to_raw)
        except ValueError:
            game.add_message("Invalid raise amount.")
            return redirect(url_for("index"))

    try:
        game.take_human_action(selected_action, raise_to)
    except ValueError as exc:
        game.add_message(f"Invalid action: {exc}")
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True)

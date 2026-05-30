"""Player stats persistence using PostgreSQL (Supabase)."""

import os
import socket
from contextlib import contextmanager
from urllib.parse import urlparse

import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
DATABASE_FORCE_IPV4 = os.getenv("DATABASE_FORCE_IPV4", "").lower() in {"1", "true", "yes"}
DATABASE_HOSTADDR = os.getenv("DATABASE_HOSTADDR")


def _resolve_ipv4_hostaddr(database_url: str) -> str:
    parsed = urlparse(database_url)
    host = parsed.hostname
    port = parsed.port or 5432
    if not host:
        raise RuntimeError("DATABASE_URL is missing a hostname.")
    infos = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
    if not infos:
        raise RuntimeError(f"No IPv4 address found for database host {host}.")
    return infos[0][4][0]


def _get_connection_hostaddr() -> str | None:
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set.")
    if DATABASE_FORCE_IPV4:
        return DATABASE_HOSTADDR or _resolve_ipv4_hostaddr(DATABASE_URL)
    return DATABASE_HOSTADDR


@contextmanager
def get_db_connection():
    """Get database connection."""
    hostaddr = _get_connection_hostaddr()
    if hostaddr:
        conn = psycopg2.connect(DATABASE_URL, hostaddr=hostaddr)
    else:
        conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    """Initialize database schema."""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS players (
                leaderboard_id TEXT NOT NULL,
                name TEXT NOT NULL,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                total_chips_won INTEGER DEFAULT 0,
                hands_played INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (leaderboard_id, name)
            )
        """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS game_results (
                id BIGSERIAL PRIMARY KEY,
                leaderboard_id TEXT NOT NULL,
                player_name TEXT NOT NULL,
                is_winner BOOLEAN,
                chips_change INTEGER,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        cursor.execute("ALTER TABLE players ADD COLUMN IF NOT EXISTS leaderboard_id TEXT")
        cursor.execute("UPDATE players SET leaderboard_id = 'global' WHERE leaderboard_id IS NULL")
        cursor.execute("ALTER TABLE players ALTER COLUMN leaderboard_id SET NOT NULL")

        cursor.execute("ALTER TABLE game_results ADD COLUMN IF NOT EXISTS leaderboard_id TEXT")
        cursor.execute("UPDATE game_results SET leaderboard_id = 'global' WHERE leaderboard_id IS NULL")
        cursor.execute("ALTER TABLE game_results ALTER COLUMN leaderboard_id SET NOT NULL")
        cursor.execute("ALTER TABLE game_results DROP CONSTRAINT IF EXISTS game_results_player_name_fkey")
        cursor.execute("ALTER TABLE game_results DROP CONSTRAINT IF EXISTS game_results_player_fkey")

        cursor.execute("ALTER TABLE players DROP CONSTRAINT IF EXISTS players_pkey")
        cursor.execute("ALTER TABLE players ADD PRIMARY KEY (leaderboard_id, name)")
        cursor.execute(
            """
            ALTER TABLE game_results
            ADD CONSTRAINT game_results_player_fkey
            FOREIGN KEY (leaderboard_id, player_name)
                REFERENCES players(leaderboard_id, name)
        """
        )

        conn.commit()
        print("✓ Database tables initialized")


def get_player_stats(leaderboard_id: str, name: str) -> dict:
    """Get player statistics."""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT name, wins, losses, total_chips_won, hands_played
            FROM players
            WHERE leaderboard_id = %s AND name = %s
        """,
            (leaderboard_id, name),
        )
        row = cursor.fetchone()

    if not row:
        return {
            "name": name,
            "wins": 0,
            "losses": 0,
            "total_chips_won": 0,
            "hands_played": 0,
            "win_rate": 0.0,
        }

    name, wins, losses, total_chips_won, hands_played = row
    total = wins + losses
    win_rate = (wins / total * 100) if total > 0 else 0.0

    return {
        "name": name,
        "wins": wins,
        "losses": losses,
        "total_chips_won": total_chips_won,
        "hands_played": hands_played,
        "win_rate": win_rate,
    }


def save_game_result(
    leaderboard_id: str, player_name: str, is_winner: bool, chips_change: int
) -> None:
    """Save game result for player."""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO players (leaderboard_id, name)
            VALUES (%s, %s)
            ON CONFLICT (leaderboard_id, name) DO NOTHING
        """,
            (leaderboard_id, player_name),
        )

        if is_winner:
            cursor.execute(
                """
                UPDATE players
                SET wins = wins + 1,
                    total_chips_won = total_chips_won + %s,
                    hands_played = hands_played + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE leaderboard_id = %s AND name = %s
            """,
                (chips_change, leaderboard_id, player_name),
            )
        else:
            cursor.execute(
                """
                UPDATE players
                SET losses = losses + 1,
                    total_chips_won = total_chips_won + %s,
                    hands_played = hands_played + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE leaderboard_id = %s AND name = %s
            """,
                (chips_change, leaderboard_id, player_name),
            )

        cursor.execute(
            """
            INSERT INTO game_results (leaderboard_id, player_name, is_winner, chips_change)
            VALUES (%s, %s, %s, %s)
        """,
            (leaderboard_id, player_name, is_winner, chips_change),
        )

        conn.commit()


def get_leaderboard(leaderboard_id: str) -> list[dict]:
    """Get top players by win rate."""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT name, wins, losses, total_chips_won, hands_played,
                   CAST(wins AS FLOAT) / (wins + losses) * 100 as win_rate
            FROM players
            WHERE leaderboard_id = %s AND hands_played >= 1
            ORDER BY win_rate DESC, hands_played DESC
            LIMIT 20
        """,
            (leaderboard_id,),
        )

        rows = cursor.fetchall()

    return [
        {
            "name": row[0],
            "wins": row[1],
            "losses": row[2],
            "total_chips_won": row[3],
            "hands_played": row[4],
            "win_rate": row[5] or 0.0,
        }
        for row in rows
    ]


if __name__ == "__main__":
    init_db()

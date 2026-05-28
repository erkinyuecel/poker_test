"""Player stats persistence using SQLite."""

import sqlite3
from pathlib import Path

DB_PATH = Path("players_data.db")


def init_db() -> None:
    """Initialize database schema."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS players (
            name TEXT PRIMARY KEY,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            total_chips_won INTEGER DEFAULT 0,
            hands_played INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS game_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_name TEXT,
            is_winner BOOLEAN,
            chips_change INTEGER,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(player_name) REFERENCES players(name)
        )
    """)
    
    conn.commit()
    conn.close()


def get_player_stats(name: str) -> dict:
    """Get player statistics."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM players WHERE name = ?", (name,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return {
            "name": name,
            "wins": 0,
            "losses": 0,
            "total_chips_won": 0,
            "hands_played": 0,
            "win_rate": 0.0,
        }
    
    wins = row["wins"]
    losses = row["losses"]
    total = wins + losses
    win_rate = (wins / total * 100) if total > 0 else 0.0
    
    return {
        "name": name,
        "wins": wins,
        "losses": losses,
        "total_chips_won": row["total_chips_won"],
        "hands_played": row["hands_played"],
        "win_rate": win_rate,
    }


def save_game_result(player_name: str, is_winner: bool, chips_change: int) -> None:
    """Save game result for player."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("INSERT OR IGNORE INTO players (name) VALUES (?)", (player_name,))
    
    if is_winner:
        cursor.execute("""
            UPDATE players 
            SET wins = wins + 1, 
                total_chips_won = total_chips_won + ?,
                hands_played = hands_played + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE name = ?
        """, (chips_change, player_name))
    else:
        cursor.execute("""
            UPDATE players 
            SET losses = losses + 1,
                total_chips_won = total_chips_won + ?,
                hands_played = hands_played + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE name = ?
        """, (chips_change, player_name))
    
    cursor.execute(
        "INSERT INTO game_results (player_name, is_winner, chips_change) VALUES (?, ?, ?)",
        (player_name, is_winner, chips_change)
    )
    
    conn.commit()
    conn.close()


def get_leaderboard() -> list[dict]:
    """Get top players by win rate."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT name, wins, losses, total_chips_won, hands_played,
               CAST(wins AS FLOAT) / (wins + losses) * 100 as win_rate
        FROM players
        WHERE hands_played >= 1
        ORDER BY win_rate DESC, hands_played DESC
        LIMIT 20
    """)
    
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]


if __name__ == "__main__":
    init_db()
    print("✓ Database initialized")

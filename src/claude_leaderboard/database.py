"""Database operations for Claude OTel leaderboard."""
import sqlite3
from typing import Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS employee_usage (
    email TEXT PRIMARY KEY,
    account_uuid TEXT,
    total_input_tokens INTEGER DEFAULT 0,
    total_output_tokens INTEGER DEFAULT 0,
    total_cache_read_tokens INTEGER DEFAULT 0,
    total_cache_creation_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    total_cost REAL DEFAULT 0.0,
    prompt_count INTEGER DEFAULT 0,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_total_tokens ON employee_usage(total_tokens DESC);
CREATE INDEX IF NOT EXISTS idx_total_cost ON employee_usage(total_cost DESC);
CREATE INDEX IF NOT EXISTS idx_prompt_count ON employee_usage(prompt_count DESC);
"""


def init_db(conn: sqlite3.Connection) -> None:
    """Initialize the database schema."""
    conn.executescript(SCHEMA)
    conn.commit()


def upsert_usage(
    conn: sqlite3.Connection,
    email: str,
    account_uuid: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int,
    cache_creation_tokens: int,
    cost_usd: float,
) -> None:
    """Upsert usage data for an employee."""
    # Only count actual API tokens, not cached tokens (they're "free" from a usage perspective)
    total_tokens = input_tokens + output_tokens

    conn.execute(
        """
        INSERT INTO employee_usage (
            email, account_uuid, total_input_tokens, total_output_tokens,
            total_cache_read_tokens, total_cache_creation_tokens, total_tokens,
            total_cost, prompt_count, last_updated
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
        ON CONFLICT(email) DO UPDATE SET
            total_input_tokens = total_input_tokens + ?,
            total_output_tokens = total_output_tokens + ?,
            total_cache_read_tokens = total_cache_read_tokens + ?,
            total_cache_creation_tokens = total_cache_creation_tokens + ?,
            total_tokens = total_tokens + ?,
            total_cost = total_cost + ?,
            prompt_count = prompt_count + 1,
            last_updated = CURRENT_TIMESTAMP
        """,
        (
            email, account_uuid, input_tokens, output_tokens,
            cache_read_tokens, cache_creation_tokens, total_tokens, cost_usd,
            # For UPDATE:
            input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens,
            total_tokens, cost_usd,
        )
    )
    conn.commit()


def get_leaderboard(
    conn: sqlite3.Connection,
    sort_by: str = "total_tokens",
) -> list[dict]:
    """Get leaderboard data sorted by the specified column."""
    valid_sort_columns = {"total_tokens", "total_cost", "prompt_count", "last_updated"}
    if sort_by not in valid_sort_columns:
        sort_by = "total_tokens"

    cursor = conn.execute(
        f"""
        SELECT
            email,
            account_uuid,
            total_tokens,
            total_cost,
            prompt_count,
            last_updated
        FROM employee_usage
        ORDER BY {sort_by} DESC
        """
    )

    rows = cursor.fetchall()
    return [
        {
            "email": row[0],
            "account_uuid": row[1],
            "total_tokens": row[2],
            "total_cost": row[3],
            "prompt_count": row[4],
            "last_updated": row[5],
        }
        for row in rows
    ]

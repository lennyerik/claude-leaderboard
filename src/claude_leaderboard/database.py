"""Database operations for Claude OTel leaderboard."""
import sqlite3
from datetime import datetime, timedelta
from typing import Optional


SCHEMA = """
CREATE TABLE IF NOT EXISTS requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL,
    session_id TEXT,
    model TEXT,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cache_read_tokens INTEGER DEFAULT 0,
    cache_creation_tokens INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0.0,
    duration_ms INTEGER DEFAULT 0,
    timestamp TEXT,
    account_uuid TEXT,
    organization_id TEXT,
    prompt_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_requests_email ON requests(email);
CREATE INDEX IF NOT EXISTS idx_requests_session ON requests(session_id);
CREATE INDEX IF NOT EXISTS idx_requests_timestamp ON requests(timestamp);
CREATE INDEX IF NOT EXISTS idx_requests_model ON requests(model);
"""


def init_db(conn: sqlite3.Connection) -> None:
    """Initialize the database schema."""
    conn.executescript(SCHEMA)
    conn.commit()


def insert_request(
    conn: sqlite3.Connection,
    email: str,
    session_id: Optional[str] = None,
    model: Optional[str] = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
    cost_usd: float = 0.0,
    duration_ms: int = 0,
    timestamp: Optional[str] = None,
    account_uuid: Optional[str] = None,
    organization_id: Optional[str] = None,
    prompt_id: Optional[str] = None,
) -> None:
    """Insert a single API request record."""
    conn.execute(
        """
        INSERT INTO requests (
            email, session_id, model, input_tokens, output_tokens,
            cache_read_tokens, cache_creation_tokens, cost_usd, duration_ms,
            timestamp, account_uuid, organization_id, prompt_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            email, session_id, model, input_tokens, output_tokens,
            cache_read_tokens, cache_creation_tokens, cost_usd, duration_ms,
            timestamp, account_uuid, organization_id, prompt_id,
        )
    )
    conn.commit()


def format_duration(ms: int) -> str:
    """Format milliseconds into human-readable duration."""
    if ms < 1000:
        return f"{ms}ms"

    total_seconds = ms // 1000
    remaining_ms = ms % 1000

    if total_seconds < 60:
        if remaining_ms > 0:
            return f"{total_seconds}s {remaining_ms}ms"
        return f"{total_seconds}s"

    minutes = total_seconds // 60
    seconds = total_seconds % 60

    if minutes < 60:
        return f"{minutes}m {seconds}s"

    hours = minutes // 60
    minutes = minutes % 60
    return f"{hours}h {minutes}m"


def get_leaderboard_tokens(conn: sqlite3.Connection) -> list[dict]:
    """Get leaderboard sorted by total tokens (input + output, excluding cache)."""
    cursor = conn.execute(
        """
        SELECT
            email,
            SUM(input_tokens + output_tokens) as total_tokens,
            SUM(cost_usd) as total_cost,
            COUNT(*) as request_count
        FROM requests
        GROUP BY email
        ORDER BY total_tokens DESC
        """
    )
    return [
        {
            "email": row[0],
            "total_tokens": row[1],
            "total_cost": row[2],
            "request_count": row[3],
        }
        for row in cursor.fetchall()
    ]


def get_leaderboard_cost(conn: sqlite3.Connection) -> list[dict]:
    """Get leaderboard sorted by total cost."""
    cursor = conn.execute(
        """
        SELECT
            email,
            SUM(cost_usd) as total_cost,
            SUM(input_tokens + output_tokens) as total_tokens,
            COUNT(*) as request_count
        FROM requests
        GROUP BY email
        ORDER BY total_cost DESC
        """
    )
    return [
        {
            "email": row[0],
            "total_cost": row[1],
            "total_tokens": row[2],
            "request_count": row[3],
        }
        for row in cursor.fetchall()
    ]


def get_leaderboard_time(conn: sqlite3.Connection) -> list[dict]:
    """Get leaderboard sorted by total time spent interacting with AI."""
    cursor = conn.execute(
        """
        SELECT
            email,
            SUM(duration_ms) as total_duration_ms,
            COUNT(*) as request_count
        FROM requests
        GROUP BY email
        ORDER BY total_duration_ms DESC
        """
    )
    return [
        {
            "email": row[0],
            "total_duration_ms": row[1],
            "total_duration": format_duration(row[1]),
            "request_count": row[2],
        }
        for row in cursor.fetchall()
    ]


def get_leaderboard_io_ratio(conn: sqlite3.Connection) -> list[dict]:
    """Get leaderboard sorted by input/output token ratio.

    Ratio > 1.0 means user talks more than AI (verbose)
    Ratio < 1.0 means user is efficient with prompts
    """
    cursor = conn.execute(
        """
        SELECT
            email,
            SUM(input_tokens) as total_input,
            SUM(output_tokens) as total_output,
            CAST(SUM(input_tokens) AS REAL) / NULLIF(SUM(output_tokens), 0) as io_ratio,
            COUNT(*) as request_count
        FROM requests
        GROUP BY email
        HAVING SUM(output_tokens) > 0
        ORDER BY io_ratio DESC
        """
    )
    return [
        {
            "email": row[0],
            "total_input": row[1],
            "total_output": row[2],
            "io_ratio": round(row[3], 2) if row[3] else 0,
            "request_count": row[4],
        }
        for row in cursor.fetchall()
    ]


def get_leaderboard_efficiency(conn: sqlite3.Connection) -> list[dict]:
    """Get leaderboard sorted by efficiency (output/input ratio, lower io_ratio = more efficient)."""
    cursor = conn.execute(
        """
        SELECT
            email,
            SUM(input_tokens) as total_input,
            SUM(output_tokens) as total_output,
            CAST(SUM(input_tokens) AS REAL) / NULLIF(SUM(output_tokens), 0) as io_ratio,
            COUNT(*) as request_count
        FROM requests
        GROUP BY email
        HAVING SUM(output_tokens) > 0
        ORDER BY io_ratio ASC
        """
    )
    return [
        {
            "email": row[0],
            "total_input": row[1],
            "total_output": row[2],
            "io_ratio": round(row[3], 2) if row[3] else 0,
            "request_count": row[4],
        }
        for row in cursor.fetchall()
    ]


def get_favorite_models(conn: sqlite3.Connection) -> list[dict]:
    """Get favorite model per user (model with most requests)."""
    cursor = conn.execute(
        """
        SELECT
            email,
            model,
            COUNT(*) as model_count
        FROM requests
        WHERE model IS NOT NULL
        GROUP BY email, model
        ORDER BY email, model_count DESC
        """
    )

    # Get the most used model per user
    user_models = {}
    for row in cursor.fetchall():
        email, model, count = row
        if email not in user_models:
            user_models[email] = {"email": email, "favorite_model": model, "model_count": count}

    return list(user_models.values())


def get_leaderboard_streak(conn: sqlite3.Connection) -> list[dict]:
    """Get leaderboard sorted by longest streak of consecutive days with AI interaction."""
    cursor = conn.execute(
        """
        SELECT
            email,
            DATE(timestamp) as day
        FROM requests
        WHERE timestamp IS NOT NULL
        GROUP BY email, day
        ORDER BY email, day
        """
    )

    # Calculate streaks per user
    user_days = {}
    for row in cursor.fetchall():
        email, day = row
        if email not in user_days:
            user_days[email] = []
        user_days[email].append(day)

    streaks = []
    for email, days in user_days.items():
        if not days:
            continue

        # Sort days and calculate longest streak
        days.sort()
        max_streak = 1
        current_streak = 1

        for i in range(1, len(days)):
            prev = datetime.strptime(days[i-1], "%Y-%m-%d")
            curr = datetime.strptime(days[i], "%Y-%m-%d")

            if (curr - prev).days == 1:
                current_streak += 1
                max_streak = max(max_streak, current_streak)
            else:
                current_streak = 1

        streaks.append({
            "email": email,
            "longest_streak": max_streak,
            "total_days": len(days),
        })

    streaks.sort(key=lambda x: x["longest_streak"], reverse=True)
    return streaks


def get_leaderboard_session(conn: sqlite3.Connection) -> list[dict]:
    """Get leaderboard sorted by longest single session."""
    cursor = conn.execute(
        """
        SELECT
            email,
            session_id,
            MIN(timestamp) as session_start,
            MAX(timestamp) as session_end,
            COUNT(*) as request_count,
            SUM(duration_ms) as session_duration_ms
        FROM requests
        WHERE session_id IS NOT NULL AND timestamp IS NOT NULL
        GROUP BY email, session_id
        """
    )

    # Find the longest session per user
    user_sessions = {}
    for row in cursor.fetchall():
        email, session_id, start, end, count, duration = row
        if email not in user_sessions or duration > user_sessions[email]["session_duration_ms"]:
            user_sessions[email] = {
                "email": email,
                "session_id": session_id,
                "session_duration_ms": duration,
                "session_duration": format_duration(duration),
                "request_count": count,
            }

    sessions = list(user_sessions.values())
    sessions.sort(key=lambda x: x["session_duration_ms"], reverse=True)
    return sessions


def get_leaderboard(
    conn: sqlite3.Connection,
    sort_by: str = "tokens",
) -> list[dict]:
    """Get leaderboard data by type (deprecated, use specific leaderboard functions)."""
    leaderboard_funcs = {
        "tokens": get_leaderboard_tokens,
        "cost": get_leaderboard_cost,
        "time": get_leaderboard_time,
        "io_ratio": get_leaderboard_io_ratio,
        "efficiency": get_leaderboard_efficiency,
        "streak": get_leaderboard_streak,
        "session": get_leaderboard_session,
        "models": get_favorite_models,
    }

    func = leaderboard_funcs.get(sort_by, get_leaderboard_tokens)
    return func(conn)

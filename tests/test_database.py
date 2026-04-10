import sqlite3
import pytest
from claude_leaderboard.database import init_db, upsert_usage, get_leaderboard

TEST_DB = ":memory:"


def test_init_db_creates_tables():
    """Test that init_db creates the employee_usage table."""
    conn = sqlite3.connect(TEST_DB)
    init_db(conn)

    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='employee_usage'")
    assert cursor.fetchone() is not None
    conn.close()


def test_upsert_usage_creates_new_record():
    """Test that upsert_usage creates a new record for new employee."""
    conn = sqlite3.connect(TEST_DB)
    init_db(conn)

    upsert_usage(conn, "alice@example.com", "uuid-123", 100, 50, 10, 5, 0.25)

    leaderboard = get_leaderboard(conn)
    assert len(leaderboard) == 1
    assert leaderboard[0]["email"] == "alice@example.com"
    assert leaderboard[0]["total_tokens"] == 165  # 100+50+10+5
    assert leaderboard[0]["total_cost"] == 0.25
    conn.close()


def test_upsert_usage_updates_existing_record():
    """Test that upsert_usage updates an existing employee record."""
    conn = sqlite3.connect(TEST_DB)
    init_db(conn)

    upsert_usage(conn, "alice@example.com", "uuid-123", 100, 50, 10, 5, 0.25)
    upsert_usage(conn, "alice@example.com", "uuid-123", 200, 100, 20, 10, 0.50)

    leaderboard = get_leaderboard(conn, sort_by="total_tokens")
    assert len(leaderboard) == 1
    assert leaderboard[0]["total_tokens"] == 495  # (100+50+10+5) + (200+100+20+10)
    assert leaderboard[0]["total_cost"] == 0.75  # 0.25 + 0.50
    conn.close()


def test_get_leaderboard_sorting():
    """Test get_leaderboard sorting by different columns."""
    conn = sqlite3.connect(TEST_DB)
    init_db(conn)

    # Add multiple requests to differentiate prompt_count
    upsert_usage(conn, "alice@example.com", "uuid-1", 100, 50, 0, 0, 0.30)
    upsert_usage(conn, "alice@example.com", "uuid-1", 100, 50, 0, 0, 0.30)  # 2nd request
    upsert_usage(conn, "bob@example.com", "uuid-2", 50, 25, 0, 0, 0.15)
    upsert_usage(conn, "charlie@example.com", "uuid-3", 200, 100, 0, 0, 0.60)
    upsert_usage(conn, "charlie@example.com", "uuid-3", 200, 100, 0, 0, 0.60)  # 2nd request
    upsert_usage(conn, "charlie@example.com", "uuid-3", 200, 100, 0, 0, 0.60)  # 3rd request

    # Sort by total_tokens descending (Charlie: 900, Alice: 300, Bob: 75)
    leaderboard = get_leaderboard(conn, sort_by="total_tokens")
    emails = [row["email"] for row in leaderboard]
    assert emails == ["charlie@example.com", "alice@example.com", "bob@example.com"]

    # Sort by total_cost descending (Charlie: 1.80, Alice: 0.60, Bob: 0.15)
    leaderboard = get_leaderboard(conn, sort_by="total_cost")
    emails = [row["email"] for row in leaderboard]
    assert emails == ["charlie@example.com", "alice@example.com", "bob@example.com"]

    # Sort by prompt_count descending (Charlie: 3, Alice: 2, Bob: 1)
    leaderboard = get_leaderboard(conn, sort_by="prompt_count")
    emails = [row["email"] for row in leaderboard]
    assert emails == ["charlie@example.com", "alice@example.com", "bob@example.com"]
    conn.close()

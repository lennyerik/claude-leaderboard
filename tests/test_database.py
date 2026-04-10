import sqlite3
import pytest
from claude_leaderboard.database import (
    init_db,
    insert_request,
    get_leaderboard_tokens,
    get_leaderboard_cost,
    get_leaderboard_time,
    get_leaderboard_io_ratio,
    get_leaderboard_efficiency,
    get_leaderboard_streak,
    get_leaderboard_session,
    get_favorite_models,
    format_duration,
)

TEST_DB = ":memory:"


def test_init_db_creates_requests_table():
    """Test that init_db creates the requests table."""
    conn = sqlite3.connect(TEST_DB)
    init_db(conn)

    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='requests'")
    assert cursor.fetchone() is not None
    conn.close()


def test_insert_request():
    """Test inserting a single request."""
    conn = sqlite3.connect(TEST_DB)
    init_db(conn)

    insert_request(
        conn,
        email="alice@example.com",
        session_id="session-1",
        model="claude-haiku-4-5-20251001",
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.001,
        duration_ms=1500,
        timestamp="2026-04-10T10:00:00Z",
    )

    cursor = conn.execute("SELECT * FROM requests")
    row = cursor.fetchone()
    assert row[1] == "alice@example.com"
    assert row[3] == "claude-haiku-4-5-20251001"
    assert row[4] == 100  # input_tokens
    assert row[5] == 50   # output_tokens
    conn.close()


def test_leaderboard_tokens():
    """Test token leaderboard calculation."""
    conn = sqlite3.connect(TEST_DB)
    init_db(conn)

    # Insert test data - Alice has most tokens
    insert_request(conn, "alice@example.com", "s1", "haiku", 100, 50, 0, 0, 0.01, 1000, "2026-04-10T10:00:00Z")
    insert_request(conn, "alice@example.com", "s1", "haiku", 50, 25, 0, 0, 0.005, 500, "2026-04-10T10:01:00Z")
    insert_request(conn, "bob@example.com", "s2", "sonnet", 30, 20, 0, 0, 0.01, 800, "2026-04-10T11:00:00Z")

    leaderboard = get_leaderboard_tokens(conn)
    assert len(leaderboard) == 2
    assert leaderboard[0]["email"] == "alice@example.com"
    assert leaderboard[0]["total_tokens"] == 225  # (100+50) + (50+25)
    assert leaderboard[0]["request_count"] == 2
    assert leaderboard[1]["email"] == "bob@example.com"
    assert leaderboard[1]["total_tokens"] == 50  # 30+20
    conn.close()


def test_leaderboard_tokens_excludes_cache():
    """Test that token leaderboard excludes cache tokens from total."""
    conn = sqlite3.connect(TEST_DB)
    init_db(conn)

    # Insert request with cache tokens
    insert_request(
        conn,
        email="alice@example.com",
        session_id="s1",
        model="haiku",
        input_tokens=10,
        output_tokens=100,
        cache_read_tokens=43997,  # Should NOT count
        cache_creation_tokens=19,
        cost_usd=0.001,
        duration_ms=1000,
        timestamp="2026-04-10T10:00:00Z",
    )

    leaderboard = get_leaderboard_tokens(conn)
    assert leaderboard[0]["total_tokens"] == 110  # Only input+output, not cache
    conn.close()


def test_leaderboard_cost():
    """Test cost leaderboard calculation."""
    conn = sqlite3.connect(TEST_DB)
    init_db(conn)

    insert_request(conn, "alice@example.com", "s1", "opus", 100, 50, 0, 0, 0.10, 1000, "2026-04-10T10:00:00Z")
    insert_request(conn, "bob@example.com", "s2", "haiku", 100, 50, 0, 0, 0.05, 1000, "2026-04-10T11:00:00Z")

    leaderboard = get_leaderboard_cost(conn)
    assert leaderboard[0]["email"] == "alice@example.com"
    assert leaderboard[0]["total_cost"] == 0.10
    assert leaderboard[1]["email"] == "bob@example.com"
    assert leaderboard[1]["total_cost"] == 0.05
    conn.close()


def test_leaderboard_time():
    """Test time leaderboard calculation."""
    conn = sqlite3.connect(TEST_DB)
    init_db(conn)

    insert_request(conn, "alice@example.com", "s1", "haiku", 10, 10, 0, 0, 0.001, 3000, "2026-04-10T10:00:00Z")  # 3s
    insert_request(conn, "alice@example.com", "s1", "haiku", 10, 10, 0, 0, 0.001, 2000, "2026-04-10T10:01:00Z")  # 2s
    insert_request(conn, "bob@example.com", "s2", "haiku", 10, 10, 0, 0, 0.001, 1000, "2026-04-10T11:00:00Z")  # 1s

    leaderboard = get_leaderboard_time(conn)
    assert leaderboard[0]["email"] == "alice@example.com"
    assert leaderboard[0]["total_duration_ms"] == 5000
    assert leaderboard[0]["total_duration"] == "5s"
    assert leaderboard[1]["total_duration_ms"] == 1000
    conn.close()


def test_leaderboard_io_ratio():
    """Test I/O ratio leaderboard calculation."""
    conn = sqlite3.connect(TEST_DB)
    init_db(conn)

    # Chatty user: lots of input, little output
    insert_request(conn, "chatty@example.com", "s1", "haiku", 1000, 10, 0, 0, 0.001, 1000, "2026-04-10T10:00:00Z")

    # Efficient user: little input, lots of output
    insert_request(conn, "efficient@example.com", "s2", "haiku", 10, 1000, 0, 0, 0.001, 1000, "2026-04-10T11:00:00Z")

    # Test chatty leaderboard (io_ratio DESC)
    leaderboard = get_leaderboard_io_ratio(conn)
    assert leaderboard[0]["email"] == "chatty@example.com"
    assert leaderboard[0]["io_ratio"] == 100.0  # 1000/10

    # Test efficiency leaderboard (io_ratio ASC)
    leaderboard = get_leaderboard_efficiency(conn)
    assert leaderboard[0]["email"] == "efficient@example.com"
    assert leaderboard[0]["io_ratio"] == 0.01  # 10/1000
    conn.close()


def test_leaderboard_streak():
    """Test streak calculation."""
    conn = sqlite3.connect(TEST_DB)
    init_db(conn)

    # User with 3-day streak
    insert_request(conn, "streaker@example.com", "s1", "haiku", 10, 10, 0, 0, 0.001, 1000, "2026-04-08T10:00:00Z")
    insert_request(conn, "streaker@example.com", "s2", "haiku", 10, 10, 0, 0, 0.001, 1000, "2026-04-09T10:00:00Z")
    insert_request(conn, "streaker@example.com", "s3", "haiku", 10, 10, 0, 0, 0.001, 1000, "2026-04-10T10:00:00Z")

    # User with 2-day streak
    insert_request(conn, "casual@example.com", "s4", "haiku", 10, 10, 0, 0, 0.001, 1000, "2026-04-09T10:00:00Z")
    insert_request(conn, "casual@example.com", "s5", "haiku", 10, 10, 0, 0, 0.001, 1000, "2026-04-10T10:00:00Z")

    leaderboard = get_leaderboard_streak(conn)
    assert leaderboard[0]["email"] == "streaker@example.com"
    assert leaderboard[0]["longest_streak"] == 3
    assert leaderboard[1]["email"] == "casual@example.com"
    assert leaderboard[1]["longest_streak"] == 2
    conn.close()


def test_leaderboard_session():
    """Test longest session calculation."""
    conn = sqlite3.connect(TEST_DB)
    init_db(conn)

    # Alice: session with multiple requests totaling 5000ms
    insert_request(conn, "alice@example.com", "session-long", "haiku", 10, 10, 0, 0, 0.001, 2000, "2026-04-10T10:00:00Z")
    insert_request(conn, "alice@example.com", "session-long", "haiku", 10, 10, 0, 0, 0.001, 3000, "2026-04-10T10:01:00Z")

    # Bob: shorter session
    insert_request(conn, "bob@example.com", "session-short", "haiku", 10, 10, 0, 0, 0.001, 1000, "2026-04-10T11:00:00Z")

    leaderboard = get_leaderboard_session(conn)
    assert leaderboard[0]["email"] == "alice@example.com"
    assert leaderboard[0]["session_duration_ms"] == 5000
    assert leaderboard[0]["request_count"] == 2
    conn.close()


def test_favorite_models():
    """Test favorite model calculation."""
    conn = sqlite3.connect(TEST_DB)
    init_db(conn)

    # Alice uses opus more often
    insert_request(conn, "alice@example.com", "s1", "claude-opus-4-6", 10, 10, 0, 0, 0.01, 1000, "2026-04-10T10:00:00Z")
    insert_request(conn, "alice@example.com", "s2", "claude-opus-4-6", 10, 10, 0, 0, 0.01, 1000, "2026-04-10T10:01:00Z")
    insert_request(conn, "alice@example.com", "s3", "claude-haiku-4-5-20251001", 10, 10, 0, 0, 0.001, 1000, "2026-04-10T10:02:00Z")

    # Bob only uses haiku
    insert_request(conn, "bob@example.com", "s4", "claude-haiku-4-5-20251001", 10, 10, 0, 0, 0.001, 1000, "2026-04-10T11:00:00Z")

    favorites = get_favorite_models(conn)
    alice = next(f for f in favorites if f["email"] == "alice@example.com")
    bob = next(f for f in favorites if f["email"] == "bob@example.com")

    assert alice["favorite_model"] == "claude-opus-4-6"
    assert alice["model_count"] == 2
    assert bob["favorite_model"] == "claude-haiku-4-5-20251001"
    conn.close()


def test_format_duration():
    """Test duration formatting."""
    assert format_duration(500) == "500ms"
    assert format_duration(1000) == "1s"
    assert format_duration(1500) == "1s 500ms"
    assert format_duration(60000) == "1m 0s"
    assert format_duration(90000) == "1m 30s"
    assert format_duration(3600000) == "1h 0m"
    assert format_duration(3661500) == "1h 1m"


def test_empty_leaderboards():
    """Test that empty leaderboards return empty lists."""
    conn = sqlite3.connect(TEST_DB)
    init_db(conn)

    assert get_leaderboard_tokens(conn) == []
    assert get_leaderboard_cost(conn) == []
    assert get_leaderboard_time(conn) == []
    assert get_leaderboard_io_ratio(conn) == []
    assert get_leaderboard_streak(conn) == []
    assert get_leaderboard_session(conn) == []
    assert get_favorite_models(conn) == []
    conn.close()

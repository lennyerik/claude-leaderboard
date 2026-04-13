import sqlite3
import os
import pytest
from fastapi.testclient import TestClient
from claude_leaderboard.main import app, get_db
from claude_leaderboard.database import init_db

TEST_DB_PATH = "/tmp/test_claude_leaderboard_main.db"


def override_get_db():
    """Override dependency to use test database."""
    conn = sqlite3.connect(TEST_DB_PATH, check_same_thread=False)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture(autouse=True)
def setup_test_db():
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)
    conn = sqlite3.connect(TEST_DB_PATH)
    init_db(conn)
    conn.close()
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)


client = TestClient(app)


def test_health_endpoint():
    """Test the health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_otlp_logs_endpoint_accepts_json():
    """Test OTLP endpoint accepts JSON payload."""
    payload = {
        "resourceLogs": [{
            "scopeLogs": [{
                "logRecords": [{
                    "attributes": [
                        {"key": "event.name", "value": {"stringValue": "claude_code.api_request"}},
                        {"key": "user.email", "value": {"stringValue": "test@example.com"}},
                        {"key": "user.account_uuid", "value": {"stringValue": "uuid-123"}},
                        {"key": "session.id", "value": {"stringValue": "session-1"}},
                        {"key": "model", "value": {"stringValue": "claude-haiku-4-5-20251001"}},
                        {"key": "input_tokens", "value": {"intValue": 100}},
                        {"key": "output_tokens", "value": {"intValue": 50}},
                        {"key": "cache_read_tokens", "value": {"intValue": 10}},
                        {"key": "cache_creation_tokens", "value": {"intValue": 5}},
                        {"key": "cost_usd", "value": {"doubleValue": 0.25}},
                        {"key": "duration_ms", "value": {"intValue": 1500}},
                        {"key": "event.timestamp", "value": {"stringValue": "2026-04-10T10:00:00Z"}},
                    ]
                }]
            }]
        }]
    }
    response = client.post("/v1/logs", json=payload)
    assert response.status_code == 200
    assert response.json()["success"] is True


def test_otlp_logs_endpoint_stores_data():
    """Test that OTLP endpoint stores data in database."""
    payload = {
        "resourceLogs": [{
            "scopeLogs": [{
                "logRecords": [{
                    "attributes": [
                        {"key": "event.name", "value": {"stringValue": "claude_code.api_request"}},
                        {"key": "user.email", "value": {"stringValue": "alice@test.com"}},
                        {"key": "user.account_uuid", "value": {"stringValue": "uuid-456"}},
                        {"key": "input_tokens", "value": {"intValue": 200}},
                        {"key": "output_tokens", "value": {"intValue": 100}},
                        {"key": "cache_read_tokens", "value": {"intValue": 0}},
                        {"key": "cache_creation_tokens", "value": {"intValue": 0}},
                        {"key": "cost_usd", "value": {"doubleValue": 0.50}},
                    ]
                }]
            }]
        }]
    }
    client.post("/v1/logs", json=payload)

    # Check that data was stored
    response = client.get("/api/leaderboard?sort=tokens")
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 1
    assert data["data"][0]["email"] == "alice@test.com"
    assert data["data"][0]["total_tokens"] == 300  # 200+100
    assert data["data"][0]["total_cost"] == 0.50


def test_api_leaderboard_with_sort():
    """Test leaderboard API with different sort options."""
    # Add two employees
    for email, tokens, cost in [("a@example.com", 100, 0.10), ("b@example.com", 200, 0.20)]:
        payload = {
            "resourceLogs": [{
                "scopeLogs": [{
                    "logRecords": [{
                        "attributes": [
                            {"key": "event.name", "value": {"stringValue": "claude_code.api_request"}},
                            {"key": "user.email", "value": {"stringValue": email}},
                            {"key": "input_tokens", "value": {"intValue": tokens}},
                            {"key": "output_tokens", "value": {"intValue": 0}},
                            {"key": "cost_usd", "value": {"doubleValue": cost}},
                        ]
                    }]
                }]
            }]
        }
        client.post("/v1/logs", json=payload)

    # Test sort by tokens (default)
    response = client.get("/api/leaderboard?sort=tokens")
    data = response.json()
    emails = [e["email"] for e in data["data"]]
    assert emails == ["b@example.com", "a@example.com"]

    # Test sort by cost
    response = client.get("/api/leaderboard?sort=cost")
    data = response.json()
    emails = [e["email"] for e in data["data"]]
    assert emails == ["b@example.com", "a@example.com"]


def test_api_leaderboard_invalid_sort_defaults_to_tokens():
    """Test that invalid sort parameter falls back to tokens."""
    payload = {
        "resourceLogs": [{
            "scopeLogs": [{
                "logRecords": [{
                    "attributes": [
                        {"key": "event.name", "value": {"stringValue": "claude_code.api_request"}},
                        {"key": "user.email", "value": {"stringValue": "test@example.com"}},
                        {"key": "input_tokens", "value": {"intValue": 100}},
                        {"key": "output_tokens", "value": {"intValue": 50}},
                        {"key": "cost_usd", "value": {"doubleValue": 0.01}},
                    ]
                }]
            }]
        }]
    }
    client.post("/v1/logs", json=payload)

    response = client.get("/api/leaderboard?sort=invalid_sort")
    assert response.status_code == 200
    data = response.json()
    assert data["leaderboard"] == "invalid_sort"
    assert data["title"] == "Token Usage"  # Falls back to tokens
    assert len(data["data"]) == 1


def test_otlp_logs_malformed_body():
    """Test that malformed (non-JSON) body returns 0 events processed."""
    response = client.post(
        "/v1/logs",
        content=b"this is not json",
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 200
    assert response.json()["events_processed"] == 0


def test_otlp_logs_skips_events_without_email():
    """Test that events without user_email are not stored."""
    payload = {
        "resourceLogs": [{
            "scopeLogs": [{
                "logRecords": [{
                    "attributes": [
                        {"key": "event.name", "value": {"stringValue": "api_request"}},
                        # user.id present but no user.email — parser falls back to user.id
                        {"key": "user.id", "value": {"stringValue": "device-abc"}},
                        {"key": "input_tokens", "value": {"intValue": 100}},
                        {"key": "output_tokens", "value": {"intValue": 50}},
                    ]
                }]
            }]
        }]
    }
    response = client.post("/v1/logs", json=payload)
    assert response.status_code == 200
    # The event is parsed with user_email="device-abc" (fallback to user.id)
    assert response.json()["events_processed"] == 1

    response = client.get("/api/leaderboard?sort=tokens")
    data = response.json()
    assert len(data["data"]) == 1
    assert data["data"][0]["email"] == "device-abc"


def test_duplicate_events_insert_separately():
    """Test that sending the same event twice creates two rows."""
    payload = {
        "resourceLogs": [{
            "scopeLogs": [{
                "logRecords": [{
                    "attributes": [
                        {"key": "event.name", "value": {"stringValue": "api_request"}},
                        {"key": "user.email", "value": {"stringValue": "dup@example.com"}},
                        {"key": "input_tokens", "value": {"intValue": 100}},
                        {"key": "output_tokens", "value": {"intValue": 50}},
                        {"key": "cost_usd", "value": {"doubleValue": 0.01}},
                    ]
                }]
            }]
        }]
    }
    client.post("/v1/logs", json=payload)
    client.post("/v1/logs", json=payload)

    response = client.get("/api/leaderboard?sort=tokens")
    data = response.json()
    user = data["data"][0]
    assert user["email"] == "dup@example.com"
    assert user["total_tokens"] == 300  # 150 * 2
    assert user["request_count"] == 2


def test_leaderboard_html_endpoint():
    """Test leaderboard HTML endpoint returns HTML."""
    response = client.get("/leaderboard")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert b"Leaderboard" in response.content


def test_leaderboard_html_with_different_tabs():
    """Test leaderboard HTML with different sort tabs."""
    tabs = ["tokens", "cost", "time", "io_ratio", "efficiency", "streak", "session", "models"]

    for tab in tabs:
        response = client.get(f"/leaderboard?sort={tab}")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


def test_leaderboard_html_escapes_email():
    """Test that HTML leaderboard escapes user-controlled strings."""
    payload = {
        "resourceLogs": [{
            "scopeLogs": [{
                "logRecords": [{
                    "attributes": [
                        {"key": "event.name", "value": {"stringValue": "api_request"}},
                        {"key": "user.email", "value": {"stringValue": "<script>alert(1)</script>@evil.com"}},
                        {"key": "input_tokens", "value": {"intValue": 100}},
                        {"key": "output_tokens", "value": {"intValue": 50}},
                        {"key": "cost_usd", "value": {"doubleValue": 0.01}},
                    ]
                }]
            }]
        }]
    }
    client.post("/v1/logs", json=payload)

    response = client.get("/leaderboard?sort=tokens")
    assert response.status_code == 200
    # The raw script tag should NOT appear in the HTML
    assert b"<script>alert(1)</script>" not in response.content
    # The escaped version should appear
    assert b"&lt;script&gt;" in response.content


def test_root_redirects():
    """Test root redirects to /leaderboard."""
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/leaderboard"

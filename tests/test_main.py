import sqlite3
import os
import pytest
from fastapi.testclient import TestClient
from claude_otel.main import app, get_db
from claude_otel.database import init_db

TEST_DB_PATH = "/tmp/test_claude_otel_main.db"


def override_get_db():
    """Override dependency to use test database."""
    conn = sqlite3.connect(TEST_DB_PATH, check_same_thread=False)
    init_db(conn)
    try:
        yield conn
    finally:
        conn.close()


# Clean up any existing test db and setup
@pytest.fixture(autouse=True)
def setup_test_db():
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)
    # Initialize test database
    conn = sqlite3.connect(TEST_DB_PATH)
    init_db(conn)
    conn.close()
    yield
    # Cleanup after tests
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)


# Override the dependency
app.dependency_overrides[get_db] = override_get_db

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
                        {"key": "input_tokens", "value": {"intValue": 100}},
                        {"key": "output_tokens", "value": {"intValue": 50}},
                        {"key": "cache_read_tokens", "value": {"intValue": 10}},
                        {"key": "cache_creation_tokens", "value": {"intValue": 5}},
                        {"key": "cost_usd", "value": {"doubleValue": 0.25}},
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
    response = client.get("/api/leaderboard")
    assert response.status_code == 200
    data = response.json()
    assert len(data["employees"]) == 1
    assert data["employees"][0]["email"] == "alice@test.com"
    assert data["employees"][0]["total_tokens"] == 300
    assert data["employees"][0]["total_cost"] == 0.50


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

    # Test sort by total_tokens
    response = client.get("/api/leaderboard?sort=total_tokens")
    data = response.json()
    emails = [e["email"] for e in data["employees"]]
    assert emails == ["b@example.com", "a@example.com"]

    # Test sort by total_cost
    response = client.get("/api/leaderboard?sort=total_cost")
    data = response.json()
    emails = [e["email"] for e in data["employees"]]
    assert emails == ["b@example.com", "a@example.com"]


def test_leaderboard_html_endpoint():
    """Test leaderboard HTML endpoint returns HTML."""
    response = client.get("/leaderboard")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert b"Leaderboard" in response.content


def test_root_redirects():
    """Test root redirects to /leaderboard."""
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/leaderboard"

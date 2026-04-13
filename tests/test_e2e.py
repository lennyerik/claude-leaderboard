"""End-to-end test simulating Claude Code sending telemetry."""
import sqlite3
import os
import pytest
from fastapi.testclient import TestClient
from claude_leaderboard.main import app, get_db
from claude_leaderboard.database import init_db

TEST_DB_PATH = "/tmp/test_claude_leaderboard_e2e.db"


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


def test_full_flow_claude_code_to_leaderboard():
    """Simulate Claude Code sending telemetry and verify leaderboard updates."""

    # Simulate multiple employees using Claude Code
    employees_data = [
        {
            "email": "alice@company.com",
            "uuid": "uuid-alice",
            "requests": [
                {"input": 1000, "output": 500, "cost": 0.015},
                {"input": 2000, "output": 1000, "cost": 0.030},
            ]
        },
        {
            "email": "bob@company.com",
            "uuid": "uuid-bob",
            "requests": [
                {"input": 500, "output": 250, "cost": 0.0075},
            ]
        },
        {
            "email": "charlie@company.com",
            "uuid": "uuid-charlie",
            "requests": [
                {"input": 3000, "output": 1500, "cost": 0.045},
                {"input": 1000, "output": 500, "cost": 0.015},
                {"input": 2000, "output": 1000, "cost": 0.030},
            ]
        },
    ]

    # Send OTLP logs for each employee
    for emp in employees_data:
        for req in emp["requests"]:
            payload = {
                "resourceLogs": [{
                    "scopeLogs": [{
                        "logRecords": [{
                            "attributes": [
                                {"key": "event.name", "value": {"stringValue": "claude_code.api_request"}},
                                {"key": "user.email", "value": {"stringValue": emp["email"]}},
                                {"key": "user.account_uuid", "value": {"stringValue": emp["uuid"]}},
                                {"key": "input_tokens", "value": {"intValue": req["input"]}},
                                {"key": "output_tokens", "value": {"intValue": req["output"]}},
                                {"key": "cache_read_tokens", "value": {"intValue": 0}},
                                {"key": "cache_creation_tokens", "value": {"intValue": 0}},
                                {"key": "cost_usd", "value": {"doubleValue": req["cost"]}},
                            ]
                        }]
                    }]
                }]
            }
            response = client.post("/v1/logs", json=payload)
            assert response.status_code == 200
            assert response.json()["success"] is True

    # Check leaderboard sorted by tokens
    response = client.get("/api/leaderboard?sort=tokens")
    assert response.status_code == 200
    data = response.json()

    # Verify we have 3 employees
    assert data["count"] == 3

    # Verify sorting (Charlie: 4500+1500+3000=9000, Alice: 1500+3000=4500, Bob: 750)
    employees = data["data"]
    assert employees[0]["email"] == "charlie@company.com"
    assert employees[0]["total_tokens"] == 9000  # (3000+1500) + (1000+500) + (2000+1000)
    assert employees[0]["total_cost"] == pytest.approx(0.09, abs=0.001)  # 0.045 + 0.015 + 0.030
    assert employees[0]["request_count"] == 3

    # Alice should be second (1000+500 + 2000+1000 = 4500)
    assert employees[1]["email"] == "alice@company.com"
    assert employees[1]["total_tokens"] == 4500
    assert employees[1]["request_count"] == 2

    # Bob should be third (500+250 = 750)
    assert employees[2]["email"] == "bob@company.com"
    assert employees[2]["total_tokens"] == 750
    assert employees[2]["request_count"] == 1

    # Test HTML leaderboard page
    response = client.get("/leaderboard")
    assert response.status_code == 200
    assert b"charlie@company.com" in response.content
    assert b"alice@company.com" in response.content
    assert b"bob@company.com" in response.content


def test_full_flow_with_all_metadata():
    """Test full flow including all metadata fields."""
    # Use a unique email to avoid conflicts with other tests
    unique_email = "metadata-test@example.com"

    payload = {
        "resourceLogs": [{
            "resource": {
                "attributes": [
                    {"key": "service.name", "value": {"stringValue": "claude-code"}},
                ]
            },
            "scopeLogs": [{
                "scope": {"name": "com.anthropic.claude_code.events"},
                "logRecords": [{
                    "attributes": [
                        {"key": "event.name", "value": {"stringValue": "api_request"}},
                        {"key": "user.email", "value": {"stringValue": unique_email}},
                        {"key": "user.account_uuid", "value": {"stringValue": "test-uuid"}},
                        {"key": "session.id", "value": {"stringValue": "session-123"}},
                        {"key": "model", "value": {"stringValue": "claude-opus-4-6"}},
                        {"key": "input_tokens", "value": {"stringValue": "100"}},
                        {"key": "output_tokens", "value": {"stringValue": "50"}},
                        {"key": "cache_read_tokens", "value": {"stringValue": "10"}},
                        {"key": "cache_creation_tokens", "value": {"stringValue": "5"}},
                        {"key": "cost_usd", "value": {"stringValue": "0.01"}},
                        {"key": "duration_ms", "value": {"stringValue": "2000"}},
                        {"key": "event.timestamp", "value": {"stringValue": "2026-04-10T12:00:00Z"}},
                        {"key": "organization.id", "value": {"stringValue": "org-123"}},
                        {"key": "prompt.id", "value": {"stringValue": "prompt-456"}},
                    ]
                }]
            }]
        }]
    }

    response = client.post("/v1/logs", json=payload)
    assert response.status_code == 200
    assert response.json()["events_processed"] == 1

    # Check various leaderboards - find our user in the results
    response = client.get("/api/leaderboard?sort=tokens")
    data = response.json()
    users = [u for u in data["data"] if u["email"] == unique_email]
    assert len(users) == 1
    assert users[0]["total_tokens"] == 150

    response = client.get("/api/leaderboard?sort=time")
    data = response.json()
    users = [u for u in data["data"] if u["email"] == unique_email]
    assert len(users) == 1
    assert users[0]["total_duration_ms"] == 2000

    response = client.get("/api/leaderboard?sort=models")
    data = response.json()
    users = [u for u in data["data"] if u["email"] == unique_email]
    assert len(users) == 1
    assert users[0]["favorite_model"] == "claude-opus-4-6"

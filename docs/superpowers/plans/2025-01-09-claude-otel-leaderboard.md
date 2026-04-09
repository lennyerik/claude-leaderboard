# Claude Code OpenTelemetry Leaderboard Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.
> **IMPORTANT:** Use `uv` for all Python operations. Do NOT install anything system-wide. All dependencies go in the uv virtual environment.

**Goal:** Build an OpenTelemetry endpoint that receives Claude Code telemetry, tracks token usage per employee, and displays a leaderboard web UI.

**Architecture:** FastAPI app with SQLite backend. OTLP logs endpoint receives Claude Code telemetry, parses `api_request` events, aggregates usage per employee, and serves a web UI with toggleable leaderboard views.

**Tech Stack:** Python 3.12+, FastAPI, uvicorn, SQLite, pytest (for testing). Using `uv` for dependency management (NOT pip, NOT system packages).

**Design Doc:** See `docs/2025-01-09-claude-otel-leaderboard-design.md`

---

## Chunk 1: Project Setup and Structure

### Task 1: Initialize uv project

**Files:**
- Create: `pyproject.toml`
- Create: `src/claude_otel/__init__.py`
- Create: `tests/__init__.py`
- Create: `.python-version`

- [ ] **Step 1: Create .python-version file**

```bash
echo "3.12" > .python-version
```

- [ ] **Step 2: Initialize uv project**

Run: `uv init --python 3.12`
Expected: Creates pyproject.toml with project structure

- [ ] **Step 3: Add dependencies with uv**

Run: `uv add fastapi uvicorn pytest pytest-asyncio httpx`
Expected: Dependencies added to pyproject.toml, uv.lock created

- [ ] **Step 4: Create directory structure**

Run:
```bash
mkdir -p src/claude_otel tests
```

- [ ] **Step 5: Create __init__.py files**

Create `src/claude_otel/__init__.py`:
```python
"""Claude Code OpenTelemetry Leaderboard."""
__version__ = "0.1.0"
```

Create `tests/__init__.py`:
```python
"""Tests for claude_otel."""
```

- [ ] **Step 6: Commit**

```bash
git add .
git commit -m "chore: initialize uv project with dependencies"
```

---

## Chunk 2: Database Layer

### Task 2: Create database module

**Files:**
- Create: `src/claude_otel/database.py`
- Test: `tests/test_database.py`

- [ ] **Step 1: Write failing test for database init**

Create `tests/test_database.py`:
```python
import sqlite3
import pytest
from claude_otel.database import init_db, upsert_usage, get_leaderboard

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

    upsert_usage(conn, "alice@example.com", "uuid-1", 100, 50, 0, 0, 0.30)
    upsert_usage(conn, "bob@example.com", "uuid-2", 50, 25, 0, 0, 0.15)
    upsert_usage(conn, "charlie@example.com", "uuid-3", 200, 100, 0, 0, 0.60)

    # Sort by total_tokens descending
    leaderboard = get_leaderboard(conn, sort_by="total_tokens")
    emails = [row["email"] for row in leaderboard]
    assert emails == ["charlie@example.com", "alice@example.com", "bob@example.com"]

    # Sort by total_cost descending
    leaderboard = get_leaderboard(conn, sort_by="total_cost")
    emails = [row["email"] for row in leaderboard]
    assert emails == ["charlie@example.com", "alice@example.com", "bob@example.com"]

    # Sort by prompt_count descending
    leaderboard = get_leaderboard(conn, sort_by="prompt_count")
    emails = [row["email"] for row in leaderboard]
    assert emails == ["charlie@example.com", "alice@example.com", "bob@example.com"]
    conn.close()
```

Run: `uv run pytest tests/test_database.py -v`
Expected: FAIL - ImportError: cannot import name 'init_db' from 'claude_otel.database'

- [ ] **Step 2: Implement database module**

Create `src/claude_otel/database.py`:
```python
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
    total_tokens = input_tokens + output_tokens + cache_read_tokens + cache_creation_tokens

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
```

- [ ] **Step 3: Run tests to verify**

Run: `uv run pytest tests/test_database.py -v`
Expected: All 4 tests PASS

- [ ] **Step 4: Commit**

```bash
git add src/claude_otel/database.py tests/test_database.py
git commit -m "feat: add database layer with init, upsert, and leaderboard queries"
```

---

## Chunk 3: OTLP Log Parsing

### Task 3: Parse OTLP logs manually

**Files:**
- Create: `src/claude_otel/otlp_parser.py`
- Test: `tests/test_otlp_parser.py`

Note: We're parsing OTLP JSON format manually. If this proves difficult, we'll use `opentelemetry-proto` package.

- [ ] **Step 1: Write failing test for OTLP parsing**

Create `tests/test_otlp_parser.py`:
```python
import json
import pytest
from claude_otel.otlp_parser import parse_otlp_logs, extract_api_request_events

def test_parse_empty_otlp_logs():
    """Test parsing empty OTLP logs."""
    payload = {"resourceLogs": []}
    result = parse_otlp_logs(json.dumps(payload))
    assert result == []

def test_parse_otlp_logs_with_api_request():
    """Test parsing OTLP logs with a claude_code.api_request event."""
    payload = {
        "resourceLogs": [{
            "scopeLogs": [{
                "logRecords": [{
                    "attributes": [
                        {"key": "event.name", "value": {"stringValue": "claude_code.api_request"}},
                        {"key": "user.email", "value": {"stringValue": "alice@example.com"}},
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
    result = parse_otlp_logs(json.dumps(payload))
    assert len(result) == 1
    assert result[0]["event_name"] == "claude_code.api_request"
    assert result[0]["user_email"] == "alice@example.com"
    assert result[0]["input_tokens"] == 100
    assert result[0]["output_tokens"] == 50
    assert result[0]["cache_read_tokens"] == 10
    assert result[0]["cache_creation_tokens"] == 5
    assert result[0]["cost_usd"] == 0.25

def test_extract_api_request_events_filters_by_event_name():
    """Test that only claude_code.api_request events are extracted."""
    events = [
        {"event_name": "claude_code.api_request", "user_email": "a@example.com"},
        {"event_name": "claude_code.user_prompt", "user_email": "a@example.com"},
        {"event_name": "claude_code.api_request", "user_email": "b@example.com"},
    ]
    result = extract_api_request_events(events)
    assert len(result) == 2
    assert all(e["event_name"] == "claude_code.api_request" for e in result)

def test_parse_handles_missing_attributes():
    """Test parsing handles missing optional attributes gracefully."""
    payload = {
        "resourceLogs": [{
            "scopeLogs": [{
                "logRecords": [{
                    "attributes": [
                        {"key": "event.name", "value": {"stringValue": "claude_code.api_request"}},
                        {"key": "user.email", "value": {"stringValue": "bob@example.com"}},
                        # Missing other attributes - should default to 0
                    ]
                }]
            }]
        }]
    }
    result = parse_otlp_logs(json.dumps(payload))
    assert len(result) == 1
    assert result[0]["input_tokens"] == 0
    assert result[0]["output_tokens"] == 0
    assert result[0]["cost_usd"] == 0.0
```

Run: `uv run pytest tests/test_otlp_parser.py -v`
Expected: FAIL - ImportError

- [ ] **Step 2: Implement OTLP parser**

Create `src/claude_otel/otlp_parser.py`:
```python
"""Parser for OTLP log data from Claude Code."""
import json
from typing import Any


def _get_attr_value(attr: dict) -> Any:
    """Extract value from OTLP attribute structure."""
    value = attr.get("value", {})
    if "stringValue" in value:
        return value["stringValue"]
    if "intValue" in value:
        return value["intValue"]
    if "doubleValue" in value:
        return value["doubleValue"]
    if "boolValue" in value:
        return value["boolValue"]
    return None


def parse_otlp_logs(data: str) -> list[dict]:
    """Parse OTLP JSON logs payload and return list of events.

    Returns list of dicts with keys:
    - event_name
    - user_email
    - account_uuid
    - input_tokens
    - output_tokens
    - cache_read_tokens
    - cache_creation_tokens
    - cost_usd
    """
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return []

    events = []
    resource_logs = payload.get("resourceLogs", [])

    for resource_log in resource_logs:
        scope_logs = resource_log.get("scopeLogs", [])
        for scope_log in scope_logs:
            log_records = scope_log.get("logRecords", [])
            for record in log_records:
                event = _parse_log_record(record)
                if event:
                    events.append(event)

    return events


def _parse_log_record(record: dict) -> dict | None:
    """Parse a single log record and extract relevant fields."""
    attributes = record.get("attributes", [])
    attr_map = {attr["key"]: _get_attr_value(attr) for attr in attributes}

    event_name = attr_map.get("event.name", "")

    # We only care about api_request events for token tracking
    if event_name != "claude_code.api_request":
        return None

    return {
        "event_name": event_name,
        "user_email": attr_map.get("user.email", ""),
        "account_uuid": attr_map.get("user.account_uuid", ""),
        "input_tokens": attr_map.get("input_tokens", 0) or 0,
        "output_tokens": attr_map.get("output_tokens", 0) or 0,
        "cache_read_tokens": attr_map.get("cache_read_tokens", 0) or 0,
        "cache_creation_tokens": attr_map.get("cache_creation_tokens", 0) or 0,
        "cost_usd": attr_map.get("cost_usd", 0.0) or 0.0,
    }


def extract_api_request_events(events: list[dict]) -> list[dict]:
    """Filter events to only include api_request events."""
    return [e for e in events if e.get("event_name") == "claude_code.api_request"]
```

- [ ] **Step 3: Run tests to verify**

Run: `uv run pytest tests/test_otlp_parser.py -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add src/claude_otel/otlp_parser.py tests/test_otlp_parser.py
git commit -m "feat: add OTLP log parser for Claude Code events"
```

---

## Chunk 4: FastAPI Application

### Task 4: Create FastAPI app with OTLP endpoint

**Files:**
- Create: `src/claude_otel/main.py`
- Test: `tests/test_main.py`

- [ ] **Step 1: Write failing test for main API**

Create `tests/test_main.py`:
```python
import pytest
from fastapi.testclient import TestClient
from claude_otel.main import app, get_db_connection

TEST_DB_PATH = ":memory:"

def get_test_db():
    import sqlite3
    conn = sqlite3.connect(TEST_DB_PATH)
    # Initialize schema if needed
    from claude_otel.database import init_db
    init_db(conn)
    return conn

# Override dependency
app.dependency_overrides[get_db_connection] = get_test_db

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
```

Run: `uv run pytest tests/test_main.py -v`
Expected: FAIL - ImportError

- [ ] **Step 2: Implement main FastAPI app**

Create `src/claude_otel/main.py`:
```python
"""FastAPI application for Claude OTel leaderboard."""
import os
import sqlite3
from contextlib import contextmanager
from fastapi import FastAPI, Request, Depends, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from claude_otel.database import init_db, upsert_usage, get_leaderboard
from claude_otel.otlp_parser import parse_otlp_logs, extract_api_request_events

# Configuration
DATABASE_PATH = os.getenv("DATABASE_PATH", "./claude_otel.db")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

app = FastAPI(title="Claude Code OTel Leaderboard")


@contextmanager
def get_db_connection():
    """Get database connection (used as FastAPI dependency)."""
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    try:
        yield conn
    finally:
        conn.close()


def get_db():
    """FastAPI dependency for database."""
    with get_db_connection() as conn:
        yield conn


# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    """Initialize database on startup."""
    conn = sqlite3.connect(DATABASE_PATH)
    init_db(conn)
    conn.close()


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/v1/logs")
async def receive_otlp_logs(request: Request):
    """Receive OTLP logs from Claude Code.

    This endpoint accepts OTLP ExportLogsServiceRequest in JSON format.
    """
    try:
        body = await request.json()
    except Exception:
        body_text = await request.body()
        body = body_text.decode("utf-8")

    # Parse the OTLP payload
    if isinstance(body, str):
        events = parse_otlp_logs(body)
    else:
        import json
        events = parse_otlp_logs(json.dumps(body))

    # Filter to only api_request events
    api_events = extract_api_request_events(events)

    # Store in database
    with get_db_connection() as conn:
        for event in api_events:
            if event.get("user_email"):
                upsert_usage(
                    conn,
                    email=event["user_email"],
                    account_uuid=event.get("account_uuid", ""),
                    input_tokens=event.get("input_tokens", 0),
                    output_tokens=event.get("output_tokens", 0),
                    cache_read_tokens=event.get("cache_read_tokens", 0),
                    cache_creation_tokens=event.get("cache_creation_tokens", 0),
                    cost_usd=event.get("cost_usd", 0.0),
                )

    return {"success": True, "events_processed": len(api_events)}


@app.get("/api/leaderboard")
async def api_leaderboard(
    sort: str = Query(default="total_tokens", description="Sort column"),
    db: sqlite3.Connection = Depends(get_db),
):
    """Get leaderboard data as JSON."""
    valid_sort = {"total_tokens", "total_cost", "prompt_count"}
    if sort not in valid_sort:
        sort = "total_tokens"

    employees = get_leaderboard(db, sort_by=sort)

    return {
        "employees": employees,
        "sort_by": sort,
        "count": len(employees),
    }


@app.get("/leaderboard", response_class=HTMLResponse)
async def leaderboard_page(
    request: Request,
    sort: str = Query(default="total_tokens"),
    db: sqlite3.Connection = Depends(get_db),
):
    """Render leaderboard HTML page."""
    valid_sort = {"total_tokens", "total_cost", "prompt_count"}
    if sort not in valid_sort:
        sort = "total_tokens"

    employees = get_leaderboard(db, sort_by=sort)

    # Build simple HTML
    html = build_leaderboard_html(employees, sort)
    return HTMLResponse(content=html)


@app.get("/")
async def root():
    """Redirect to leaderboard."""
    return RedirectResponse(url="/leaderboard", status_code=307)


def build_leaderboard_html(employees: list[dict], current_sort: str) -> str:
    """Build simple HTML for leaderboard."""
    sort_options = [
        ("total_tokens", "Tokens"),
        ("total_cost", "Cost ($)"),
        ("prompt_count", "Activity"),
    ]

    # Build sort buttons
    sort_buttons = []
    for sort_key, label in sort_options:
        if sort_key == current_sort:
            sort_buttons.append(f'<strong>{label}</strong>')
        else:
            sort_buttons.append(f'<a href="/leaderboard?sort={sort_key}">{label}</a>')

    # Build table rows
    rows = []
    for i, emp in enumerate(employees, 1):
        rows.append(f"""
        <tr>
            <td>{i}</td>
            <td>{emp['email']}</td>
            <td>{emp['total_tokens']:,}</td>
            <td>${emp['total_cost']:.4f}</td>
            <td>{emp['prompt_count']}</td>
        </tr>
        """
        )

    rows_html = "".join(rows) if rows else '<tr><td colspan="5">No data yet</td></tr>'

    return f"""<!DOCTYPE html>
<html>
<head>
    <title>Claude Code Leaderboard</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta http-equiv="refresh" content="30">
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 800px;
            margin: 40px auto;
            padding: 0 20px;
            background: #f5f5f5;
        }}
        h1 {{
            color: #333;
            border-bottom: 2px solid #4CAF50;
            padding-bottom: 10px;
        }}
        .sort-links {{
            margin: 20px 0;
            padding: 10px;
            background: white;
            border-radius: 4px;
        }}
        .sort-links a {{
            margin-right: 15px;
            color: #2196F3;
            text-decoration: none;
        }}
        .sort-links a:hover {{
            text-decoration: underline;
        }}
        table {{
            width: 100%;
            background: white;
            border-collapse: collapse;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background: #4CAF50;
            color: white;
            font-weight: 600;
        }}
        tr:hover {{
            background: #f5f5f5;
        }}
        .auto-refresh {{
            color: #666;
            font-size: 14px;
            margin-top: 10px;
        }}
    </style>
</head>
<body>
    <h1>Claude Code Usage Leaderboard</h1>
    <div class="sort-links">
        Sort by: {" | ".join(sort_buttons)}
    </div>
    <table>
        <thead>
            <tr>
                <th>Rank</th>
                <th>Employee</th>
                <th>Total Tokens</th>
                <th>Total Cost</th>
                <th>API Requests</th>
            </tr>
        </thead>
        <tbody>
            {rows_html}
        </tbody>
    </table>
    <p class="auto-refresh">Auto-refreshes every 30 seconds</p>
</body>
</html>"""


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)
```

- [ ] **Step 3: Run tests to verify**

Run: `uv run pytest tests/test_main.py -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add src/claude_otel/main.py tests/test_main.py
git commit -m "feat: add FastAPI app with OTLP endpoint and leaderboard UI"
```

---

## Chunk 5: Containerization

### Task 5: Create Dockerfile

**Files:**
- Create: `Dockerfile`

- [ ] **Step 1: Create Dockerfile**

Create `Dockerfile`:
```dockerfile
FROM python:3.12-slim

# Install uv
RUN pip install uv

# Set working directory
WORKDIR /app

# Copy project files
COPY pyproject.toml uv.lock* ./
COPY src/ ./src/

# Create virtual environment and install dependencies
RUN uv sync --no-dev

# Create directory for database
RUN mkdir -p /data

# Set environment variables
ENV DATABASE_PATH=/data/claude_otel.db
ENV HOST=0.0.0.0
ENV PORT=8000
ENV PYTHONPATH=/app/src

# Expose port
EXPOSE 8000

# Run the application
CMD ["uv", "run", "--", "python", "-m", "claude_otel.main"]
```

- [ ] **Step 2: Test Docker build**

Run: `docker build -t claude-otel-leaderboard .`
Expected: Build succeeds

- [ ] **Step 3: Add .dockerignore**

Create `.dockerignore`:
```
__pycache__/
*.pyc
*.pyo
*.pyd
.Python
*.so
*.egg
*.egg-info/
dist/
build/
.git/
.gitignore
.pytest_cache/
.coverage
htmlcov/
.tox/
.venv/
*.db
```

- [ ] **Step 4: Commit**

```bash
git add Dockerfile .dockerignore
git commit -m "chore: add Dockerfile for containerized deployment"
```

---

## Chunk 6: Documentation

### Task 6: Write README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Create README**

Create `README.md`:
```markdown
# Claude Code OpenTelemetry Leaderboard

Track token usage and costs per employee from Claude Code (Cowork) telemetry.

## Features

- Receives OTLP logs from Claude Code
- Tracks tokens (input, output, cache read, cache creation)
- Tracks estimated costs per employee
- Web UI with sortable leaderboard
- JSON API for programmatic access

## Quick Start

### Using uv (Recommended)

```bash
# Clone and enter directory
cd claude-otel-leaderboard

# Run with uv
uv run python -m claude_otel.main
```

The server will start on http://localhost:8000

### Using Docker

```bash
# Build image
docker build -t claude-otel-leaderboard .

# Run container
docker run -p 8000:8000 -v $(pwd)/data:/data claude-otel-leaderboard
```

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_PATH` | `./claude_otel.db` | Path to SQLite database |
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `8000` | Server port |

## Claude Code Configuration

Configure Claude Code (Cowork) to send telemetry to this endpoint:

1. Go to **Admin settings > Cowork**
2. Set **OTLP endpoint**: `http://your-server:8000/v1/logs`
3. Set **OTLP protocol**: `http/json`

Or via environment variables:
```bash
export OTEL_LOGS_EXPORTER=otlp
export OTEL_EXPORTER_OTLP_LOGS_PROTOCOL=http/json
export OTEL_EXPORTER_OTLP_LOGS_ENDPOINT=http://your-server:8000/v1/logs
```

## Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | Redirects to leaderboard |
| `GET /leaderboard` | Web UI with leaderboard |
| `GET /api/leaderboard?sort=total_tokens\|total_cost\|prompt_count` | JSON API |
| `POST /v1/logs` | OTLP logs receiver (Claude Code sends here) |
| `GET /health` | Health check |

## Development

```bash
# Install dev dependencies
uv sync

# Run tests
uv run pytest

# Run with auto-reload (for development)
uv run uvicorn claude_otel.main:app --reload
```

## License

MIT
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add README with setup and configuration instructions"
```

---

## Chunk 7: Integration Test

### Task 7: Add end-to-end test

**Files:**
- Test: `tests/test_e2e.py`

- [ ] **Step 1: Write end-to-end test**

Create `tests/test_e2e.py`:
```python
"""End-to-end test simulating Claude Code sending telemetry."""
import pytest
from fastapi.testclient import TestClient
from claude_otel.main import app, get_db_connection
import sqlite3

TEST_DB = ":memory:"

def get_test_db():
    conn = sqlite3.connect(TEST_DB)
    from claude_otel.database import init_db
    init_db(conn)
    return conn

app.dependency_overrides[get_db_connection] = get_test_db

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
    response = client.get("/api/leaderboard?sort=total_tokens")
    assert response.status_code == 200
    data = response.json()

    # Verify we have 3 employees
    assert data["count"] == 3

    # Verify sorting (Charlie has most tokens: 3000+1500+2000+1000 = 7500)
    employees = data["employees"]
    assert employees[0]["email"] == "charlie@company.com"
    assert employees[0]["total_tokens"] == 7500
    assert employees[0]["total_cost"] == pytest.approx(0.09, abs=0.001)
    assert employees[0]["prompt_count"] == 3

    # Alice should be second
    assert employees[1]["email"] == "alice@company.com"
    assert employees[1]["total_tokens"] == 4500  # 1000+500 + 2000+1000
    assert employees[1]["prompt_count"] == 2

    # Bob should be third
    assert employees[2]["email"] == "bob@company.com"
    assert employees[2]["total_tokens"] == 750  # 500+250
    assert employees[2]["prompt_count"] == 1

    # Test HTML leaderboard page
    response = client.get("/leaderboard")
    assert response.status_code == 200
    assert b"charlie@company.com" in response.content
    assert b"alice@company.com" in response.content
    assert b"bob@company.com" in response.content
```

- [ ] **Step 2: Run end-to-end test**

Run: `uv run pytest tests/test_e2e.py -v`
Expected: PASS

- [ ] **Step 3: Run all tests**

Run: `uv run pytest -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_e2e.py
git commit -m "test: add end-to-end test simulating Claude Code telemetry"
```

---

## Summary

After completing all tasks:

1. Project is initialized with uv
2. Database layer handles SQLite operations
3. OTLP parser extracts token usage from Claude Code events
4. FastAPI app receives telemetry and serves leaderboard
5. Docker container is ready for deployment
6. Documentation is complete
7. All tests pass

**To run:**
```bash
uv run python -m claude_otel.main
```

**To test:**
```bash
uv run pytest
```

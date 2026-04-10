# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Claude Leaderboard is a FastAPI application that receives OpenTelemetry logs from Claude Code (Cowork) and tracks token usage per employee via a web-based leaderboard. It parses `claude_code.api_request` events and aggregates usage data in SQLite.

## Common Commands

**Run the server:**
```bash
uv run python -m claude_leaderboard.main
```

**Run tests:**
```bash
uv run pytest
```

**Run a single test:**
```bash
uv run pytest tests/test_database.py::test_init_db_creates_tables -v
```

**Run with auto-reload (development):**
```bash
uv run uvicorn claude_leaderboard.main:app --reload
```

**Build and run with Docker:**
```bash
docker build -t claude-otel-leaderboard .
docker run -p 8000:8000 -v $(pwd)/data:/data claude-otel-leaderboard
```

## Architecture

**Data Flow:**
1. Claude Code sends OTLP `ExportLogsServiceRequest` (JSON) to `POST /v1/logs` every 5 seconds
2. `otlp_parser.py` extracts `claude_code.api_request` events from the payload
3. `main.py` receives events and stores them via `database.py`
4. `database.py` upserts SQLite records in `employee_usage` table (aggregated per email)
5. Web UI (`/leaderboard`) queries SQLite and renders rankings

**Key Implementation Details:**

- **OTLP Parsing:** Claude Code sends numeric values as strings (e.g., `{'stringValue': '10'}` not `{'intValue': 10}`), and `event.name` is just `"api_request"` (not `"claude_code.api_request"`). The parser handles both short and full event names and converts string values to integers/floats.

- **User Identification:** When Claude Code is authenticated via OAuth, `user.email` is present. When unauthenticated, only `user.id` (device ID) is sent. The parser falls back to `user.id` when email is missing.

- **Database Schema:** The `employee_usage` table uses email (or device ID) as primary key with pre-computed totals. The `upsert_usage` function handles both INSERT (new employee) and UPDATE (increment existing) via SQLite's `ON CONFLICT` clause.

- **FastAPI Dependencies:** `get_db()` provides SQLite connections via FastAPI's dependency injection. The database is initialized on startup via `@app.on_event("startup")`.

## Project Structure

- `src/claude_leaderboard/main.py` - FastAPI app, OTLP endpoint, leaderboard UI
- `src/claude_leaderboard/database.py` - SQLite schema and operations
- `src/claude_leaderboard/otlp_parser.py` - OTLP JSON payload parser
- `tests/test_*.py` - Unit and integration tests
- `pyproject.toml` - uv project configuration

## Configuration

Environment variables:
- `DATABASE_PATH` - SQLite file path (default: `./claude_leaderboard.db`)
- `HOST`/`PORT` - Server bind address
- `CLAUDE_CODE_ENABLE_TELEMETRY=1`, `OTEL_LOGS_EXPORTER=otlp`, `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT=http://...` - Claude Code configuration

Claude Code sends telemetry to `POST /v1/logs`. The leaderboard UI is at `/leaderboard` and JSON API at `/api/leaderboard?sort=total_tokens|total_cost|prompt_count`.

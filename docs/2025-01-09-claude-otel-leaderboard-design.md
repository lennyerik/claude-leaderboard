# Claude Code OpenTelemetry Leaderboard - Design Document

**Date:** 2025-01-09

## Overview

An OpenTelemetry endpoint that receives Claude Code (Cowork) telemetry, tracks token usage per employee, and displays a leaderboard via a web UI.

## Requirements

- Receive OTLP logs from Claude Code/Cowork
- Track token usage per employee (by email)
- Display leaderboard with multiple metric views (tokens, cost, activity)
- Simple deployment: `uv run` or Docker
- SQLite for data persistence
- No authentication (internal network)
- Near real-time updates (per-request leaderboard calculation)

## Architecture

```
┌─────────────────┐     OTLP/HTTP      ┌─────────────────────────┐
│  Claude Code    │ ─────────────────> │  FastAPI App            │
│  (Cowork)       │   (v1/logs)        │  ┌─────────────────┐   │
│                 │                    │  │ OTLP Receiver   │   │
└─────────────────┘                    │  │ (POST /v1/logs) │   │
                                       │  └────────┬────────┘   │
                                       │           │            │
                                       │  ┌────────▼────────┐   │
                                       │  │ SQLite Storage  │   │
                                       │  └────────┬────────┘   │
                                       │           │            │
                                       │  ┌────────▼────────┐   │
                                       │  │ Web UI          │   │
                                       │  │ (/leaderboard)  │   │
                                       │  └─────────────────┘   │
                                       └─────────────────────────┘
```

## Data Flow

1. **Cowork sends OTLP ExportLogsServiceRequest** (every 5 seconds by default)
2. **Our `/v1/logs` endpoint receives** the protobuf/JSON payload
3. **Parse `claude_code.api_request` events** which contain:
   - `user.email` - employee identifier
   - `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_creation_tokens`
   - `cost_usd` - estimated cost
   - `timestamp` - when the request occurred
4. **Upsert SQLite** - Add to running totals per user
5. **Leaderboard query** - Aggregate and sort for display

## Data Model (SQLite)

```sql
CREATE TABLE employee_usage (
    email TEXT PRIMARY KEY,           -- user.email from telemetry
    account_uuid TEXT,                 -- user.account_uuid for reference
    total_input_tokens INTEGER DEFAULT 0,
    total_output_tokens INTEGER DEFAULT 0,
    total_cache_read_tokens INTEGER DEFAULT 0,
    total_cache_creation_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,  -- sum of all token types
    total_cost REAL DEFAULT 0.0,     -- sum of cost_usd
    prompt_count INTEGER DEFAULT 0,  -- number of API requests
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_total_tokens ON employee_usage(total_tokens DESC);
CREATE INDEX idx_total_cost ON employee_usage(total_cost DESC);
CREATE INDEX idx_prompt_count ON employee_usage(prompt_count DESC);
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/logs` | POST | OTLP logs receiver (Claude Code sends here) |
| `/health` | GET | Health check |
| `/` | GET | Redirects to `/leaderboard` |
| `/leaderboard` | GET | HTML page with leaderboard |
| `/api/leaderboard` | GET | JSON API returning rankings |

## Web UI

- Table showing employees ranked by selected metric
- Toggle buttons: Tokens | Cost | Activity
- Columns: Rank, Email, Total Tokens, Cost ($), API Requests
- Auto-refresh every 30 seconds

## Project Structure

```
claude-otel-leaderboard/
├── pyproject.toml          # uv project config, dependencies
├── README.md               # Setup and usage instructions
├── Dockerfile              # Container build
├── src/
│   └── claude_leaderboard/
│       ├── __init__.py
│       ├── main.py         # FastAPI app, OTLP receiver, API endpoints
│       ├── database.py     # SQLite operations
│       ├── models.py       # Pydantic models for OTLP + API
│       └── templates.py    # Simple HTML template for leaderboard
└── tests/
    ├── test_otlp_receive.py
    ├── test_database.py
    └── test_api.py
```

## Dependencies

- `fastapi` - Web framework
- `uvicorn` - ASGI server
- Optional: `opentelemetry-proto` - Only if manual parsing fails

## Testing Strategy

Unit tests for:
- OTLP log ingestion and parsing
- Database operations (upsert, query)
- API endpoints (health, leaderboard JSON)

## Configuration

Environment variables:
- `DATABASE_PATH` - SQLite file path (default: `./claude_leaderboard.db`)
- `PORT` - Server port (default: 8000)
- `HOST` - Bind address (default: `0.0.0.0`)

## Deployment

Local development:
```bash
uv run python -m claude_leaderboard.main
```

Docker:
```bash
docker build -t claude-otel-leaderboard .
docker run -p 8000:8000 claude-otel-leaderboard
```

## Claude Code/Cowork Configuration

Set in admin settings or managed settings:
```
OTEL_LOGS_EXPORTER=otlp
OTEL_EXPORTER_OTLP_LOGS_PROTOCOL=http/json
OTEL_EXPORTER_OTLP_LOGS_ENDPOINT=http://your-server:8000/v1/logs
```

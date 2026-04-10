# Claude Leaderboard

Track Claude Code token usage and costs per employee. A simple OpenTelemetry endpoint with a web-based leaderboard.

## Features

- Receives OTLP logs from Claude Code via HTTP/JSON
- Tracks tokens (input, output, cache read, cache creation)
- Tracks estimated costs per employee
- Web UI with sortable leaderboard (Tokens, Cost, Activity)
- JSON API for programmatic access
- SQLite database for persistence
- Runs with `uv` or Docker

## Quick Start

### Using uv (Recommended)

```bash
# Run the server
uv run python -m claude_leaderboard.main
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
| `DATABASE_PATH` | `./claude_leaderboard.db` | Path to SQLite database |
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `8000` | Server port |

## Claude Code Configuration

Configure Claude Code (Cowork) to send telemetry to this endpoint:

**Via Admin Settings:**
1. Go to **Admin settings > Cowork**
2. Set **OTLP endpoint**: `http://your-server:8000/v1/logs`
3. Set **OTLP protocol**: `http/json`

**Via Environment Variables:**
```bash
export CLAUDE_CODE_ENABLE_TELEMETRY=1
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
# Run tests
uv run pytest

# Run with auto-reload (for development)
uv run uvicorn claude_leaderboard.main:app --reload
```

## Project Structure

```
claude-otel-leaderboard/
├── src/claude_leaderboard/
│   ├── __init__.py
│   ├── main.py         # FastAPI app
│   ├── database.py     # SQLite operations
│   └── otlp_parser.py  # OTLP log parser
├── tests/
│   ├── test_database.py
│   ├── test_otlp_parser.py
│   ├── test_main.py
│   └── test_e2e.py
├── Dockerfile
├── pyproject.toml
└── README.md
```

## License

MIT

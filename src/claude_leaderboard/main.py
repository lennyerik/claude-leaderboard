"""FastAPI application for Claude OTel leaderboard."""
import os
import sqlite3
from contextlib import asynccontextmanager, contextmanager
from fastapi import FastAPI, Request, Depends, Query
from fastapi.responses import HTMLResponse, RedirectResponse

from claude_leaderboard.database import init_db, upsert_usage, get_leaderboard
from claude_leaderboard.otlp_parser import parse_otlp_logs, extract_api_request_events

# Configuration
DATABASE_PATH = os.getenv("DATABASE_PATH", "./claude_leaderboard.db")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan handler for startup/shutdown events."""
    # Startup: Initialize database
    conn = sqlite3.connect(DATABASE_PATH)
    init_db(conn)
    conn.close()
    yield
    # Shutdown: nothing to clean up


app = FastAPI(title="Claude Code OTel Leaderboard", lifespan=lifespan)


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


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/v1/logs")
async def receive_otlp_logs(request: Request, db=Depends(get_db)):
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
    for event in api_events:
        if event.get("user_email"):
            upsert_usage(
                db,
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
    db = Depends(get_db),
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
    db = Depends(get_db),
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

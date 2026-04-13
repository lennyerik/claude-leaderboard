"""FastAPI application for Claude OTel leaderboard."""
import os
import sqlite3
from contextlib import asynccontextmanager, contextmanager
from html import escape as html_escape
from fastapi import FastAPI, Request, Depends, Query
from fastapi.responses import HTMLResponse, RedirectResponse

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
)
from claude_leaderboard.otlp_parser import parse_otlp_logs, extract_api_request_events

# Configuration
DATABASE_PATH = os.getenv("DATABASE_PATH", "./claude_leaderboard.db")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# Leaderboard types and their display info
LEADERBOARDS = {
    "tokens": {"title": "Token Usage", "func": get_leaderboard_tokens},
    "cost": {"title": "Total Cost", "func": get_leaderboard_cost},
    "time": {"title": "Time Spent", "func": get_leaderboard_time},
    "io_ratio": {"title": "I/O Ratio (Chatty)", "func": get_leaderboard_io_ratio},
    "efficiency": {"title": "Efficiency (Concise)", "func": get_leaderboard_efficiency},
    "streak": {"title": "Longest Streak", "func": get_leaderboard_streak},
    "session": {"title": "Longest Session", "func": get_leaderboard_session},
    "models": {"title": "Favorite Models", "func": get_favorite_models},
}


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
            insert_request(
                db,
                email=event["user_email"],
                session_id=event.get("session_id", ""),
                model=event.get("model", ""),
                input_tokens=event.get("input_tokens", 0),
                output_tokens=event.get("output_tokens", 0),
                cache_read_tokens=event.get("cache_read_tokens", 0),
                cache_creation_tokens=event.get("cache_creation_tokens", 0),
                cost_usd=event.get("cost_usd", 0.0),
                duration_ms=event.get("duration_ms", 0),
                timestamp=event.get("timestamp", ""),
                account_uuid=event.get("account_uuid", ""),
                organization_id=event.get("organization_id", ""),
                prompt_id=event.get("prompt_id", ""),
            )

    return {"success": True, "events_processed": len(api_events)}


@app.get("/api/leaderboard")
async def api_leaderboard(
    sort: str = Query(default="tokens", description="Leaderboard type"),
    db=Depends(get_db),
):
    """Get leaderboard data as JSON."""
    leaderboard_info = LEADERBOARDS.get(sort, LEADERBOARDS["tokens"])
    data = leaderboard_info["func"](db)

    return {
        "leaderboard": sort,
        "title": leaderboard_info["title"],
        "data": data,
        "count": len(data),
    }


@app.get("/leaderboard", response_class=HTMLResponse)
async def leaderboard_page(
    request: Request,
    sort: str = Query(default="tokens"),
    db=Depends(get_db),
):
    """Render leaderboard HTML page."""
    if sort not in LEADERBOARDS:
        sort = "tokens"

    leaderboard_info = LEADERBOARDS[sort]
    data = leaderboard_info["func"](db)

    html = build_leaderboard_html(data, sort, LEADERBOARDS)
    return HTMLResponse(content=html)


@app.get("/")
async def root():
    """Redirect to leaderboard."""
    return RedirectResponse(url="/leaderboard", status_code=307)


def build_leaderboard_html(data: list[dict], current_sort: str, leaderboards: dict) -> str:
    """Build HTML for leaderboard with tabs."""

    # Build tab navigation
    tabs = []
    for key, info in leaderboards.items():
        if key == current_sort:
            tabs.append(f'<li class="active"><a href="leaderboard?sort={key}">{info["title"]}</a></li>')
        else:
            tabs.append(f'<li><a href="leaderboard?sort={key}">{info["title"]}</a></li>')

    tabs_html = "".join(tabs)

    # Build table based on leaderboard type
    table_html = build_table_html(data, current_sort)

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
            max-width: 900px;
            margin: 40px auto;
            padding: 0 20px;
            background: #f5f5f5;
        }}
        h1 {{
            color: #333;
            border-bottom: 2px solid #4CAF50;
            padding-bottom: 10px;
        }}
        .tabs {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin: 20px 0;
            padding: 10px;
            background: white;
            border-radius: 4px;
            list-style: none;
        }}
        .tabs li {{
            margin: 0;
        }}
        .tabs a {{
            display: block;
            padding: 8px 16px;
            background: #e0e0e0;
            border-radius: 4px;
            color: #333;
            text-decoration: none;
            font-size: 14px;
        }}
        .tabs a:hover {{
            background: #d0d0d0;
        }}
        .tabs li.active a {{
            background: #4CAF50;
            color: white;
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
    <h1>Claude Code Leaderboard</h1>
    <ul class="tabs">
        {tabs_html}
    </ul>
    {table_html}
    <p class="auto-refresh">Auto-refreshes every 30 seconds</p>
</body>
</html>"""


def build_table_html(data: list[dict], sort_type: str) -> str:
    """Build table HTML based on leaderboard type."""

    if sort_type == "tokens":
        return build_tokens_table(data)
    elif sort_type == "cost":
        return build_cost_table(data)
    elif sort_type == "time":
        return build_time_table(data)
    elif sort_type == "io_ratio":
        return build_io_ratio_table(data, "I/O Ratio (Chatty users)")
    elif sort_type == "efficiency":
        return build_io_ratio_table(data, "Efficiency (Concise users)")
    elif sort_type == "streak":
        return build_streak_table(data)
    elif sort_type == "session":
        return build_session_table(data)
    elif sort_type == "models":
        return build_models_table(data)
    else:
        return build_generic_table(data)


def build_tokens_table(data: list[dict]) -> str:
    rows = []
    for i, row in enumerate(data, 1):
        rows.append(f"""
        <tr>
            <td>{i}</td>
            <td>{html_escape(row['email'])}</td>
            <td>{row['total_tokens']:,}</td>
            <td>${row['total_cost']:.4f}</td>
            <td>{row['request_count']}</td>
        </tr>
        """)
    rows_html = "".join(rows) if rows else '<tr><td colspan="5">No data yet</td></tr>'

    return f"""<table>
        <thead><tr><th>Rank</th><th>Employee</th><th>Total Tokens</th><th>Total Cost</th><th>Requests</th></tr></thead>
        <tbody>{rows_html}</tbody>
    </table>"""


def build_cost_table(data: list[dict]) -> str:
    rows = []
    for i, row in enumerate(data, 1):
        rows.append(f"""
        <tr>
            <td>{i}</td>
            <td>{html_escape(row['email'])}</td>
            <td>${row['total_cost']:.4f}</td>
            <td>{row['total_tokens']:,}</td>
            <td>{row['request_count']}</td>
        </tr>
        """)
    rows_html = "".join(rows) if rows else '<tr><td colspan="5">No data yet</td></tr>'

    return f"""<table>
        <thead><tr><th>Rank</th><th>Employee</th><th>Total Cost</th><th>Total Tokens</th><th>Requests</th></tr></thead>
        <tbody>{rows_html}</tbody>
    </table>"""


def build_time_table(data: list[dict]) -> str:
    rows = []
    for i, row in enumerate(data, 1):
        rows.append(f"""
        <tr>
            <td>{i}</td>
            <td>{html_escape(row['email'])}</td>
            <td>{row['total_duration']}</td>
            <td>{row['request_count']}</td>
        </tr>
        """)
    rows_html = "".join(rows) if rows else '<tr><td colspan="4">No data yet</td></tr>'

    return f"""<table>
        <thead><tr><th>Rank</th><th>Employee</th><th>Total Time</th><th>Requests</th></tr></thead>
        <tbody>{rows_html}</tbody>
    </table>"""


def build_io_ratio_table(data: list[dict], title: str) -> str:
    rows = []
    for i, row in enumerate(data, 1):
        rows.append(f"""
        <tr>
            <td>{i}</td>
            <td>{html_escape(row['email'])}</td>
            <td>{row['io_ratio']}</td>
            <td>{row['total_input']:,}</td>
            <td>{row['total_output']:,}</td>
            <td>{row['request_count']}</td>
        </tr>
        """)
    rows_html = "".join(rows) if rows else '<tr><td colspan="6">No data yet</td></tr>'

    return f"""<table>
        <thead><tr><th>Rank</th><th>Employee</th><th>I/O Ratio</th><th>Input Tokens</th><th>Output Tokens</th><th>Requests</th></tr></thead>
        <tbody>{rows_html}</tbody>
    </table>"""


def build_streak_table(data: list[dict]) -> str:
    rows = []
    for i, row in enumerate(data, 1):
        rows.append(f"""
        <tr>
            <td>{i}</td>
            <td>{html_escape(row['email'])}</td>
            <td>{row['longest_streak']} days</td>
            <td>{row['total_days']} days</td>
        </tr>
        """)
    rows_html = "".join(rows) if rows else '<tr><td colspan="4">No data yet</td></tr>'

    return f"""<table>
        <thead><tr><th>Rank</th><th>Employee</th><th>Longest Streak</th><th>Total Days Active</th></tr></thead>
        <tbody>{rows_html}</tbody>
    </table>"""


def build_session_table(data: list[dict]) -> str:
    rows = []
    for i, row in enumerate(data, 1):
        rows.append(f"""
        <tr>
            <td>{i}</td>
            <td>{html_escape(row['email'])}</td>
            <td>{row['session_duration']}</td>
            <td>{row['request_count']}</td>
        </tr>
        """)
    rows_html = "".join(rows) if rows else '<tr><td colspan="4">No data yet</td></tr>'

    return f"""<table>
        <thead><tr><th>Rank</th><th>Employee</th><th>Longest Session</th><th>Requests in Session</th></tr></thead>
        <tbody>{rows_html}</tbody>
    </table>"""


def build_models_table(data: list[dict]) -> str:
    rows = []
    for i, row in enumerate(data, 1):
        rows.append(f"""
        <tr>
            <td>{i}</td>
            <td>{html_escape(row['email'])}</td>
            <td>{html_escape(row['favorite_model'])}</td>
            <td>{row['model_count']}</td>
        </tr>
        """)
    rows_html = "".join(rows) if rows else '<tr><td colspan="4">No data yet</td></tr>'

    return f"""<table>
        <thead><tr><th>Rank</th><th>Employee</th><th>Favorite Model</th><th>Uses</th></tr></thead>
        <tbody>{rows_html}</tbody>
    </table>"""


def build_generic_table(data: list[dict]) -> str:
    if not data:
        return '<table><tbody><tr><td>No data yet</td></tr></tbody></table>'

    headers = list(data[0].keys())
    header_row = "".join(f"<th>{html_escape(str(h))}</th>" for h in headers)

    rows = []
    for row in data:
        cells = "".join(f"<td>{html_escape(str(row.get(h, '')))}</td>" for h in headers)
        rows.append(f"<tr>{cells}</tr>")
    rows_html = "".join(rows)

    return f"""<table>
        <thead><tr>{header_row}</tr></thead>
        <tbody>{rows_html}</tbody>
    </table>"""


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)

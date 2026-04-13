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


def parse_otlp_logs(data: str | dict) -> list[dict]:
    """Parse OTLP JSON logs payload and return list of events.

    Returns list of dicts with keys:
    - event_name
    - user_email
    - account_uuid
    - session_id
    - model
    - input_tokens
    - output_tokens
    - cache_read_tokens
    - cache_creation_tokens
    - cost_usd
    - duration_ms
    - timestamp
    - organization_id
    - prompt_id
    """
    if isinstance(data, dict):
        payload = data
    else:
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

    # Check event.name attribute (can be "api_request" or "claude_code.api_request")
    event_name = attr_map.get("event.name", "")

    # We only care about api_request events for token tracking
    # Check both "api_request" (from attribute) and "claude_code.api_request" (from body/full name)
    if event_name not in ("api_request", "claude_code.api_request"):
        return None

    # Helper to convert value to int (handles strings from OTLP)
    def to_int(val, default=0):
        if val is None:
            return default
        if isinstance(val, int):
            return val
        if isinstance(val, str):
            try:
                return int(val)
            except ValueError:
                return default
        return default

    # Helper to convert value to float (handles strings from OTLP)
    def to_float(val, default=0.0):
        if val is None:
            return default
        if isinstance(val, float):
            return val
        if isinstance(val, int):
            return float(val)
        if isinstance(val, str):
            try:
                return float(val)
            except ValueError:
                return default
        return default

    # Get user identifier - prefer email, fall back to user.id (anonymous device ID)
    user_email = attr_map.get("user.email", "")
    if not user_email:
        user_email = attr_map.get("user.id", "anonymous")

    return {
        "event_name": event_name,
        "user_email": user_email,
        "account_uuid": attr_map.get("user.account_uuid", ""),
        "session_id": attr_map.get("session.id", ""),
        "model": attr_map.get("model", ""),
        "input_tokens": to_int(attr_map.get("input_tokens")),
        "output_tokens": to_int(attr_map.get("output_tokens")),
        "cache_read_tokens": to_int(attr_map.get("cache_read_tokens")),
        "cache_creation_tokens": to_int(attr_map.get("cache_creation_tokens")),
        "cost_usd": to_float(attr_map.get("cost_usd")),
        "duration_ms": to_int(attr_map.get("duration_ms")),
        "timestamp": attr_map.get("event.timestamp", ""),
        "organization_id": attr_map.get("organization.id", ""),
        "prompt_id": attr_map.get("prompt.id", ""),
    }



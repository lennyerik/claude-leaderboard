import json
import pytest
from claude_leaderboard.otlp_parser import parse_otlp_logs, extract_api_request_events


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


def test_parse_handles_string_values():
    """Test parsing handles string values for numeric fields (Claude Code format)."""
    payload = {
        "resourceLogs": [{
            "scopeLogs": [{
                "logRecords": [{
                    "attributes": [
                        {"key": "event.name", "value": {"stringValue": "claude_code.api_request"}},
                        {"key": "user.email", "value": {"stringValue": "lenny@example.com"}},
                        {"key": "user.account_uuid", "value": {"stringValue": "37c434a0-c19e-4622-a6e3-48cf1f49d020"}},
                        {"key": "input_tokens", "value": {"stringValue": "10"}},
                        {"key": "output_tokens", "value": {"stringValue": "68"}},
                        {"key": "cache_read_tokens", "value": {"stringValue": "43931"}},
                        {"key": "cache_creation_tokens", "value": {"stringValue": "22"}},
                        {"key": "cost_usd", "value": {"stringValue": "0.0047706"}},
                    ]
                }]
            }]
        }]
    }
    result = parse_otlp_logs(json.dumps(payload))
    assert len(result) == 1
    assert result[0]["user_email"] == "lenny@example.com"
    assert result[0]["input_tokens"] == 10
    assert result[0]["output_tokens"] == 68
    assert result[0]["cache_read_tokens"] == 43931
    assert result[0]["cache_creation_tokens"] == 22
    assert result[0]["cost_usd"] == 0.0047706


def test_parse_real_claude_code_payload():
    """Test parsing actual Claude Code OTLP payload with all fields redacted."""
    payload = {
        "resourceLogs": [{
            "resource": {
                "attributes": [
                    {"key": "host.arch", "value": {"stringValue": "amd64"}},
                    {"key": "os.type", "value": {"stringValue": "linux"}},
                    {"key": "os.version", "value": {"stringValue": "6.x.x-generic"}},
                    {"key": "service.name", "value": {"stringValue": "claude-code"}},
                    {"key": "service.version", "value": {"stringValue": "2.1.100"}},
                ],
                "droppedAttributesCount": 0
            },
            "scopeLogs": [{
                "scope": {
                    "name": "com.anthropic.claude_code.events",
                    "version": "2.1.100"
                },
                "logRecords": [
                    {
                        "timeUnixNano": "1775848016533000000",
                        "observedTimeUnixNano": "1775848016533000000",
                        "body": {"stringValue": "claude_code.user_prompt"},
                        "attributes": [
                            {"key": "user.id", "value": {"stringValue": "437d99a5-14e7-497a-9352-14972feb900b"}},
                            {"key": "session.id", "value": {"stringValue": "29d083fa-fdd2-4031-9259-cfae09b04e2d"}},
                            {"key": "organization.id", "value": {"stringValue": "5f60b26b-c53d-4e0f-8e74-f2c2895bbd9b"}},
                            {"key": "user.email", "value": {"stringValue": "user@example.com"}},
                            {"key": "user.account_uuid", "value": {"stringValue": "37c434a0-c19e-4622-a6e3-48cf1f49d020"}},
                            {"key": "user.account_id", "value": {"stringValue": "user_01XXXXXXXXXXXXXXXXXXX"}},
                            {"key": "terminal.type", "value": {"stringValue": "alacritty"}},
                            {"key": "event.name", "value": {"stringValue": "user_prompt"}},
                            {"key": "event.timestamp", "value": {"stringValue": "2026-04-10T19:06:56.533Z"}},
                            {"key": "event.sequence", "value": {"intValue": 5}},
                            {"key": "prompt.id", "value": {"stringValue": "1f8abf8a-2e3f-4d0b-ad61-dd8ab7796e3a"}},
                            {"key": "prompt_length", "value": {"stringValue": "4"}},
                            {"key": "prompt", "value": {"stringValue": "<REDACTED>"}},
                        ],
                        "droppedAttributesCount": 0
                    },
                    {
                        "timeUnixNano": "1775848019553000000",
                        "observedTimeUnixNano": "1775848019553000000",
                        "body": {"stringValue": "claude_code.api_request"},
                        "attributes": [
                            {"key": "user.id", "value": {"stringValue": "437d99a5-14e7-497a-9352-14972feb900b"}},
                            {"key": "session.id", "value": {"stringValue": "29d083fa-fdd2-4031-9259-cfae09b04e2d"}},
                            {"key": "organization.id", "value": {"stringValue": "5f60b26b-c53d-4e0f-8e74-f2c2895bbd9b"}},
                            {"key": "user.email", "value": {"stringValue": "user@example.com"}},
                            {"key": "user.account_uuid", "value": {"stringValue": "37c434a0-c19e-4622-a6e3-48cf1f49d020"}},
                            {"key": "user.account_id", "value": {"stringValue": "user_01XXXXXXXXXXXXXXXXXXX"}},
                            {"key": "terminal.type", "value": {"stringValue": "alacritty"}},
                            {"key": "event.name", "value": {"stringValue": "api_request"}},
                            {"key": "event.timestamp", "value": {"stringValue": "2026-04-10T19:06:59.553Z"}},
                            {"key": "event.sequence", "value": {"intValue": 6}},
                            {"key": "prompt.id", "value": {"stringValue": "1f8abf8a-2e3f-4d0b-ad61-dd8ab7796e3a"}},
                            {"key": "model", "value": {"stringValue": "claude-haiku-4-5-20251001"}},
                            {"key": "input_tokens", "value": {"stringValue": "10"}},
                            {"key": "output_tokens", "value": {"stringValue": "100"}},
                            {"key": "cache_read_tokens", "value": {"stringValue": "43997"}},
                            {"key": "cache_creation_tokens", "value": {"stringValue": "19"}},
                            {"key": "cost_usd", "value": {"stringValue": "0.004933450000000001"}},
                            {"key": "duration_ms", "value": {"stringValue": "2967"}},
                            {"key": "speed", "value": {"stringValue": "normal"}},
                        ],
                        "droppedAttributesCount": 0
                    }
                ]
            }]
        }]
    }
    result = parse_otlp_logs(json.dumps(payload))
    # user_prompt events are filtered out at parse time (only api_request kept)
    assert len(result) == 1

    # api_request event is parsed
    assert result[0]["event_name"] == "api_request"
    assert result[0]["user_email"] == "user@example.com"
    assert result[0]["account_uuid"] == "37c434a0-c19e-4622-a6e3-48cf1f49d020"
    assert result[0]["input_tokens"] == 10
    assert result[0]["output_tokens"] == 100
    assert result[0]["cache_read_tokens"] == 43997
    assert result[0]["cache_creation_tokens"] == 19
    assert result[0]["cost_usd"] == 0.004933450000000001

    # Test filtering (already filtered but ensures consistency)
    api_events = extract_api_request_events(result)
    assert len(api_events) == 1
    assert api_events[0]["event_name"] == "api_request"


def test_parse_short_event_name():
    """Test parsing handles 'api_request' (without claude_code. prefix) from event.name attribute."""
    payload = {
        "resourceLogs": [{
            "scopeLogs": [{
                "logRecords": [{
                    "timeUnixNano": "1775840982418000000",
                    "observedTimeUnixNano": "1775840982418000000",
                    "body": {"stringValue": "claude_code.api_request"},
                    "attributes": [
                        {"key": "user.id", "value": {"stringValue": "437d99a5-14e7-497a-9352-14972feb900b"}},
                        {"key": "user.email", "value": {"stringValue": "lenny@example.com"}},
                        {"key": "user.account_uuid", "value": {"stringValue": "37c434a0-c19e-4622-a6e3-48cf1f49d020"}},
                        {"key": "event.name", "value": {"stringValue": "api_request"}},  # Short name!
                        {"key": "input_tokens", "value": {"stringValue": "10"}},
                        {"key": "output_tokens", "value": {"stringValue": "68"}},
                        {"key": "cache_read_tokens", "value": {"stringValue": "43931"}},
                        {"key": "cache_creation_tokens", "value": {"stringValue": "22"}},
                        {"key": "cost_usd", "value": {"stringValue": "0.0047706"}},
                    ]
                }]
            }]
        }]
    }
    result = parse_otlp_logs(json.dumps(payload))
    assert len(result) == 1
    assert result[0]["event_name"] == "api_request"  # Should preserve short name
    assert result[0]["user_email"] == "lenny@example.com"
    assert result[0]["input_tokens"] == 10

    # Test extract_api_request_events works with both formats
    events = [
        {"event_name": "api_request", "user_email": "a@example.com"},
        {"event_name": "user_prompt", "user_email": "b@example.com"},
        {"event_name": "claude_code.api_request", "user_email": "c@example.com"},
    ]
    filtered = extract_api_request_events(events)
    assert len(filtered) == 2
    assert filtered[0]["user_email"] == "a@example.com"
    assert filtered[1]["user_email"] == "c@example.com"

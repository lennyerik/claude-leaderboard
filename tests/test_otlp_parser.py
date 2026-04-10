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


def test_parse_handles_string_values():
    """Test parsing handles string values for numeric fields (Claude Code format)."""
    payload = {
        "resourceLogs": [{
            "scopeLogs": [{
                "logRecords": [{
                    "attributes": [
                        {"key": "event.name", "value": {"stringValue": "claude_code.api_request"}},
                        {"key": "user.email", "value": {"stringValue": "lenny@example.com"}},
                        {"key": "user.account_uuid", "value": {"stringValue": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"}},
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
                        {"key": "user.id", "value": {"stringValue": "anonymized-device-id"}},
                        {"key": "user.email", "value": {"stringValue": "lenny@example.com"}},
                        {"key": "user.account_uuid", "value": {"stringValue": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"}},
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

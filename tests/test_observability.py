import json
import logging

import pytest

from observability import (
    JsonFormatter,
    estimate_cost_usd,
    new_request_id,
    request_id_var,
    user_id_var,
)


def format_record(logger_name="test", level=logging.INFO, msg="some.event", **extra):
    record = logging.LogRecord(
        name=logger_name, level=level, pathname=__file__, lineno=1,
        msg=msg, args=(), exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return json.loads(JsonFormatter().format(record))


@pytest.fixture(autouse=True)
def clear_context():
    """ContextVars leak between tests otherwise, since they are module-level."""
    request_id_var.set(None)
    user_id_var.set(None)
    yield
    request_id_var.set(None)
    user_id_var.set(None)


# --- shape ------------------------------------------------------------------


def test_output_is_one_json_object():
    payload = format_record()
    assert payload["event"] == "some.event"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "test"
    assert "ts" in payload


def test_timestamp_is_timezone_aware_utc():
    # A naive timestamp is ambiguous once logs from several sources are merged.
    assert format_record()["ts"].endswith("+00:00")


def test_extra_fields_are_promoted_to_top_level():
    payload = format_record(duration_ms=12.5, status=200)
    assert payload["duration_ms"] == 12.5
    assert payload["status"] == 200


def test_context_vars_are_attached_when_set():
    request_id_var.set("abc123")
    user_id_var.set("user-1")
    payload = format_record()
    assert payload["request_id"] == "abc123"
    assert payload["user_id"] == "user-1"


def test_context_vars_are_omitted_when_unset():
    payload = format_record()
    assert "request_id" not in payload
    assert "user_id" not in payload


def test_exception_is_captured():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys
        record = logging.LogRecord(
            name="t", level=logging.ERROR, pathname=__file__, lineno=1,
            msg="failed", args=(), exc_info=sys.exc_info(),
        )
        payload = json.loads(JsonFormatter().format(record))
    assert "ValueError: boom" in payload["exception"]


def test_non_serializable_values_do_not_raise():
    payload = format_record(obj=object())
    assert isinstance(payload["obj"], str)


# --- redaction --------------------------------------------------------------
# A Google refresh token grants durable calendar access and does not expire, so
# one leaking into CloudWatch is a real compromise.


@pytest.mark.parametrize("key", [
    "refresh_token", "access_token", "token", "client_secret",
    "authorization", "password", "jwt", "session_token", "api_key",
])
def test_sensitive_keys_are_redacted(key):
    payload = format_record(**{key: "super-secret-value"})
    assert payload[key] == "[redacted]"
    assert "super-secret-value" not in json.dumps(payload)


def test_redaction_is_case_insensitive():
    payload = format_record(Refresh_Token="secret")
    assert payload["Refresh_Token"] == "[redacted]"


def test_non_sensitive_keys_survive():
    payload = format_record(user_email_domain="example.com")
    assert payload["user_email_domain"] == "example.com"


# --- request ids ------------------------------------------------------------


def test_request_ids_are_unique():
    assert new_request_id() != new_request_id()


# --- cost estimation --------------------------------------------------------


def test_cost_is_zero_for_no_tokens():
    assert estimate_cost_usd(0, 0) == 0.0


def test_cost_scales_with_tokens():
    assert estimate_cost_usd(2_000_000, 0) == 2 * estimate_cost_usd(1_000_000, 0)


def test_output_tokens_cost_more_than_input():
    assert estimate_cost_usd(0, 1_000_000) > estimate_cost_usd(1_000_000, 0)

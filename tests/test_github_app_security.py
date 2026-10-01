"""Phase 5 — GitHub App security policy tests."""

import pytest

from app.github_security import (
    REQUIRED_INSTALLATION_PERMISSIONS,
    SUPPORTED_WEBHOOK_EVENTS,
    validate_delivery_id,
    validate_installation_id,
    validate_token_permissions,
    validate_webhook_event,
)


def test_required_permissions_are_minimum_runtime_scope():
    assert REQUIRED_INSTALLATION_PERMISSIONS == {
        "pull_requests": "write",
        "contents": "read",
        "metadata": "read",
    }


def test_supported_webhook_events_are_explicit():
    assert {"pull_request", "installation", "installation_repositories", "ping"} <= (
        SUPPORTED_WEBHOOK_EVENTS
    )


@pytest.mark.parametrize("event", ["", "push", "issues", "workflow_run"])
def test_unknown_or_missing_event_is_rejected(event):
    with pytest.raises(ValueError):
        validate_webhook_event(event)


@pytest.mark.parametrize("delivery", ["", " ", "bad id", "a/b", "x" * 256])
def test_invalid_delivery_id_is_rejected(delivery):
    with pytest.raises(ValueError):
        validate_delivery_id(delivery)


def test_delivery_id_is_normalized_and_accepted():
    assert validate_delivery_id(
        "  123e4567-e89b-12d3-a456-426614174000  "
    ) == "123e4567-e89b-12d3-a456-426614174000"


@pytest.mark.parametrize("value", [None, 0, -1, "", "abc", True])
def test_invalid_installation_id_is_rejected(value):
    with pytest.raises(ValueError):
        validate_installation_id(value)


def test_installation_id_is_positive_integer():
    assert validate_installation_id("123") == 123


def test_optional_installation_id_can_be_absent():
    assert validate_installation_id(None, required=False) is None


def test_token_permissions_require_exact_levels_for_required_scope():
    assert validate_token_permissions(
        {"pull_requests": "write", "contents": "read", "metadata": "read"}
    )


def test_token_permissions_reject_missing_or_overly_restrictive_scope():
    assert not validate_token_permissions(
        {"pull_requests": "read", "contents": "read", "metadata": "read"}
    )
    assert not validate_token_permissions(
        {"pull_requests": "write", "contents": "read"}
    )
    assert not validate_token_permissions(None)

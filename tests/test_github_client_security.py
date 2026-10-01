"""Phase 5 — GitHub App installation-token security tests."""

from types import SimpleNamespace

import pytest

from app import github_client


def test_installation_token_is_rejected_when_required_permissions_are_missing(
    monkeypatch,
):
    client = object.__new__(github_client.GitHubAppClient)
    client.app_id = "123"
    client.installation_id = 456
    client._private_key_pem = "test-key"

    monkeypatch.setattr(github_client, "_generate_jwt", lambda *_: "jwt")

    class Response:
        status_code = 201

        def json(self):
            return {
                "token": "ghs_test",
                "expires_at": "2099-01-01T00:00:00Z",
                "permissions": {
                    "pull_requests": "read",
                    "contents": "read",
                    "metadata": "read",
                },
            }

        def raise_for_status(self):
            raise AssertionError("should not be called")

    monkeypatch.setattr(github_client.requests, "post", lambda *a, **k: Response())

    with pytest.raises(RuntimeError, match="required"):
        client._fetch_installation_token()


def test_installation_token_accepts_minimum_required_permissions(monkeypatch):
    client = object.__new__(github_client.GitHubAppClient)
    client.app_id = "123"
    client.installation_id = 456
    client._private_key_pem = "test-key"

    monkeypatch.setattr(github_client, "_generate_jwt", lambda *_: "jwt")

    class Response:
        status_code = 201

        def json(self):
            return {
                "token": "ghs_test",
                "expires_at": "2099-01-01T00:00:00Z",
                "permissions": {
                    "pull_requests": "write",
                    "contents": "read",
                    "metadata": "read",
                    "issues": "read",
                },
            }

        def raise_for_status(self):
            return None

    monkeypatch.setattr(github_client.requests, "post", lambda *a, **k: Response())

    token, expires_at = client._fetch_installation_token()
    assert token == "ghs_test"
    assert expires_at > 0


def test_token_fetch_does_not_log_token_value_on_permission_failure(monkeypatch, caplog):
    client = object.__new__(github_client.GitHubAppClient)
    client.app_id = "123"
    client.installation_id = 456
    client._private_key_pem = "test-key"

    monkeypatch.setattr(github_client, "_generate_jwt", lambda *_: "jwt")

    class Response:
        status_code = 201

        def json(self):
            return {
                "token": "ghs_super_secret_should_not_be_logged",
                "expires_at": "2099-01-01T00:00:00Z",
                "permissions": {},
            }

        def raise_for_status(self):
            return None

    monkeypatch.setattr(github_client.requests, "post", lambda *a, **k: Response())

    with pytest.raises(RuntimeError):
        client._fetch_installation_token()

    assert "ghs_super_secret_should_not_be_logged" not in caplog.text

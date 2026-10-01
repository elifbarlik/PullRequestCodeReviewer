"""Phase 7 — GitHub PR file-list pagination tests."""

from app.github_client import GitHubAppClient


class _Response:
    def __init__(self, payload, next_url=None):
        self._payload = payload
        self.links = {}
        if next_url:
            self.links["next"] = {"url": next_url}

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_get_pr_files_follows_next_links(monkeypatch):
    client = object.__new__(GitHubAppClient)
    calls = []

    def fake_get(url, headers=None, params=None, timeout=None):
        calls.append((url, params, timeout))
        if len(calls) == 1:
            return _Response(
                [{"filename": "a.py"}, {"filename": "b.py"}],
                next_url="https://api.github.com/repos/o/r/pulls/7/files?page=2",
            )
        return _Response([{"filename": "c.py"}])

    monkeypatch.setattr("app.github_client.requests.get", fake_get)
    monkeypatch.setattr(client, "_auth_headers", lambda: {"Authorization": "test"})

    files = client.get_pr_files("o", "r", 7)

    assert [item["filename"] for item in files] == ["a.py", "b.py", "c.py"]
    assert calls[0][0].endswith("/pulls/7/files")
    assert calls[0][1] == {"per_page": 100}
    assert calls[1][0].endswith("page=2")
    assert calls[1][1] is None


def test_get_pr_files_stops_without_next_link(monkeypatch):
    client = object.__new__(GitHubAppClient)
    calls = []

    def fake_get(url, headers=None, params=None, timeout=None):
        calls.append((url, params))
        return _Response([{"filename": "only.py"}])

    monkeypatch.setattr("app.github_client.requests.get", fake_get)
    monkeypatch.setattr(client, "_auth_headers", lambda: {"Authorization": "test"})

    files = client.get_pr_files("o", "r", 9)

    assert files == [{"filename": "only.py"}]
    assert len(calls) == 1


def test_get_pr_files_rejects_non_list_page(monkeypatch):
    client = object.__new__(GitHubAppClient)

    monkeypatch.setattr(
        "app.github_client.requests.get",
        lambda *args, **kwargs: _Response({"error": "bad payload"}),
    )
    monkeypatch.setattr(client, "_auth_headers", lambda: {"Authorization": "test"})

    try:
        client.get_pr_files("o", "r", 10)
    except ValueError as exc:
        assert "beklenmeyen" in str(exc)
    else:
        raise AssertionError("Expected ValueError")

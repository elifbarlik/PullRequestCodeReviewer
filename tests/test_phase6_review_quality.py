import pytest

from app.semgrep_scanner import (
    DEFAULT_SEMGREP_CONFIGS,
    MAX_DIFF_BYTES,
    MAX_SCAN_FILES,
    SUPPORTED_FILE_EXTENSIONS,
    build_scan_plan,
)
from app import reviewer
from app.main import _run_semgrep_for_pr


def test_phase6_scan_plan_separates_supported_and_unsupported_files():
    files = [
        {"filename": "app/main.py", "status": "modified"},
        {"filename": "frontend/app.tsx", "status": "modified"},
        {"filename": "README.md", "status": "modified"},
        {"filename": "image.png", "status": "modified"},
        {"filename": "deleted.py", "status": "removed"},
    ]
    plan = build_scan_plan(files)

    assert plan["candidates"] == ["app/main.py", "frontend/app.tsx"]
    assert plan["supported_count"] == 2
    assert plan["unsupported_count"] == 2
    assert plan["removed_count"] == 1
    assert plan["skipped_for_cap"] == 0


def test_phase6_scan_plan_exposes_file_cap():
    files = [{"filename": f"src/file_{i}.py", "status": "modified"} for i in range(MAX_SCAN_FILES + 7)]
    plan = build_scan_plan(files)

    assert len(plan["candidates"]) == MAX_SCAN_FILES
    assert plan["supported_count"] == MAX_SCAN_FILES + 7
    assert plan["skipped_for_cap"] == 7


def test_phase6_constants_define_explicit_scan_contract():
    assert MAX_SCAN_FILES == 60
    assert MAX_DIFF_BYTES == 512 * 1024
    assert ".py" in SUPPORTED_FILE_EXTENSIONS
    assert ".ts" in SUPPORTED_FILE_EXTENSIONS
    assert ".go" in SUPPORTED_FILE_EXTENSIONS
    assert DEFAULT_SEMGREP_CONFIGS == ["p/default", "p/python", "p/security-audit", "p/secrets"]


def test_partial_scan_never_reports_safe_when_no_findings(monkeypatch):
    monkeypatch.setattr(
        reviewer,
        "explain_security_findings",
        lambda *a, **k: {
            "vulnerabilities": [],
            "has_security_issues": False,
            "security_level": "safe",
        },
    )
    result = reviewer.build_security_result(
        {
            "status": "ok",
            "findings": [],
            "partial": True,
            "partial_reason": "file_scope_limit",
            "message": "Partial scan: 7 files were not scanned.",
        },
        "diff",
    )

    assert result["partial_scan"] is True
    assert result["security_level"] == "unknown"
    assert result["partial_message"].startswith("Partial scan:")


def test_scan_error_is_not_safe():
    result = reviewer.build_security_result(
        {
            "status": "unavailable",
            "error": f"diff exceeds {MAX_DIFF_BYTES} bytes",
            "partial": True,
            "partial_reason": "diff_size_limit",
        },
        "diff",
    )
    assert result["security_level"] == "unknown"
    assert result["partial_scan"] is True
    assert result["partial_reason"] == "diff_size_limit"


class _FakeClient:
    def __init__(self):
        self.calls = []

    def get_files_content(self, owner, repo, filenames, ref):
        self.calls.append((owner, repo, filenames, ref))
        return {name: "x = 1\n" for name in filenames}


def test_phase6_diff_size_limit_skips_semgrep(monkeypatch):
    called = {"scan": False}

    def fake_scan(*args, **kwargs):
        called["scan"] = True
        return []

    monkeypatch.setattr("app.main.scan_diff", fake_scan)
    result = _run_semgrep_for_pr(
        _FakeClient(), "o", "r", 1, "x" * (MAX_DIFF_BYTES + 1), "sha",
        [{"filename": "app.py", "status": "modified"}],
    )

    assert result["status"] == "unavailable"
    assert result["partial_reason"] == "diff_size_limit"
    assert called["scan"] is False


def test_phase6_unsupported_only_pr_is_partial_not_safe(monkeypatch):
    result = _run_semgrep_for_pr(
        _FakeClient(), "o", "r", 1, "diff", "sha",
        [{"filename": "README.md", "status": "modified"}],
    )

    assert result["status"] == "ok"
    assert result["findings"] == []
    assert result["partial"] is True
    assert result["partial_reason"] == "unsupported_files"

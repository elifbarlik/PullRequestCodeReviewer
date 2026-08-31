"""
Hibrit güvenlik akışı testleri: explain_security_findings + build_security_result.

Bu testler gerçek Gemini API'sini ÇAĞIRMAZ (call_llm monkeypatch'lenir) —
amaç, Semgrep bulgusu -> Gemini açıklama -> birleştirilmiş sonuç akışının
mantığını doğrulamak, gerçek LLM kalitesini değil.
"""

import json

import pytest

from app import reviewer


SAMPLE_FINDING = {
    "file": "app/auth.py",
    "line": 42,
    "end_line": 42,
    "rule_id": "python.lang.security.audit.hardcoded-password",
    "severity": "high",
    "message": "Hardcoded password detected",
    "cwe": ["CWE-798"],
    "owasp": None,
}


class TestBuildSecurityResult:
    def test_none_scan_means_unavailable(self):
        result = reviewer.build_security_result(None, "diff")
        assert result["scan_error"]
        assert result["security_level"] == "unknown"
        assert result["vulnerabilities"] == []

    def test_unavailable_status_carries_error_message(self):
        result = reviewer.build_security_result(
            {"status": "unavailable", "error": "semgrep kurulu değil"}, "diff"
        )
        assert result["scan_error"] == "semgrep kurulu değil"
        assert result["security_level"] == "unknown"

    def test_error_status_never_reports_safe(self):
        result = reviewer.build_security_result(
            {"status": "error", "error": "GitHub API 500"}, "diff"
        )
        assert result["scan_error"] == "GitHub API 500"
        assert result.get("has_security_issues") is False
        # KRİTİK: hata durumunda security_level "safe" OLAMAZ
        assert result["security_level"] != "safe"

    def test_ok_status_with_no_findings_is_genuinely_safe(self):
        result = reviewer.build_security_result({"status": "ok", "findings": []}, "diff")
        assert result["security_level"] == "safe"
        assert "scan_error" not in result


class TestExplainSecurityFindings:
    def test_empty_findings_returns_safe_without_llm_call(self, monkeypatch):
        called = {"n": 0}
        monkeypatch.setattr(reviewer, "call_llm", lambda *a, **k: called.__setitem__("n", called["n"] + 1))

        result = reviewer.explain_security_findings([], "diff")

        assert result == {
            "vulnerabilities": [],
            "has_security_issues": False,
            "security_level": "safe",
        }
        assert called["n"] == 0  # bulgu yoksa Gemini hiç çağrılmamalı

    def test_severity_and_location_come_from_semgrep_not_gemini(self, monkeypatch):
        # Gemini'nin dönüşü severity/file/line iceriyor olsa bile YOK SAYILMALI —
        # bunlar Semgrep'ten gelir, Gemini sadece description/recommendation uretir.
        fake_response = json.dumps({
            "explanations": [
                {"index": 0, "description": "Türkçe açıklama", "recommendation": "Şöyle düzelt"}
            ]
        })
        monkeypatch.setattr(reviewer, "call_llm", lambda *a, **k: fake_response)

        result = reviewer.explain_security_findings([SAMPLE_FINDING], "diff")

        assert result["has_security_issues"] is True
        assert result["security_level"] == "high"
        vuln = result["vulnerabilities"][0]
        assert vuln["file"] == "app/auth.py"
        assert vuln["line"] == 42
        assert vuln["risk"] == "high"
        assert vuln["description"] == "Türkçe açıklama"
        assert vuln["recommendation"] == "Şöyle düzelt"

    def test_llm_failure_falls_back_to_raw_semgrep_message(self, monkeypatch):
        def boom(*a, **k):
            raise Exception("Gemini API zaman aşımı")

        monkeypatch.setattr(reviewer, "call_llm", boom)

        result = reviewer.explain_security_findings([SAMPLE_FINDING], "diff")

        # Gemini patlasa bile gerçek Semgrep bulgusu KAYBOLMAMALI
        assert result["has_security_issues"] is True
        assert len(result["vulnerabilities"]) == 1
        assert "Hardcoded password detected" in result["vulnerabilities"][0]["description"]

    def test_worst_severity_wins_across_multiple_findings(self, monkeypatch):
        monkeypatch.setattr(reviewer, "call_llm", lambda *a, **k: '{"explanations": []}')

        low_finding = {**SAMPLE_FINDING, "severity": "low", "line": 1}
        high_finding = {**SAMPLE_FINDING, "severity": "high", "line": 2}

        result = reviewer.explain_security_findings([low_finding, high_finding], "diff")
        assert result["security_level"] == "high"

    def test_type_field_extracted_from_rule_id(self, monkeypatch):
        monkeypatch.setattr(reviewer, "call_llm", lambda *a, **k: '{"explanations": []}')
        result = reviewer.explain_security_findings([SAMPLE_FINDING], "diff")
        assert result["vulnerabilities"][0]["type"] == "hardcoded-password"


class TestReviewDiffSecurityScanRouting:
    def test_security_scan_none_falls_back_to_old_llm_path(self, monkeypatch):
        # security_scan verilmezse (ornek: /local-review), eski
        # analyze_diff_stage2 (LLM-only SECURITY_REVIEW) devreye girmeli —
        # explain_security_findings/build_security_result HIC cagrilmamali.
        monkeypatch.setattr(
            reviewer, "analyze_diff_stage1",
            lambda *a, **k: {"summary": "x", "severity": "low", "type": "refactor"},
        )
        called = {"n": 0}

        def fake_build_security_result(*a, **k):
            called["n"] += 1
            return {}

        monkeypatch.setattr(reviewer, "build_security_result", fake_build_security_result)
        monkeypatch.setattr(
            reviewer, "analyze_diff_stage2",
            lambda diff, types: {"security": {"vulnerabilities": [], "has_security_issues": False, "security_level": "safe"}},
        )

        result = reviewer.review_diff("diff", review_types=["short_summary", "security"], security_scan=None)

        assert called["n"] == 0
        assert result["analyses"]["security"]["security_level"] == "safe"

    def test_security_scan_provided_uses_semgrep_path(self, monkeypatch):
        monkeypatch.setattr(
            reviewer, "analyze_diff_stage1",
            lambda *a, **k: {"summary": "x", "severity": "low", "type": "refactor"},
        )
        called = {"n": 0}

        def fake_build_security_result(scan, diff):
            called["n"] += 1
            return {"vulnerabilities": [], "has_security_issues": False, "security_level": "safe"}

        monkeypatch.setattr(reviewer, "build_security_result", fake_build_security_result)

        result = reviewer.review_diff(
            "diff",
            review_types=["short_summary", "security"],
            security_scan={"status": "ok", "findings": []},
        )

        assert called["n"] == 1
        assert "security" in result["analyses"]

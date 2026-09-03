"""
Faz 4.1 — satır-içi (inline) PR review yorumları.

İki eksen:
  1. _build_inline_comments: bulgu → inline yorum eşlemesi doğru mu?
     (diff'te olan satır inline'a gider, olmayan özete düşer)
  2. _run_pr_review akışı: inline varsa create_review, yoksa post_pr_comment;
     inline review patlarsa özet yoruma güvenli düşüş; synchronize'da mükerrer
     yorum atlanır.
"""

import asyncio

import pytest

from app import main


# =====================================================================
# _build_inline_comments — saf fonksiyon
# =====================================================================

def _security_result(vulns):
    return {
        "analyses": {
            "security": {
                "has_security_issues": True,
                "security_level": "high",
                "vulnerabilities": vulns,
            }
        }
    }


class TestBuildInlineComments:
    def test_finding_on_changed_line_becomes_inline(self):
        result = _security_result([
            {"file": "app/db.py", "line": 12, "risk": "high", "type": "sql-injection",
             "description": "d", "recommendation": "r"},
        ])
        added = {"app/db.py": {10, 11, 12, 13}}

        inline, unplaced = main._build_inline_comments(result, added)

        assert len(inline) == 1
        assert unplaced == []
        assert inline[0]["path"] == "app/db.py"
        assert inline[0]["line"] == 12
        assert main._INLINE_MARKER in inline[0]["body"]
        assert "sql-injection" in inline[0]["body"]

    def test_finding_off_diff_goes_to_unplaced(self):
        result = _security_result([
            {"file": "app/db.py", "line": 999, "risk": "high", "type": "x",
             "description": "d", "recommendation": "r"},
        ])
        added = {"app/db.py": {10, 11, 12}}

        inline, unplaced = main._build_inline_comments(result, added)

        assert inline == []
        assert len(unplaced) == 1

    def test_finding_in_untouched_file_goes_to_unplaced(self):
        result = _security_result([
            {"file": "other.py", "line": 5, "risk": "low", "type": "x",
             "description": "d", "recommendation": "r"},
        ])
        added = {"app/db.py": {5}}

        inline, unplaced = main._build_inline_comments(result, added)
        assert inline == []
        assert len(unplaced) == 1

    def test_mixed_findings_split_correctly(self):
        result = _security_result([
            {"file": "a.py", "line": 3, "risk": "high", "type": "t1",
             "description": "d", "recommendation": "r"},
            {"file": "a.py", "line": 100, "risk": "low", "type": "t2",
             "description": "d", "recommendation": "r"},
        ])
        added = {"a.py": {1, 2, 3, 4}}

        inline, unplaced = main._build_inline_comments(result, added)
        assert [c["line"] for c in inline] == [3]
        assert [v["line"] for v in unplaced] == [100]

    def test_non_int_line_is_unplaced_not_crash(self):
        result = _security_result([
            {"file": "a.py", "line": "?", "risk": "high", "type": "t",
             "description": "d", "recommendation": "r"},
        ])
        inline, unplaced = main._build_inline_comments(result, {"a.py": {1}})
        assert inline == []
        assert len(unplaced) == 1

    def test_no_security_issues_returns_empty(self):
        result = {"analyses": {"security": {"has_security_issues": False}}}
        assert main._build_inline_comments(result, {}) == ([], [])

    def test_scan_error_returns_empty(self):
        result = {"analyses": {"security": {"scan_error": "semgrep yok"}}}
        assert main._build_inline_comments(result, {}) == ([], [])

    def test_missing_security_analysis_returns_empty(self):
        result = {"analyses": {"short_summary": {"summary": "x"}}}
        assert main._build_inline_comments(result, {}) == ([], [])


# =====================================================================
# _format_review_comment — inline_count etkisi
# =====================================================================

class TestFormatSummaryWithInline:
    def test_summary_shrinks_when_inline_used(self):
        result = _security_result([
            {"file": "a.py", "line": 3, "risk": "high", "type": "sqli",
             "description": "uzun aciklama", "recommendation": "uzun oneri"},
        ])
        body = main._format_review_comment(result, inline_count=1, unplaced=[])
        # inline kullanıldığında tam açıklama metni özet gövdede TEKRARLANMAZ
        assert "1/1" in body
        assert "uzun aciklama" not in body

    def test_unplaced_findings_listed_in_full_in_summary(self):
        vuln = {"file": "a.py", "line": 100, "risk": "low", "type": "t",
                "description": "yerlesemeyen aciklama", "recommendation": "r"}
        result = _security_result([vuln])
        body = main._format_review_comment(result, inline_count=0, unplaced=[vuln])
        assert "yerlesemeyen aciklama" in body

    def test_no_inline_lists_all_vulns(self):
        result = _security_result([
            {"file": "a.py", "line": 3, "risk": "high", "type": "t",
             "description": "aciklama", "recommendation": "r"},
        ])
        body = main._format_review_comment(result, inline_count=0, unplaced=[])
        assert "aciklama" in body


# =====================================================================
# _run_pr_review — uçtan uca akış (DB kapalı, GitHub mock)
# =====================================================================

@pytest.fixture
def _patch_semgrep(monkeypatch, db_disabled):
    """Semgrep'i sabitler (bulgu var); review_diff her testte override edilir."""
    monkeypatch.setattr(
        main, "_run_semgrep_for_pr",
        lambda *a, **k: {"status": "ok", "findings": [{"x": 1}]},
    )
    yield monkeypatch


def _patch_review_diff(monkeypatch, vulns=None, has_issues=True):
    if vulns is None and has_issues:
        vulns = [{"file": "app/db.py", "line": 2, "risk": "high", "type": "sqli",
                  "description": "d", "recommendation": "r"}]
    if has_issues:
        analyses = _security_result(vulns)["analyses"]
    else:
        analyses = {"security": {"has_security_issues": False, "security_level": "safe"}}
    monkeypatch.setattr(
        main, "review_diff",
        lambda **k: {"status": "success", "metadata": {}, "analyses": analyses},
    )


class TestRunPrReviewInlineFlow:
    def test_inline_review_created_when_finding_on_diff(self, _patch_semgrep, fake_github_client):
        holder = fake_github_client()
        _patch_review_diff(_patch_semgrep)

        res = asyncio.run(main._run_pr_review(
            installation_id=1, owner="o", repo="r", pr_number=5,
            review_types=["short_summary", "security"], action="opened",
        ))

        rec = holder.client.recorder
        assert res["status"] == "success"
        assert "create_review" in rec
        assert "post_pr_comment" not in rec
        cr = rec["create_review"]
        assert cr["commit_id"] == "headsha123"
        assert len(cr["comments"]) == 1
        assert cr["comments"][0]["path"] == "app/db.py"
        assert cr["comments"][0]["line"] == 2

    def test_falls_back_to_issue_comment_when_no_placeable_finding(
        self, _patch_semgrep, fake_github_client
    ):
        holder = fake_github_client()
        _patch_review_diff(_patch_semgrep, vulns=[
            {"file": "app/db.py", "line": 999, "risk": "high", "type": "t",
             "description": "d", "recommendation": "r"},
        ])

        asyncio.run(main._run_pr_review(
            installation_id=1, owner="o", repo="r", pr_number=5,
            review_types=["short_summary", "security"], action="opened",
        ))

        rec = holder.client.recorder
        assert "create_review" not in rec
        assert len(rec["post_pr_comment"]) == 1

    def test_inline_review_exception_falls_back_to_issue_comment(
        self, _patch_semgrep, fake_github_client
    ):
        def boom(self, **kw):
            raise RuntimeError("422 line not in diff")

        holder = fake_github_client(create_review=boom)
        _patch_review_diff(_patch_semgrep)

        res = asyncio.run(main._run_pr_review(
            installation_id=1, owner="o", repo="r", pr_number=5,
            review_types=["short_summary", "security"], action="opened",
        ))

        assert res["status"] == "success"
        assert len(holder.client.recorder["post_pr_comment"]) == 1

    def test_synchronize_skips_already_commented_lines(self, _patch_semgrep, fake_github_client):
        holder = fake_github_client(existing_comments=[
            {"path": "app/db.py", "line": 2,
             "body": f"{main._INLINE_MARKER}\neski yorum"},
        ])
        _patch_review_diff(_patch_semgrep)

        asyncio.run(main._run_pr_review(
            installation_id=1, owner="o", repo="r", pr_number=5,
            review_types=["short_summary", "security"], action="synchronize",
        ))

        rec = holder.client.recorder
        assert "create_review" not in rec
        assert len(rec["post_pr_comment"]) == 1

    def test_clean_pr_posts_plain_summary(self, _patch_semgrep, fake_github_client):
        holder = fake_github_client()
        _patch_review_diff(_patch_semgrep, has_issues=False)

        asyncio.run(main._run_pr_review(
            installation_id=1, owner="o", repo="r", pr_number=5,
            review_types=["short_summary", "security"], action="opened",
        ))

        rec = holder.client.recorder
        assert "create_review" not in rec
        assert len(rec["post_pr_comment"]) == 1

    def test_timing_breakdown_in_result(self, _patch_semgrep, fake_github_client):
        holder = fake_github_client()
        _patch_review_diff(_patch_semgrep, has_issues=False)

        res = asyncio.run(main._run_pr_review(
            installation_id=1, owner="o", repo="r", pr_number=5,
            review_types=["short_summary", "security"], action="opened",
        ))

        assert set(res["timing_ms"]) == {"total", "github", "semgrep_and_summary", "gemini_detail"}
        assert all(isinstance(v, int) for v in res["timing_ms"].values())

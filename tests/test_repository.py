"""
Faz 2b veri katmanı testleri: app/repository.py.

İki eksen:
  1. DB açıkken (SQLite in-memory) CRUD davranışı doğru mu?
  2. DB kapalıyken tüm fonksiyonlar sessizce no-op / None mı? (regresyon kalkanı —
     /local-review ve installation'sız akışlar DB olmadan çalışmaya devam etmeli)
"""

import pytest

from app import repository
from app.models import Finding, Installation, UsageLog


# =====================================================================
# DB AÇIK — CRUD davranışı
# =====================================================================

class TestInstallationCrud:
    def test_upsert_creates_row(self, db_session):
        repository.upsert_installation(111, "acme", "Organization", "all")

        with db_session() as s:
            inst = s.get(Installation, 111)
            assert inst is not None
            assert inst.account_login == "acme"
            assert inst.account_type == "Organization"
            assert inst.repository_selection == "all"
            assert inst.is_active is True

    def test_upsert_is_idempotent_and_updates(self, db_session):
        repository.upsert_installation(111, "acme", "Organization", "all")
        repository.upsert_installation(111, "acme-renamed", "User", "selected")

        with db_session() as s:
            rows = s.query(Installation).filter_by(id=111).all()
            assert len(rows) == 1  # mükerrer satır YOK
            assert rows[0].account_login == "acme-renamed"
            assert rows[0].account_type == "User"
            assert rows[0].repository_selection == "selected"

    def test_deactivate_is_soft_delete(self, db_session):
        repository.upsert_installation(111, "acme", "Organization", "all")
        repository.deactivate_installation(111)

        with db_session() as s:
            inst = s.get(Installation, 111)
            assert inst is not None          # satır SİLİNMEZ
            assert inst.is_active is False

    def test_deactivate_unknown_installation_is_noop(self, db_session):
        # Kayıtsız bir id gelse bile patlamamalı
        repository.deactivate_installation(999999)
        with db_session() as s:
            assert s.get(Installation, 999999) is None

    def test_reactivate_via_upsert(self, db_session):
        # Kullanıcı kaldırıp tekrar kurarsa is_active yeniden True olmalı
        repository.upsert_installation(111, "acme", "User", "all")
        repository.deactivate_installation(111)
        repository.upsert_installation(111, "acme", "User", "all")
        with db_session() as s:
            assert s.get(Installation, 111).is_active is True

    def test_update_repos_touches_existing_row(self, db_session):
        repository.upsert_installation(111, "acme", "User", "selected")
        # Sadece patlamadan çalışmalı (repo listesi tablosu Faz 2c)
        repository.update_installation_repos(111, ["acme/a", "acme/b"], [])
        with db_session() as s:
            assert s.get(Installation, 111) is not None


class TestUsageAndFindings:
    def test_record_usage_returns_id_and_persists(self, db_session):
        repository.upsert_installation(111, "acme", "User", "all")

        usage_id = repository.record_usage(
            installation_id=111,
            owner="acme",
            repo="web",
            pr_number=7,
            review_types=["short_summary", "security"],
            diff_size=1234,
            was_truncated=True,
            semgrep_status="ok",
            finding_count=2,
            parse_success=True,
            duration_ms=850,
        )
        assert isinstance(usage_id, int)

        with db_session() as s:
            log = s.get(UsageLog, usage_id)
            assert log.installation_id == 111
            assert log.repo == "web"
            assert log.pr_number == 7
            assert log.review_types == ["short_summary", "security"]
            assert log.was_truncated is True
            assert log.semgrep_status == "ok"
            assert log.finding_count == 2
            assert log.parse_success is True
            assert log.duration_ms == 850

    def test_record_findings_links_to_usage_log(self, db_session):
        repository.upsert_installation(111, "acme", "User", "all")
        usage_id = repository.record_usage(
            installation_id=111, owner="acme", repo="web", pr_number=7,
            semgrep_status="ok", finding_count=2,
        )
        findings = [
            {"file": "app/db.py", "line": 10, "rule_id": "python.sqli", "severity": "high", "cwe": ["CWE-89"]},
            {"file": "app/x.py", "line": 3, "rule_id": "python.secret", "severity": "medium", "cwe": None},
        ]
        repository.record_findings(usage_id, 111, findings)

        with db_session() as s:
            rows = s.query(Finding).filter_by(usage_log_id=usage_id).order_by(Finding.line).all()
            assert len(rows) == 2
            assert rows[0].rule_id == "python.secret"  # line=3
            assert rows[1].rule_id == "python.sqli"    # line=10
            assert rows[1].cwe == "CWE-89"             # liste -> düz metin
            assert rows[1].installation_id == 111

    def test_record_findings_empty_list_is_noop(self, db_session):
        repository.upsert_installation(111, "acme", "User", "all")
        usage_id = repository.record_usage(installation_id=111, owner="a", repo="b", pr_number=1)
        repository.record_findings(usage_id, 111, [])
        with db_session() as s:
            assert s.query(Finding).count() == 0

    def test_record_findings_with_none_usage_id_is_noop(self, db_session):
        # record_usage None dönmüşse (örn. hata), findings sessizce atlanmalı
        repository.record_findings(None, 111, [{"file": "x", "line": 1, "rule_id": "r", "severity": "low"}])
        with db_session() as s:
            assert s.query(Finding).count() == 0


class TestStatsSummary:
    def test_summary_counts(self, db_session):
        repository.upsert_installation(1, "a", "User", "all")
        repository.upsert_installation(2, "b", "User", "all")
        repository.deactivate_installation(2)
        repository.record_usage(installation_id=1, owner="a", repo="r", pr_number=1)
        repository.record_usage(installation_id=1, owner="a", repo="r", pr_number=2)

        summary = repository.get_stats_summary()
        assert summary["installations_total"] == 2
        assert summary["installations_active"] == 1
        assert summary["reviews_total"] == 2
        assert summary["reviews_last_7d"] == 2


# =====================================================================
# DB KAPALI — her şey sessizce no-op
# =====================================================================

class TestDbDisabledIsSafe:
    def test_all_writes_are_noop_without_raising(self, db_disabled):
        # Hiçbiri exception atmamalı
        repository.upsert_installation(1, "a", "User", "all")
        repository.deactivate_installation(1)
        repository.update_installation_repos(1, ["a/b"], [])
        assert repository.record_usage(installation_id=1, owner="a", repo="r", pr_number=1) is None
        repository.record_findings(None, 1, [{"file": "x", "line": 1, "rule_id": "r", "severity": "low"}])
        repository.record_findings(5, 1, [{"file": "x", "line": 1, "rule_id": "r", "severity": "low"}])

    def test_stats_summary_is_none_when_disabled(self, db_disabled):
        assert repository.get_stats_summary() is None


# =====================================================================
# REGRESYON — _run_pr_review DB kapalıyken bugünküyle aynı davranmalı
# =====================================================================

class TestRunPrReviewRegression:
    def test_pr_review_works_with_db_disabled(self, db_disabled, monkeypatch):
        """
        DB kapalıyken _run_pr_review; diff çeker, analiz eder, yorum gönderir —
        loglama katmanı hiçbir şeyi bozmaz. (test_security_explain.py deseni)
        """
        import asyncio

        from app import main  # noqa: PLC0415

        class FakeClient:
            def __init__(self, installation_id):
                self.installation_id = installation_id
                self.posted = []

            def get_pr_diff(self, owner, repo, pr_number):
                return "--- a/x.py\n+++ b/x.py\n@@ -1 +1,2 @@\n x\n+y\n"

            def get_pr_details(self, *a, **k):
                return {"head": {"sha": "abc123"}}

            def get_pr_files(self, *a, **k):
                return []

            def post_pr_comment(self, owner, repo, pr_number, body):
                self.posted.append(body)
                return {"id": 1}

        monkeypatch.setattr(main, "GitHubAppClient", FakeClient)
        # Semgrep'i devre dışı bırak — bu test loglama akışını doğruluyor, taramayı değil
        monkeypatch.setattr(
            main, "_run_semgrep_for_pr",
            lambda *a, **k: {"status": "unavailable", "error": "test"},
        )
        monkeypatch.setattr(
            main, "review_diff",
            lambda **k: {
                "status": "success",
                "analyses": {"short_summary": {"summary": "x", "severity": "low", "type": "refactor"}},
                "metadata": {},
            },
        )

        result = asyncio.run(
            main._run_pr_review(
                installation_id=42, owner="acme", repo="web", pr_number=3,
                review_types=["short_summary", "security"],
            )
        )
        assert result["status"] == "success"
        assert result["pr_number"] == 3

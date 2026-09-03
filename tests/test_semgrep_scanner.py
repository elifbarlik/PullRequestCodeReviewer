"""
semgrep_scanner testleri.

NOT: p/security-audit / p/secrets gibi registry config'leri internet
gerektirir (semgrep.dev'den indirilir). CI'de öngörülebilir kalması
için testler kendi yerel kural dosyasını (fixture) kullanır — asıl
üretim config'i (DEFAULT_SEMGREP_CONFIGS) değil.
"""

import os
import textwrap

import pytest

from app.semgrep_scanner import (
    run_semgrep,
    scan_diff,
    validate_configs,
    SemgrepNotAvailable,
    DEFAULT_SEMGREP_CONFIGS,
)
from app import semgrep_scanner


LOCAL_RULE_YAML = textwrap.dedent(
    """
    rules:
      - id: test-os-system
        languages: [python]
        severity: ERROR
        message: "os.system kullanımı komut enjeksiyonuna açık olabilir"
        patterns:
          - pattern: os.system(...)
    """
)


@pytest.fixture
def local_rule_file(tmp_path):
    rule_path = tmp_path / "rule.yml"
    rule_path.write_text(LOCAL_RULE_YAML, encoding="utf-8")
    return str(rule_path)


@pytest.mark.requires_semgrep
class TestRunSemgrep:
    def test_finds_known_pattern(self, local_rule_file):
        files = {"vuln.py": 'import os\n\ndef run(x):\n    os.system("echo " + x)\n'}
        results = run_semgrep(files, configs=[local_rule_file])

        assert len(results) == 1
        # Semgrep, yerel dosya yolundan yuklenen kurallarin check_id'sini
        # dosya yoluna gore namespace'ler (orn. ".../rule.yml" -> "...tmp.rule.test-os-system").
        # Registry config'lerinde de (p/security-audit) check_id her zaman
        # boyle namespace'li gelir (orn. "python.lang.security.audit...") —
        # bu yuzden tam esitlik yerine icerik kontrolu yapiyoruz.
        assert results[0]["check_id"].endswith("test-os-system")
        assert results[0]["path"] == "vuln.py"
        assert results[0]["start"]["line"] == 4

    def test_no_findings_for_clean_file(self, local_rule_file):
        files = {"clean.py": "def add(a, b):\n    return a + b\n"}
        results = run_semgrep(files, configs=[local_rule_file])
        assert results == []

    def test_empty_files_returns_empty(self, local_rule_file):
        assert run_semgrep({}, configs=[local_rule_file]) == []

    def test_path_traversal_attempt_is_skipped(self, local_rule_file):
        # Şüpheli yol (../../etc/passed gibi) sessizce atlanmalı, exception
        # fırlatmamalı ya da tmpdir dışına yazmamalı
        files = {"../../evil.py": "os.system('rm -rf /')"}
        results = run_semgrep(files, configs=[local_rule_file])
        assert results == []


@pytest.mark.requires_semgrep
class TestScanDiff:
    def test_only_reports_findings_on_added_lines(self, local_rule_file):
        # Dosyada İKİ os.system çağrısı var: biri PR'den ÖNCE de vardı
        # (context/değişmemiş), biri PR'de YENİ eklendi. Sadece yenisi
        # rapor edilmeli.
        file_content = (
            "import os\n"                              # 1 (context)
            "\n"                                        # 2 (context)
            "def old_func():\n"                         # 3 (context)
            "    os.system('echo old')\n"                # 4 (context — PR'den önce vardı)
            "\n"                                        # 5 (context)
            "def new_func():\n"                          # 6 (added)
            "    os.system('echo new')\n"                # 7 (added)
        )
        diff_text = (
            "diff --git a/app.py b/app.py\n"
            "index 111..222 100644\n"
            "--- a/app.py\n"
            "+++ b/app.py\n"
            "@@ -1,5 +1,7 @@\n"
            " import os\n"
            " \n"
            " def old_func():\n"
            "     os.system('echo old')\n"
            " \n"
            "+def new_func():\n"
            "+    os.system('echo new')\n"
        )

        findings = scan_diff({"app.py": file_content}, diff_text, configs=[local_rule_file])

        assert len(findings) == 1
        assert findings[0]["line"] == 7
        assert findings[0]["severity"] == "high"  # ERROR -> high eşlemesi

    def test_no_findings_when_diff_touches_nothing_risky(self, local_rule_file):
        file_content = "os.system('echo old')\nx = 1\n"
        diff_text = (
            "diff --git a/app.py b/app.py\n"
            "--- a/app.py\n"
            "+++ b/app.py\n"
            "@@ -1,2 +1,2 @@\n"
            " os.system('echo old')\n"
            "-x = 1\n"
            "+x = 2\n"
        )
        findings = scan_diff({"app.py": file_content}, diff_text, configs=[local_rule_file])
        assert findings == []


class TestSemgrepNotAvailable:
    def test_raises_when_binary_missing(self, monkeypatch):
        # PATH'te yok...
        monkeypatch.setattr(semgrep_scanner.shutil, "which", lambda name: None)
        # ...ve venv Scripts/bin fallback'inde de yok
        monkeypatch.setattr(semgrep_scanner.os.path, "isfile", lambda p: False)
        with pytest.raises(SemgrepNotAvailable):
            run_semgrep({"a.py": "x = 1"})


class TestValidateConfigs:
    def test_none_returns_default(self):
        assert validate_configs(None) == list(DEFAULT_SEMGREP_CONFIGS)

    def test_empty_returns_default(self):
        assert validate_configs([]) == list(DEFAULT_SEMGREP_CONFIGS)

    def test_keeps_only_allowed(self):
        result = validate_configs(["p/secrets", "p/python", "p/definitely-not-real"])
        assert result == ["p/secrets", "p/python"]

    def test_all_invalid_falls_back_to_default(self):
        # Keyfi dosya yolu / URL kabul edilmez — komut enjeksiyonu / SSRF yüzeyi
        assert validate_configs(["/etc/passwd", "https://evil.test/rules.yml"]) == list(
            DEFAULT_SEMGREP_CONFIGS
        )

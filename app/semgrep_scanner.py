"""
Semgrep tabanlı deterministik güvenlik taraması.

Roadmap'in Faz 0'da karar verdiği hibrit mimarinin çekirdeği: Gemini
kendi başına güvenlik açığı "tahmin etmiyor" — Semgrep bilinen
pattern'leri (SQL injection, hardcoded secret, path traversal, SSRF vb.)
deterministik olarak buluyor, Gemini'nin rolü bu bulguları Türkçe ve
öğretici şekilde açıklamaya dönüştürmek (bkz. app/reviewer.py, Faz 2.2).
"""

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from typing import Dict, List, Optional

from app.diff_utils import parse_added_lines

logger = logging.getLogger(__name__)

# Varsayılan ruleset seti. `p/security-audit` tek başına konservatif —
# benchmark (benchmarks/, Faz 4.2) ile ölçüldü: `p/python` + `p/default`
# eklendiğinde SQLi, komut enjeksiyonu, zayıf kripto, eval, insecure
# deserialization, JWT/TLS misconfig, XSS (mark_safe) sınıflarında recall
# belirgin artıyor; `p/secrets` API key / parola / bulut anahtarı yakalıyor.
# Gerçek çalışma ortamında internet erişimi gerekir (rule pack'ler ilk
# çalıştırmada semgrep.dev'den indirilir; Dockerfile bunları build'de
# önceden cache'liyor — Faz 4.4).
DEFAULT_SEMGREP_CONFIGS = ["p/default", "p/python", "p/security-audit", "p/secrets"]

# Semgrep OSS "ERROR/WARNING/INFO" seviyelerini SecPR-TR'nin risk
# skalasına (critical/high/medium/low) eşler. Semgrep OSS varsayılan
# olarak "critical" üretmez — bu skala reviewer.py'daki SECURITY_REVIEW
# şablonuyla tutarlı kalsın diye bilinçli olarak korunuyor.
_SEVERITY_MAP = {
    "ERROR": "high",
    "WARNING": "medium",
    "INFO": "low",
}

# Faz 4.4: içeriğe göre kademeli timeout. Küçük PR için 120 sn fazla —
# kullanıcı 2 dk yorum bekleyemez. Dosya sayısına göre run_semgrep ayarlar.
SEMGREP_TIMEOUT_SECONDS = 120          # geriye dönük varsayılan (dış çağrılar)
SEMGREP_TIMEOUT_SMALL = 45            # ≤ SEMGREP_SMALL_FILE_LIMIT dosya
SEMGREP_TIMEOUT_LARGE = 120
SEMGREP_SMALL_FILE_LIMIT = 12

# Faz 2c: installation başına seçilebilen ruleset'ler. Sadece Semgrep
# Registry'nin "p/..." kısayolları — keyfi dosya yolu / URL kabul edilmez
# (kullanıcı kontrollü config = komut enjeksiyonu / SSRF yüzeyi).
ALLOWED_SEMGREP_CONFIGS = {
    "p/security-audit",
    "p/secrets",
    "p/owasp-top-ten",
    "p/python",
    "p/javascript",
    "p/typescript",
    "p/golang",
    "p/java",
    "p/ci",
    "p/default",
    "p/command-injection",
    "p/sql-injection",
    "p/xss",
}


def validate_configs(configs: Optional[List[str]]) -> List[str]:
    """
    Kullanıcıdan gelen ruleset listesini ALLOWED_SEMGREP_CONFIGS'e göre
    filtreler. Geçersiz/boş sonuç → DEFAULT_SEMGREP_CONFIGS.

    Bu fonksiyon hem yazma yolunda (ayar kaydedilmeden önce) hem okuma
    yolunda (tarama başlamadan önce) çağrılır — defansif katman.
    """
    if not configs:
        return list(DEFAULT_SEMGREP_CONFIGS)
    valid = [c for c in configs if c in ALLOWED_SEMGREP_CONFIGS]
    if not valid:
        logger.warning(
            f"⚠️  Geçerli Semgrep config yok ({configs!r}), varsayılana dönülüyor"
        )
        return list(DEFAULT_SEMGREP_CONFIGS)
    return valid


class SemgrepNotAvailable(Exception):
    """Semgrep CLI PATH'te bulunamadığında fırlatılır."""


def _semgrep_binary() -> str:
    # 1. PATH
    path = shutil.which("semgrep")
    if path:
        return path
    # 2. Aktif Python yorumlayıcısının yanındaki Scripts/bin dizini —
    #    venv'i "activate" etmeden çalıştırıldığında (Windows dev, bazı CI)
    #    semgrep PATH'te olmayabilir ama pip ile kurulmuştur.
    exe_dir = os.path.dirname(sys.executable)
    for name in ("semgrep", "semgrep.exe"):
        candidate = os.path.join(exe_dir, name)
        if os.path.isfile(candidate):
            return candidate
    raise SemgrepNotAvailable(
        "semgrep CLI bulunamadı (PATH veya venv Scripts). Kurulum: pip install semgrep"
    )


def run_semgrep(
    files: Dict[str, str],
    configs: Optional[List[str]] = None,
    timeout: Optional[int] = None,
) -> List[dict]:
    """
    Verilen dosyaları (yol -> içerik) geçici bir dizine yazıp Semgrep
    çalıştırır, ham (normalize edilmemiş) bulgu listesini döndürür.

    Args:
        files: {göreli_dosya_yolu: dosya_içeriği} — PR head'indeki tam içerik
        configs: Semgrep --config değerleri (varsayılan: DEFAULT_SEMGREP_CONFIGS)
        timeout: saniye cinsinden zaman aşımı

    Returns:
        Semgrep'in ham `results` listesi (bkz. `semgrep scan --json` çıktısı),
        `path` alanları göreli dosya yoluna çevrilmiş olarak

    Raises:
        SemgrepNotAvailable: semgrep CLI kurulu değilse
        RuntimeError: semgrep beklenmedik şekilde başarısız olursa / timeout
    """
    if not files:
        return []

    binary = _semgrep_binary()
    configs = configs or DEFAULT_SEMGREP_CONFIGS

    # Faz 4.4: küçük PR'de kısa timeout — kullanıcı 2 dk bekleyemez.
    if timeout is None:
        timeout = (
            SEMGREP_TIMEOUT_SMALL
            if len(files) <= SEMGREP_SMALL_FILE_LIMIT
            else SEMGREP_TIMEOUT_LARGE
        )

    with tempfile.TemporaryDirectory(prefix="secpr_semgrep_") as tmpdir:
        written_paths = []
        for rel_path, content in files.items():
            # Path traversal'a karşı savunma: '..' içeren veya mutlak
            # yollar (GitHub API'den gelen path'ler normalde güvenli
            # olsa da, dışarıdan gelen veriye asla güvenilmez)
            norm = os.path.normpath(rel_path)
            if norm.startswith("..") or os.path.isabs(norm):
                logger.warning(f"⚠️  Şüpheli dosya yolu atlandı: {rel_path!r}")
                continue

            full_path = os.path.join(tmpdir, norm)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w", encoding="utf-8", errors="replace") as f:
                f.write(content)
            written_paths.append(full_path)

        if not written_paths:
            return []

        cmd = [binary, "scan"]
        for cfg in configs:
            cmd += ["--config", cfg]
        cmd += [
            "--json",
            "--metrics=off",
            "--disable-version-check",  # bkz. modül docstring'i — bu olmadan
                                         # ağ kısıtlı ortamlarda scan sonrası asılı kalır
            "--quiet",
            "--jobs", str(os.cpu_count() or 1),   # Faz 4.4: çok çekirdek kullan
            "--max-target-bytes", "1000000",       # 1 MB üstü dosyaları atla (üretilmiş/minified)
            tmpdir,
        ]

        logger.info(
            f"📤 Semgrep çalıştırılıyor: {len(written_paths)} dosya, "
            f"config={configs}, timeout={timeout}s"
        )
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout
            )
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(f"Semgrep {timeout}s içinde tamamlanamadı") from e

        if proc.returncode != 0:
            logger.error(f"❌ Semgrep hata verdi (exit={proc.returncode}): {proc.stderr[-2000:]}")
            raise RuntimeError(f"Semgrep başarısız (exit={proc.returncode})")

        try:
            output = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Semgrep JSON çıktısı parse edilemedi: {e}") from e

        results = output.get("results", [])
        logger.info(f"📥 Semgrep tamamlandı: {len(results)} ham bulgu")

        for r in results:
            # tmpdir'e göre göreli yol; ayrıca POSIX ayraç ('/') — GitHub
            # diff'lerindeki path'ler her zaman '/' kullanır ve scan_diff
            # bunları parse_added_lines çıktısıyla eşleştirir. Windows'ta
            # os.path.relpath ters slash döndürüp eşleşmeyi bozuyordu.
            r["path"] = os.path.relpath(r["path"], tmpdir).replace(os.sep, "/")

        return results


def _normalize_finding(raw: dict) -> dict:
    """Semgrep ham bulgusunu SecPR-TR'nin iç formatına çevirir."""
    extra = raw.get("extra", {})
    metadata = extra.get("metadata", {}) or {}
    return {
        "file": raw.get("path", "unknown"),
        "line": raw.get("start", {}).get("line", 0),
        "end_line": raw.get("end", {}).get("line", 0),
        "rule_id": raw.get("check_id", "unknown"),
        "severity": _SEVERITY_MAP.get(extra.get("severity", "WARNING"), "medium"),
        "message": extra.get("message", ""),
        "cwe": metadata.get("cwe"),
        "owasp": metadata.get("owasp"),
    }


def scan_diff(
    files: Dict[str, str],
    diff_text: str,
    configs: Optional[List[str]] = None,
) -> List[dict]:
    """
    Semgrep'i çalıştırır ve bulguları SADECE PR'de gerçekten
    eklenen/değişen satırlarla sınırlar — dosyada önceden var olan ve
    bu PR'nin sebep olmadığı bulgular rapor edilmez. Bu filtre olmadan
    her PR, dosyadaki eski/ilgisiz bulgularla gürültülü hale gelir.

    Args:
        files: {göreli_dosya_yolu: PR head'indeki tam dosya içeriği}
        diff_text: PR'nin unified diff'i (satır filtrelemesi için)
        configs: Semgrep --config değerleri

    Returns:
        Normalize edilmiş bulgu listesi:
        [{file, line, end_line, rule_id, severity, message, cwe, owasp}, ...]
    """
    added_lines = parse_added_lines(diff_text)
    raw_findings = run_semgrep(files, configs=configs)

    filtered = []
    for raw in raw_findings:
        finding = _normalize_finding(raw)
        touched = added_lines.get(finding["file"], set())
        finding_range = set(range(finding["line"], finding["end_line"] + 1))
        if touched & finding_range:
            filtered.append(finding)

    logger.info(
        f"🔎 Semgrep: {len(raw_findings)} ham bulgu → "
        f"{len(filtered)} PR'de değişen satırlarla eşleşen"
    )
    return filtered

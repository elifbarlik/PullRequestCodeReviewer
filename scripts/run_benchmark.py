#!/usr/bin/env python3
"""
SecPR-TR benchmark koşucusu (Faz 4.2).

`benchmarks/cases/*` altındaki her senaryoyu `app.semgrep_scanner.scan_diff`'ten
geçirir, `meta.json`'daki beklenen bulgularla karşılaştırır ve
recall / precision / F1 + tarama süresi (medyan, p95) hesaplar.

Çıktı:
  - varsayılan: konsol tablosu + `benchmarks/RESULTS.md` güncellenir
  - `--json`: tek satır makine-okur özet, RESULTS.md'ye dokunmaz

Kullanım:
  python scripts/run_benchmark.py
  python scripts/run_benchmark.py --case sqli_01
  python scripts/run_benchmark.py --json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.semgrep_scanner import SemgrepNotAvailable, scan_diff  # noqa: E402

CASES_DIR = ROOT / "benchmarks" / "cases"
RESULTS_MD = ROOT / "benchmarks" / "RESULTS.md"

LINE_TOLERANCE = 2  # Semgrep blok başı vs ifade satırı toleransı


# ---------------------------------------------------------------------------
# Case yükleme
# ---------------------------------------------------------------------------

def load_case(case_dir: Path) -> dict:
    """Bir case klasörünü {id, meta, diff, files} olarak yükler."""
    meta_path = case_dir / "meta.json"
    diff_path = case_dir / "change.diff"
    if not meta_path.is_file() or not diff_path.is_file():
        raise ValueError(f"{case_dir.name}: meta.json veya change.diff eksik")

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    diff_text = diff_path.read_text(encoding="utf-8")

    # files: meta.json ve change.diff dışındaki her dosya = PR head içeriği
    files: dict[str, str] = {}
    for p in case_dir.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(case_dir).as_posix()
        if rel in ("meta.json", "change.diff"):
            continue
        files[rel] = p.read_text(encoding="utf-8", errors="replace")

    return {"id": case_dir.name, "meta": meta, "diff": diff_text, "files": files}


# ---------------------------------------------------------------------------
# Eşleştirme
# ---------------------------------------------------------------------------

def _match(expected: list[dict], findings: list[dict]) -> tuple[int, int, int, int]:
    """
    Beklenen bulgularla gerçek bulguları eşleştirir.

    - Bir gerçek bulgu, aynı dosyada ve satırı ±LINE_TOLERANCE içinde
      HENÜZ eşleşmemiş bir beklenen bulguya denk geliyorsa TP.
    - Aynı beklenen bulgunun satır aralığına düşen İKİNCİ bir gerçek bulgu
      (farklı kural aynı sorunu yakalamış) FP DEĞİL — "dup" sayılır; gürültü
      ama yanlış alarm değil. Precision'ı haksız cezalandırmamak için ayrılır.
    - Hiçbir beklenene denk gelmeyen gerçek bulgu FP.
    - Eşleşmeyen beklenen bulgu FN.

    Returns:
        (tp, fp, fn, dup)
    """
    matched_expected: list[dict] = []
    tp = fp = dup = 0

    for f in findings:
        # önce henüz eşleşmemiş bir beklenene bak
        hit = next(
            (
                exp for exp in expected
                if exp not in matched_expected
                and exp["file"] == f["file"]
                and abs(int(exp["line"]) - int(f["line"])) <= LINE_TOLERANCE
            ),
            None,
        )
        if hit is not None:
            tp += 1
            matched_expected.append(hit)
            continue
        # zaten eşleşmiş bir beklenenin aralığına mı düşüyor? → dup
        near_matched = any(
            exp["file"] == f["file"]
            and abs(int(exp["line"]) - int(f["line"])) <= LINE_TOLERANCE
            for exp in matched_expected
        )
        if near_matched:
            dup += 1
        else:
            fp += 1

    fn = len(expected) - len(matched_expected)
    return tp, fp, fn, dup


# ---------------------------------------------------------------------------
# Koşum
# ---------------------------------------------------------------------------

def run_case(case: dict) -> dict:
    """Tek case'i tarar ve sonucu döndürür."""
    meta = case["meta"]
    expected = meta.get("expected", []) if meta.get("should_flag", True) else []

    t0 = time.monotonic()
    try:
        findings = scan_diff(case["files"], case["diff"])
        error = None
    except SemgrepNotAvailable:
        raise
    except Exception as e:  # noqa: BLE001 — case bazlı hata raporlanır, koşum devam eder
        findings = []
        error = str(e)
    scan_ms = int((time.monotonic() - t0) * 1000)

    tp, fp, fn, dup = _match(expected, findings)

    return {
        "id": case["id"],
        "category": meta.get("category", "?"),
        "should_flag": meta.get("should_flag", True),
        "scan_ms": scan_ms,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "dup": dup,
        "n_findings": len(findings),
        "error": error,
    }


def aggregate(results: list[dict]) -> dict:
    tp = sum(r["tp"] for r in results)
    fp = sum(r["fp"] for r in results)
    fn = sum(r["fn"] for r in results)
    dup = sum(r.get("dup", 0) for r in results)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    times = sorted(r["scan_ms"] for r in results)
    median_ms = int(statistics.median(times)) if times else 0
    p95_ms = times[int(len(times) * 0.95) - 1] if len(times) >= 2 else (times[0] if times else 0)

    clean = [r for r in results if not r["should_flag"]]
    clean_fp = sum(r["fp"] for r in clean)

    return {
        "cases": len(results),
        "vuln_cases": sum(1 for r in results if r["should_flag"]),
        "clean_cases": len(clean),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "dup": dup,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "clean_false_positives": clean_fp,
        "median_scan_ms": median_ms,
        "p95_scan_ms": p95_ms,
        "errors": [r["id"] for r in results if r["error"]],
    }


# ---------------------------------------------------------------------------
# Rapor
# ---------------------------------------------------------------------------

def render_markdown(agg: dict, results: list[dict]) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Benchmark Sonuçları",
        "",
        f"_Son çalıştırma: {now} · `python scripts/run_benchmark.py`_",
        "",
        "## Özet",
        "",
        "| Metrik | Değer |",
        "|---|---|",
        f"| Toplam senaryo | {agg['cases']} ({agg['vuln_cases']} açıklı, {agg['clean_cases']} temiz) |",
        f"| **Recall** (yakalanan / olması gereken) | **{agg['recall']*100:.1f}%** |",
        f"| **Precision** (doğru / tüm bulgular) | **{agg['precision']*100:.1f}%** |",
        f"| **F1** | **{agg['f1']*100:.1f}%** |",
        f"| Temiz PR'lerde false positive | {agg['clean_false_positives']} |",
        f"| Medyan tarama süresi | {agg['median_scan_ms']} ms |",
        f"| p95 tarama süresi | {agg['p95_scan_ms']} ms |",
        f"| TP / FP / FN | {agg['tp']} / {agg['fp']} / {agg['fn']} |",
        f"| Dup (aynı sorunu ikinci kural yakaladı) | {agg['dup']} |",
    ]
    if agg["errors"]:
        lines.append(f"| Hata veren senaryolar | {', '.join(agg['errors'])} |")
    lines += [
        "",
        "## Senaryo bazında",
        "",
        "| Senaryo | Kategori | Bekleniyor | TP | FP | FN | Dup | Süre (ms) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in sorted(results, key=lambda x: (not x["should_flag"], x["category"], x["id"])):
        flag = "açık" if r["should_flag"] else "temiz"
        note = " ⚠️" if r["error"] else ""
        lines.append(
            f"| `{r['id']}`{note} | {r['category']} | {flag} | "
            f"{r['tp']} | {r['fp']} | {r['fn']} | {r.get('dup', 0)} | {r['scan_ms']} |"
        )
    lines += [
        "",
        "## Yöntem",
        "",
        f"- Eşleşme toleransı: dosya aynı + satır ±{LINE_TOLERANCE}",
        "- Ölçülen katman: `app/semgrep_scanner.scan_diff` (Semgrep + diff-satır filtresi)",
        "- LLM açıklama katmanı dahil değil (o bulur değil, açıklar)",
        "- Sınırlar için `benchmarks/README.md`",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="SecPR-TR benchmark koşucusu")
    ap.add_argument("--case", help="Sadece bu case id'sini çalıştır")
    ap.add_argument("--json", action="store_true", help="JSON özet bas, RESULTS.md yazma")
    args = ap.parse_args()

    if not CASES_DIR.is_dir():
        print(f"❌ {CASES_DIR} yok — benchmark case'i eklenmemiş", file=sys.stderr)
        return 2

    case_dirs = sorted(d for d in CASES_DIR.iterdir() if d.is_dir())
    if args.case:
        case_dirs = [d for d in case_dirs if d.name == args.case]
        if not case_dirs:
            print(f"❌ Case bulunamadı: {args.case}", file=sys.stderr)
            return 2

    if not case_dirs:
        print("❌ Hiç case yok", file=sys.stderr)
        return 2

    try:
        results = [run_case(load_case(d)) for d in case_dirs]
    except SemgrepNotAvailable as e:
        print(f"❌ Semgrep kurulu değil: {e}\n   pip install semgrep", file=sys.stderr)
        return 3

    agg = aggregate(results)

    if args.json:
        print(json.dumps(agg, ensure_ascii=False))
        return 0

    md = render_markdown(agg, results)
    RESULTS_MD.write_text(md, encoding="utf-8")

    print(f"\n{'='*60}")
    print(f"  Senaryo: {agg['cases']}  |  Recall: {agg['recall']*100:.1f}%  "
          f"|  Precision: {agg['precision']*100:.1f}%  |  F1: {agg['f1']*100:.1f}%")
    print(f"  Temiz PR false positive: {agg['clean_false_positives']}")
    print(f"  Medyan süre: {agg['median_scan_ms']} ms  |  p95: {agg['p95_scan_ms']} ms")
    if agg["errors"]:
        print(f"  ⚠️  Hata: {', '.join(agg['errors'])}")
    print(f"{'='*60}")
    print(f"  → {RESULTS_MD.relative_to(ROOT)} güncellendi\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# SecPR-TR Benchmark

`app/semgrep_scanner.scan_diff` katmanının (hibrit mimarinin deterministik yarısı)
**recall / precision / F1** değerlerini ve **tarama süresini** ölçer.

> Ölçülen: Semgrep + diff-satır filtresi. Gemini açıklama katmanı (LLM) bu
> benchmark'ta yer almaz — o "bulguyu açıklar", "bulur" değil; kalite Semgrep'in
> `should_flag` doğruluğuyla belirlenir.

## Yapı

```
benchmarks/
  cases/
    <case_id>/
      meta.json            # açıklama, kategori, should_flag, beklenen bulgular
      <path/to/file.py>    # PR head'indeki TAM dosya içeriği (scan_diff'in "files" argümanı)
      change.diff          # unified diff (scan_diff'in "diff_text" argümanı)
  RESULTS.md               # run_benchmark.py çıktısı (repoya commit'lenir)
```

### `meta.json` şeması

```json
{
  "description": "Kullanıcı girdisi string concat ile SQL sorgusuna gömülüyor",
  "category": "sql-injection",
  "should_flag": true,
  "expected": [
    { "file": "app/db.py", "line": 12, "cwe_hint": "CWE-89" }
  ]
}
```

- `should_flag: false` → **temiz** örnek; herhangi bir bulgu = false positive.
- `expected[].line` → beklenen bulgu satırı. Eşleşme toleransı `±LINE_TOLERANCE`
  (varsayılan 2) — Semgrep bazen bloğun ilk satırını, bazen ifadenin satırını verir.
- `expected[].cwe_hint` yalnızca insan okuması için; eşleşmeye girmez.

## Çalıştırma

```bash
pip install semgrep
python scripts/run_benchmark.py                 # tüm case'ler, RESULTS.md güncellenir
python scripts/run_benchmark.py --case sqli_01  # tek case
python scripts/run_benchmark.py --json          # makine-okur çıktı, RESULTS.md yazma
```

İlk çalıştırma Semgrep ruleset'lerini indirir (birkaç dakika); sonra cache'lenir.

## Öncesi / sonrası kıyas (Faz 4.4)

```bash
git stash && git checkout <opt-öncesi-commit>
python scripts/run_benchmark.py --json > /tmp/before.json
git checkout main && git stash pop
python scripts/run_benchmark.py --json > /tmp/after.json
```

Süre farkı `median_scan_ms` / `p95_scan_ms` alanlarında.

## Sınırlar (dürüst not)

- Örneklerin bir kısmı elle yazıldı, bir kısmı OWASP/Semgrep test-case'lerinden
  türetildi. Gerçek dünya dağılımını temsil etmez — **yönelim** verir, mutlak
  garanti değil.
- Yalnızca `ALLOWED_SEMGREP_CONFIGS` ruleset kapsamındaki açık sınıfları.
- İş mantığı açıkları (authz bypass, IDOR mantığı, race condition) kapsam dışı —
  statik kural bunları yakalamaz, bu bilinçli bir sınır.

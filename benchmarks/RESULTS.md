# Benchmark Sonuçları

_Son çalıştırma: 2026-09-03 13:23 UTC · `python scripts/run_benchmark.py`_

## Özet

| Metrik | Değer |
|---|---|
| Toplam senaryo | 28 (20 açıklı, 8 temiz) |
| **Recall** (yakalanan / olması gereken) | **52.4%** |
| **Precision** (doğru / tüm bulgular) | **100.0%** |
| **F1** | **68.8%** |
| Temiz PR'lerde false positive | 0 |
| Medyan tarama süresi | 5717 ms |
| p95 tarama süresi | 6533 ms |
| TP / FP / FN | 11 / 0 / 10 |
| Dup (aynı sorunu ikinci kural yakaladı) | 2 |

## Senaryo bazında

| Senaryo | Kategori | Bekleniyor | TP | FP | FN | Dup | Süre (ms) |
|---|---|---|---|---|---|---|---|
| `assert_01_auth` | broken-auth | açık | 0 | 0 | 1 | 0 | 5637 |
| `jwt_01_noverify` | broken-auth | açık | 1 | 0 | 0 | 0 | 6660 |
| `eval_01_user` | code-injection | açık | 1 | 0 | 0 | 0 | 6720 |
| `cmdi_01_ossystem` | command-injection | açık | 0 | 0 | 1 | 0 | 5945 |
| `cmdi_02_shell_true` | command-injection | açık | 1 | 0 | 0 | 0 | 5800 |
| `secret_01_apikey` | hardcoded-secret | açık | 1 | 0 | 0 | 0 | 6388 |
| `secret_02_password` | hardcoded-secret | açık | 0 | 0 | 1 | 0 | 5443 |
| `secret_03_aws` | hardcoded-secret | açık | 0 | 0 | 2 | 0 | 5680 |
| `pickle_01_loads` | insecure-deserialization | açık | 1 | 0 | 0 | 0 | 5648 |
| `yaml_01_unsafe` | insecure-deserialization | açık | 0 | 0 | 1 | 0 | 5696 |
| `flask_01_debug` | misconfiguration | açık | 1 | 0 | 0 | 1 | 6143 |
| `tls_01_verify_false` | misconfiguration | açık | 1 | 0 | 0 | 0 | 5813 |
| `path_01_open` | path-traversal | açık | 0 | 0 | 1 | 0 | 5739 |
| `tmp_01_mktemp` | race-condition | açık | 0 | 0 | 1 | 0 | 5617 |
| `sqli_01_concat` | sql-injection | açık | 1 | 0 | 0 | 0 | 6023 |
| `sqli_02_format` | sql-injection | açık | 1 | 0 | 0 | 1 | 6258 |
| `ssrf_01_requests` | ssrf | açık | 0 | 0 | 1 | 0 | 5522 |
| `crypto_01_md5` | weak-crypto | açık | 1 | 0 | 0 | 0 | 5742 |
| `xss_01_marksafe` | xss | açık | 1 | 0 | 0 | 0 | 5674 |
| `xxe_01_lxml` | xxe | açık | 0 | 0 | 1 | 0 | 6533 |
| `clean_03_subprocess_list` | command-injection | temiz | 0 | 0 | 0 | 0 | 5397 |
| `clean_02_env_secret` | hardcoded-secret | temiz | 0 | 0 | 0 | 0 | 5433 |
| `clean_06_yaml_safe` | insecure-deserialization | temiz | 0 | 0 | 0 | 0 | 5475 |
| `clean_04_refactor` | none | temiz | 0 | 0 | 0 | 0 | 5403 |
| `clean_07_docstring` | none | temiz | 0 | 0 | 0 | 0 | 5474 |
| `clean_08_logging` | none | temiz | 0 | 0 | 0 | 0 | 5759 |
| `clean_01_param_sql` | sql-injection | temiz | 0 | 0 | 0 | 0 | 5376 |
| `clean_05_hashlib_sha256` | weak-crypto | temiz | 0 | 0 | 0 | 0 | 5765 |

## Yöntem

- Eşleşme toleransı: dosya aynı + satır ±2
- Ölçülen katman: `app/semgrep_scanner.scan_diff` (Semgrep + diff-satır filtresi)
- LLM açıklama katmanı dahil değil (o bulur değil, açıklar)
- Sınırlar için `benchmarks/README.md`

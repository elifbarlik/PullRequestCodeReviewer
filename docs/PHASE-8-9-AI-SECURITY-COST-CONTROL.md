# Faz 8 + Faz 9 — AI Güvenliği ve Cost Control

Bu PR yalnızca yol haritasındaki iki kapsamı uygular.

## Faz 8 — AI / Gemini güvenliği

- Gemini'ye giden Semgrep bulguları ve diff **güvenilmeyen veri** olarak açıkça tanımlanır.
- Diff içindeki prompt-injection benzeri metinler talimat kabul edilmez.
- Detection = Semgrep, Explanation = Gemini ayrımı korunur.
- Gemini yeni vulnerability/finding/severity/file/line icat etmemelidir.
- Final güvenlik sonucu severity ve konumu yalnızca Semgrep girdisinden alır.
- Gemini yalnızca açıklama ve öneri üretir.

## Faz 9 — Cost control

Mevcut cost-control katmanı korunur ve ölçümler testlerle sabitlenir:

- LLM_CACHE_ENABLED
- LLM_CACHE_TTL_SECONDS
- LLM_CACHE_MAX_ENTRIES
- LLM_MAX_OUTPUT_TOKENS
- GEMINI_MODEL
- request başına input/output token ve yaklaşık maliyet
- cache hit ve LLM call sayısı
- cache key SHA-256 ile üretilir; prompt/source kodu loglanmaz veya key içinde açıkça tutulmaz.

Usage log'a yalnızca operasyonel metrikler yazılır. Full source code, full diff,
API key veya token değeri cost-control log/metric alanlarına eklenmez.

## Kapsam dışı

- Dashboard
- Landing page
- Marketplace
- Yeni LLM sağlayıcısı
- Gemini model değişimi
- Yeni Semgrep ruleset/kural tasarımı
- Authentication/tenant isolation redesign
- Billing/paid plan

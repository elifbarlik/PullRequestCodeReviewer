# Faz 7 — GitHub PR File Pagination

Bu fazın amacı Faz 6'da özellikle ertelenen **GitHub PR file-list pagination** problemini çözmektir.

## Kapsam

GitHub PR files endpoint'i tek response ile sınırlı değildir. Client artık:

1. İlk istekte `per_page=100` kullanır.
2. Response içindeki GitHub `Link` header'ının `rel="next"` bağlantısını takip eder.
3. Sonraki sayfaları aynı şekilde toplar.
4. `next` bağlantısı kalmadığında tek bir birleşik dosya listesi döndürür.

Böylece 100'den fazla dosya değiştiren PR'larda yalnızca ilk sayfanın analiz edilmesi engellenir.

## Değişen bileşen

- `app/github_client.py`
  - `GitHubAppClient.get_pr_files()` pagination-aware hale getirildi.
  - `get_pr_bundle()` aynı sözleşmeyi kullanmaya devam eder; başka bir çağırma akışı eklenmedi.

## Test kapsamı

- Birden fazla sayfanın birleştirilmesi.
- `next` bağlantısı yoksa tek sayfada durma.
- Beklenmeyen API payload'ının reddedilmesi.

## Faz 7 çıkış kriterleri

- [x] PR file-list endpoint'inde `per_page=100` korunuyor.
- [x] `rel="next"` pagination takip ediliyor.
- [x] Tüm sayfalar tek dosya listesinde birleştiriliyor.
- [x] Pagination için unit testleri eklendi.
- [x] `get_pr_bundle()` mevcut akışı bozmadan pagination-aware client'ı kullanıyor.

## Kapsam dışı

Bu fazda özellikle yapılmayanlar:

- Yeni scanner veya Semgrep ruleset'i.
- Gemini model/prompt redesign.
- Dashboard veya landing page.
- Marketplace/launch değişiklikleri.
- Cost-control mimarisinin yeniden tasarımı.
- Authentication / tenant-isolation redesign.
- PR review lifecycle'ın yeni bir mimariye taşınması.

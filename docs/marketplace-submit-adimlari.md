# GitHub Marketplace Submit Rehberi

Bu belge Faz 3 — Marketplace Listing için repo tarafında hazırlanan materyali ve GitHub tarafında manuel yapılması gereken adımları ayırır.

## 1. Repo tarafı hazır

- [x] MIT lisansı
- [x] PRIVACY.md
- [x] SUPPORT.md
- [x] Marketplace listing metni: docs/marketplace-listing.md
- [x] 200×200 SVG logo kaynağı: static/secpr-tr-logo.svg
- [x] Landing page'de App install bağlantısı
- [x] Production homepage: Fly.io üzerinde /
- [ ] Faz 4 sonrası gerçek inline-review ekran görüntüsü

## 2. GitHub App Settings

- [ ] Make public ile uygulamayı public yap
- [ ] Homepage URL → https://pr-reviewer-quiet-fire-1218.fly.dev/
- [ ] Privacy URL → https://github.com/elifbarlik/PullRequestCodeReviewer/blob/main/PRIVACY.md
- [ ] Support URL → https://github.com/elifbarlik/PullRequestCodeReviewer/issues
- [ ] Webhook URL → production /webhook endpoint'i
- [ ] Webhook secret ve production environment değişkenlerinin eşleştiğini doğrula
- [ ] App logo → static/secpr-tr-logo.svg dosyasından üretilen 200×200 logo

## 3. Marketplace Listing

- [ ] docs/marketplace-listing.md içeriğini Marketplace formuna aktar
- [ ] App name: SecPR-TR
- [ ] Ücretsiz planı seç
- [ ] Kategori ve açıklamaları doldur
- [ ] En az bir gerçek ürün ekran görüntüsü ekle
- [ ] Faz 4 tamamlandıktan sonra gerçek PR inline-review ekran görüntüsünü ekle
- [ ] Install / Homepage / Privacy / Support linklerinin açıldığını doğrula

## 4. Submit öncesi teknik doğrulama

Production üzerinde:

- [ ] GET /health → status: ok
- [ ] GET / açılıyor
- [ ] GET /dashboard açılıyor
- [ ] /webhook imza doğrulaması çalışıyor
- [ ] Gerçek bir PR opened veya synchronize event'i analiz başlatıyor
- [ ] Semgrep CLI container içinde mevcut
- [ ] Gemini yapılandırılmış
- [ ] Neon/PostgreSQL bağlantısı sağlıklı

## 5. Submit kararı

Faz 3 repo hazırlığı kod tarafında tamamlanabilir; Marketplace'e gerçek submit Faz 4 tamamlandıktan sonra yapılmalıdır.

Bunun nedeni: listing materyalinin artık canlı /health, gerçek PR çıktısı ve inline review ekran görüntüsüyle desteklenebilmesi.

## 6. Son kontrol listesi

Marketplace formunu göndermeden önce şu üç bağlantı grubunu doğrula:

1. Production homepage / health
2. Gerçek PR inline-review örneği
3. Privacy + Support sayfaları

Bu doğrulamalar tamamlanmadan Marketplace submit yapılmamalıdır.
# GitHub Marketplace Submit Rehberi

Bu belge Faz 3 — Marketplace Listing için repo tarafında hazırlanan materyali ve GitHub tarafında manuel yapılması gereken adımları ayırır.

## 1. Repo tarafı hazır

- [x] MIT lisansı
- [x] PRIVACY.md
- [x] SUPPORT.md
- [x] Marketplace listing metni: docs/marketplace-listing.md
- [x] Logo kaynak tasarımı: static/secpr-tr-logo.svg
- [x] Landing page'de App install bağlantısı
- [x] Production homepage: Fly.io üzerinde /
- [ ] Faz 4 sonrası gerçek inline-review ekran görüntüsü
- [ ] GitHub Marketplace için logo kaynağını 200×200 PNG/JPG/GIF olarak dışa aktar
- [ ] Marketplace feature-card görselini hazırla (965×482)

## 2. GitHub App Settings

- [ ] Make public ile uygulamayı public yap
- [ ] Homepage URL → https://pr-reviewer-quiet-fire-1218.fly.dev/
- [ ] Privacy URL → https://github.com/elifbarlik/PullRequestCodeReviewer/blob/main/PRIVACY.md
- [ ] Support URL → https://github.com/elifbarlik/PullRequestCodeReviewer/issues
- [ ] Webhook URL → production /webhook endpoint'i
- [ ] Webhook secret ve production environment değişkenlerinin eşleştiğini doğrula
- [ ] App logo → 200×200 PNG/JPG/GIF olarak dışa aktarılan logo
- [ ] Badge background color seç

## 3. Marketplace Listing

- [ ] docs/marketplace-listing.md içeriğini Marketplace formuna aktar
- [ ] App name: SecPR-TR
- [ ] Ücretsiz planı seç
- [ ] Kategori ve açıklamaları doldur
- [ ] Feature card görselini ekle
- [ ] En az bir gerçek ürün ekran görüntüsü ekle
- [ ] Faz 4 tamamlandıktan sonra gerçek PR inline-review ekran görüntüsünü ekle
- [ ] Tüm ekran görüntülerini aynı boyutta ve en az 1200px genişlikte hazırla
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

Bunun nedeni: listing materyalinin canlı /health, gerçek PR çıktısı ve inline review ekran görüntüsüyle desteklenebilmesi.

## 6. Son kontrol listesi

Marketplace formunu göndermeden önce şu üç bağlantı grubunu doğrula:

1. Production homepage / health
2. Gerçek PR inline-review örneği
3. Privacy + Support sayfaları

Bu doğrulamalar tamamlanmadan Marketplace submit yapılmamalıdır.

### GitHub'ın güncel görsel kuralları

GitHub Marketplace logo için en az 200×200 piksel özel bir görsel ister; GitHub App badge'i için PNG, JPG veya GIF altında 1 MB desteklenir. Marketplace listing ekran görüntülerinin aynı boyutta olması ve en az 1200 px genişlikte hazırlanması önerilir.

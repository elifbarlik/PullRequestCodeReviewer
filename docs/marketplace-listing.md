# SecPR-TR — GitHub Marketplace Listing

## Short description

Türkçe odaklı, güvenlik odaklı GitHub Pull Request inceleme asistanı. Semgrep bulgularını Gemini destekli açıklamalarla birleştirir ve sonucu PR'e geri yazar.

## Full description

SecPR-TR, GitHub Pull Request'lerini güvenlik açıkları açısından otomatik inceleyen bir GitHub App'tir.

Uygulama iki katmanlı bir analiz akışı kullanır:

1. Semgrep değişen kodu bilinen güvenlik pattern'leri için tarar.
2. Gemini bulunan güvenlik bulgularını geliştirici dostu, Türkçe açıklamalarla yorumlar.
3. Mümkün olduğunda bulgular doğrudan ilgili PR satırına inline review olarak eklenir; diff dışında kalan bulgular özet yorumunda gösterilir.
4. Analiz ve kalite metrikleri PostgreSQL/Neon üzerinde operasyonel metadata olarak tutulabilir.

### Neden SecPR-TR?

- Güvenlik odaklı: genel kod kalitesi yerine önceliği güvenlik bulgularına verir.
- Türkçe açıklamalar: bulunan riskleri geliştiricinin anlayabileceği öğretici biçimde açıklar.
- Hibrit analiz: deterministik statik analiz + LLM tabanlı açıklama.
- Diff-satır odaklı: mümkün olduğunda yalnızca PR'de değişen satırlara yorum bırakır.
- GitHub App modeli: kurulum bazlı GitHub yetkilendirmesi ve webhook doğrulaması kullanır.

### Analiz akışı

GitHub PR → webhook → GitHub API → Semgrep + Gemini → inline review / özet → kullanım metrikleri.

### Veri ve gizlilik

SecPR-TR kaynak kodunu kalıcı olarak saklamayı amaçlamaz. PR diff'i ve değişen dosya içeriği analiz sırasında işlenir; kalıcı veri katmanında kurulum ve kullanım/finding metadata'sı tutulur.

Güncel veri işleme ayrıntıları için:

- PRIVACY.md
- SUPPORT.md

### GitHub izinleri

Uygulama yalnızca gerekli GitHub App izinlerini kullanır:

- Pull requests: Read & write
- Contents: Read-only
- Metadata: Read-only

### Harici servisler

- Semgrep: statik analiz motoru
- Google Gemini API: güvenlik bulgularını açıklamak için kullanılır
- PostgreSQL / Neon: kurulum, kullanım ve finding metadata'sı için opsiyonel kalıcı veri katmanı

### Mevcut kapsam ve sınırlar

SecPR-TR'nin community Semgrep ruleset'leri her güvenlik sınıfını yakalamaz. Benchmark sonuçları bu kapsam sınırlarını açıkça raporlar; araç, bulgu üretemediğinde bunu güvenli sonucu olarak yorumlamaz.

### Destek

Sorular ve hata bildirimleri GitHub Issues üzerinden alınır:

https://github.com/elifbarlik/PullRequestCodeReviewer/issues

## Listing bilgileri

- App name: SecPR-TR
- Category: Developer tools / Code security
- Launch model: Free
- Homepage: https://pr-reviewer-quiet-fire-1218.fly.dev/
- Privacy URL: https://github.com/elifbarlik/PullRequestCodeReviewer/blob/main/PRIVACY.md
- Support URL: https://github.com/elifbarlik/PullRequestCodeReviewer/issues
- Repository: https://github.com/elifbarlik/PullRequestCodeReviewer
- Install URL: https://github.com/apps/secpr-tr

> Marketplace submission'dan önce Homepage, Privacy ve Support URL'lerini GitHub App ayarlarında doğrulayın. Gerçek ekran görüntüsü ve inline-review demosu Faz 4 tamamlandıktan sonra eklenmelidir.
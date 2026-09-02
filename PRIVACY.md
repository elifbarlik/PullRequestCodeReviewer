# Gizlilik Politikası — SecPR-TR

**Son güncelleme:** 2 Eylül 2026

SecPR-TR, GitHub pull request'lerini güvenlik açıkları için otomatik inceleyen
bir GitHub App'idir. Bu politika, uygulamanın hangi verilere eriştiğini, bu
verileri nasıl işlediğini ve ne kadar sakladığını açıklar.

## 1. Erişilen veriler

Uygulama, yalnızca kurulduğu repolarda ve yalnızca aşağıdaki GitHub izinleriyle çalışır:

| İzin | Neden gerekli |
|------|---------------|
| **Pull requests: Read & write** | PR diff'ini okumak ve inceleme sonucunu yorum olarak yazmak |
| **Contents: Read-only** | Semgrep taraması için değişen dosyaların tam içeriğini okumak |
| **Metadata: Read-only** | GitHub App'lerin zorunlu temel izni |

Uygulama; özel anahtarlarınıza, diğer repolarınıza, GitHub Actions secret'larınıza
veya hesap ayarlarınıza **erişmez**.

## 2. Verilerin işlenmesi

Bir PR açıldığında veya güncellendiğinde:

1. Değişen dosyaların diff'i ve tam içeriği GitHub API'den okunur.
2. Diff'te **değişen satırlar** [Semgrep](https://semgrep.dev) ile statik olarak
   taranır (kod sunucuda geçici bir dizine yazılır, tarama biter bitmez silinir).
3. Bulunan güvenlik bulguları — kod bağlamıyla birlikte — açıklama üretmesi için
   Google Gemini API'ye (`google-genai`) gönderilir.
4. Üretilen Türkçe açıklama PR'e yorum olarak yazılır.

### Üçüncü taraf servisler

- **Google Gemini API** — bulgu açıklaması üretmek için diff parçaları ve Semgrep
  bulgu metinleri gönderilir. Google'ın veri işleme koşulları için:
  <https://ai.google.dev/gemini-api/terms>
- **Semgrep** — kurallar `semgrep.dev` registry'sinden indirilir (ilk çalıştırmada,
  sonra cache'lenir). Kodunuz Semgrep'e ait bir sunucuya **gönderilmez**; tarama
  tamamen SecPR-TR sunucusunda çalışır.

## 3. Saklanan veriler

Uygulama **kaynak kodunuzu saklamaz**. Diff ve dosya içerikleri yalnızca analiz
süresince bellekte/geçici dizinde tutulur ve işlem bitince silinir.

Kalıcı olarak saklanan tek şey, işletme amaçlı meta verilerdir:

| Veri | Amaç | Örnek |
|------|------|-------|
| Kurulum kaydı | Hangi hesap/organizasyonun uygulamayı kurduğu | `installation_id`, hesap adı, hesap tipi |
| Kullanım logu | Kullanım takibi ve maliyet analizi | repo adı, PR numarası, diff boyutu, bulgu sayısı, analiz süresi, tarih |
| Bulgu meta verisi | Doğruluk/kalite ölçümü | dosya yolu, satır no, Semgrep kural id'si, önem derecesi |

Bu kayıtlar **kod içermez** — yalnızca "hangi kuralın hangi dosyanın hangi
satırında tetiklendiği" bilgisini tutar.

## 4. Veri saklama süresi

- Kurulum ve ayar kayıtları: uygulama kurulu kaldığı sürece.
- Kullanım logları ve bulgu meta verileri: en fazla **90 gün**, ardından silinir.
- Uygulamayı bir hesaptan kaldırdığınızda, ilgili kurulum kaydı pasifleştirilir
  ve 30 gün içinde tüm meta verileriyle birlikte silinir.

## 5. Veri paylaşımı

Toplanan hiçbir veri satılmaz, kiralanmaz veya üçüncü taraflarla pazarlama
amacıyla paylaşılmaz. Veriler yalnızca yukarıda tanımlanan servis işlevi için
kullanılır.

## 6. Haklarınız

Verilerinizin silinmesini veya bir kopyasını talep etmek için
[destek kanalı](SUPPORT.md) üzerinden iletişime geçebilirsiniz. Talepler 30 gün
içinde karşılanır.

## 7. Değişiklikler

Bu politika değişirse, güncellenmiş sürüm bu dosyada yayımlanır ve "Son
güncelleme" tarihi değiştirilir.

## 8. İletişim

Sorularınız için: <https://github.com/elifbarlik/PullRequestCodeReviewer/issues>

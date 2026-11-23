# SecPR-TR

**Pull request'lerdeki güvenlik açıklarını bulan ve bulguları Türkçe, öğretici bir dille açıklayan bir GitHub App.**

SecPR-TR, bir repoya kurulduğunda açılan veya güncellenen her pull request'i otomatik inceler. Değişen kodu Semgrep ile tarar, bulunan sorunları Gemini ile Türkçe açıklatır ve sonucu doğrudan PR'ın ilgili satırlarına yorum olarak bırakır.

> Bu bir portföy projesidir ve canlı bir servis olarak yayında değildir. Yerelde çalıştırarak denenebilir. SecPR-TR yardımcı bir araçtır; insan kod incelemesinin veya profesyonel bir güvenlik denetiminin yerini tutmaz.

## İçindekiler

1. [Proje ne yapıyor?](#proje-ne-yapıyor)
2. [Bir PR nasıl incelenir?](#bir-pr-nasıl-incelenir)
3. [Neyi neden böyle yaptım?](#neyi-neden-böyle-yaptım)
4. [Kullanılan teknolojiler](#kullanılan-teknolojiler)
5. [Güvenlik önlemleri](#güvenlik-önlemleri)
6. [Veri modeli](#veri-modeli)
7. [Yerelde çalıştırma](#yerelde-çalıştırma)
8. [Endpoint'ler](#endpointler)
9. [Testler ve benchmark](#testler-ve-benchmark)
10. [Bilinen sınırlar](#bilinen-sınırlar)

## Proje ne yapıyor?

Bir geliştirici PR açtığında SecPR-TR şunları yapar:

1. GitHub'dan PR'ın diff'ini ve değişen dosyaların içeriğini çeker.
2. Değişen dosyaları **Semgrep** ile tarar. Sadece PR'da eklenen veya değiştirilen satırlardaki bulgular tutulur; dosyadaki eski sorunlar PR'a gürültü olarak yansımaz.
3. **Gemini** ile PR'ın kısa bir özetini çıkarır.
4. Semgrep'in bulduğu her sorun için Gemini'den Türkçe bir açıklama ister: neden risk, nasıl istismar edilir, nasıl düzeltilir.
5. Sonucu GitHub'a tek bir review olarak gönderir: genel özet ve bulguların bulunduğu satırlara iliştirilmiş satır-içi yorumlar.
6. Analizin metadatasını (süre, bulgu sayısı, Semgrep durumu, tahmini maliyet) PostgreSQL'e kaydeder. Dashboard bu veriyi gösterir.

Hedef kitle, güvenlik bilgisi henüz gelişmekte olan junior geliştiriciler ve küçük ekiplerdir. Bu yüzden çıktı sadece "burada SQL injection var" demez; sorunun neden önemli olduğunu ve nasıl düzeltileceğini kod örneğiyle anlatır.

## Bir PR nasıl incelenir?

```text
GitHub pull_request olayı
        |
        v
POST /webhook  ── imza (HMAC) ve X-GitHub-Delivery kontrolü
        |           hemen 202 döner, analiz arka planda sürer
        v
GitHub App kimlik doğrulama (JWT → installation token)
        |
        v
PR diff + dosya listesi + dosya içerikleri (paralel çekilir)
        |
        +-------------------------+
        |                         |
        v                         v
 Semgrep taraması          Gemini PR özeti
 (değişen dosyalar)        (paralel çalışır)
        |                         |
        v                         |
 Bulgular PR'da değişen            |
 satırlarla filtrelenir            |
        |                         |
        v                         |
 Gemini bulguları Türkçe           |
 açıklar (bulgu varsa)             |
        |                         |
        +------------+------------+
                     v
   GitHub review: özet + satır-içi yorumlar
                     |
                     v
   PostgreSQL: kullanım, bulgu ve review kaydı
```

Önemli ayrıntılar:

- **Webhook anında yanıtlanır.** GitHub webhook yanıtı için kısa bir süre bekler; analiz uzun sürdüğü için istek hemen `202` ile kapatılır ve iş FastAPI'nin arka plan görevlerinde çalışır.
- **Mükerrer teslimat atlanır.** GitHub aynı olayı tekrar gönderirse (`X-GitHub-Delivery`) aynı PR için ikinci kez analiz yapılmaz.
- **`synchronize` olayında tekrar yorum yazılmaz.** PR'a yeni commit eklendiğinde, aynı dosya ve satırda zaten yorum varsa ikincisi eklenmez.
- **Satır-içi yorum yerleştirilemezse özete düşer.** GitHub bir satıra yorum kabul etmezse bulgu kaybolmaz, özet yorumda yer alır.
- **Çok büyük PR'lar sınırlanır.** En fazla 60 dosya taranır ve yalnızca desteklenen uzantılar dikkate alınır. Taranmayan kısım için özet yorumda not düşülür.

## Neyi neden böyle yaptım?

### Tespit ve açıklama ayrı katmanlarda
Güvenlik açığı aramayı doğrudan bir dil modeline bırakmak hem kaçırılan açıklara (false negative) hem de olmayan sorunların bildirilmesine (false positive) yol açar. Bu yüzden iş ikiye bölündü:

- **Semgrep** neyin açık olduğuna karar verir. Kural tabanlıdır, aynı girdide hep aynı sonucu verir ve test edilebilir.
- **Gemini** sadece bulunmuş bir sorunu açıklar. Yeni açık "keşfetmez".

Böylece "bu bulgu nereden geldi?" sorusunun cevabı her zaman bir Semgrep kuralıdır.

### Tarama yapılamadıysa "güvenli" denmez
Semgrep çalışmazsa, zaman aşımına uğrarsa veya hiç dosya taranamazsa çıktı "sorun yok" olmaz; yorumda taramanın yapılamadığı açıkça belirtilir. Bir güvenlik aracının en tehlikeli hatası yanlış güven vermektir.

### Sadece değişen satırlar raporlanır
Semgrep tüm dosyayı tarar ama bulgular PR diff'indeki eklenen satırlarla kesiştirilir. Aksi halde bir dosyaya tek satır eklemek, dosyadaki eski bütün sorunları PR'a yığardı.

### Satır-içi yorum
Tek bir uzun yorum yerine, bulgu hangi satırdaysa oraya yorum yazılır. Yorumlar tek bir GitHub review isteğiyle toplu gönderilir; böylece her bulgu için ayrı API çağrısı yapılmaz ve geliştirici N ayrı bildirim almaz.

### GitHub App, kişisel token değil
Kimlik doğrulama GitHub App ile yapılır: uygulama kendi özel anahtarıyla imzalı bir JWT üretir, bunu installation başına kısa ömürlü bir erişim token'ıyla değiştirir. Token önbelleğe alınır ve süresi dolmadan yenilenir. Her müşteri sadece kendi kurulumuna erişebilir ve kullanıcıdan token istenmez.

### Semgrep ruleset'leri izin listesiyle sınırlı
Installation ayarlarından hangi Semgrep ruleset'inin kullanılacağı seçilebilir. Kullanıcıdan gelen değerin doğrudan Semgrep'e verilmesi komut enjeksiyonu veya SSRF yüzeyi açacağı için yalnızca önceden belirlenmiş registry kısayolları (`p/security-audit`, `p/secrets`, `p/owasp-top-ten`, `p/python` vb.) kabul edilir. Geçersiz veya boş seçimde varsayılan setle devam edilir.

### Veritabanı kritik yol değil
PostgreSQL kullanım kaydı, dashboard ve ayarlar için vardır ama PR yorumunun gönderilmesi ona bağlı değildir. Veritabanı yapılandırılmamış veya erişilemezse inceleme yine çalışır, sadece kayıt tutulmaz. Veri kaybı, servis kaybından daha az zararlıdır.

### Gecikme ve maliyet kontrolü
- GitHub API çağrıları (diff, PR detayı, dosya listesi, dosya içerikleri) paralel yapılır.
- Semgrep taraması ile Gemini özeti aynı anda çalışır.
- Gemini'ye açıklama isteği yalnızca bulgu varsa gönderilir.
- Aynı istek kısa sürede tekrarlanırsa süreli (TTL) ve sınırlı bir önbellek Gemini'yi yeniden çağırmaz.
- Gemini çıktısı için global bir token üst sınırı vardır ve "thinking" kapatılmıştır (`thinking_budget=0`); bu iş için hız ve maliyet, derin akıl yürütmeden daha önemlidir.
- Tarama süresi dosya sayısına göre ayarlanır (az dosya için kısa, çok dosya için uzun zaman aşımı).
- Installation başına saatlik PR analiz sınırı vardır (`HOURLY_PR_LIMIT`).

### JSON çıktısına karşı dayanıklı ayrıştırma
LLM'den gelen JSON bazen bozuk veya kod bloğu içinde gelir. `json_parser.py` birkaç kademeli yöntemle çözmeyi dener; başarı oranı `/stats` altında izlenir.

### Her kararın ölçülebilir olması
Semgrep katmanı için tekrarlanabilir bir benchmark var (aşağıda). Bu benchmark geliştirme sırasında gerçek hatalar da yakaladı: Windows'ta dosya yollarındaki ters eğik çizgi yüzünden tüm bulgular satır filtresinde elenmişti ve varsayılan ruleset seti fazla dardı.

## Kullanılan teknolojiler

| Alan | Teknoloji | Neden |
|---|---|---|
| Backend | Python 3.11, FastAPI, Uvicorn | Hızlı geliştirme, tip destekli istek/yanıt modelleri, arka plan görevleri |
| GitHub entegrasyonu | GitHub App, Webhook, REST API, PyJWT | Installation bazlı yetki; kişisel token gerekmez |
| Güvenlik analizi | Semgrep | Deterministik, çok dilli, topluluk kural setleri |
| Yapay zekâ | Google Gemini (`google-genai`) | Bulguları Türkçe açıklama; PR özeti |
| Veri | PostgreSQL, SQLAlchemy, Alembic | Çok kiracılı kayıt; şema değişiklikleri migration ile |
| Dashboard | HTML, CSS, JavaScript (`static/`) | Ek bir frontend derlemesi gerektirmeyen sade arayüz |
| Kimlik doğrulama | GitHub OAuth, imzalı oturum çerezi | Kullanıcı sadece kendi kurulumlarını görür |
| Gözlemlenebilirlik | JSON loglama, Sentry (isteğe bağlı), `/metrics` | Hata ve performans takibi |
| Hız sınırlama | slowapi | `/local-review` gibi uçların kötüye kullanımını önlemek |
| Paketleme | Docker, Docker Compose | Tek komutla uygulama + PostgreSQL |
| Test | pytest, SQLite (bellek içi) | Hızlı, harici servis gerektirmeyen testler |

## Güvenlik önlemleri

- **Webhook imzası:** `X-Hub-Signature-256` HMAC-SHA256 ile doğrulanır, karşılaştırma sabit zamanlıdır. Secret tanımlı değilse istek reddedilir.
- **Installation izolasyonu:** Dashboard, `/metrics`, `/stats` ve ayar uçları yalnızca giriş yapan kullanıcının erişebildiği installation verisini döner.
- **Korumalı uçlar:** `/local-review` kimlik doğrulama ister (`X-Admin-Token` veya GitHub oturumu) ve saatlik 10 istekle sınırlıdır. `/admin/*` uçları admin token ister.
- **OAuth:** `state` doğrulanır; oturum imzalı ve `HttpOnly` çerezde tutulur.
- **Hata detayları gizlenir:** İstemciye iç hata mesajları veya stack trace dönmez, ayrıntı sadece loglara yazılır.
- **Container:** Uygulama root olmayan bir kullanıcıyla çalışır.
- **Ruleset izin listesi:** Yukarıda açıklandığı gibi kullanıcı girdisi Semgrep komutuna doğrudan geçmez.

## Veri modeli

Tablolar `app/models.py` içinde, migration'lar `alembic/versions/` altında:

| Tablo | İçerik |
|---|---|
| `installations` | GitHub App kurulumları (kaldırılınca silinmez, pasif işaretlenir) |
| `repositories` | Kuruluma bağlı repolar |
| `settings` | Installation başına Semgrep ayarları |
| `review_runs` | Her PR analizinin durumu ve yaşam döngüsü |
| `usage_logs` | Süre, diff boyutu, Semgrep durumu, bulgu sayısı, adım süreleri, tahmini maliyet |
| `findings` | Bulunan sorunlar |
| `webhook_deliveries` | İşlenmiş teslimatlar (mükerrer koruma) |

## Yerelde çalıştırma

### Gereksinimler

- Docker ve Docker Compose
- Bir GitHub App (webhook ve repo erişimi için)
- Bir Google Gemini API anahtarı

### 1. Ortam değişkenlerini ayarla

```bash
cp .env.example .env
```

Zorunlu değerler:

| Değişken | Açıklama |
|---|---|
| `GEMINI_API_KEY` | Gemini API anahtarı |
| `GITHUB_APP_ID` | GitHub App kimliği |
| `GITHUB_APP_PRIVATE_KEY` veya `GITHUB_APP_PRIVATE_KEY_PATH` | App'in özel anahtarı |
| `GITHUB_WEBHOOK_SECRET` | Webhook imza secret'ı |
| `ADMIN_SECRET` | Admin uçları için token |

Dashboard girişi için `GITHUB_OAUTH_CLIENT_ID`, `GITHUB_OAUTH_CLIENT_SECRET` ve `GITHUB_OAUTH_SESSION_SECRET` gerekir. Callback adresi varsayılan olarak `/auth/github/callback` türetilir; farklıysa `GITHUB_OAUTH_REDIRECT_URI` verilir.

İsteğe bağlı: `HOURLY_PR_LIMIT`, `LOG_FORMAT`, `SENTRY_DSN`, `LLM_CACHE_*`, `LLM_MAX_OUTPUT_TOKENS`, `GEMINI_MODEL` (varsayılanlar `.env.example` içinde).

### 2. Başlat

```bash
docker compose up --build -d
docker compose logs -f pr-reviewer
```

Uygulama `http://localhost:8000` adresinde açılır. Durdurmak için `docker compose down` (yerel PostgreSQL verisini de silmek için `-v` ekle).

### 3. GitHub webhook'unu bağla

GitHub App'in webhook adresini `https://<adresin>/webhook` yap; `Pull request`, `Installation` ve `Installation repositories` olaylarını aç. İzinler: Pull requests (okuma/yazma), Contents (okuma), Metadata (okuma).

Yerelde GitHub'ın size ulaşabilmesi için bir tünel gerekir; `scripts/smee_proxy.py` smee.io üzerinden bunu sağlar:

```bash
python scripts/smee_proxy.py https://smee.io/<kanalın>
python scripts/get_installation_id.py     # kurulu installation'ları listeler
```

## Endpoint'ler

| Endpoint | Erişim | Açıklama |
|---|---|---|
| `GET /health` | Açık | Uygulama ve bağımlılık durumu |
| `POST /webhook` | İmzalı | GitHub olay alıcısı, `202` döner |
| `POST /local-review` | Admin token veya oturum | Diff'i doğrudan gönderip inceletme |
| `GET /metrics` | Oturum | Kullanıcının kendi kurulumlarının süre, maliyet ve hata metrikleri |
| `GET /stats` | Oturum | JSON ayrıştırma başarı oranı ve kullanıcının kurulumlarına ait sayaçlar |
| `GET /dashboard` | Oturum | Review geçmişi arayüzü |
| `GET /dashboard/api/summary`, `/reviews`, `/reviews/{id}` | Oturum | Dashboard verisi |
| `GET/PUT /installations/{id}/settings` | Oturum | Installation başına Semgrep ayarları |
| `GET /auth/github`, `/auth/github/callback`, `POST /auth/logout`, `GET /auth/me` | — | GitHub OAuth girişi |
| `POST /admin/logging-test`, `/admin/sentry-test` | Admin token | Log ve Sentry doğrulama |

`/local-review` gerçek dosya erişimi olmadığı için Semgrep'i çalıştıramaz; yalnızca LLM tabanlı bir inceleme yapar.

```bash
curl -X POST http://localhost:8000/local-review \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: $ADMIN_SECRET" \
  -d '{"diff_text": "--- a/x.py\n+++ b/x.py\n...", "review_types": ["short_summary", "security"]}'
```

## Testler ve benchmark

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

Testler GitHub ve Gemini'yi taklit eder, veritabanı testleri bellek içi SQLite kullanır; harici hesap gerekmez. Ağ veya Semgrep CLI isteyen testler işaretlidir ve ortam uygun değilse atlanır. Windows'ta emoji çıktısı hata verirse `PYTHONUTF8=1` ile çalıştır.

### Güvenlik benchmark'ı

Semgrep katmanı için küçük ve tekrarlanabilir bir benchmark vardır:

```bash
python scripts/run_benchmark.py
```

28 senaryo içerir: 20 açıklı (SQL injection, hardcoded secret, komut enjeksiyonu, path traversal, SSRF, zayıf kripto, `eval`, `pickle`, `yaml.load`, TLS doğrulamasını kapatma vb.) ve 8 temiz (false positive ölçümü). Son kayıtlı sonuç:

| Metrik | Değer |
|---|---|
| Recall | %52,4 |
| Precision | %100 |
| F1 | %68,8 |
| Temiz senaryolarda false positive | 0 |

Bu rakamlar yalnızca bu 28 senaryo ve açık kaynak Semgrep kuralları için geçerlidir; gerçek dünyadaki doğruluğu temsil etmez. Yöntem için [benchmarks/README.md](benchmarks/README.md), ayrıntılı sonuçlar için [benchmarks/RESULTS.md](benchmarks/RESULTS.md) dosyasına bakın.

## Bilinen sınırlar

- Semgrep kapsamı, kullanılan açık kaynak kural setlerine ve desteklenen dosya türlerine bağlıdır. Bulgu çıkmaması kodun güvenli olduğunu kanıtlamaz. Benchmark'ta kaçırılan sınıflar arasında bazı `os.system` birleştirmeleri, `mktemp`, `assert` ile yetkilendirme, XXE ve düz metin parola/AWS anahtarları var.
- Benchmark kasıtlı olarak küçüktür ve gerçek repolardaki açık dağılımını yansıtmaz.
- Gemini açıklamaları eksik veya hatalı olabilir; bir geliştirici tarafından kontrol edilmelidir.
- Analiz işleri uygulama içi arka plan görevleriyle yürür. Süreç çökerse iş kaybolabilir; her altyapı hatasında tam bir kez çalışma garantisi yoktur.
- Gemini ve GitHub API kullanılabilirliği uygulamanın kontrolü dışındadır.

## Diğer dosyalar

- [Gizlilik politikası](PRIVACY.md)
- [Destek ve hata bildirimi](SUPPORT.md)
- [MIT Lisansı](LICENSE)

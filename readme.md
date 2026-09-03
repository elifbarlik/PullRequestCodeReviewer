# SecPR-TR

**Türkçe, güvenlik odaklı pull request incelemesi yapan bir GitHub App.**

Bir PR açıldığında veya güncellendiğinde otomatik devreye girer, değişen kodu
güvenlik açıkları için tarar ve her bulguyu junior geliştiricinin anlayacağı
**Türkçe, öğretici** bir yorumla **ilgili kod satırına** iliştirir; genel bir
özet de PR'e review olarak eklenir.

## Neden var?

AI destekli PR review pazarı kalabalık (CodeRabbit, GitHub Copilot code review,
Greptile...) ama hepsi İngilizce çıktı verir ve genel amaçlıdır. SecPR-TR dar bir
boşluğa oturur: **Türkiye'deki takımlar ve junior geliştiriciler için ana dilde,
güvenlik odaklı** inceleme.

## Hibrit mimari — neden salt-LLM değil?

Sadece LLM'e "bu diff'te güvenlik açığı var mı?" diye sormak, false positive ve
false negative riski taşır. SecPR-TR bunun yerine işi ikiye böler:

1. **Semgrep** (deterministik statik analiz) diff'te *değişen satırlarda*
   bilinen açık pattern'lerini bulur — SQL injection, hardcoded secret, path
   traversal, SSRF, komut enjeksiyonu vb. Bulgunun *var olup olmadığına* ve
   *önem derecesine* Semgrep karar verir.
2. **Gemini** (google-genai) bu bulguları **açıklar** — açık aramaz.
   Her bulgu için: neden risk, somut olarak nasıl istismar edilir, nasıl
   düzeltilir (kod örneğiyle). Türkçe ve öğretici tonda.

Gemini çağrısı başarısız olsa bile gerçek Semgrep bulguları asla kaybolmaz —
ham Semgrep mesajıyla raporlanır. Semgrep hiç çalışamazsa (CLI yok, ağ yok, API
hatası) sonuç **asla "güvenli" denmez**; şeffaf bir "tarama yapılamadı" uyarısı
verilir.

## Mimari bileşenler

| Modül | Sorumluluk |
|-------|-----------|
| `app/semgrep_scanner.py` | Semgrep'i çalıştırır, bulguları PR'de gerçekten değişen satırlarla sınırlar (`diff_utils.parse_added_lines`) |
| `app/reviewer.py` | Semgrep bulgularını Türkçe açıklamaya çevirir (`explain_security_findings`); `security_scan` verilmezse eski LLM-only `SECURITY_REVIEW`'a düşer; iki aşamalı analiz (özet → detay); token/diff kırpma |
| `app/main.py` → `_build_inline_comments` | Her bulguyu, satırı diff'te varsa GitHub review API'sinin inline yorumuna çevirir; yerleştirilemeyenler özet yoruma düşer. `create_review` tek istekte özet + tüm inline yorumları gönderir; `synchronize`'da `_INLINE_MARKER` ile mükerrer yorum atlanır |
| `app/json_parser.py` | LLM yanıtını 5 katmanlı fallback ile parse eder (direkt JSON → markdown blok → yaygın hata düzeltme → regex → şablon) |
| `app/github_client.py` | GitHub App kimlik doğrulama: RS256 JWT → installation access token; PAT kullanılmaz |
| `app/prompts.py` | Türkçe, junior-dostu prompt şablonları (`SECURITY_EXPLAIN`, `SHORT_SUMMARY`, ...) |
| `app/db.py` / `app/models.py` / `app/repository.py` | Çok kiracılı veri katmanı: kurulum kayıtları, kullanım logları, güvenlik bulguları (Faz 2b) |
| `app/main.py` | FastAPI uygulaması + webhook event yönlendirmesi |

## Veri katmanı (Faz 2b)

`DATABASE_URL` tanımlıysa şu tablolar tutulur:

- **`installations`** — her GitHub App kurulumu (`installation_id` → hesap/org, `is_active` soft-delete)
- **`usage_logs`** — her PR analizi (`installation_id`, diff boyutu, Semgrep durumu, bulgu sayısı, süre — Gemini maliyet kalibrasyonu için)
- **`findings`** — her güvenlik bulgusu (ileride false-positive oranı metriği için)
- **`settings`** — installation bazlı ayarlar: taramanın açık/kapalı olması ve hangi Semgrep ruleset'lerinin çalışacağı (Faz 2c)

### Installation ayarları (Faz 2c)

Her installation için güvenlik taramasını kapatabilir veya çalışacak Semgrep
ruleset'lerini seçebilirsiniz. Henüz dashboard yok (Faz 5); ayarlar iki endpoint
ile yönetilir:

```bash
# Oku (ayar yoksa varsayılan: enabled=true, semgrep_configs=null → p/security-audit + p/secrets)
curl http://localhost:8000/installations/12345678/settings

# Taramayı kapat
curl -X PUT http://localhost:8000/installations/12345678/settings \
  -H "Content-Type: application/json" -d '{"enabled": false}'

# Belirli ruleset'ler (yalnızca izinli olanlar; geçersizler elenir)
curl -X PUT http://localhost:8000/installations/12345678/settings \
  -H "Content-Type: application/json" -d '{"semgrep_configs": ["p/python", "p/secrets"]}'

# Varsayılan ruleset'e dön
curl -X PUT http://localhost:8000/installations/12345678/settings \
  -H "Content-Type: application/json" -d '{"reset_configs": true}'
```

İzinli ruleset'ler `semgrep_scanner.ALLOWED_SEMGREP_CONFIGS` içinde tanımlıdır
(keyfi dosya yolu / URL kabul edilmez — komut enjeksiyonu / SSRF yüzeyi).
`DATABASE_URL` yoksa bu endpoint'ler `503` döner; tarama her installation için
varsayılan ayarla çalışır.

**`DATABASE_URL` boşsa veri katmanı tamamen devre dışı kalır** ve uygulama
(webhook analizi, `/local-review`, testler) DB olmadan çalışır. DB geçici olarak
düşse bile PR yorumu gönderilmeye devam eder — loglama hataları yutulur.

## Kurulum

### 1. GitHub App kaydı

GitHub → Settings → Developer settings → GitHub Apps → New GitHub App:

- **Webhook URL**: `https://<alan-adınız>/webhook`
- **Webhook secret**: rastgele bir değer (`python -c "import secrets; print(secrets.token_hex(32))"`)
- **İzinler** (minimum): Pull requests → Read & write, Contents → Read-only
- **Events**: Pull request, Installation, Installation repositories
- Private key üret ve `.pem` dosyasını indir

### 2. Ortam değişkenleri

`.env.example`'ı `.env` olarak kopyalayıp doldurun:

```
GEMINI_API_KEY=...
GITHUB_APP_ID=...
GITHUB_APP_PRIVATE_KEY_PATH=/path/to/app.pem      # veya GITHUB_APP_PRIVATE_KEY (tek satır)
GITHUB_WEBHOOK_SECRET=...
DATABASE_URL=                                      # boş → DB devre dışı; compose otomatik doldurur
```

### 3. Çalıştırma — Docker Compose (önerilen)

```bash
docker-compose up -d          # uygulama + PostgreSQL
docker-compose logs -f pr-reviewer
```

`http://localhost:8000` üzerinde çalışır. Postgres otomatik ayağa kalkar ve
tablolar açılışta oluşturulur.

### 4. Yerel geliştirme

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Webhook'ları yerelde test etmek için:

```bash
python scripts/smee_proxy.py https://smee.io/<kanalınız>   # webhook tüneli
python scripts/get_installation_id.py                       # kurulu installation'ları listele
```

## API Endpoint'leri

| Endpoint | Açıklama |
|----------|----------|
| `GET /health` | Sağlık kontrolü |
| `POST /webhook` | GitHub App webhook alıcısı (imza doğrulaması zorunlu) |
| `POST /local-review` | Diff'i doğrudan gönderip analiz ettirme — Semgrep çalıştırılamaz (gerçek dosya erişimi yok), LLM-only güvenlik incelemesine düşer |
| `GET /stats` | JSON parser başarı oranı + (DB açıksa) kurulum/analiz sayaçları |
| `GET/PUT /installations/{id}/settings` | Installation bazlı Semgrep ayarları (Faz 2c) — DB açıksa |

```bash
curl -X POST http://localhost:8000/local-review \
  -H "Content-Type: application/json" \
  -d '{"diff_text": "--- a/x.py\n+++ b/x.py\n...", "review_types": ["short_summary", "security"]}'
```

## Test

```bash
pytest tests/ -v
```

88 test fonksiyonu. Ağ erişimi yoksa (gerçek Gemini çağrısı) veya `semgrep` CLI
kurulu değilse ilgili testler otomatik atlanır — bkz. `tests/conftest.py`
marker'ları (`network`, `requires_semgrep`). Veri katmanı testleri SQLite
in-memory kullanır, Postgres gerektirmez.

```bash
pytest tests/ --cov=app --cov-report=html
```

## Katkı ve destek

- **Lisans:** [MIT](LICENSE)
- **Gizlilik:** [PRIVACY.md](PRIVACY.md)
- **Destek / hata bildirimi:** [SUPPORT.md](SUPPORT.md) → [Issues](https://github.com/elifbarlik/PullRequestCodeReviewer/issues)


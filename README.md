# 🤖 PR Code Reviewer

Otomatik Pull Request analizi ve kod incelemesi için FastAPI tabanlı uygulama. GitHub PR'lerinizi LLM (Large Language Model) ile otomatik olarak analiz eder ve akıllı yorumlar yapar.

## ✨ Özellikler

- 🔍 **Otomatik PR Analizi**: GitHub webhook ile PR açıldığında otomatik review
- 🐛 **Bug Detection**: Potansiyel hataları tespit eder
- 🔒 **Security Analysis**: Güvenlik açıklarını kontrol eder
- ⚡ **Performance Review**: Performans iyileştirme önerileri
- 📝 **Code Summary**: Değişikliklerin özetini çıkarır
- 🔐 **Webhook Security**: HMAC SHA-256 signature doğrulaması
- 🚀 **Fast & Lightweight**: FastAPI ile yüksek performans

## 🏗️ Mimari

```
┌─────────────────┐
│   GitHub PR     │
└────────┬────────┘
         │ Webhook
         ▼
┌─────────────────┐      ┌──────────────┐
│  FastAPI Server │─────>│ Gemini LLM   │
│  /webhook       │      │ (Code Review)│
└────────┬────────┘      └──────────────┘
         │
         ▼
┌─────────────────┐
│  GitHub API     │
│  Post Comment   │
└─────────────────┘
```

## 📦 Kurulum

### 1. Repository'yi Klonlayın

```bash
git clone https://github.com/elifbarlik/PullRequestCodeReviewer.git
cd PullRequestCodeReviewer
```

### 2. Virtual Environment Oluşturun

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

### 3. Bağımlılıkları Yükleyin

```bash
pip install -r requirements.txt
```

### 4. Environment Variables Yapılandırın

```bash
cp .env.example .env
```

`.env` dosyasını düzenleyin:

```env
# GitHub Personal Access Token
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx

# GitHub Webhook Secret
GITHUB_WEBHOOK_SECRET=your_secret_here

# Google Gemini API Key
GOOGLE_API_KEY=AIxxxxxxxxxxxxxxxxxxxxx
```

#### GitHub Token Oluşturma

1. https://github.com/settings/tokens
2. "Generate new token (classic)"
3. İzinler: `repo`, `write:discussion`

#### Google Gemini API Key

1. https://makersuite.google.com/app/apikey
2. API key oluşturun

## 🚀 Kullanım

### Manuel Test (Local Review)

```bash
# Uygulamayı başlat
uvicorn app.main:app --reload --port 8000
```

**POST /local-review** endpoint'ine diff gönderin:

```bash
curl -X POST http://localhost:8000/local-review \
  -H "Content-Type: application/json" \
  -d '{
    "diff_text": "diff --git a/file.py ...",
    "review_types": ["bug_detection", "security"]
  }'
```

### GitHub PR Review (Manuel)

**POST /github-review** endpoint'i kullanarak belirli bir PR'ı analiz edin:

```bash
curl -X POST http://localhost:8000/github-review \
  -H "Content-Type: application/json" \
  -d '{
    "owner": "elifbarlik",
    "repo": "test-repo",
    "pr_number": 1,
    "review_types": ["short_summary", "bug_detection", "security"]
  }'
```

### Otomatik Webhook Modu

GitHub webhook'ları ile PR açıldığında otomatik review yapılır.

**Detaylı kurulum için:** [WEBHOOK_SETUP.md](WEBHOOK_SETUP.md)

**Hızlı Başlangıç:**

1. **Uygulamayı başlatın:**
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

2. **Ngrok ile localhost'u açın:**
```bash
ngrok http 8000
```

3. **GitHub webhook ekleyin:**
   - Repository → Settings → Webhooks → Add webhook
   - URL: `https://your-ngrok-url.app/webhook`
   - Content type: `application/json`
   - Secret: `.env` dosyanızdaki `GITHUB_WEBHOOK_SECRET`
   - Events: `Pull requests`

4. **Test PR açın!** 🎉

## 🧪 Test

### Webhook Testi

```bash
python test_webhook.py
```

Bu script:
- ✅ Signature doğrulamasını test eder
- ✅ Farklı event tiplerini test eder
- ✅ Geçersiz signature'ları test eder
- ✅ Interaktif test menüsü sunar

### Unit Tests

```bash
pytest tests/
```

## 📋 API Endpoints

| Endpoint | Method | Açıklama |
|----------|--------|----------|
| `/health` | GET | Health check |
| `/local-review` | POST | Manuel diff analizi |
| `/github-review` | POST | GitHub PR'den diff al ve analiz et |
| `/webhook` | POST | GitHub webhook handler (otomatik) |

## 🔒 Güvenlik

### Webhook Signature Doğrulaması

Her webhook isteği HMAC SHA-256 ile doğrulanır:

```python
def verify_github_signature(payload_body: bytes, signature_header: str) -> bool:
    """GitHub webhook signature'ını doğrula"""
    mac = hmac.new(
        webhook_secret.encode(),
        msg=payload_body,
        digestmod=hashlib.sha256
    )
    return hmac.compare_digest(calculated, expected)
```

Avantajları:
- ✅ Sadece GitHub'dan gelen istekler kabul edilir
- ✅ Man-in-the-middle saldırıları engellenir
- ✅ Timing attack'lara karşı korumalı

## 📊 Review Türleri

### 1. Short Summary
```json
{
  "summary": "Added authentication middleware",
  "severity": "medium",
  "type": "feature"
}
```

### 2. Bug Detection
```json
{
  "has_bugs": true,
  "issues": [
    {
      "file": "app.py",
      "line": 42,
      "severity": "high",
      "description": "Potential null pointer exception",
      "suggestion": "Add null check before accessing property"
    }
  ],
  "overall_risk": "medium"
}
```

### 3. Security Analysis
```json
{
  "has_security_issues": true,
  "vulnerabilities": [
    {
      "file": "auth.py",
      "line": 15,
      "risk": "high",
      "recommendation": "Use bcrypt for password hashing"
    }
  ],
  "security_level": "vulnerable"
}
```

### 4. Performance Review
```json
{
  "suggestions": [
    {
      "file": "query.py",
      "line": 28,
      "issue": "N+1 query problem",
      "recommendation": "Use select_related() to optimize queries"
    }
  ],
  "optimization_potential": "high"
}
```

## 📁 Proje Yapısı

```
PullRequestCodeReviewer/
├── app/
│   ├── main.py              # FastAPI uygulaması
│   ├── github_client.py     # GitHub API client
│   ├── reviewer.py          # LLM review logic
│   └── prompts.py           # LLM prompt templates
├── tests/
│   └── test_*.py            # Unit tests
├── .env.example             # Environment variables template
├── requirements.txt         # Python dependencies
├── test_webhook.py          # Webhook test script
├── WEBHOOK_SETUP.md         # Detaylı webhook kurulum rehberi
└── README.md                # Bu dosya
```

## 🛠️ Teknolojiler

- **FastAPI**: Modern, hızlı web framework
- **Google Gemini**: LLM ile kod analizi
- **PyGithub**: GitHub API client
- **Pydantic**: Data validation
- **Uvicorn**: ASGI server
- **Ngrok**: Localhost tunneling

## 🔄 Workflow

1. **PR Açılır** → GitHub webhook tetiklenir
2. **Webhook POST** → FastAPI `/webhook` endpoint'ine gelir
3. **Signature Verify** → HMAC SHA-256 doğrulaması
4. **Get PR Diff** → GitHub API'den değişiklikler alınır
5. **LLM Analysis** → Gemini ile kod analizi yapılır
6. **Post Comment** → GitHub PR'ye otomatik yorum eklenir

## 🐛 Sorun Giderme

### Webhook Çalışmıyor

- Ngrok çalışıyor mu? (`ngrok http 8000`)
- Uygulama çalışıyor mu? (`/health` endpoint'ini kontrol edin)
- GitHub webhook "Active" mi?

### 403 Forbidden

- `GITHUB_WEBHOOK_SECRET` doğru mu?
- GitHub webhook secret'ı doğru girilmiş mi?

### 401 Unauthorized

- `GITHUB_TOKEN` geçerli mi?
- Token'ın gerekli izinleri var mı? (`repo`, `write:discussion`)

### Bot Yorum Yapmıyor

- Terminal loglarını kontrol edin
- `GOOGLE_API_KEY` doğru mu?
- GitHub token write izni var mı?

## 📈 Gelecek Özellikler

- [ ] Code suggestion'lar (inline comments)
- [ ] PR approval/request changes automation
- [ ] Custom review rules (YAML config)
- [ ] Multi-file context awareness
- [ ] Database için review history
- [ ] Dashboard UI
- [ ] Slack/Discord entegrasyonu

## 🤝 Katkıda Bulunma

1. Fork edin
2. Feature branch oluşturun (`git checkout -b feature/amazing`)
3. Commit edin (`git commit -m 'Add amazing feature'`)
4. Push edin (`git push origin feature/amazing`)
5. Pull Request açın

## 📄 Lisans

MIT License - detaylar için [LICENSE](LICENSE) dosyasına bakın.

## 👤 Yazar

**Elif Barlık**
- GitHub: [@elifbarlik](https://github.com/elifbarlik)

## 🙏 Teşekkürler

- [FastAPI](https://fastapi.tiangolo.com/)
- [Google Gemini](https://ai.google.dev/)
- [GitHub API](https://docs.github.com/en/rest)
- [Ngrok](https://ngrok.com/)

---

⭐ Bu projeyi beğendiyseniz star vermeyi unutmayın!

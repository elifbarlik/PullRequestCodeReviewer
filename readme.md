# PR Code Reviewer

Otomatik kod review aracı. GitHub PR'lerini analiz edip AI-powered feedback veriyor.

## Özellikler

- **Lokal Review**: Diff metni gönderip analiz al
- **GitHub Entegrasyonu**: PR'den otomatik diff çek, yorum yap
- **Webhook Support**: GitHub webhook'tan PR event'lerini dinle
- **Çoklu Analiz**: Short summary, bug detection, security, performance
- **Robust Parser**: 5 fallback strategy ile JSON parsing
- **Token Management**: Otomatik diff truncation

## Kurulum

```bash
# Dependencies yükle
pip install -r requirements.txt

# .env dosyası oluştur
GITHUB_TOKEN=your_github_token
GEMINI_API_KEY=your_gemini_api_key
GITHUB_WEBHOOK_SECRET=your_webhook_secret  # (optional)
```

## Başlama

### 1. Lokal API

```bash
uvicorn app.main:app --reload
```

**Endpoints:**

```bash
# Health check
GET /health

# Lokal diff analiz et
POST /local-review
{
  "diff_text": "--- a/file.py\n+++ b/file.py\n...",
  "review_types": ["short_summary", "bug_detection"]
}

# GitHub PR'dan review
POST /github-review
{
  "owner": "username",
  "repo": "repo-name",
  "pr_number": 1
}

# Statistics
GET /stats
```

### 2. Docker

```bash
# Build
docker build -t pr-code-reviewer .

# Run
docker run -p 8000:8000 \
  -e GITHUB_TOKEN=xxx \
  -e GEMINI_API_KEY=yyy \
  pr-code-reviewer
```

### 3. GitHub Webhook

Repository settings → Webhooks → Add webhook
- Payload URL: `https://your-domain/webhook`
- Events: Pull requests
- Secret: `GITHUB_WEBHOOK_SECRET`

## Mimarı

### Bileşenler

```
app/
├── main.py          # FastAPI endpoints
├── reviewer.py      # Analiz motoru (two-stage)
├── json_parser.py   # Robust JSON parsing (5 strategy)
├── github_client.py # GitHub API client
└── prompts.py       # LLM prompts
```

### Two-Stage Analysis

**Stage 1:** Quick summary (fast, low tokens)
- Change summary, severity, type

**Stage 2:** Detailed analysis (on demand, full diff)
- Bug detection
- Security review
- Performance analysis

### JSON Parser Strategies

1. Direct parse (`json.loads()`)
2. Extract from markdown (```json...```)
3. Fix common errors (single quotes, unquoted keys, trailing commas)
4. Regex extraction
5. Fallback template

## Test

```bash
# Tüm testler
pytest tests/ -v

# Spesifik test
pytest tests/test_local_review.py -v

# Coverage
pytest tests/ --cov=app --cov-report=html
```

**Test Coverage:** 24/24 passed (100%)
- Schema validation (8 test)
- Parser robustness (9 test)
- Diff scenarios (7 test)

## CI/CD

GitHub Actions workflows:
- **test.yml**: Her push'ta pytest çalıştır
- **docker.yml**: Main branch'e push → Docker image build et

## Yapılandırma

### Token Limits

```python
MAX_INPUT_TOKENS = 30000
MAX_OUTPUT_TOKENS = 2000
RESERVED_FOR_PROMPT = 2000
```

### Diff Truncation

```python
max_length = TokenManager.get_max_diff_length()
# Otomatik olarak önemli satırları tutar
```

## Monitoring

```bash
# Parser istatistikleri
GET /stats
```

Response:
```json
{
  "total_attempts": 24,
  "successful": 24,
  "failed": 0,
  "success_rate": "100.0%"
}
```

## Hatalar & Debug

```bash
# Logs görmek
docker logs container-id

# Local debug
export PYTHONUNBUFFERED=1
python -m app.main
```
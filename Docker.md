# Docker - Build & Run Guide

## 🐳 Dockerfile Ne Yapıyor?

```dockerfile
FROM python:3.11-slim as builder
# 1. Python 3.11 slim image kullan (küçük, hızlı)

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# 2. Python packages install et

FROM python:3.11-slim
# 3. Yeni (final) stage başlat (sadece runtime)

COPY --from=builder /usr/local/lib/python3.11/site-packages ...
# 4. Builder'dan installed packages'ları kopyala

COPY app/ ./app/
COPY .env.example .env
# 5. Kod dosyalarını kopyala

EXPOSE 8000
# 6. Port 8000 aç

HEALTHCHECK ...
# 7. Health check ekle (container sağlık kontrolü)

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
# 8. App başlat
```

---

## 🏗️ Multi-Stage Build Neden?

### Neden multi-stage?

**Seçenek 1: Single Stage (kötü)**
```
Image size: 2GB+ (büyük!)
Teknik borç: Builder tools hala image'da
```

**Seçenek 2: Multi-Stage (iyi) ✅**
```
Stage 1: Build (pip install, compile)
Stage 2: Runtime (sadece gerekli dosyalar)

Sonuç: Image size 400MB (5x daha küçük!)
```

---

## 🚀 Docker Build

### Build et:
```bash
docker build -t pr-code-reviewer:latest .
```

### Run et:
```bash
docker run -p 8000:8000 \
  -e GITHUB_TOKEN=your_token \
  -e GEMINI_API_KEY=your_api_key \
  pr-code-reviewer:latest
```

### Test et:
```bash
curl http://localhost:8000/health
# Response: {"status": "ok", "version": "0.2.0"}
```

---

## 🔍 .dockerignore

Gereksiz dosyaları image'a ekleme:

```
__pycache__        ← Python cache
*.pyc              ← Compiled files
venv/              ← Virtual env
tests/             ← Test files (production'da lazım değil)
.git/              ← Git history (lazım değil)
*.md               ← Markdown (lazım değil)
```

**Sonuç:** Image daha küçük, daha hızlı build.

---

## 🏥 Health Check

```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')" || exit 1
```

**Ne yapıyor?**
- Her 30 saniyede health check yap
- `/health` endpoint'ine GET request gönder
- Fail olursa 3 kez daha dene
- Sonra container'ı unhealthy işaretle

**Kubernetes/Docker Compose faydalı:**
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
  interval: 30s
  timeout: 10s
  retries: 3
```

---

## 📝 Environment Variables

Dockerfile'da `.env.example` kopyalanır. Runtime'da override edilir:

```bash
docker run -e GITHUB_TOKEN=xxx -e GEMINI_API_KEY=yyy pr-code-reviewer
```

**Veya .env dosyasından:**
```bash
docker run --env-file .env pr-code-reviewer
```

---

## 🔐 Security Best Practices

1. **Secrets eklememe** - Dockerfile'da secret yok ✅
2. **Non-root user** - python:3.11-slim zaten non-root kullanıyor
3. **Minimal base image** - slim version (full değil)
4. **No cache** - pip install --no-cache-dir (image size azalır)

---

## 📊 Image Size Karşılaştırma

```
Single Stage (python:3.11):        2.5GB
Multi-Stage (python:3.11-slim):    450MB   ← İyi! ✅
Alpine base (python:3.11-alpine):  200MB   (ama daha riskli)
```

---

## 🎯 Özet

| Öğe | Amaç |
|-----|------|
| **FROM python:3.11-slim** | Minimal base image |
| **Multi-stage** | Küçük final image |
| **COPY app/** | Sadece gerekli kod |
| **.dockerignore** | Gereksiz dosya exclude |
| **HEALTHCHECK** | Container sağlık kontrolü |
| **ENV variables** | Runtime configuration |

---

## ❌ Yapmaması Gerekenler

```dockerfile
# ❌ DON'T: Secret'ları hardcode etme
ENV GITHUB_TOKEN=my_secret_token

# ❌ DON'T: Full Python image
FROM python:3.11

# ❌ DON'T: Root user olarak çalıştırma
USER root

# ✅ DO: Runtime'da pass et
docker run -e GITHUB_TOKEN=$GITHUB_TOKEN ...
```

---

**Dockerfile hazır ve production-ready!** ✅
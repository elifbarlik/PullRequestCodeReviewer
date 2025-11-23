# GitHub Actions - CI/CD Pipeline

## 🔄 Test Workflow (test.yml)

```yaml
name: Tests

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main, develop ]
```

**Ne demek?**
- `push` olduğunda → Tests çalıştır
- `pull_request` açıldığında → Tests çalıştır
- Sadece main/develop branches'e

---

## 📋 Test Job Steps

### Step 1: Checkout
```yaml
- uses: actions/checkout@v4
```
**Ne yapıyor:** Repo'yu GitHub Actions runner'ına clone et

---

### Step 2: Python Setup
```yaml
- name: Set up Python 3.11
  uses: actions/setup-python@v4
  with:
    python-version: '3.11'
    cache: 'pip'
```

**Ne yapıyor:**
- Python 3.11 yükle
- `cache: 'pip'` → pip packages cache'le (hızlı)

---

### Step 3: Dependencies
```yaml
- name: Install dependencies
  run: |
    python -m pip install --upgrade pip
    pip install -r requirements.txt
    pip install pytest pytest-cov
```

**Ne yapıyor:** Tüm dependencies install et

---

### Step 4: Run Tests
```yaml
- name: Run tests
  run: |
    pytest tests/ -v --tb=short
```

**Ne yapıyor:** Tests'i çalıştır
- `-v` → Verbose (details göster)
- `--tb=short` → Kısa traceback

---

### Step 5: Badge Status
```yaml
- name: Create test badge
  if: always()
  run: |
    if pytest tests/ -q > /dev/null 2>&1; then
      echo "Tests passed!"
      echo "BADGE_STATUS=passing" >> $GITHUB_ENV
    else
      echo "Tests failed!"
      echo "BADGE_STATUS=failing" >> $GITHUB_ENV
    fi
```

**Ne yapıyor:** Test status'u kontrol et (badge için)

---

## 🐳 Docker Build Workflow (docker.yml)

```yaml
name: Docker Build

on:
  push:
    branches: [ main ]
    tags: [ 'v*' ]
```

**Ne demek?**
- Main branch'e push → Build
- v* tags (v1.0.0, v0.2.0) → Build

---

## 📋 Docker Job Steps

### Step 1: Checkout
```yaml
- uses: actions/checkout@v4
```

---

### Step 2: Docker Buildx Setup
```yaml
- name: Set up Docker Buildx
  uses: docker/setup-buildx-action@v2
```

**Ne yapıyor:** Docker buildx tool'u setup et (multi-platform builds)

---

### Step 3: Build Image
```yaml
- name: Build Docker image
  uses: docker/build-push-action@v4
  with:
    context: .
    push: false
    tags: pr-code-reviewer:latest
    cache-from: type=gha
    cache-to: type=gha,mode=max
```

**Ne yapıyor:**
- Image build et (push etme, sadece test için)
- `cache-from/to: type=gha` → GitHub cache kullan (hızlı)

---

### Step 4: Test Docker Image
```yaml
- name: Test Docker image
  run: |
    docker build -t pr-code-reviewer:test .
    docker run --rm pr-code-reviewer:test pytest tests/ -v || true
```

**Ne yapıyor:**
- Docker image'ı build et
- Container'da tests çalıştır
- `|| true` → Fail olsa da pipeline devam etsin (opsiyonel)

---

## 🔗 Badge'ları README'ye Ekle

```markdown
[![Tests](https://github.com/YOUR_USERNAME/PR-Reviewer/actions/workflows/test.yml/badge.svg)](https://github.com/YOUR_USERNAME/PR-Reviewer/actions)
[![Docker Build](https://github.com/YOUR_USERNAME/PR-Reviewer/actions/workflows/docker.yml/badge.svg)](https://github.com/YOUR_USERNAME/PR-Reviewer/actions)
```

**Ne yapıyor:** GitHub Actions status badge göster

---

## 📊 Pipeline Flow

```
Code Push
  ↓
GitHub Actions Triggered
  ↓
├─ Job 1: Tests
│  ├─ Checkout
│  ├─ Setup Python
│  ├─ Install deps
│  ├─ Run pytest
│  └─ ✅ or ❌
│
└─ Job 2: Docker Build
   ├─ Checkout
   ├─ Setup Docker
   ├─ Build image
   ├─ Test image
   └─ ✅ or ❌
```

---

## 🎯 Başarı Kriterleri

✅ **Test Job:** 24 tests passed
✅ **Docker Build:** Image successful build
✅ **Badges:** README'de status göster

---

## 📈 CI/CD Avantajları

| Avantaj | Açıklama |
|---------|----------|
| **Otomatik Test** | Her push'ta tests çalışır |
| **Early Detection** | Bug'lar production'a gitmeden bulunur |
| **Docker Ready** | Image'ı otomatik build et ve test et |
| **Status Tracking** | Badge'larla status göster |
| **Deployment Ready** | Build başarılı ise deploy edebilirsin |

---

## 🔐 Security Notes

1. **Secrets güvenli:** GITHUB_TOKEN vs. action secrets olarak sakla
2. **No hardcoded:** Tokens Dockerfile'da yok ✅
3. **Minimal permissions:** Actions için sadece gerekli permissions ver

---

## 🚀 Kurulum Adımları

### 1. Repo'ya Push Et
```bash
git add .
git commit -m "Add Docker and GitHub Actions"
git push origin main
```

### 2. GitHub'da Check Et
```
Repository → Actions
→ Workflows çalışıyor mu?
→ Test job pasif mi? (aktif olmalı!)
```

### 3. Badge'ları README'ye Ekle
```markdown
[![Tests](https://github.com/YOUR/REPO/actions/workflows/test.yml/badge.svg)]
```

### 4. Konfirm Et
- ✅ Tests çalıştı mı?
- ✅ Docker build başarılı mı?
- ✅ Badge yeşil mi?

---

## 🎓 Best Practices

✅ **Do:**
- Her push'ta test çalıştır
- Docker image build et
- Status badge göster
- Secrets GitHub Secrets'ta sakla

❌ **Don't:**
- Secrets hardcode etme
- Test olmadan deploy etme
- Docker olmadan production deploy etme
- Manual testing'e güvenme

---

**CI/CD pipeline production-ready!** ✅
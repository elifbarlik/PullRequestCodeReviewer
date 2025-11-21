# GitHub Webhook Setup Guide

Bu döküman, PR Code Reviewer uygulamasını GitHub webhook'ları ile otomatik çalışacak şekilde nasıl yapılandıracağınızı adım adım açıklar.

## 📋 Gereksinimler

- Python 3.8+
- GitHub hesabı ve repository
- GitHub Personal Access Token
- Ngrok hesabı (ücretsiz)

## 🚀 Adım 1: Ngrok Kurulumu ve Localhost'u Dışarı Açma

### 1.1 Ngrok İndirme ve Kurulum

**Linux/Mac:**
```bash
# Ngrok'u indir
wget https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz

# Çıkart
tar -xvzf ngrok-v3-stable-linux-amd64.tgz

# /usr/local/bin'e taşı (opsiyonel)
sudo mv ngrok /usr/local/bin/
```

**Windows:**
- https://ngrok.com/download adresinden ngrok'u indirin
- ZIP'i çıkartın ve ngrok.exe'yi PATH'e ekleyin

### 1.2 Ngrok Auth Token Kurulumu

1. https://dashboard.ngrok.com/get-started/your-authtoken adresine gidin
2. Auth token'ınızı kopyalayın
3. Terminalde aşağıdaki komutu çalıştırın:

```bash
ngrok config add-authtoken YOUR_AUTH_TOKEN
```

### 1.3 Uygulamayı Başlatın

```bash
# Virtual environment oluştur (ilk kez)
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Bağımlılıkları yükle
pip install -r requirements.txt

# .env dosyasını oluştur ve doldur
cp .env.example .env
# .env dosyasını düzenleyin ve token'larınızı ekleyin

# Uygulamayı başlat
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 1.4 Ngrok ile Localhost'u Dışarı Açın

**Yeni bir terminal açın** ve aşağıdaki komutu çalıştırın:

```bash
ngrok http 8000
```

Çıktıda şuna benzer bir URL göreceksiniz:
```
Forwarding    https://abc123.ngrok-free.app -> http://localhost:8000
```

Bu HTTPS URL'ini kopyalayın - GitHub webhook'unda kullanacağız!

## 🔧 Adım 2: GitHub Webhook Yapılandırması

### 2.1 Repository Settings'e Gidin

1. GitHub'da repository'nize gidin
2. **Settings** > **Webhooks** > **Add webhook**

### 2.2 Webhook'u Yapılandırın

**Payload URL:**
```
https://YOUR_NGROK_URL/webhook
```

**Örnek:**
```
https://abc123.ngrok-free.app/webhook
```

**Content type:**
```
application/json
```

**Secret:**
- Güçlü bir secret oluşturun (örn: `openssl rand -hex 32`)
- Bu secret'ı hem GitHub'da hem de `.env` dosyanızda `GITHUB_WEBHOOK_SECRET` olarak kullanın

**Which events would you like to trigger this webhook?**
- "Let me select individual events" seçin
- Sadece **"Pull requests"** seçeneğini işaretleyin

**Active:**
- ✅ İşaretli olsun

### 2.3 Webhook'u Kaydet

"Add webhook" butonuna tıklayın.

## 🔐 Adım 3: Environment Variables

`.env` dosyanızı şu şekilde yapılandırın:

```env
# GitHub API Token (repo ve pull_request izinleri gerekli)
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx

# GitHub Webhook Secret (webhook oluştururken belirlediğiniz)
GITHUB_WEBHOOK_SECRET=your_secret_here

# Google Gemini API Key (LLM için)
GOOGLE_API_KEY=AIxxxxxxxxxxxxxxxxxxxxx
```

### GitHub Token Oluşturma

1. https://github.com/settings/tokens adresine gidin
2. **Generate new token** > **Generate new token (classic)**
3. Şu izinleri seçin:
   - `repo` (tüm alt izinler)
   - `write:discussion`
4. Token'ı kopyalayın ve `.env` dosyasına ekleyin

## ✅ Adım 4: Test

### 4.1 Webhook Ping Testi

1. GitHub repository > Settings > Webhooks
2. Webhook'unuza tıklayın
3. "Recent Deliveries" bölümünden "Redeliver" yapın
4. Uygulamanızın loglarında şunu görmelisiniz:

```
🔔 Webhook alındı: event=ping
```

### 4.2 PR Testi

1. Test repository'nizde yeni bir branch oluşturun
2. Bir dosyada değişiklik yapın ve commit edin
3. Pull Request açın
4. Birkaç saniye içinde bot otomatik yorum yapmalı!

Örnek bot yorumu:
```
## 🤖 PR Code Reviewer - Otomatik Analiz

### 📝 Özet
**Değişiklik:** Added new feature X
**Önem:** medium
**Tip:** feature

### 🐛 Bulunan Hatalar
...
```

## 🔍 Webhook Nasıl Çalışır?

1. **PR Açılır** → GitHub webhook tetiklenir
2. **Webhook POST isteği** → Ngrok üzerinden localhost:8000/webhook'a gelir
3. **Signature Doğrulama** → HMAC SHA-256 ile güvenlik kontrolü
4. **PR Diff Alınır** → GitHub API'den değişiklikler çekilir
5. **LLM Analizi** → Gemini API ile kod analizi yapılır
6. **Yorum Gönderilir** → GitHub API ile PR'ye otomatik yorum eklenir

## 🔒 Güvenlik

### HMAC Signature Doğrulaması

Uygulama, gelen webhook isteklerini şu şekilde doğrular:

```python
def verify_github_signature(payload_body: bytes, signature_header: str) -> bool:
    """GitHub webhook signature'ını doğrula (HMAC SHA-256)"""
    webhook_secret = os.getenv("GITHUB_WEBHOOK_SECRET")

    mac = hmac.new(
        webhook_secret.encode(),
        msg=payload_body,
        digestmod=hashlib.sha256
    )
    calculated_signature = mac.hexdigest()

    return hmac.compare_digest(calculated_signature, expected_signature)
```

Bu sayede:
- ✅ Sadece GitHub'dan gelen istekler kabul edilir
- ✅ Man-in-the-middle saldırıları engellenir
- ✅ Timing attack'lara karşı korumalıdır

## 📊 Webhook Events

Uygulama şu PR event'lerini işler:

| Event | Action | İşlem |
|-------|--------|-------|
| `pull_request` | `opened` | ✅ Otomatik review yapar |
| `pull_request` | `synchronize` | ✅ Otomatik review yapar |
| `pull_request` | `closed` | ⏭️ Atlanır |
| Diğer event'ler | - | ⏭️ Atlanır |

## 🐛 Sorun Giderme

### Webhook Tetiklenmiyor

1. Ngrok hala çalışıyor mu? Terminal'de kontrol edin
2. Uygulama çalışıyor mu? `http://localhost:8000/health` kontrolü yapın
3. GitHub webhook'u "Active" mi? Settings > Webhooks'ta kontrol edin

### 403 Forbidden Hatası

- `GITHUB_WEBHOOK_SECRET` doğru mu?
- GitHub webhook settings'te secret doğru girilmiş mi?

### 401 Unauthorized (GitHub API)

- `GITHUB_TOKEN` geçerli mi?
- Token'ın `repo` ve `write:discussion` izinleri var mı?

### Bot Yorum Yapmıyor

1. Terminal loglarını kontrol edin
2. `GOOGLE_API_KEY` doğru mu?
3. GitHub token'ın write izni var mı?

## 🔄 Workflow Diyagramı

```
┌─────────────┐
│   PR Açıldı  │
└──────┬──────┘
       │
       ▼
┌─────────────────────┐
│  GitHub Webhook     │
│  POST /webhook      │
└──────┬──────────────┘
       │
       ▼
┌─────────────────────┐
│  Signature Verify   │
│  (HMAC SHA-256)     │
└──────┬──────────────┘
       │
       ▼
┌─────────────────────┐
│  Parse Payload      │
│  Extract PR Info    │
└──────┬──────────────┘
       │
       ▼
┌─────────────────────┐
│  Get PR Diff        │
│  (GitHub API)       │
└──────┬──────────────┘
       │
       ▼
┌─────────────────────┐
│  Review Diff        │
│  (Gemini LLM)       │
└──────┬──────────────┘
       │
       ▼
┌─────────────────────┐
│  Post Comment       │
│  (GitHub API)       │
└─────────────────────┘
```

## 📚 Kaynaklar

- [GitHub Webhooks Documentation](https://docs.github.com/en/webhooks)
- [Ngrok Documentation](https://ngrok.com/docs)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)

## 🎯 Başarı Kıstasları

✅ Test PR açıldığında webhook tetikleniyor
✅ Signature doğrulaması çalışıyor
✅ PR'ye bot yorumu bırakılıyor
✅ Güvenlik analizi yapılıyor
✅ Bug detection çalışıyor

---

**Not:** Ngrok ücretsiz planında her yeniden başlatmada URL değişir. Production için kalıcı bir domain veya ngrok paid plan kullanmanız önerilir.

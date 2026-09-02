# Deploy: Fly.io (uygulama) + Neon (PostgreSQL)

Faz 3'ün ön koşulu — Marketplace, kurulum akışını canlı test eder, bu yüzden
webhook URL'sinin **public ve her zaman açık** olması gerekir. Bu belge, ücretsiz
(fiilen ~$0) bir kurulumu adım adım anlatır.

- **Fly.io** — uygulamayı çalıştırır. Uyku yok, `Dockerfile` deploy, 512 MB VM.
  Kredi kartı ister ama bu ölçekte fatura genelde minimumun altında kalıp $0 çıkar.
- **Neon** — yönetilen PostgreSQL. Ücretsiz katman 0.5 GB, otomatik uyanma (~1 sn).

Repoda `fly.toml` hazır. Aşağıdaki adımlar Windows PowerShell içindir.

---

## 0. Hesaplar ve CLI

1. <https://neon.tech> — GitHub ile giriş yap.
2. <https://fly.io> — GitHub ile giriş yap, kredi kartı ekle (Billing).
3. Fly CLI kur (PowerShell):
   ```powershell
   pwsh -Command "iwr https://fly.io/install.ps1 -useb | iex"
   ```
   Yeni bir terminal aç, doğrula:
   ```powershell
   fly version
   fly auth login
   ```

---

## 1. Neon'da veritabanı oluştur

1. Neon dashboard → **New Project** → ad: `secpr-tr`, region: **Europe (Frankfurt)**.
2. Proje açılınca **Connection string**'i kopyala. Şuna benzer:
   ```
   postgresql://secpr_owner:npg_xxxx@ep-cool-name-123456.eu-central-1.aws.neon.tech/secpr?sslmode=require
   ```
3. **Sürücü öneki ekle.** Bizim kod `psycopg` (v3) kullanır; `postgresql://` yerine
   `postgresql+psycopg://` olmalı. `sslmode=require` kalsın:
   ```
   postgresql+psycopg://secpr_owner:npg_xxxx@ep-cool-name-123456.eu-central-1.aws.neon.tech/secpr?sslmode=require
   ```
   Bu tam string'i bir yere kaydet — Adım 3'te lazım.

---

## 2. Fly uygulamasını oluştur (deploy etmeden)

Repo kökünde:

```powershell
cd C:\Users\elifb\Documents\Pr-Review\pr-reviewer
fly launch --no-deploy --copy-config --name secpr-tr --region fra
```

- `--copy-config` → mevcut `fly.toml`'u kullanır, üzerine yazmaz.
- `secpr-tr` adı alınmışsa Fly sana benzersiz bir ad önerir; kabul et ve
  `fly.toml` içindeki `app = "..."` satırını o adla güncelle.
- Postgres/Redis eklemeyi sorarsa **hayır** de (Neon kullanıyoruz).

---

## 3. Secret'ları ayarla

`.pem` dosyasını tek satıra çevir (Fly secret çok satırlıyı da kabul eder ama
tek satır daha güvenli):

```powershell
$key = (Get-Content "C:\Users\elifb\Documents\Pr-Review\secpr-tr.2026-08-30.private-key.pem" -Raw) -replace "`r`n","`n"
```

Sonra hepsini tek komutta ver (kendi değerlerinle):

```powershell
fly secrets set `
  GEMINI_API_KEY="AIza..." `
  GITHUB_APP_ID="123456" `
  GITHUB_WEBHOOK_SECRET="<.env'deki değer>" `
  DATABASE_URL="postgresql+psycopg://secpr_owner:npg_xxxx@ep-...eu-central-1.aws.neon.tech/secpr?sslmode=require" `
  GITHUB_APP_PRIVATE_KEY="$key"
```

Kontrol:
```powershell
fly secrets list
```
(Değerler görünmez, sadece adlar ve digest.)

---

## 4. Deploy

```powershell
fly deploy
```

İlk build birkaç dakika sürer (semgrep + psycopg derlenir). Bittiğinde:

```powershell
fly status
fly logs
```

Loglarda şunları görmelisin:
- `✅ DB tabloları hazır (installations, usage_logs, findings, settings)`
- `Uvicorn running on http://0.0.0.0:8000`

Domain'i öğren:
```powershell
fly info    # "Hostname" satırı: secpr-tr.fly.dev
```

---

## 5. Doğrula

```powershell
curl https://secpr-tr.fly.dev/health
# {"status":"ok","version":"0.3.0","app":"SecPR-TR"}

curl https://secpr-tr.fly.dev/stats
# "usage" bloğu görünüyorsa DB bağlı: {"installations_total":0, ...}
```

`usage` bloğu yoksa `DATABASE_URL` yanlış — `fly logs` içinde
`get_stats_summary başarısız` veya `DB devre dışı` satırı arayın, sürücü önekini
(`+psycopg`) ve `sslmode=require`'ı kontrol edin.

---

## 6. GitHub App webhook URL'sini güncelle

GitHub → Settings → Developer settings → GitHub Apps → **SecPR-TR** → **General**:

- **Webhook URL** = `https://secpr-tr.fly.dev/webhook`
- **Save changes**

Sonra **Advanced → Recent Deliveries** sekmesinden "Redeliver" ile bir test
event'i gönder; yanıt **200** olmalı.

---

## 7. Uçtan uca test

1. Test reposuna App'i kur: `https://github.com/apps/secpr-tr`
2. Bir dosyaya bilinçli açık ekleyip PR aç:
   ```python
   DB_PASSWORD = "hunter2"   # hardcoded secret — Semgrep yakalamalı
   ```
3. Birkaç saniyede SecPR-TR Türkçe güvenlik yorumu yazmalı.
4. Yorumun **ekran görüntüsünü al** — Marketplace görselleri ve Faz 5 için.
5. `fly logs` ile akışı izle: `installation.created` → `pull_request` →
   `Semgrep sonucu` → `PR'e yorum gönderiliyor`.

---

## Maliyet ve bakım

- Fly: 1× `shared-cpu-1x` 512 MB makine 7/24 açık ≈ ayda ~$2; Fly'ın aylık
  ~$5 kullanım eşiğinin altında kalırsa faturaya yansımaz. `fly dashboard` →
  Billing'den takip et.
- Neon: ücretsiz katman yeterli. 1 haftadan uzun inaktiflikte proje "suspended"
  olur, ilk sorguda otomatik uyanır (~1-2 sn).
- Güncelleme: `git push` sonrası tekrar `fly deploy`. (İstersen
  `.github/workflows` içine `flyctl deploy` adımı eklenebilir — Faz 4/5.)

---

## Sorun giderme

| Belirti | Olası neden | Çözüm |
|---------|-------------|-------|
| `fly deploy` build'de OOM | 512 MB az geldi | `fly scale memory 1024` (kısa süre), sonra geri düşür |
| `/health` 200 ama `/stats`'ta `usage` yok | `DATABASE_URL` öneki/SSL | `postgresql+psycopg://...?sslmode=require` |
| Webhook 502/timeout | makine uyumuş | `fly.toml`'da `min_machines_running = 1` ve `auto_stop_machines = false` olmalı (repoda öyle) |
| `SemgrepNotAvailable` yorumları | pip semgrep kurulmamış | `requirements.txt`'te `semgrep` var; `fly deploy` loglarında pip çıktısını kontrol et |
| Gemini `PERMISSION_DENIED` | API key yanlış/kısıtlı | `fly secrets set GEMINI_API_KEY=...` ile yenile |

# Faz 3 — GitHub Marketplace'e Ücretsiz Listing: Adım Adım

Bu belge, **senin GitHub arayüzünde elle yapacağın** işleri sırayla anlatır.
Kod tarafı (LICENSE, PRIVACY.md, SUPPORT.md, listing metni) repoda hazır.

Hedef **gelir değil portföy** olduğu için uygulama tamamen ücretsiz yayımlanır.
Bunun getirdiği basitleştirmeler:

- **Publisher verification gerekmez** (yalnızca paid plan'lar için zorunlu).
- **Marketplace Billing API** (purchased/cancelled/changed) event handling **gerekmez**.
- "X kurulum" sayısı App sayfanda görünür kalır — CV'de somut bir sayı olarak kullanılabilir.

---

## Ön koşullar (zaten var)

- [x] GitHub App kaydı yapılmış (Faz 1). App ID `.env`'de `GITHUB_APP_ID`.
- [x] Webhook secret tanımlı, private key `.pem` güvende (repo dışında, `.gitignore`'da).
- [x] `PRIVACY.md`, `SUPPORT.md`, `LICENSE`, `docs/marketplace-listing.md` repoda.
- [ ] **Uygulama bir yerde çalışıyor olmalı** — webhook URL'sinin public ve
  ayakta olması gerekir (Railway / Render / Fly.io / VPS). Marketplace, kurulum
  akışını test eder.

---

## Adım 1 — Uygulamayı public erişilebilir bir yere deploy et

Marketplace listing'i submit etmeden önce webhook URL'sinin **public ve her
zaman açık** olması lazım (GitHub 10 sn içinde yanıt bekler; uyuyan servis
webhook'u timeout'a düşürür).

**Önerilen kurulum: Fly.io (uygulama) + Neon (PostgreSQL) — fiilen ~$0.**
Tam adım adım rehber: **[docs/deploy-fly-neon.md](deploy-fly-neon.md)**

Özet:
1. Neon'da Postgres projesi aç, connection string'i al, önekini
   `postgresql+psycopg://...?sslmode=require` yap.
2. Repo kökünde `fly launch --no-deploy --copy-config` (repoda `fly.toml` hazır).
3. `fly secrets set` ile: `GEMINI_API_KEY`, `GITHUB_APP_ID`,
   `GITHUB_APP_PRIVATE_KEY` (tek satır), `GITHUB_WEBHOOK_SECRET`, `DATABASE_URL`.
4. `fly deploy` → `https://<app>.fly.dev/health` → `{"status":"ok","app":"SecPR-TR"}`.
5. **GitHub App ayarlarında Webhook URL'yi güncelle:**
   GitHub → Settings → Developer settings → GitHub Apps → SecPR-TR → General →
   **Webhook URL** = `https://<app>.fly.dev/webhook`.

> Yerel Docker ile denemek için `docker-compose up -d` (Postgres dahil) hâlâ
> çalışır — ama webhook'ları dışarıdan almak için `scripts/smee_proxy.py`
> gerekir. Marketplace testi için gerçek bir public deploy şart.

---

## Adım 2 — App'i "public" yap

GitHub → Settings → Developer settings → GitHub Apps → **SecPR-TR** → **Advanced**
(veya General'in altında) → **"Make this GitHub App public"**.

> Public olmadan Marketplace listing oluşturulamaz. Public yapmak, App'in
> herkes tarafından kurulabilmesi demektir; kodun veya sunucunun görünür olması
> **değil**.

Ayrıca **General** sekmesinde şunları doldur:
- **Homepage URL**: şimdilik `https://github.com/elifbarlik/PullRequestCodeReviewer`
  (Faz 5'te landing page ile değişecek).
- **Description**: `docs/marketplace-listing.md` içindeki "Introductory description".

---

## Adım 3 — İzinlerin minimum olduğunu doğrula

GitHub App → **Permissions & events**. Şunlar dışında bir şey **açık olmamalı**:

| İzin | Seviye |
|------|--------|
| Repository → Pull requests | Read & write |
| Repository → Contents | Read-only |
| Repository → Metadata | Read-only (zorunlu, otomatik) |

**Subscribe to events:** `Pull request`, `Installation`, `Installation repositories`.

> Fazla izin, kurulum ekranında kullanıcıya güvensizlik verir. Marketplace
> incelemesi de gereksiz izinleri sorgular.

---

## Adım 4 — Marketplace listing taslağını oluştur

GitHub App → **SecPR-TR** sayfası → sağ üstte veya "Advanced" altında
**"List in Marketplace"** / **"Create a draft listing"**.

Formu `docs/marketplace-listing.md` ile doldur:

1. **Listing name**: `SecPR-TR`
2. **Very short description**: dosyadaki tek cümle
3. **Categories**: Primary `Code review`, Secondary `Security`
4. **Supported languages**: Python, JavaScript, TypeScript, Go, Java
5. **Introductory description** ve **Detailed description**: dosyadaki metinler
   (Detailed description Markdown kabul eder)
6. **Logo**: 200×200 PNG yükle
7. **Screenshots / feature card**: en az 1 ekran görüntüsü
   (`docs/marketplace-listing.md` → "Görseller" tablosuna göre hazırla)
8. **Privacy policy URL**:
   `https://github.com/elifbarlik/PullRequestCodeReviewer/blob/master/PRIVACY.md`
9. **Support URL**:
   `https://github.com/elifbarlik/PullRequestCodeReviewer/blob/master/SUPPORT.md`
   (veya `.../issues`)

---

## Adım 5 — Ücretsiz plan tanımla

Listing formunun **"Plans and pricing"** bölümünde:

1. **"New plan"** → **Free**
2. Plan adı: `Free`
3. Açıklama: `Tüm özellikler ücretsiz. Kamuya açık ve özel repolar için.`
4. "Available for" → **Both personal accounts and organizations**

> Ücretsiz plan seçildiği için **billing webhook** ve **publisher verification**
> adımları atlanır. İleride paid plan eklemek her zaman mümkün — bu kapıyı şimdi
> kapatmıyoruz.

---

## Adım 6 — Kendi hesabında test et

Listing "Draft" haldeyken bile App'i kurabilirsin:

1. `https://github.com/apps/secpr-tr` (veya App sayfasındaki **Install** linki)
2. Bir test reposuna kur.
3. O repoda küçük bir PR aç — örneğin bir dosyaya bilinçli olarak
   `password = "hunter2"` ekle.
4. SecPR-TR birkaç saniye içinde Türkçe bir güvenlik yorumu yazmalı.
5. **Bu yorumun ekran görüntüsünü al** — Marketplace görselleri ve Faz 5 için lazım.

Sorun olursa:
- Deploy loglarına bak (`installation.created` ve `pull_request` event'leri görünmeli).
- `https://<domain>/stats` → `usage` bölümünde kurulum/analiz sayısı artmalı.
- GitHub App → **Advanced** → **Recent Deliveries**: webhook'ların 200 döndüğünü doğrula.

---

## Adım 7 — Submit et

Listing formunun sonunda **"Submit for review"**.

- GitHub'ın incelemesi **birkaç gün - birkaç hafta** sürebilir.
- Bu sürede Faz 5 (landing page, README revizyonu, demo videosu, topluluk
  paylaşımı) üzerinde çalışabilirsin — yol haritası bunu öneriyor.
- İnceleme geri dönerse istenen düzeltmeleri yapıp tekrar submit et.

---

## Sonuç kontrolü

- [ ] `https://<domain>/health` public ve çalışıyor
- [ ] GitHub App public
- [ ] İzinler minimum (PR read/write, Contents read)
- [ ] Webhook URL production domain'e ayarlı, Recent Deliveries 200
- [ ] Listing draft'ı dolduruldu (metin + logo + ≥1 screenshot + privacy + support)
- [ ] Free plan tanımlı
- [ ] Kendi test repoda çalıştığı doğrulandı + ekran görüntüsü alındı
- [ ] "Submit for review" tıklandı

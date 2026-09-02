# GitHub Marketplace Listing Metni — SecPR-TR

Bu dosya, GitHub Marketplace listing formuna kopyalanacak metinleri içerir.
Marketplace şu an İngilizce listing bekler; Türkçe farklılaşmayı **listing
gövdesinde** vurguluyoruz (başlık/kısa açıklama İngilizce arama için, ayrıntı
Türkçe kimlik için).

---

## Temel bilgiler

| Alan | Değer |
|------|-------|
| **Name** | SecPR-TR |
| **Very short description** (kısa tanıtım, ~1 cümle) | Security-focused PR review with Turkish, beginner-friendly explanations (hybrid Semgrep + LLM). |
| **Categories** | Primary: `Code review` — Secondary: `Security` |
| **Supported languages** | Python, JavaScript, TypeScript, Go, Java (Semgrep ruleset kapsamı) |
| **Pricing** | Free |

---

## Listing gövdesi (Introductory description / Detailed description)

### Introductory description (kısa, Marketplace kartında görünür)

> Türkçe, güvenlik odaklı otomatik PR incelemesi. Semgrep ile değişen kodu SQL
> injection, hardcoded secret, path traversal ve SSRF gibi bilinen açık
> pattern'leri için tarar; bulguları junior geliştiricinin anlayacağı Türkçe bir
> açıklamaya çevirir — neden risk, nasıl istismar edilir, nasıl düzeltilir.

### Detailed description (uzun, listing sayfasında görünür — Markdown)

```markdown
## SecPR-TR nedir?

SecPR-TR, pull request açıldığında veya güncellendiğinde otomatik devreye giren
bir güvenlik incelemesi aracıdır. Genel amaçlı "her şeyi incele" araçlarından
farklı olarak **tek işe odaklanır: güvenlik** — ve çıktısını **Türkçe, öğretici**
bir dille verir.

## Neden hibrit (Semgrep + LLM)?

Sadece bir dil modeline "bu diff'te açık var mı?" diye sormak, yanlış pozitif ve
yanlış negatif riski taşır. SecPR-TR işi ikiye böler:

1. **Semgrep** (deterministik statik analiz) diff'te *değişen satırlarda* bilinen
   açık pattern'lerini bulur. Bulgunun var olup olmadığına ve önem derecesine
   Semgrep karar verir — dil modeli değil.
2. **Dil modeli** bu bulguları *açıklar*: neden risk, somut olarak nasıl istismar
   edilir, nasıl düzeltilir (kod örneğiyle). Türkçe ve junior-dostu tonda.

Tarama tamamlanamazsa sonuç **asla "güvenli" demez**; şeffaf bir "tarama
yapılamadı, manuel inceleyin" uyarısı verir.

## Kimler için?

- Türkiye'deki 2-10 kişilik geliştirici ekipleri
- Ana dilde geri bildirimden faydalanan junior geliştiriciler
- Güvenlik incelemesini CI'ya eklemek isteyen açık kaynak bakımcıları

## Kurulum

1. **Install** butonuna tıklayın, uygulamayı repo(lar)ınıza ekleyin.
2. Başka ayar gerekmez — bir sonraki PR'de otomatik çalışır.
3. İsterseniz belirli Semgrep ruleset'lerini açıp kapatabilirsiniz.

## Gizlilik

Kaynak kodunuz saklanmaz; yalnızca analiz süresince işlenir. Ayrıntılar:
[Gizlilik Politikası](https://github.com/elifbarlik/PullRequestCodeReviewer/blob/master/PRIVACY.md).

## Fiyatlandırma

Ücretsiz.
```

---

## Görseller (yükleme öncesi hazırlanacak)

Marketplace listing için gereken görseller:

| Görsel | Boyut | İçerik |
|--------|-------|--------|
| **Logo** | 200×200 px, PNG | "SecPR-TR" — kilit ikonu + kısa kod motifi |
| **Feature card / hero** | 1200×630 px | Öncesi/sonrası: solda ham diff, sağda SecPR-TR'nin Türkçe güvenlik yorumu |
| **Ekran görüntüsü 1** | ≥ 1200 px genişlik | Gerçek bir PR'de SecPR-TR yorumu (hardcoded secret bulgusu, Türkçe açıklama + düzeltme örneği) |
| **Ekran görüntüsü 2** | ≥ 1200 px genişlik | "Güvenlik açığı tespit edilmedi" temiz PR yorumu |
| **Ekran görüntüsü 3** (opsiyonel) | ≥ 1200 px genişlik | Installation ayarları (ruleset seçimi) |

> En ikna edici içerik: **gerçek bir Türkçe güvenlik açıklaması ekran görüntüsü.**
> Tek başına farklılaşmayı gösterir. Faz 6 pilotundan alınacak.

---

## Listing checklist

- [ ] GitHub App kaydı tamamlandı (Faz 1 — yapıldı)
- [ ] App public olarak işaretlendi (Settings → Advanced → "Make public")
- [ ] Homepage URL girildi (landing page — Faz 5, veya şimdilik repo README)
- [ ] Privacy policy URL: `.../blob/master/PRIVACY.md`
- [ ] Support URL: `.../blob/master/SUPPORT.md` veya Issues sayfası
- [ ] Kategoriler seçildi: Code review + Security
- [ ] Ücretsiz plan tanımlandı
- [ ] Logo + en az 1 ekran görüntüsü yüklendi
- [ ] Listing "Draft" olarak kaydedildi
- [ ] Kendi hesabında test kurulumu yapıldı
- [ ] "Submit for review" (GitHub incelemesi birkaç gün-hafta sürebilir)

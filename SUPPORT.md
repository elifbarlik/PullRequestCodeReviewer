# Destek — SecPR-TR

## Nasıl yardım alırım?

**Hata bildirimi, soru veya öneri için GitHub Issues kullanın:**

<https://github.com/elifbarlik/PullRequestCodeReviewer/issues>

Yeni bir issue açmadan önce mevcut issue'ları aramanız, aynı konunun tekrar
açılmasını önler.

## Bir hata bildirirken ekleyin

- Ne yaptınız, ne bekliyordunuz, ne oldu?
- Hangi repo / PR'de gördünüz? (link verebilirseniz)
- SecPR-TR'nin PR'e yazdığı yorumun ekran görüntüsü veya metni
- Varsa hata mesajı

## Yanıt süresi

Bu proje tek kişi tarafından geliştirilen açık kaynak bir araçtır. Issue'lara
genellikle birkaç gün içinde yanıt verilir; acil müdahale garantisi yoktur.

## Güvenlik açığı bildirimi

SecPR-TR'nin kendisinde bir güvenlik açığı bulduysanız, lütfen **herkese açık
issue açmayın**. Bunun yerine repo sahibine GitHub üzerinden özel mesaj
gönderin veya
[GitHub Security Advisories](https://github.com/elifbarlik/PullRequestCodeReviewer/security/advisories/new)
üzerinden bildirin.

## Sık sorulanlar

**S: PR'e neden hiç yorum gelmedi?**
Y: Değişen satırlarda Semgrep bir güvenlik pattern'i bulamadıysa "güvenlik açığı
tespit edilmedi" yorumu yazılır. Hiç yorum gelmediyse webhook uygulamaya
ulaşmamış olabilir — repo ayarlarında App'in kurulu olduğundan emin olun.

**S: "Güvenlik taraması yapılamadı" yorumu ne demek?**
Y: Semgrep taraması (ör. ağ hatası, dosya erişimi) tamamlanamadı. SecPR-TR bu
durumda asla "güvenli" demez; değişiklikleri manuel incelemenizi önerir.

**S: Yanlış pozitif bir bulgu aldım.**
Y: Bulgular Semgrep'in community ruleset'lerinden gelir. Belirli bir ruleset'i
kapatmak için installation ayarlarını kullanabilirsiniz (bkz. README — "Installation
ayarları"). Sistematik yanlış pozitifleri issue olarak bildirin.

**S: Kodum saklanıyor mu?**
Y: Hayır. Ayrıntılar için [Gizlilik Politikası](PRIVACY.md).

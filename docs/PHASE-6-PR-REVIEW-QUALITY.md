# Faz 6 — PR Review Kalitesi

Bu fazın amacı yeni özellik eklemek değil, mevcut Semgrep + Gemini review sonucunun kapsamını ve güvenilirliğini açıkça tanımlamaktır.

## Semgrep sözleşmesi

Varsayılan ruleset'ler:

- `p/default`
- `p/python`
- `p/security-audit`
- `p/secrets`

Kuralları kullanıcı ayarlarından seçme mekanizması mevcut `ALLOWED_SEMGREP_CONFIGS` allowlist'i ile sınırlıdır.

### Desteklenen dosya türleri

Tarama planı şu uzantıları desteklenen kapsam olarak kabul eder:

Python, JavaScript/JSX, TypeScript/TSX, Go, Java, Ruby, PHP, C, C++, C#, Scala, Kotlin, Rust, Shell ve YAML.

Bunun dışındaki dosyalar Semgrep'e gönderilmez. Bu dosyalar PR'de değişmişse review sonucu "tam tarandı" veya "safe" olarak sunulmaz; kullanıcıya **Partial scan** bilgisi gösterilir.

Silinen dosyalar da tarama kapsamı dışındadır.

## Tarama sınırları

- Maksimum taranabilir dosya: `60`
- Maksimum güvenlik taraması diff boyutu: `512 KiB`
- Semgrep'teki tek dosya hedef boyutu sınırı: `1 MB`
- Mevcut Semgrep timeout davranışı korunur.

60 dosyalık sınır Faz 6'nın kullanıcıya görünür kapsam sınırıdır. Daha büyük PR'lar için pagination ve daha ileri review-size yönetimi Faz 7 kapsamındadır; bu fazda yapılmamıştır.

Diff boyutu 512 KiB'yi aşarsa güvenlik taraması "safe" üretmez. Review sonucu taramanın yapılamadığını açıkça belirtir.

## Kısmi tarama davranışı

Örneğin 73 desteklenen dosya değiştiğinde:

> Partial scan: 13 değişen dosya güvenlik taramasının kapsamı dışında kaldı.

Bu durumda:

- Taranan kapsamda bulgu varsa bulgular yayınlanır ve sonucun kısmi olduğu belirtilir.
- Taranan kapsamda bulgu yoksa güvenlik seviyesi **unknown** kalır; "güvenli" denmez.
- Desteklenmeyen dosya türleri kullanıcıdan gizlenmez.

## Gemini güvenlik sınırı

Mimari ayrım korunur:

`Detection = Semgrep`

`Explanation = Gemini`

Gemini:

- Semgrep bulgusunun severity değerini değiştirmez.
- Dosya/satır konumunu belirlemez.
- Semgrep bulgusu yokken yeni vulnerability üretmek için kullanılmaz.
- Açıklama veya recommendation üretemezse ham Semgrep mesajı fallback olarak kullanılır.

Böylece AI çıktısı güvenlik tespitinin kaynağı değil, mevcut deterministik bulgunun açıklamasıdır.

## Faz 6 çıkış kriterleri

- [x] Desteklenen dosya kapsamı kodda açık.
- [x] Varsayılan Semgrep ruleset'leri dokümante.
- [x] Maksimum dosya sayısı açık.
- [x] Maksimum diff boyutu açık.
- [x] Unsupported file handling kullanıcıya yansıyor.
- [x] File-cap partial scan kullanıcıya yansıyor.
- [x] Partial scan hiçbir durumda "safe" sayılmıyor.
- [x] Gemini severity/location üretmiyor veya değiştirmiyor.
- [x] Gemini başarısız olsa bile Semgrep bulgusu kaybolmuyor.
- [x] Faz 6 için unit testleri eklendi.

## Kapsam dışı

Bu fazda özellikle yapılmayanlar:

- GitHub PR file-list pagination
- Yeni scanner eklemek
- Gemini model değiştirmek
- Cost-control mimarisini yeniden tasarlamak
- Dashboard değişiklikleri
- Authentication / tenant isolation
- Marketplace değişiklikleri

Bunlar roadmap'deki sonraki fazlara bırakılmıştır.

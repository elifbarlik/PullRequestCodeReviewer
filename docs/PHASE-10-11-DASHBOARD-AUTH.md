# Faz 10-11 — Dashboard + GitHub User Authentication

## Faz 10 — Product dashboard

Dashboard artık parser/system overview yerine kalıcı review lifecycle verisini kullanır.

- Toplam review
- Başarılı review
- Başarısız review
- Toplam finding
- Critical / High / Medium / Low dağılımı
- Son review'lar: repository, PR, status, files, findings
- Review detail: commit, status, files scanned, findings ve severity dağılımı

API:
- GET /dashboard/api/summary
- GET /dashboard/api/reviews
- GET /dashboard/api/reviews/{review_run_id}

## Faz 11 — GitHub user authentication

Dashboard kullanıcı girişi GitHub App user authorization web flow'u ile yapılır.

Akış:
1. /auth/github → GitHub authorization
2. /auth/github/callback → code + state doğrulaması
3. GitHub user identity alınır
4. /user/installations üzerinden kullanıcının erişebildiği App installation ID'leri alınır
5. Kısa ömürlü, imzalı HttpOnly session cookie oluşturulur
6. Dashboard API'leri yalnızca session'daki installation ID'leri sorgular

Güvenlik:
- OAuth state doğrulanır.
- GitHub access token session cookie'ye yazılmaz ve DB'ye persist edilmez.
- Session cookie HttpOnly + SameSite=Lax'tır.
- Dashboard endpoint'leri authentication olmadan review verisi döndürmez.
- Kullanıcının installation listesi boşsa dashboard boş sonuç döndürür.

Gerekli production env:
- GITHUB_OAUTH_CLIENT_ID
- GITHUB_OAUTH_CLIENT_SECRET
- GITHUB_OAUTH_SESSION_SECRET
- GITHUB_OAUTH_REDIRECT_URI (opsiyonel; yoksa /auth/github/callback türetilir)

GitHub App ayarlarında user authorization callback URL'si /auth/github/callback ile eşleşmelidir.

## Kapsam dışı

- Faz 12'deki bağımsız tenant-isolation redesign
- Installation settings UI
- Marketplace
- Billing
- Yeni review pipeline
- Yeni Semgrep/Gemini davranışı

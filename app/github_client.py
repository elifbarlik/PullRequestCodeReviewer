"""
GitHub App authentication ve API client modülü.

PAT (Personal Access Token) yerine GitHub App akışını kullanır:
  1. Uygulama özel anahtarıyla RS256 JWT üretir  (10 dk geçerli)
  2. JWT ile GitHub'dan installation access token alır (1 saat geçerli)
  3. Tüm API çağrıları installation token ile yapılır

Bu sayede her kullanıcı kendi PAT'ını vermek zorunda kalmaz;
uygulama, kurulduğu hesap/organizasyon adına hareket eder.
"""

import os
import time
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Dict, Any

import jwt          # PyJWT — RS256 imzalama
import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------
# Sabitler
# -------------------------------------------------------------------
GITHUB_API_BASE = "https://api.github.com"
JWT_EXPIRY_SECONDS = 540          # 9 dk — GitHub maks 10 dk izin verir
TOKEN_REFRESH_BUFFER_SECONDS = 60  # Token süresi dolmaya 60 sn kala yenile


# -------------------------------------------------------------------
# Yardımcı: Private key yükleme
# -------------------------------------------------------------------

def _load_private_key() -> str:
    """
    GitHub App private key'i yükler.

    Öncelik sırası:
      1. GITHUB_APP_PRIVATE_KEY env değişkeni (tek satır, \\n kaçış karakterli)
      2. GITHUB_APP_PRIVATE_KEY_PATH env değişkeni (dosya yolu)

    Returns:
        PEM formatında private key string'i

    Raises:
        ValueError: Key bulunamazsa
    """
    # 1. Önce ortam değişkeninden dene (Railway / Docker deploy için ideal)
    key_env = os.getenv("GITHUB_APP_PRIVATE_KEY", "")
    if key_env.strip():
        # Railway'de satır sonları \\n olarak saklanır — gerçek \n'e çevir
        return key_env.replace("\\n", "\n")

    # 2. Dosya yolundan dene
    key_path = os.getenv("GITHUB_APP_PRIVATE_KEY_PATH", "")
    if key_path and os.path.isfile(key_path):
        with open(key_path, "r", encoding="utf-8") as f:
            return f.read()

    raise ValueError(
        "GitHub App private key bulunamadı. "
        "GITHUB_APP_PRIVATE_KEY veya GITHUB_APP_PRIVATE_KEY_PATH env değişkenini ayarlayın."
    )


# -------------------------------------------------------------------
# Yardımcı: JWT üretimi
# -------------------------------------------------------------------

def _generate_jwt(app_id: str, private_key_pem: str) -> str:
    """
    GitHub App JWT'si üretir (RS256 imzalı).

    Args:
        app_id: GitHub App ID (Settings sayfasındaki sayısal değer)
        private_key_pem: PEM formatında RSA private key

    Returns:
        İmzalı JWT string'i
    """
    now = int(time.time())
    payload = {
        "iat": now - 60,          # issued at — clock skew toleransı için 60 sn geri al
        "exp": now + JWT_EXPIRY_SECONDS,
        "iss": app_id,
    }
    return jwt.encode(payload, private_key_pem, algorithm="RS256")


# -------------------------------------------------------------------
# Ana client sınıfı
# -------------------------------------------------------------------

class GitHubAppClient:
    """
    GitHub App kimlik doğrulamasıyla çalışan API client.

    Her örnek belirli bir installation'a bağlıdır.
    Installation access token cache'lenir ve süresi dolmadan önce
    otomatik olarak yenilenir.

    Kullanım:
        client = GitHubAppClient(installation_id=12345678)
        diff = client.get_pr_diff("owner", "repo", 42)
    """

    def __init__(self, installation_id: int):
        """
        Args:
            installation_id: GitHub App'in kurulu olduğu hesabın/org'un installation ID'si.
                             Webhook payload'larında `installation.id` olarak gelir.
        """
        self.installation_id = installation_id

        # Env değişkenlerinden konfigürasyon oku
        self.app_id = os.getenv("GITHUB_APP_ID", "")
        if not self.app_id:
            raise ValueError("GITHUB_APP_ID env değişkeni ayarlanmamış")

        self._private_key_pem = _load_private_key()

        # Token cache
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0

    # ------------------------------------------------------------------
    # Token yönetimi
    # ------------------------------------------------------------------

    def _get_access_token(self) -> str:
        """
        Installation access token döndürür.
        Token geçerliyse cache'den, süresi dolmuşsa GitHub'dan taze token alır.
        """
        now = time.time()
        if self._access_token and now < self._token_expires_at - TOKEN_REFRESH_BUFFER_SECONDS:
            return self._access_token

        logger.info(f"🔑 Installation {self.installation_id} için yeni access token alınıyor...")
        self._access_token, self._token_expires_at = self._fetch_installation_token()
        return self._access_token

    def _fetch_installation_token(self) -> tuple[str, float]:
        """
        GitHub API'den installation access token alır.

        Returns:
            (token_string, unix_timestamp_expiry) çifti
        """
        jwt_token = _generate_jwt(self.app_id, self._private_key_pem)

        url = f"{GITHUB_API_BASE}/app/installations/{self.installation_id}/access_tokens"
        headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        response = requests.post(url, headers=headers, timeout=10)

        if response.status_code != 201:
            logger.error(f"Token alınamadı: {response.status_code} — {response.text}")
            response.raise_for_status()

        data = response.json()
        token = data["token"]

        # GitHub ISO 8601 döndürür, unix timestamp'e çevir
        from datetime import datetime, timezone
        expires_at_str = data.get("expires_at", "")
        try:
            dt = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
            expires_at = dt.timestamp()
        except (ValueError, AttributeError):
            # Parse edilemezse 1 saat sonra expiry varsay
            expires_at = time.time() + 3600

        logger.info(f"✅ Access token alındı, geçerlilik: {expires_at_str}")
        return token, expires_at

    def _auth_headers(self) -> Dict[str, str]:
        """Installation access token ile hazır request header'ları döndürür."""
        return {
            "Authorization": f"token {self._get_access_token()}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # GitHub API işlemleri
    # ------------------------------------------------------------------

    def get_pr_diff(self, owner: str, repo: str, pr_number: int) -> str:
        """
        PR diff'ini string olarak döndürür.

        Args:
            owner: Repository sahibi (kullanıcı adı veya org)
            repo: Repository adı
            pr_number: Pull Request numarası

        Returns:
            Unified diff string'i

        Raises:
            requests.RequestException: API çağrısı başarısız olursa
            ValueError: Diff boş gelirse
        """
        url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls/{pr_number}"
        headers = self._auth_headers()
        headers["Accept"] = "application/vnd.github.v3.diff"

        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        diff_text = response.text
        if not diff_text:
            raise ValueError(f"PR diff'i boş döndü ({owner}/{repo}#{pr_number})")

        return diff_text

    def get_pr_files(self, owner: str, repo: str, pr_number: int) -> list:
        """
        PR'daki değişen dosyaların listesini döndürür.

        Returns:
            Her dosya için: filename, status, additions, deletions, patch vb.
        """
        url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls/{pr_number}/files"
        response = requests.get(
            url, headers=self._auth_headers(), params={"per_page": 100}, timeout=10
        )
        response.raise_for_status()
        return response.json()

    def get_pr_bundle(self, owner: str, repo: str, pr_number: int) -> Dict[str, Any]:
        """
        PR analizi için gereken üç bağımsız kaynağı TEK SEFERDE paralel çeker:
        diff (unified), details (head SHA, başlık vb.), değişen dosya listesi.

        Seri çağrıldığında ~3 tam API round-trip; paralelde ~1. Access token
        ilk çağrıda alınır ve cache'lenir, o yüzden token round-trip'i
        paralelliği bozmaz (ilk thread alır, diğerleri cache'den okur —
        yarış olsa bile en fazla 2 token isteği, sonuç aynı).

        Returns:
            {"diff": str, "details": dict, "files": list}

        Raises:
            İçlerden herhangi biri başarısız olursa o exception yükselir
            (ThreadPoolExecutor future.result() ilk hatayı fırlatır).
        """
        with ThreadPoolExecutor(max_workers=3) as ex:
            f_diff = ex.submit(self.get_pr_diff, owner, repo, pr_number)
            f_details = ex.submit(self.get_pr_details, owner, repo, pr_number)
            f_files = ex.submit(self.get_pr_files, owner, repo, pr_number)
            return {
                "diff": f_diff.result(),
                "details": f_details.result(),
                "files": f_files.result(),
            }

    def get_files_content(
        self, owner: str, repo: str, filenames: list, ref: str, max_workers: int = 8
    ) -> Dict[str, str]:
        """
        Birden çok dosyanın içeriğini `ref`'te paralel çeker.

        Seri `get_file_content` döngüsü N dosya için N round-trip; bu
        yaklaşım hepsini aynı anda ister. İçeriği alınamayan (binary, 404,
        hata) dosyalar sonuç dict'inde yer almaz — çağıran taraf zaten
        eksik dosyaya toleranslı (Semgrep sadece elindekini tarar).

        Returns:
            {filename: content} — yalnızca başarıyla alınanlar
        """
        results: Dict[str, str] = {}
        if not filenames:
            return results

        def _one(name: str):
            try:
                return name, self.get_file_content(owner, repo, name, ref=ref)
            except Exception as e:  # noqa: BLE001 — tek dosya hatası taramayı durdurmamalı
                logger.warning(f"⚠️  {name} içeriği alınamadı, atlanıyor: {e}")
                return name, None

        with ThreadPoolExecutor(max_workers=min(max_workers, len(filenames))) as ex:
            for name, content in ex.map(_one, filenames):
                if content is not None:
                    results[name] = content
        return results

    def get_pr_details(self, owner: str, repo: str, pr_number: int) -> Dict[str, Any]:
        """
        PR metadata'sını döndürür (başlık, açıklama, head commit SHA vb.).
        """
        url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls/{pr_number}"
        response = requests.get(url, headers=self._auth_headers(), timeout=10)
        response.raise_for_status()
        return response.json()

    def get_file_content(
        self, owner: str, repo: str, path: str, ref: str
    ) -> Optional[str]:
        """
        Belirli bir ref'teki (commit SHA / branch) dosyanın tam içeriğini
        döndürür. Semgrep taraması diff hunk'ı değil, gerçek dosya içeriği
        ister — bu yüzden diff'ten ayrı bir Contents API çağrısı gerekir.

        Args:
            path: Repo köküne göre dosya yolu (diff'teki gibi)
            ref: Commit SHA'sı (genelde PR'nin head SHA'sı)

        Returns:
            Dosya içeriği (UTF-8 metin) veya dosya bulunamadı/binary/
            dizinse None. Semgrep zaten kaynak kodu taradığı için binary
            dosyaların atlanması sorun değil.
        """
        import base64

        url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/contents/{path}"
        response = requests.get(
            url, headers=self._auth_headers(), params={"ref": ref}, timeout=10
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()

        data = response.json()
        if isinstance(data, list):
            # path bir dizin olarak geldi (beklenmez, savunma amaçlı)
            return None
        if data.get("encoding") != "base64" or not data.get("content"):
            return None

        try:
            return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        except Exception:
            return None

    def post_pr_comment(
        self, owner: str, repo: str, pr_number: int, body: str
    ) -> Dict[str, Any]:
        """
        PR'e genel bir yorum gönderir (issue comment).

        Args:
            body: Yorum metni (Markdown desteklenir)

        Returns:
            GitHub API yanıtı (comment ID, URL vb.)
        """
        url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/issues/{pr_number}/comments"
        response = requests.post(
            url, headers=self._auth_headers(), json={"body": body}, timeout=10
        )
        response.raise_for_status()
        return response.json()

    def post_review_comment(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        commit_id: str,
        path: str,
        line: int,
        body: str,
    ) -> Dict[str, Any]:
        """
        PR'de belirli bir satıra tek bir inline review yorumu gönderir.

        Genelde `create_review` tercih edilir (tek istek, çok yorum);
        bu metod tekil/özel durumlar için korunuyor.

        Args:
            commit_id: Head commit SHA'sı
            path: Dosya yolu (diff'teki gibi)
            line: Değiştirilen satır numarası
            body: Yorum metni
        """
        url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls/{pr_number}/comments"
        payload = {
            "commit_id": commit_id,
            "path": path,
            "line": line,
            "body": body,
            "side": "RIGHT",
        }
        response = requests.post(
            url, headers=self._auth_headers(), json=payload, timeout=10
        )
        response.raise_for_status()
        return response.json()

    def create_review(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        body: str,
        comments: Optional[list] = None,
        commit_id: Optional[str] = None,
        event: str = "COMMENT",
    ) -> Dict[str, Any]:
        """
        PR'e tek istekte bir review oluşturur — genel bir gövde metni +
        isteğe bağlı satır-içi (inline) yorumlar.

        Bu, her bulgu için ayrı `post_review_comment` çağırmaktan iyidir:
        tek review objesi, tek API isteği, rate-limit dostu, PR'de tek bir
        "SecPR-TR reviewed" bloğu olarak görünür.

        Args:
            body: Review'ın genel özet metni (Markdown)
            comments: [{path, line, body}, ...] — her biri diff'te RIGHT
                      tarafında var olan bir satıra iliştirilecek. Boş/None
                      ise sadece özet review gönderilir.
            commit_id: Head commit SHA'sı (verilmezse GitHub PR'nin son
                       commit'ini kullanır)
            event: "COMMENT" (onaylamaz/reddetmez), "APPROVE" veya
                   "REQUEST_CHANGES". Güvenlik aracı için varsayılan COMMENT —
                   merge'i bloklama kararını insana bırakırız.

        Returns:
            GitHub review API yanıtı (review id, state vb.)
        """
        url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls/{pr_number}/reviews"
        payload: Dict[str, Any] = {"body": body, "event": event}
        if commit_id:
            payload["commit_id"] = commit_id
        if comments:
            payload["comments"] = [
                {"path": c["path"], "line": c["line"], "side": "RIGHT", "body": c["body"]}
                for c in comments
            ]

        response = requests.post(
            url, headers=self._auth_headers(), json=payload, timeout=15
        )
        response.raise_for_status()
        return response.json()

    def list_review_comments(
        self, owner: str, repo: str, pr_number: int
    ) -> list:
        """
        PR'deki tüm inline review yorumlarını döndürür.

        `synchronize` event'inde aynı bulgu için mükerrer yorum atmamak
        amacıyla kullanılır (idempotency kontrolü).
        """
        url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls/{pr_number}/comments"
        response = requests.get(
            url, headers=self._auth_headers(), params={"per_page": 100}, timeout=10
        )
        response.raise_for_status()
        return response.json()


# -------------------------------------------------------------------
# App-level işlemler (installation_id gerektirmez)
# -------------------------------------------------------------------

class GitHubAppInfo:
    """
    JWT seviyesinde (installation bağımsız) GitHub App bilgilerini sorgular.
    Webhook'larda installation.id alınmadan önce kullanılır.
    """

    def __init__(self):
        self.app_id = os.getenv("GITHUB_APP_ID", "")
        if not self.app_id:
            raise ValueError("GITHUB_APP_ID env değişkeni ayarlanmamış")
        self._private_key_pem = _load_private_key()

    def _jwt_headers(self) -> Dict[str, str]:
        jwt_token = _generate_jwt(self.app_id, self._private_key_pem)
        return {
            "Authorization": f"Bearer {jwt_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def get_installation(self, installation_id: int) -> Dict[str, Any]:
        """Belirli bir installation'ın detaylarını döndürür."""
        url = f"{GITHUB_API_BASE}/app/installations/{installation_id}"
        response = requests.get(url, headers=self._jwt_headers(), timeout=10)
        response.raise_for_status()
        return response.json()

    def list_installations(self) -> list:
        """Bu App'in kurulu olduğu tüm installation'ları listeler."""
        url = f"{GITHUB_API_BASE}/app/installations"
        response = requests.get(url, headers=self._jwt_headers(), timeout=10)
        response.raise_for_status()
        return response.json()

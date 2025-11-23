import requests
from typing import Optional, Dict, Any
import os
from dotenv import load_dotenv

load_dotenv()


class GitHubClient:
    """GitHub API ile PR diff'i ve comment işlemleri için client"""

    def __init__(self, token: Optional[str] = None):
        """
        GitHub client'ı initialize et

        Args:
            token: GitHub Personal Access Token. Eğer None ise, GITHUB_TOKEN env'den alınır
        """
        self.token = token or os.getenv("GITHUB_TOKEN")
        if not self.token:
            raise ValueError(
                "GITHUB_TOKEN env değişkeni veya token parametresi gereklidir"
            )

        self.base_url = "https://api.github.com"
        self.headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
        }

    def get_pr_diff(self, owner: str, repo: str, pr_number: int) -> str:
        """
        PR'dan diff string'i al

        Args:
            owner: Repository owner (GitHub kullanıcı adı)
            repo: Repository adı
            pr_number: Pull Request numarası

        Returns:
            Diff string'i

        Raises:
            requests.RequestException: API çağrısı başarısız olursa
            ValueError: Response parse edilemezse
        """
        url = f"{self.base_url}/repos/{owner}/{repo}/pulls/{pr_number}"

        # Diff'i almak için Accept header'ını değiştir
        headers = self.headers.copy()
        headers["Accept"] = "application/vnd.github.v3.diff"

        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            diff_text = response.text

            if not diff_text:
                raise ValueError("PR diff'i boş döndü")

            return diff_text

        except requests.exceptions.RequestException as e:
            raise requests.RequestException(
                f"PR diff alınamadı ({owner}/{repo}#{pr_number}): {str(e)}"
            )

    def get_pr_files(self, owner: str, repo: str, pr_number: int) -> list:
        """
        PR'daki değişen dosyaları al

        Args:
            owner: Repository owner
            repo: Repository adı
            pr_number: Pull Request numarası

        Returns:
            Dosya listesi (her dosya: filename, status, additions, deletions vb.)
        """
        url = f"{self.base_url}/repos/{owner}/{repo}/pulls/{pr_number}/files"

        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()

            return response.json()

        except requests.exceptions.RequestException as e:
            raise requests.RequestException(
                f"PR dosyaları alınamadı ({owner}/{repo}#{pr_number}): {str(e)}"
            )

    def post_pr_comment(
        self, owner: str, repo: str, pr_number: int, body: str
    ) -> Dict[str, Any]:
        """
        PR'e yorum yap

        Args:
            owner: Repository owner
            repo: Repository adı
            pr_number: Pull Request numarası
            body: Yorum metni (Markdown desteklenir)

        Returns:
            GitHub API response (comment details)

        Raises:
            requests.RequestException: API çağrısı başarısız olursa
        """
        url = f"{self.base_url}/repos/{owner}/{repo}/issues/{pr_number}/comments"

        payload = {"body": body}

        try:
            response = requests.post(
                url, headers=self.headers, json=payload, timeout=10
            )
            response.raise_for_status()

            return response.json()

        except requests.exceptions.RequestException as e:
            raise requests.RequestException(
                f"PR yorumu gönderilemedii ({owner}/{repo}#{pr_number}): {str(e)}"
            )

    def post_pr_review_comment(
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
        PR'de specific bir satıra review comment yap (inline comment)

        Args:
            owner: Repository owner
            repo: Repository adı
            pr_number: Pull Request numarası
            commit_id: Commit SHA
            path: Dosya yolu
            line: Değiştirilmiş satır numarası
            body: Yorum metni

        Returns:
            GitHub API response
        """
        url = f"{self.base_url}/repos/{owner}/{repo}/pulls/{pr_number}/comments"

        payload = {"commit_id": commit_id, "path": path, "line": line, "body": body}

        try:
            response = requests.post(
                url, headers=self.headers, json=payload, timeout=10
            )
            response.raise_for_status()

            return response.json()

        except requests.exceptions.RequestException as e:
            raise requests.RequestException(f"Review comment gönderilemedii: {str(e)}")


# ============= Test Fonksiyonları =============


def test_get_pr_diff():
    """get_pr_diff tests et"""
    print("=" * 60)
    print("TEST: get_pr_diff")
    print("=" * 60)

    # Kendi repo ve PR numarası ile tests et
    owner = input("Repository owner girin (örn: username): ").strip()
    repo = input("Repository adı girin (örn: pr-reviewer): ").strip()
    pr_number = int(input("PR numarası girin (örn: 1): "))

    try:
        client = GitHubClient()
        diff = client.get_pr_diff(owner, repo, pr_number)

        print(f"\n✅ Başarılı! Diff uzunluğu: {len(diff)} karakter")
        print("\nDiff preview (ilk 500 karakter):")
        print("-" * 60)
        print(diff[:500])
        print("-" * 60)

        return diff

    except Exception as e:
        print(f"❌ Hata: {str(e)}")
        return None


def test_post_pr_comment():
    """post_pr_comment tests et"""
    print("\n" + "=" * 60)
    print("TEST: post_pr_comment")
    print("=" * 60)

    owner = input("Repository owner girin: ").strip()
    repo = input("Repository adı girin: ").strip()
    pr_number = int(input("PR numarası girin: "))

    # Test comment
    test_body = """## 🤖 PR Code Reviewer - Test Comment

Bu bir tests yorumudur. Eğer bu mesajı görüyorsanız, GitHub API entegrasyonu çalışıyor!

**Test detayları:**
- ✅ Token geçerli
- ✅ API çağrısı başarılı
- ✅ Comment postu çalışıyor

---
*Otomatik olarak oluşturuldu*
"""

    try:
        client = GitHubClient()
        response = client.post_pr_comment(owner, repo, pr_number, test_body)

        print(f"\n✅ Başarılı! Comment ID: {response.get('id')}")
        print(f"Comment URL: {response.get('html_url')}")

        return response

    except Exception as e:
        print(f"❌ Hata: {str(e)}")
        return None


def test_get_pr_files():
    """get_pr_files tests et"""
    print("\n" + "=" * 60)
    print("TEST: get_pr_files")
    print("=" * 60)

    owner = input("Repository owner girin: ").strip()
    repo = input("Repository adı girin: ").strip()
    pr_number = int(input("PR numarası girin: "))

    try:
        client = GitHubClient()
        files = client.get_pr_files(owner, repo, pr_number)

        print(f"\n✅ Başarılı! {len(files)} dosya bulundu\n")

        for file in files:
            print(f"📄 {file['filename']}")
            print(f"   Status: {file['status']}")
            print(f"   Changes: +{file['additions']} -{file['deletions']}")
            print()

        return files

    except Exception as e:
        print(f"❌ Hata: {str(e)}")
        return None


if __name__ == "__main__":
    print("🚀 GitHub Client Test Suite\n")

    menu = """
Seçim yapın:
1. get_pr_diff tests et
2. post_pr_comment tests et
3. get_pr_files tests et
4. Tümünü sırasıyla tests et
0. Çık

Seçiminiz: """

    while True:
        choice = input(menu).strip()

        if choice == "1":
            test_get_pr_diff()
        elif choice == "2":
            test_post_pr_comment()
        elif choice == "3":
            test_get_pr_files()
        elif choice == "4":
            test_get_pr_diff()
            test_get_pr_files()
            test_post_pr_comment()
        elif choice == "0":
            print("\nÇıkılıyor...")
            break
        else:
            print("❌ Geçersiz seçim")

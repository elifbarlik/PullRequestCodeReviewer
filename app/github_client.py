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

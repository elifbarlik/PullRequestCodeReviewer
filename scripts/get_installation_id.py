"""
GitHub App'in kurulu olduğu tüm hesap/repo'ları listeler.

installation_id'yi bulmak için kullanılır — webhook payload'larında
`installation.id` olarak gelir, ama App'i UI'dan kurduktan hemen sonra
elle test etmek istersen buradan da öğrenebilirsin.

Kullanım:
    python scripts/get_installation_id.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.github_client import GitHubAppInfo


def main():
    try:
        info = GitHubAppInfo()
        installations = info.list_installations()
    except Exception as e:
        print(f"HATA: {e}")
        sys.exit(1)

    if not installations:
        print("Hiç kurulum bulunamadı. App'i bir hesaba/repoya kurduğundan emin ol.")
        sys.exit(0)

    print(f"{len(installations)} kurulum bulundu:\n")
    for inst in installations:
        account = inst.get("account", {})
        print(f"  installation_id : {inst['id']}")
        print(f"  hesap           : {account.get('login')} ({account.get('type')})")
        print(f"  repo_selection  : {inst.get('repository_selection')}")
        print(f"  izinler         : {inst.get('permissions')}")
        print()


if __name__ == "__main__":
    main()

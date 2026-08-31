"""
Pytest Configuration & Shared Fixtures
- Global setup
- Common fixtures
- Test utilities
"""

import pytest
import sys

import os

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from app.reviewer import ParseStatistics

import socket


def _has_network(host: str = "8.8.8.8", port: int = 53, timeout: float = 2.0) -> bool:
    """Gerçek internet erişimi var mı, kısa bir soket denemesiyle kontrol eder."""
    try:
        socket.setdefaulttimeout(timeout)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((host, port))
        return True
    except OSError:
        return False


NETWORK_AVAILABLE = _has_network()




def pytest_collection_modifyitems(config, items):
    """Ağ erişimi yoksa @pytest.mark.network testlerini atla — CI/offline ortamda asılı kalmasınlar."""
    if NETWORK_AVAILABLE:
        return
    skip_network = pytest.mark.skip(
        reason="Ağ erişimi yok — gerçek Gemini API çağrısı gerektiren tests atlandı"
    )
    for item in items:
        if "network" in item.keywords:
            item.add_marker(skip_network)


@pytest.fixture(autouse=True)
def reset_statistics():
    """Her tests'ten önce statistics'i reset et"""
    ParseStatistics.total_attempts = 0
    ParseStatistics.successful_parses = 0
    ParseStatistics.failed_parses = 0

    yield

    # Cleanup after tests
    ParseStatistics.total_attempts = 0
    ParseStatistics.successful_parses = 0
    ParseStatistics.failed_parses = 0


@pytest.fixture
def sample_github_pr():
    """GitHub PR örneği"""
    return {
        "owner": "testuser",
        "repo": "tests-repo",
        "pr_number": 1,
        "diff": """--- a/tests.py
+++ b/tests.py
@@ -1,3 +1,3 @@
 def tests():
-    pass
+    return True
""",
    }


def pytest_configure(config):
    """Pytest başlangıcında çalışır"""
    config.addinivalue_line(
        "markers", "network: gerçek Gemini API çağrısı yapan tests (ağ erişimi gerektirir)"
    )
    print("\n" + "=" * 70)
    print("🧪 PR CODE REVIEWER - TEST SUITE")
    print("=" * 70)
    print("Testing improvements:")
    print("  1. Prompt Optimization")
    print("  2. Robust JSON Parser")
    print("  3. Token Management")
    print("  4. Two-Stage Analysis")
    print("=" * 70 + "\n")


def pytest_runtest_logreport(report):
    """Her tests sonrası rapor et"""
    if report.when == "call":
        if report.outcome == "passed":
            print(f"✅ {report.nodeid}")
        elif report.outcome == "failed":
            print(f"❌ {report.nodeid}")

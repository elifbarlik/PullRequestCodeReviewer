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

import shutil

SEMGREP_AVAILABLE = shutil.which("semgrep") is not None


def pytest_collection_modifyitems(config, items):
    """Ağ erişimi yoksa @pytest.mark.network, semgrep kurulu değilse
    @pytest.mark.requires_semgrep testlerini atla — CI/offline ortamda
    asılı kalmasınlar veya ImportError ile patlamasınlar."""
    skip_network = pytest.mark.skip(
        reason="Ağ erişimi yok — gerçek Gemini API çağrısı gerektiren tests atlandı"
    )
    skip_semgrep = pytest.mark.skip(
        reason="semgrep CLI kurulu değil — `pip install semgrep` ile kurun"
    )
    for item in items:
        if not NETWORK_AVAILABLE and "network" in item.keywords:
            item.add_marker(skip_network)
        if not SEMGREP_AVAILABLE and "requires_semgrep" in item.keywords:
            item.add_marker(skip_semgrep)


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
def db_session(monkeypatch):
    """
    İzole, in-memory SQLite DB — her test kendi şemasını alır.

    app.db modülünün lazy engine cache'ini bu test için SQLite'a yönlendirir
    ve DATABASE_URL'i set eder ki repository.db_enabled() True dönsün.
    Test bitince cache temizlenir.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app import db as db_module
    from app.models import Base

    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)

    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    db_module._reset_for_tests(engine=engine, session_factory=TestSession)

    try:
        yield TestSession
    finally:
        Base.metadata.drop_all(engine)
        db_module._reset_for_tests(engine=None, session_factory=None)


@pytest.fixture
def db_disabled(monkeypatch):
    """DATABASE_URL yok — veri katmanı tamamen devre dışı olmalı."""
    from app import db as db_module

    monkeypatch.delenv("DATABASE_URL", raising=False)
    db_module._reset_for_tests(engine=None, session_factory=None)
    yield
    db_module._reset_for_tests(engine=None, session_factory=None)


class FakeGitHubClient:
    """
    GitHubAppClient yerine geçen sahte istemci — _run_pr_review akış
    testleri için. Faz 4.4 sonrası main.py'nin kullandığı yüzey:
    get_pr_bundle, get_files_content, create_review, post_pr_comment,
    list_review_comments.

    `recorder` dict'ine gönderilen çağrıları kaydeder; testler bunu
    inceler. `diff` / `files` / `head_sha` / `existing_comments` sınıf
    seviyesinde override edilebilir.
    """

    diff = (
        "--- a/app/db.py\n"
        "+++ b/app/db.py\n"
        "@@ -1,2 +1,4 @@\n"
        " import os\n"
        "+query = \"SELECT * FROM u WHERE id = \" + uid\n"
        "+os.system(cmd)\n"
        " x = 1\n"
    )
    files = [{"filename": "app/db.py", "status": "modified"}]
    head_sha = "headsha123"

    def __init__(self, installation_id):
        self.installation_id = installation_id
        self.recorder = {}

    # --- Faz 4.4 toplu çekim ---
    def get_pr_bundle(self, owner, repo, pr_number):
        return {
            "diff": self.diff,
            "details": {"head": {"sha": self.head_sha}},
            "files": self.files,
        }

    def get_files_content(self, owner, repo, filenames, ref, max_workers=8):
        return {name: "print('x')\n" for name in filenames}

    # --- geriye dönük tekil erişimler (bazı testler hâlâ kullanabilir) ---
    def get_pr_diff(self, *a, **k):
        return self.diff

    def get_pr_details(self, *a, **k):
        return {"head": {"sha": self.head_sha}}

    def get_pr_files(self, *a, **k):
        return self.files

    def get_file_content(self, owner, repo, path, ref):
        return "print('x')\n"

    # --- yorum gönderimi ---
    def create_review(self, **kw):
        self.recorder["create_review"] = kw
        return {"id": 10, "state": "COMMENTED"}

    def post_pr_comment(self, **kw):
        self.recorder.setdefault("post_pr_comment", []).append(kw)
        return {"id": 1}

    def list_review_comments(self, *a, **k):
        return getattr(self, "existing_comments", [])


@pytest.fixture
def fake_github_client(monkeypatch):
    """
    main.GitHubAppClient'i FakeGitHubClient ile değiştirir ve son
    oluşturulan örneği (recorder erişimi için) yakalar.

    Kullanım:
        def test_x(fake_github_client, ...):
            holder = fake_github_client(diff=..., files=..., head_sha=...)
            asyncio.run(main._run_pr_review(...))
            assert "create_review" in holder.client.recorder
    """
    from app import main

    class Holder:
        client = None

    holder = Holder()

    def _factory(**overrides):
        class _Configured(FakeGitHubClient):
            pass
        for k, v in overrides.items():
            setattr(_Configured, k, v)

        def _make(installation_id):
            holder.client = _Configured(installation_id)
            return holder.client

        monkeypatch.setattr(main, "GitHubAppClient", _make)
        return holder

    return _factory


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
    config.addinivalue_line(
        "markers", "requires_semgrep: semgrep CLI kurulu olmasını gerektiren tests"
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

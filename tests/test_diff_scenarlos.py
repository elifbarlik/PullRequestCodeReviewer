"""
TEST 3: Different Diff Scenarios
- Küçük değişiklik (1-2 satır)
- Uzun dosya (1000+ satır değişiklik)
- Çoklu dosya (3+ dosya)
"""

import pytest
import sys
import os

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
from app.reviewer import review_diff, TokenManager, truncate_diff


class TestDiffScenarios:
    """Farklı diff senaryoları"""

    @pytest.fixture
    def small_diff(self):
        """Scenario 1: Küçük değişiklik (1 dosya, 2 satır)"""
        return """--- a/utils.py
+++ b/utils.py
@@ -1,3 +1,3 @@
 def add(a, b):
-    return a + b + 1
+    return a + b
"""

    @pytest.fixture
    def medium_diff(self):
        """Scenario 2: Orta boy değişiklik (1 dosya, 20 satır)"""
        diff_lines = ["--- a/app.py\n", "+++ b/app.py\n", "@@ -1,20 +1,25 @@\n"]
        for i in range(20):
            diff_lines.append(f" line {i}\n")
            if i == 10:
                diff_lines.append("+added line\n")
        return "".join(diff_lines)

    @pytest.fixture
    def large_diff(self):
        """Scenario 3: Büyük diff (1 dosya, 500+ satır)"""
        diff = """--- a/large_file.py
+++ b/large_file.py
@@ -1,500 +1,510 @@
"""
        for i in range(500):
            diff += f" line {i}\n"
            if i % 50 == 0:
                diff += f"+added at line {i}\n"
        return diff

    @pytest.fixture
    def multi_file_diff(self):
        """Scenario 4: Çoklu dosya (3 dosya)"""
        return """--- a/file1.py
+++ b/file1.py
@@ -1,3 +1,3 @@
 def func1():
-    pass
+    return True

--- a/file2.py
+++ b/file2.py
@@ -1,3 +1,3 @@
 def func2():
-    pass
+    return False

--- a/file3.py
+++ b/file3.py
@@ -1,3 +1,3 @@
 def func3():
-    pass
+    return None
"""

    # SCENARIO 1: Küçük diff
    def test_small_diff_success(self, small_diff):
        """Test: Küçük diff başarıyla işleniyor mu?"""
        result = review_diff(small_diff, review_types=["short_summary"])

        assert result["status"] == "success"
        assert "short_summary" in result["analyses"]
        assert not result["metadata"]["was_truncated"]

    def test_small_diff_fast(self, small_diff):
        """Test: Küçük diff tokenları az kullanıyor mu?"""
        result = review_diff(small_diff, review_types=["short_summary"])

        original = result["metadata"]["original_size"]
        processed = result["metadata"]["processed_size"]

        # Küçük diff kesilmemeli
        assert original == processed, "Small diff should not be truncated"

    # SCENARIO 2: Orta boy diff
    def test_medium_diff_success(self, medium_diff):
        """Test: Orta boy diff başarıyla işleniyor mu?"""
        result = review_diff(medium_diff, review_types=["short_summary"])

        assert result["status"] == "success"
        assert not result["metadata"]["was_truncated"]

    # SCENARIO 3: Büyük diff
    def test_large_diff_handled(self, large_diff):
        """Test: Büyük diff truncate ediliyor mu?"""
        result = review_diff(large_diff, review_types=["short_summary"])

        assert result["status"] == "success"
        # Büyük diff'ler truncate olabilir
        assert (
            result["metadata"]["processed_size"] <= TokenManager.get_max_diff_length()
        )

    def test_large_diff_summary_extraction(self, large_diff):
        """Test: Büyük diff önemli satırları koruyor mu?"""
        truncated = truncate_diff(large_diff)

        # Önemli markers korunmalı
        assert (
            "---" in truncated or "++" in truncated or "@@" in truncated
        ), "Important diff markers should be preserved"

    # SCENARIO 4: Çoklu dosya
    def test_multi_file_diff_success(self, multi_file_diff):
        """Test: Çoklu dosya diff başarıyla işleniyor mu?"""
        result = review_diff(multi_file_diff, review_types=["short_summary"])

        assert result["status"] == "success"
        assert "short_summary" in result["analyses"]

    def test_multi_file_diff_contains_file_info(self, multi_file_diff):
        """Test: Çoklu dosya diff dosya bilgisi içeriyor mu?"""
        # Diff'te 3 dosya var olmalı
        assert multi_file_diff.count("--- a/") == 3, "Should have 3 files"
        assert multi_file_diff.count("+++ b/") == 3, "Should have 3 file changes"

    # GENERAL TESTS
    def test_all_scenarios_return_valid_analyses(
        self, small_diff, medium_diff, large_diff, multi_file_diff
    ):
        """Test: Tüm scenario'lar valid analyses döndürüyor mu?"""
        scenarios = [
            ("small", small_diff),
            ("medium", medium_diff),
            ("large", large_diff),
            ("multi", multi_file_diff),
        ]

        for name, diff in scenarios:
            result = review_diff(diff, review_types=["short_summary"])

            assert result["status"] == "success", f"{name} diff failed"
            assert "analyses" in result, f"{name} diff missing analyses"
            assert (
                "short_summary" in result["analyses"]
            ), f"{name} diff missing short_summary"

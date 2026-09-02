"""
diff_utils.parse_added_lines testleri — Semgrep bulgu filtrelemesinin
temeli, bu yüzden edge case'ler (çoklu dosya, silme, context satırlar,
yeniden adlandırma) doğru işlenmeli.
"""

from app.diff_utils import parse_added_lines


SAMPLE_DIFF = """diff --git a/app/utils.py b/app/utils.py
index abc123..def456 100644
--- a/app/utils.py
+++ b/app/utils.py
@@ -10,6 +10,8 @@ def existing_function():
     x = 1
     y = 2
     return x + y
+
+def new_function(user_input):
+    os.system("echo " + user_input)
diff --git a/app/main.py b/app/main.py
index 111..222 100644
--- a/app/main.py
+++ b/app/main.py
@@ -1,4 +1,4 @@
 import os
-print("old")
+print("new")
 def foo():
     pass
"""


class TestParseAddedLines:
    def test_finds_added_file(self):
        result = parse_added_lines(SAMPLE_DIFF)
        assert "app/utils.py" in result
        assert "app/main.py" in result

    def test_new_function_lines_are_added(self):
        result = parse_added_lines(SAMPLE_DIFF)
        # @@ -10,6 +10,8 @@ -> yeni dosyada satır 10'dan başlar
        # context: 10,11,12 (x=1,y=2,return) -> 13 bos satir -> 14 def -> 15 os.system
        assert 14 in result["app/utils.py"]
        assert 15 in result["app/utils.py"]

    def test_context_lines_not_marked_added(self):
        result = parse_added_lines(SAMPLE_DIFF)
        # satır 10,11,12 context (değişmemiş) - eklenen olarak sayılmamalı
        assert 10 not in result["app/utils.py"]
        assert 11 not in result["app/utils.py"]

    def test_replaced_line_counted_as_added(self):
        result = parse_added_lines(SAMPLE_DIFF)
        # print("new") eski print("old")'un yerini aldı -> satır 2 eklendi sayılır
        assert 2 in result["app/main.py"]

    def test_unchanged_context_in_second_file_not_added(self):
        result = parse_added_lines(SAMPLE_DIFF)
        # "import os" (satır 1) context, değişmedi
        assert 1 not in result["app/main.py"]

    def test_no_files_for_empty_diff(self):
        assert parse_added_lines("") == {}

    def test_deleted_file_only_diff(self):
        deleted_diff = """diff --git a/old.py b/old.py
deleted file mode 100644
index abc..000
--- a/old.py
+++ /dev/null
@@ -1,2 +0,0 @@
-x = 1
-y = 2
"""
        result = parse_added_lines(deleted_diff)
        # /dev/null hedefi olan dosyalar icin eklenen satir olamaz
        assert result == {}

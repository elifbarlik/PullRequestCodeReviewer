"""
TEST 1: Local Review Endpoint Test
- Örnek diff'i /local-review'a gönder
- Response schema'sını kontrol et
- Parse başarısını doğrula
"""

import pytest
import sys
import os

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
from app.reviewer import review_diff, truncate_diff


class TestLocalReview:
    """Local review endpoint testleri"""

    @pytest.fixture
    def sample_diff(self):
        """Basit tests diff"""
        return """--- a/app.py
                +++ b/app.py
                @@ -1,3 +1,4 @@
                 def hello():
                -    print("hi")
                +    print("hello world")
                +    return True
                """

    @pytest.fixture
    def expected_response_keys(self):
        """Beklenen response anahtarları"""
        return {"status": str, "analyses": dict, "metadata": dict}

    def test_response_has_required_keys(self, sample_diff, expected_response_keys):
        """Test: Response zorunlu anahtarları içeriyor mu?"""
        result = review_diff(sample_diff, review_types=["short_summary"])

        # Check required keys
        for key, expected_type in expected_response_keys.items():
            assert key in result, f"Missing key: {key}"
            assert isinstance(
                result[key], expected_type
            ), f"Key {key} should be {expected_type}, got {type(result[key])}"

    def test_status_is_success(self, sample_diff):
        """Test: Status 'success' mi?"""
        result = review_diff(sample_diff, review_types=["short_summary"])
        assert (
            result["status"] == "success"
        ), f"Expected status 'success', got {result['status']}"

    def test_analyses_has_short_summary(self, sample_diff):
        """Test: Analyses kısmında short_summary var mı?"""
        result = review_diff(sample_diff, review_types=["short_summary"])

        assert "short_summary" in result["analyses"], "short_summary not in analyses"
        assert isinstance(
            result["analyses"]["short_summary"], dict
        ), "short_summary should be a dict"

    def test_short_summary_has_required_fields(self, sample_diff):
        """Test: short_summary zorunlu alanları içeriyor mu?"""
        result = review_diff(sample_diff, review_types=["short_summary"])
        summary = result["analyses"]["short_summary"]

        required_fields = ["summary", "severity", "type"]
        for field in required_fields:
            assert field in summary, f"Missing field in short_summary: {field}"

    def test_metadata_has_truncation_info(self, sample_diff):
        """Test: Metadata truncation bilgisi içeriyor mu?"""
        result = review_diff(sample_diff, review_types=["short_summary"])
        metadata = result["metadata"]

        required_fields = ["original_size", "processed_size", "was_truncated"]
        for field in required_fields:
            assert field in metadata, f"Missing field in metadata: {field}"

    def test_small_diff_not_truncated(self, sample_diff):
        """Test: Küçük diff kesilmiyor mu?"""
        result = review_diff(sample_diff, review_types=["short_summary"])
        assert (
            result["metadata"]["was_truncated"] == False
        ), "Small diff should not be truncated"

    def test_diff_size_tracking(self, sample_diff):
        """Test: Diff boyutları doğru kaydediliyor mu?"""
        result = review_diff(sample_diff, review_types=["short_summary"])

        original = result["metadata"]["original_size"]
        processed = result["metadata"]["processed_size"]

        assert original == len(sample_diff), "Original size mismatch"
        assert processed <= original, "Processed size cannot exceed original"

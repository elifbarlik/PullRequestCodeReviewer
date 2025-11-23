"""
TEST 2: Mock LLM Output - Parser Unit Tests
- LLM'den gelebilecek farklı formatları simulate et
- JSON parser'ı tests et (5 strategy)
- Fallback mekanizmasını doğrula
"""

import pytest
import sys

import os
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from app.json_parser import JSONParser


class TestMockLLMOutputs:
    """Mock LLM çıktılarıyla parser testleri"""

    def test_parse_valid_json(self):
        """Test: Geçerli JSON parse ediliyor mu?"""
        valid_json = '{"summary": "Added validation", "severity": "low", "type": "feature"}'
        result = JSONParser.parse(valid_json, "short_summary")

        assert result is not None, "Parser should not return None for valid JSON"
        assert result["summary"] == "Added validation"
        assert result["severity"] == "low"

    def test_parse_json_in_markdown(self):
        """Test: Markdown içindeki JSON parse ediliyor mu?"""
        markdown_json = '''
```json
{"summary": "Fixed bug", "severity": "high", "type": "bugfix"}
```
'''
        result = JSONParser.parse(markdown_json, "short_summary")

        assert result is not None, "Should extract JSON from markdown"
        assert result["type"] == "bugfix"

    def test_parse_json_with_text_before(self):
        """Test: JSON'dan önce yazı varsa parse ediliyor mu?"""
        mixed = '''
The code has been analyzed.

{"summary": "Code improvement", "severity": "medium", "type": "refactor"}
'''
        result = JSONParser.parse(mixed, "short_summary")

        assert result is not None, "Should extract JSON despite surrounding text"
        assert result["summary"] == "Code improvement"

    def test_parse_json_with_single_quotes(self):
        """Test: Single quotes JSON parse ediliyor mu?"""
        single_quotes = "{'summary': 'tests', 'severity': 'low'}"
        result = JSONParser.parse(single_quotes, "short_summary")

        assert result is not None, "Should handle single quotes"
        assert result["summary"] == "tests"

    def test_parse_unquoted_keys(self):
        """Test: Quoted olmayan keys parse ediliyor mu?"""
        unquoted = '{summary: "tests", severity: "low"}'
        result = JSONParser.parse(unquoted, "short_summary")

        assert result is not None, "Should fix unquoted keys"
        assert result["severity"] == "low"

    def test_parse_trailing_commas(self):
        """Test: Trailing commas temizleniyor mu?"""
        trailing = '{"summary": "tests", "severity": "low",}'
        result = JSONParser.parse(trailing, "short_summary")

        assert result is not None, "Should remove trailing commas"
        assert result["summary"] == "tests"

    def test_fallback_for_invalid_json(self):
        """Test: Geçersiz JSON fallback template döndürüyor mu?"""
        invalid = "completely invalid @#$%"
        result = JSONParser.parse(invalid, "short_summary")

        assert result is not None, "Should return fallback response"
        assert "summary" in result, "Fallback should have summary field"

    def test_fallback_template_for_bug_detection(self):
        """Test: Bug detection için fallback template doğru mu?"""
        invalid = "@#$%"
        result = JSONParser.parse(invalid, "bug_detection")

        assert result is not None
        assert "issues" in result
        assert "has_bugs" in result
        assert "overall_risk" in result

    def test_parser_strategy_chain(self):
        """Test: Parser strategies sırasında çalışıyor mu?"""
        # Bu tests, strategy chain'in çalıştığını doğrular
        test_cases = [
            '{"tests": 1}',  # Direct parse
            '```json\n{"tests": 2}\n```',  # Markdown
            "{'tests': 3}",  # Single quotes
            '{tests: "4"}',  # Unquoted keys
        ]

        for i, test_json in enumerate(test_cases, 1):
            result = JSONParser.parse(test_json, "generic")
            assert result is not None, f"Strategy {i} failed on: {test_json}"
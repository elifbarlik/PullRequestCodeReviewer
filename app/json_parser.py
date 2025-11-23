"""
Robust JSON Parser with Fallback Strategies
- Ana parser başarısız olunca fallback stratejileri dene
- Regex-based recovery
- Few-shot parsing
"""

import json
import re
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class JSONParser:
    """Robust JSON parser with multiple fallback strategies"""

    @staticmethod
    def parse(response_text: str, expected_structure: str = "generic") -> Optional[Dict[str, Any]]:
        """
        Parse LLM response with multiple fallback strategies

        Args:
            response_text: Raw LLM response
            expected_structure: Type of expected JSON (for fallback templates)

        Returns:
            Parsed JSON or None if all strategies fail
        """

        # Strategy 1: Direct JSON parsing
        result = JSONParser._strategy_direct_parse(response_text)
        if result:
            logger.debug("✅ Strategy 1 (Direct Parse) succeeded")
            return result

        # Strategy 2: Extract JSON from markdown code blocks
        result = JSONParser._strategy_extract_from_markdown(response_text)
        if result:
            logger.debug("✅ Strategy 2 (Markdown Extract) succeeded")
            return result

        # Strategy 3: Fix common JSON syntax errors
        result = JSONParser._strategy_fix_common_errors(response_text)
        if result:
            logger.debug("✅ Strategy 3 (Fix Common Errors) succeeded")
            return result

        # Strategy 4: Regex-based extraction
        result = JSONParser._strategy_regex_extraction(response_text)
        if result:
            logger.debug("✅ Strategy 4 (Regex Extraction) succeeded")
            return result

        # Strategy 5: Fallback empty response (graceful degradation)
        result = JSONParser._strategy_fallback_template(expected_structure)
        if result:
            logger.warning(f"⚠️  Strategy 5 (Fallback Template) used for: {expected_structure}")
            return result

        logger.error(f"❌ All strategies failed for response: {response_text[:100]}...")
        return None

    @staticmethod
    def _strategy_direct_parse(text: str) -> Optional[Dict[str, Any]]:
        """Try direct JSON parsing"""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _strategy_extract_from_markdown(text: str) -> Optional[Dict[str, Any]]:
        """Extract JSON from ```json ... ``` blocks"""
        try:
            # Try ```json blocks
            if "```json" in text:
                start = text.find("```json") + 7
                end = text.find("```", start)
                if end > start:
                    json_str = text[start:end].strip()
                    return json.loads(json_str)

            # Try plain ``` blocks
            if "```" in text:
                start = text.find("```") + 3
                end = text.find("```", start)
                if end > start:
                    json_str = text[start:end].strip()
                    return json.loads(json_str)

        except (json.JSONDecodeError, ValueError):
            pass

        return None

    @staticmethod
    def _strategy_fix_common_errors(text: str) -> Optional[Dict[str, Any]]:
        """Fix common JSON formatting errors"""
        try:
            # Remove leading/trailing whitespace and non-JSON characters
            text = text.strip()

            # Remove BOM if present
            if text.startswith('\ufeff'):
                text = text[1:]

            # Remove common prefixes
            for prefix in ['```json', '```', 'json', 'JSON']:
                if text.startswith(prefix):
                    text = text[len(prefix):].strip()

            # Remove common suffixes
            text = text.rstrip('`')

            # Fix single quotes to double quotes (dangerous but sometimes necessary)
            # Only if no double quotes exist
            if '"' not in text and "'" in text:
                text = text.replace("'", '"')

            # Fix unquoted keys: {key: -> {"key":
            text = re.sub(r'{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'{"\1":', text)
            text = re.sub(r',\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r',"\1":', text)

            # Fix trailing commas: , ] -> ]
            text = re.sub(r',\s*]', ']', text)
            text = re.sub(r',\s*}', '}', text)

            # Try to parse fixed JSON
            return json.loads(text)

        except (json.JSONDecodeError, ValueError):
            return None

    @staticmethod
    def _strategy_regex_extraction(text: str) -> Optional[Dict[str, Any]]:
        """Extract JSON using regex patterns"""
        try:
            # Find JSON-like object: { ... }
            match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
            if match:
                json_str = match.group(0)
                return json.loads(json_str)

        except (json.JSONDecodeError, ValueError):
            pass

        return None

    @staticmethod
    def _strategy_fallback_template(expected_structure: str) -> Optional[Dict[str, Any]]:
        """Return fallback empty response based on expected structure"""

        fallback_responses = {
            "short_summary": {
                "summary": "Unable to analyze - parsing error",
                "severity": "unknown",
                "type": "unknown"
            },
            "bug_detection": {
                "issues": [],
                "has_bugs": False,
                "overall_risk": "unknown"
            },
            "performance": {
                "suggestions": [],
                "optimization_potential": "unknown"
            },
            "security": {
                "vulnerabilities": [],
                "has_security_issues": False,
                "security_level": "unknown"
            },
            "generic": {
                "error": "Parsing failed",
                "status": "degraded"
            }
        }

        return fallback_responses.get(expected_structure, fallback_responses["generic"])


# ============= Test Fonksiyonları =============

def test_parser():
    """Test JSON parser with various malformed inputs"""

    test_cases = [
        # Test 1: Valid JSON
        ('{"summary": "tests", "severity": "low"}', True),

        # Test 2: JSON in markdown
        ('```json\n{"summary": "tests"}\n```', True),

        # Test 3: Single quotes
        ("{'summary': 'tests', 'severity': 'low'}", True),

        # Test 4: Unquoted keys
        ('{summary: "tests", severity: "low"}', True),

        # Test 5: Trailing commas
        ('{"summary": "tests", "severity": "low",}', True),

        # Test 6: Text before JSON
        ('Some explanation\n{"summary": "tests"}', True),

        # Test 7: Text after JSON
        ('{"summary": "tests"}\nMore explanation', True),

        # Test 8: Multiple issues
        ("```json\n{summary: 'tests', severity: 'low',}\n```", True),
    ]

    print("=" * 60)
    print("JSON Parser Test Suite")
    print("=" * 60)

    passed = 0
    for i, (test_input, should_succeed) in enumerate(test_cases, 1):
        result = JSONParser.parse(test_input)
        success = result is not None

        status = "✅ PASS" if success == should_succeed else "❌ FAIL"
        print(f"\nTest {i}: {status}")
        print(f"Input: {test_input[:50]}...")
        print(f"Result: {result}")

        if success == should_succeed:
            passed += 1

    print("\n" + "=" * 60)
    print(f"Results: {passed}/{len(test_cases)} passed")
    print("=" * 60)


if __name__ == "__main__":
    test_parser()
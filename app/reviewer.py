import json
from typing import Dict, Any, Optional
from app.prompts import get_prompt


def call_llm(prompt: str, prompt_name: str = "SHORT_SUMMARY") -> str:
    """LLM'ye istek gönder ve JSON cevap al (şimdilik mock)"""

    mock_responses = {
        "SHORT_SUMMARY": {
            "summary": "Bu değişiklik yeni bir doğrulama fonksiyonu ekledi",
            "severity": "low",
            "type": "feature"
        },
        "BUG_DETECTION": {
            "issues": [
                {
                    "file": "auth.py",
                    "line": 42,
                    "severity": "medium",
                    "description": "Burada None değeri kontrol edilmiyor",
                    "suggestion": "if user is not None: ekle"
                }
            ],
            "has_bugs": True,
            "overall_risk": "medium"
        },
        "PERFORMANCE_REVIEW": {
            "suggestions": [
                {
                    "file": "utils.py",
                    "line": 15,
                    "issue": "Döngü O(n²) karmaşıklığında çalışıyor",
                    "recommendation": "Set veri yapısı kullan"
                }
            ],
            "optimization_potential": "high"
        },
        "SECURITY_REVIEW": {
            "vulnerabilities": [],
            "has_security_issues": False,
            "security_level": "safe"
        }
    }

    response = mock_responses.get(prompt_name, mock_responses["SHORT_SUMMARY"])
    return json.dumps(response, ensure_ascii=False)


def parse_llm_response(response_text: str) -> Optional[Dict[str, Any]]:
    """LLM'nin JSON cevabını parse et"""
    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        return None


def review_diff(diff_text: str, review_types: list = None) -> Dict[str, Any]:
    """Diff'i analiz et"""

    if review_types is None:
        review_types = ["short_summary", "bug_detection"]

    results = {"status": "success", "analyses": {}}

    prompt_mapping = {
        "short_summary": "SHORT_SUMMARY",
        "bug_detection": "BUG_DETECTION",
        "performance": "PERFORMANCE_REVIEW",
        "security": "SECURITY_REVIEW"
    }

    for review_type in review_types:
        if review_type not in prompt_mapping:
            continue

        prompt_name = prompt_mapping[review_type]
        prompt = get_prompt(prompt_name, diff_text=diff_text)
        llm_response = call_llm(prompt, prompt_name)
        parsed = parse_llm_response(llm_response)

        if parsed:
            results["analyses"][review_type] = parsed
        else:
            results["analyses"][review_type] = {"error": "Parse hatası"}

    return results


def truncate_diff(diff_text: str, max_length: int = 4000) -> str:
    """Çok uzun diff'leri kırıp max_length'e sığdır"""
    if len(diff_text) <= max_length:
        return diff_text

    truncated = diff_text[:max_length]
    truncated += "\n\n[... Diff çok uzun, kesildi ...]"
    return truncated
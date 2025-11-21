import json
from typing import Dict, Any, Optional
from app.prompts import get_prompt
from dotenv import load_dotenv
import os
import google.generativeai as genai

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))


def call_llm(prompt: str, prompt_name: str = "SHORT_SUMMARY", max_tokens: int = 500) -> str:
    """Gemini API'ye çağrı yap ve JSON cevap al"""

    try:
        model = genai.GenerativeModel("gemini-2.0-flash")
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=max_tokens,
                temperature=0.5,
            )
        )
        return response.text.strip()

    except Exception as e:
        raise Exception(f"LLM çağrısı başarısız: {str(e)}")


def parse_llm_response(response_text: str) -> Optional[Dict[str, Any]]:
    """LLM cevabını parse et, JSON dışı kısımları temizle"""

    try:
        # JSON'ı çıkart (```json ... ``` içindeyse)
        if "```json" in response_text:
            start = response_text.find("```json") + 7
            end = response_text.find("```", start)
            json_str = response_text[start:end].strip()
        elif "```" in response_text:
            start = response_text.find("```") + 3
            end = response_text.find("```", start)
            json_str = response_text[start:end].strip()
        else:
            json_str = response_text

        return json.loads(json_str)

    except json.JSONDecodeError:
        return None


def extract_diff_summary(diff_text: str, max_lines: int = 30) -> str:
    """Diff'ten önemli satırları ayıkla (sadece değişen kısımlar)"""

    lines = diff_text.split("\n")
    important_lines = []

    for line in lines:
        if line.startswith("+") or line.startswith("-"):
            important_lines.append(line)
        elif line.startswith("@@"):
            important_lines.append(line)

    # İlk max_lines'ı al
    important = important_lines[:max_lines]
    return "\n".join(important)


def truncate_diff(diff_text: str, max_length: int = 3000) -> str:
    """Diff'i çok uzunsa kırp, önemli satırları al"""

    if len(diff_text) <= max_length:
        return diff_text

    # Önemli satırları ayıkla
    summary = extract_diff_summary(diff_text, max_lines=20)

    if len(summary) <= max_length:
        return summary

    # Hala çok uzunsa sondan kes
    return summary[:max_length] + "\n[... Kesildi ...]"


def review_diff(diff_text: str, review_types: list = None) -> Dict[str, Any]:
    """Diff'i gerçek LLM ile analiz et"""

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

        try:
            prompt_name = prompt_mapping[review_type]
            prompt = get_prompt(prompt_name, diff_text=diff_text)
            llm_response = call_llm(prompt, prompt_name)
            parsed = parse_llm_response(llm_response)

            if parsed:
                results["analyses"][review_type] = parsed
            else:
                results["analyses"][review_type] = {"error": "Parse hatası", "raw": llm_response[:200]}

        except Exception as e:
            results["analyses"][review_type] = {"error": str(e)}

    return results
"""
Enhanced PR Reviewer with:
1. Robust JSON parsing (fallback strategies)
2. Token limit management
3. Two-stage analysis (summary → detail)
4. Improved LLM error handling
"""

import json
import logging
from typing import Dict, Any, Optional, List
from app.prompts import get_prompt, get_prompt_config
from app.json_parser import JSONParser
from dotenv import load_dotenv
import os
from google import genai
from google.genai import types

load_dotenv()

# Gemini client lazy oluşturulur (import anında GEMINI_API_KEY zorunlu olmasın —
# testler ve tooling'in .env'siz de import edilebilmesi için).
_gemini_client: Optional["genai.Client"] = None


def _get_gemini_client() -> "genai.Client":
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    return _gemini_client

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============= TOKEN MANAGEMENT =============


class TokenManager:
    """Manage token limits for LLM calls"""

    # Rough estimates (Gemini token counts)
    TOKENS_PER_CHAR = 0.25  # ~4 chars = 1 token (rough estimate)

    # Model limits
    MAX_INPUT_TOKENS = 30000  # Safe limit for Gemini
    MAX_OUTPUT_TOKENS = 2000
    BUFFER_TOKENS = 500  # Safety buffer

    # Reserved tokens
    RESERVED_FOR_PROMPT = 2000  # Prompt template tokens
    RESERVED_FOR_OUTPUT = 1000  # Output tokens

    @classmethod
    def estimate_tokens(cls, text: str) -> int:
        """Rough token estimation"""
        return max(1, int(len(text) * cls.TOKENS_PER_CHAR))

    @classmethod
    def get_max_diff_length(cls) -> int:
        """Calculate max diff length based on model limits"""
        available = cls.MAX_INPUT_TOKENS - cls.RESERVED_FOR_PROMPT - cls.BUFFER_TOKENS
        max_chars = int(available / cls.TOKENS_PER_CHAR)
        return max_chars

    @classmethod
    def should_truncate(cls, diff_text: str) -> bool:
        """Check if diff should be truncated"""
        token_count = cls.estimate_tokens(diff_text)
        return token_count > cls.get_max_diff_length()


def extract_diff_summary(diff_text: str, max_lines: int = 30) -> str:
    """Extract important lines from diff (+ and - lines only)"""

    lines = diff_text.split("\n")
    important_lines = []

    for line in lines:
        # Keep file headers and change markers
        if line.startswith("+++") or line.startswith("---"):
            important_lines.append(line)
        elif line.startswith("@@"):
            important_lines.append(line)
        elif line.startswith("+") or line.startswith("-"):
            important_lines.append(line)

    # Take first max_lines
    important = important_lines[:max_lines]
    return "\n".join(important)


def truncate_diff(diff_text: str, max_length: int = None) -> str:
    """
    Intelligently truncate diff while preserving important information

    Args:
        diff_text: Original diff
        max_length: Maximum length (uses TokenManager if None)

    Returns:
        Truncated diff
    """

    if max_length is None:
        max_length = TokenManager.get_max_diff_length()

    # Already short enough
    if len(diff_text) <= max_length:
        logger.info(f"✅ Diff size OK: {len(diff_text)} chars")
        return diff_text

    logger.warning(f"⚠️  Diff too long ({len(diff_text)} chars), truncating...")

    # Try to extract important lines first
    summary = extract_diff_summary(diff_text, max_lines=20)

    if len(summary) <= max_length:
        logger.info(f"✅ Summary fits: {len(summary)} chars")
        return summary

    # Still too long - cut from the end
    logger.warning(f"⚠️  Summary still too long ({len(summary)} chars), cutting...")
    truncated = (
        summary[: max_length - 50] + "\n[... Diff truncated due to size limits ...]"
    )

    return truncated


# ============= LLM CALLING WITH ERROR HANDLING =============


def call_llm(
    prompt: str,
    prompt_name: str = "SHORT_SUMMARY",
    max_tokens: int = 500,
    temperature: float = 0.1,
    use_json_mode: bool = True,
) -> str:
    """
    Gemini API çağrısı — hata yönetimiyle.

    use_json_mode=True  → response_mime_type='application/json' (detaylı analizler için)
    use_json_mode=False → serbest metin modu (kısa özet için, güvenlik filtresi sorunu yok)
    """
    try:
        gen_config_kwargs = {
            "max_output_tokens": max_tokens,
            "temperature": temperature,
            # gemini-2.5-flash bir "thinking" modeli — thinking_budget=0
            # olmadan max_output_tokens'ın bir kısmı görünmeyen düşünme
            # adımına gidiyor (bkz. Faz 1 doğrulamasındaki short_summary
            # kırpılması buggu). Bu görevlerin hiçbiri derin akıl yürütme
            # gerektirmiyor (sınıflandırma / yapılandırılmış çıkarım),
            # o yüzden thinking tamamen kapatılıyor: daha hızlı + daha ucuz.
            "thinking_config": types.ThinkingConfig(thinking_budget=0),
        }
        if use_json_mode:
            gen_config_kwargs["response_mime_type"] = "application/json"

        logger.info(f"📤 LLM çağrısı: {prompt_name} (max_tokens={max_tokens}, json_mode={use_json_mode})")
        response = _get_gemini_client().models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(**gen_config_kwargs),
        )

        response_text = (response.text or "").strip()
        if not response_text:
            raise Exception("Gemini boş yanıt döndürdü")

        logger.info(f"📥 Yanıt alındı ({len(response_text)} karakter)")
        return response_text

    except Exception as e:
        logger.error(f"❌ LLM çağrısı başarısız: {str(e)}")
        raise Exception(f"LLM call failed for {prompt_name}: {str(e)}")


def parse_llm_response(
    response_text: str, expected_type: str
) -> Optional[Dict[str, Any]]:
    """
    Parse LLM response using robust parser with fallback strategies

    Args:
        response_text: Raw LLM response
        expected_type: Expected response type (for fallback templates)

    Returns:
        Parsed JSON dict or None
    """

    try:
        result = JSONParser.parse(response_text, expected_type)

        if result:
            logger.info(f"✅ Parse successful: {expected_type}")
            return result
        else:
            logger.error(f"❌ Parse failed for {expected_type} — ham yanıt: {repr(response_text)}")
            return None

    except Exception as e:
        logger.error(f"❌ Parse exception: {str(e)}")
        return None


# ============= TWO-STAGE ANALYSIS =============


def analyze_diff_stage1(diff_text: str) -> Optional[Dict[str, Any]]:
    """
    Stage 1: Quick summary analysis (fast, low tokens)

    Returns:
        {summary, severity, type} or None
    """

    try:
        # Truncate for quick analysis
        short_diff = truncate_diff(diff_text, max_length=1000)

        prompt_name = "SHORT_SUMMARY"
        prompt = get_prompt(prompt_name, diff_text=short_diff)
        config = get_prompt_config(prompt_name)

        response = call_llm(
            prompt, prompt_name,
            config["max_tokens"],
            config.get("temperature", 0.1),
            use_json_mode=False,   # kısa özet: serbest metin modu
        )
        logger.info(f"🔎 SHORT_SUMMARY ham yanıt ({len(response)} karakter): {repr(response)}")
        result = parse_llm_response(response, "short_summary")

        return result

    except Exception as e:
        logger.error(f"Stage 1 failed: {str(e)}")
        return None


def analyze_diff_stage2(diff_text: str, review_types: List[str]) -> Dict[str, Any]:
    """
    Stage 2: Detailed analysis (can use more tokens)

    Returns:
        {bug_detection, security, performance, etc}
    """

    results = {}

    prompt_mapping = {
        "bug_detection": "BUG_DETECTION",
        "performance": "PERFORMANCE_REVIEW",
        "security": "SECURITY_REVIEW",
    }

    for review_type in review_types:
        if review_type not in prompt_mapping:
            continue

        try:
            # Use full diff for detailed analysis
            full_diff = truncate_diff(
                diff_text, max_length=TokenManager.get_max_diff_length()
            )

            prompt_name = prompt_mapping[review_type]
            prompt = get_prompt(prompt_name, diff_text=full_diff)
            config = get_prompt_config(prompt_name)

            response = call_llm(prompt, prompt_name, config["max_tokens"], config.get("temperature", 0.1))
            result = parse_llm_response(response, review_type)

            if result:
                results[review_type] = result
            else:
                # Fallback response
                results[review_type] = JSONParser._strategy_fallback_template(
                    review_type
                )

        except Exception as e:
            logger.error(f"Stage 2 ({review_type}) failed: {str(e)}")
            results[review_type] = {"error": str(e), "status": "failed"}

    return results


# ============= SEMGREP BULGU AÇIKLAMASI (Faz 0 hibrit mimari) =============

_SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def explain_security_findings(
    findings: List[Dict[str, Any]], diff_text: str
) -> Dict[str, Any]:
    """
    Semgrep'in deterministik olarak bulduğu güvenlik açıklarını Türkçe ve
    öğretici bir açıklamaya çevirir. Gemini burada açık ARAMAZ — sadece
    zaten bulunmuş olanı açıklar. Bulgunun varlığı/önem derecesi Semgrep'ten
    gelir ve DEĞİŞTİRİLMEZ; Gemini yalnızca description/recommendation üretir.

    Gemini çağrısı başarısız olsa veya JSON parse edilemese bile, gerçek
    Semgrep bulguları asla sessizce kaybolmaz — açıklama üretilemeyen
    bulgular ham Semgrep mesajıyla (fallback) raporlanır.

    Args:
        findings: semgrep_scanner.scan_diff() çıktısı — her biri
                  {file, line, end_line, rule_id, severity, message, cwe, owasp}
        diff_text: Bağlam için PR diff'i

    Returns:
        {vulnerabilities: [...], has_security_issues: bool, security_level: str}
    """
    if not findings:
        return {
            "vulnerabilities": [],
            "has_security_issues": False,
            "security_level": "safe",
        }

    findings_json = json.dumps(
        [
            {
                "index": i,
                "file": f["file"],
                "line": f["line"],
                "rule_id": f["rule_id"],
                "severity": f["severity"],
                "semgrep_message": f["message"],
            }
            for i, f in enumerate(findings)
        ],
        ensure_ascii=False,
    )

    explanations_by_index: Dict[int, dict] = {}
    try:
        prompt = get_prompt(
            "SECURITY_EXPLAIN",
            findings_json=findings_json,
            diff_text=truncate_diff(diff_text, max_length=2000),
        )
        config = get_prompt_config("SECURITY_EXPLAIN")
        response = call_llm(
            prompt, "SECURITY_EXPLAIN", config["max_tokens"], config.get("temperature", 0.2)
        )
        parsed = parse_llm_response(response, "security_explain")
        if parsed and isinstance(parsed.get("explanations"), list):
            for item in parsed["explanations"]:
                idx = item.get("index")
                if isinstance(idx, int):
                    explanations_by_index[idx] = item
    except Exception as e:
        logger.error(f"❌ Security explain (Gemini) başarısız, ham Semgrep mesajlarıyla devam: {e}")

    vulnerabilities = []
    worst_severity = "low"
    for i, f in enumerate(findings):
        exp = explanations_by_index.get(i, {})
        description = exp.get("description") or f"(Otomatik açıklama üretilemedi) {f['message']}"
        recommendation = exp.get("recommendation") or "Bu bulguyu manuel olarak inceleyin."

        vulnerabilities.append(
            {
                "file": f["file"],
                "line": f["line"],
                "risk": f["severity"],
                "type": f["rule_id"].rsplit(".", 1)[-1],
                "description": description,
                "recommendation": recommendation,
            }
        )
        if _SEVERITY_RANK.get(f["severity"], 0) > _SEVERITY_RANK.get(worst_severity, 0):
            worst_severity = f["severity"]

    return {
        "vulnerabilities": vulnerabilities,
        "has_security_issues": True,
        "security_level": worst_severity,
    }


def build_security_result(security_scan: Optional[Dict[str, Any]], diff_text: str) -> Dict[str, Any]:
    """
    main.py'den gelen Semgrep tarama sonucunu ("status": ok/unavailable/error)
    review_diff'in beklediği security analiz sonucuna çevirir.

    ÖNEMLİ: "unavailable" veya "error" durumunda ASLA "safe" DENMEZ — bir
    güvenlik aracının tarama yapamadığı halde "güvenli" demesi, hiç tarama
    yapmamaktan daha kötü bir yanlış güven duygusu yaratır. Bunun yerine
    scan_error alanıyla şeffaf şekilde raporlanır (bkz. main.py yorum formatı).
    """
    status = security_scan.get("status") if security_scan else "unavailable"

    if status == "ok":
        return explain_security_findings(security_scan.get("findings") or [], diff_text)

    return {
        "vulnerabilities": [],
        "has_security_issues": False,
        "security_level": "unknown",
        "scan_error": security_scan.get("error", "Güvenlik taraması yapılamadı") if security_scan else "Güvenlik taraması yapılamadı",
    }


# ============= MAIN ANALYSIS FUNCTION =============


def review_diff(
    diff_text: str,
    review_types: List[str] = None,
    security_scan: Optional[Dict[str, Any]] = None,
    precomputed_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Analyze diff using two-stage approach:
    1. Quick summary (always)
    2. Detailed analysis (on demand)

    Args:
        diff_text: Code diff text
        review_types: List of analysis types to perform
                     ["short_summary", "bug_detection", "performance", "security"]
        security_scan: main.py'nin Semgrep tarama sonucu — {"status": "ok",
                       "findings": [...]} / {"status": "unavailable"|"error",
                       "error": "..."}. None ise (örn. /local-review — gerçek
                       dosya erişimi olmadığı için Semgrep çalıştırılamaz)
                       "security" eski LLM-tabanlı SECURITY_REVIEW'a düşer.
        precomputed_summary: Faz 4.4 — çağıran taraf (main._run_pr_review)
                       stage 1 (short_summary) analizini Semgrep'le PARALEL
                       çalıştırıp sonucu buraya verir. Verilmişse burada
                       tekrar LLM çağrısı yapılmaz. None ise stage 1 burada
                       çalışır (eski davranış, /local-review vb.).

    Returns:
        Analysis results with metadata
    """

    if review_types is None:
        review_types = ["short_summary", "bug_detection"]

    logger.info(f"🔍 Review starting: {review_types}")

    # Prepare diff
    processed_diff = truncate_diff(diff_text)

    results = {
        "status": "success",
        "analyses": {},
        "metadata": {
            "original_size": len(diff_text),
            "processed_size": len(processed_diff),
            "was_truncated": len(processed_diff) < len(diff_text),
            "stages_completed": [],
        },
    }

    # Stage 1: Always do summary
    if "short_summary" in review_types:
        if precomputed_summary is not None:
            logger.info("📊 Stage 1: özet dışarıdan verildi (paralel çalıştırılmış)")
            stage1_result = precomputed_summary
        else:
            logger.info("📊 Stage 1: Summary analysis...")
            stage1_result = analyze_diff_stage1(processed_diff)

        if stage1_result:
            results["analyses"]["short_summary"] = stage1_result
            results["metadata"]["stages_completed"].append("stage1_summary")
            logger.info("✅ Stage 1 completed")
        else:
            results["analyses"]["short_summary"] = {
                "summary": "Analysis failed",
                "severity": "unknown",
                "type": "unknown",
            }

    # Stage 2: Detailed analysis
    detail_types = [rt for rt in review_types if rt != "short_summary"]

    # "security", Semgrep tarama sonucu VERİLDİYSE (webhook akışı) hibrit
    # açıklama yoluna gider; verilmediyse (örn. /local-review) eski
    # LLM-only SECURITY_REVIEW'a düşer — aşağıdaki analyze_diff_stage2 listesinde kalır.
    if "security" in detail_types and security_scan is not None:
        detail_types = [rt for rt in detail_types if rt != "security"]
        results["analyses"]["security"] = build_security_result(security_scan, processed_diff)
        results["metadata"]["stages_completed"].append("security_semgrep")

    if detail_types:
        logger.info(f"🔬 Stage 2: Detailed analysis ({detail_types})...")
        stage2_results = analyze_diff_stage2(processed_diff, detail_types)
        results["analyses"].update(stage2_results)
        results["metadata"]["stages_completed"].append("stage2_detail")
        logger.info("✅ Stage 2 completed")

    logger.info(f"✅ Review complete: {len(results['analyses'])} analyses done")

    return results


# ============= STATISTICS TRACKING =============


class ParseStatistics:
    """Track parsing success rate"""

    total_attempts = 0
    successful_parses = 0
    failed_parses = 0

    @classmethod
    def record_attempt(cls, success: bool):
        cls.total_attempts += 1
        if success:
            cls.successful_parses += 1
        else:
            cls.failed_parses += 1

    @classmethod
    def get_success_rate(cls) -> float:
        if cls.total_attempts == 0:
            return 0.0
        return (cls.successful_parses / cls.total_attempts) * 100

    @classmethod
    def print_stats(cls):
        rate = cls.get_success_rate()
        print("\n" + "=" * 60)
        print("📊 JSON Parser Statistics")
        print("=" * 60)
        print(f"Total attempts: {cls.total_attempts}")
        print(f"Successful: {cls.successful_parses}")
        print(f"Failed: {cls.failed_parses}")
        print(f"Success rate: {rate:.1f}%")
        print("=" * 60 + "\n")


if __name__ == "__main__":
    # Test the enhanced reviewer
    test_diff = """--- a/app/main.py
+++ b/app/main.py
@@ -1,5 +1,10 @@
 from fastapi import FastAPI

+def validate_input(data: str) -> bool:
+    if not data:
+        return False
+    return True
+
 app = FastAPI()

 @app.get("/")"""

    print("Testing enhanced reviewer...")
    result = review_diff(test_diff, review_types=["short_summary", "bug_detection"])
    print(json.dumps(result, indent=2))

"""
Prompt şablonları ve LLM ile iletişim için gerekli yapılar.
Her prompt, bir diff'i analiz etmek için kullanılacak sorular içerir.
"""

# =====================================================
# 1. PROMPT ŞABLONLARı (Templates)
# =====================================================

SHORT_SUMMARY = """
Aşağıdaki kod değişikliğini (diff) analiz et.

Diff:
{diff_text}

SADECE bu JSON'ı döndür, başka hiçbir metin yazma:
{{
    "summary": "1-2 cümle açıklama",
    "severity": "low",
    "type": "bugfix"
}}

Örnek cevap:
{{"summary": "None kontrolü eklendi", "severity": "medium", "type": "bugfix"}}
"""

BUG_DETECTION = """
Aşağıdaki kod değişikliğinde (diff) olası bug'lar, sorunlar veya risk alanlarını bul.

Diff:
{diff_text}

Lütfen SADECE şu JSON formatında cevap ver (başka metin yazma):
{{
    "issues": [
        {{
            "file": "dosya_adi.py",
            "line": 12,
            "severity": "critical | high | medium | low",
            "description": "Burada ne sorun var? Açıkla.",
            "suggestion": "Nasıl düzeltebilirsin?"
        }}
    ],
    "has_bugs": true | false,
    "overall_risk": "low | medium | high"
}}

Eğer sorun yoksa, "issues" boş liste olabilir.
"""

PERFORMANCE_REVIEW = """
Aşağıdaki kod değişikliğini (diff) performans açısından değerlendir.

Diff:
{diff_text}

Lütfen SADECE şu JSON formatında cevap ver (başka metin yazma):
{{
    "suggestions": [
        {{
            "file": "dosya_adi.py",
            "line": 5,
            "issue": "Bu loop 1000 kere işlem yapıyor ve yavaş olabilir",
            "recommendation": "List comprehension kullan veya döngüyü optimize et"
        }}
    ],
    "optimization_potential": "low | medium | high"
}}
"""

SECURITY_REVIEW = """
Aşağıdaki kod değişikliğini (diff) güvenlik açısından kontrol et.

Diff:
{diff_text}

Lütfen SADECE şu JSON formatında cevap ver (başka metin yazma):
{{
    "vulnerabilities": [
        {{
            "file": "dosya_adi.py",
            "line": 15,
            "risk": "SQL injection riski var",
            "recommendation": "Parametrized queries kullan"
        }}
    ],
    "has_security_issues": true | false,
    "security_level": "safe | caution | dangerous"
}}
"""

# =====================================================
# 2. BEKLENEN JSON ŞEMASI (Expected Output Schema)
# =====================================================

"""
Her LLM çağrısından dönecek JSON'ın yapısı şu şekildedir:

SHORT_SUMMARY dönüş örneği:
{
    "summary": "Bu değişiklik kullanıcı giriş fonksiyonuna yeni validation ekledi",
    "severity": "medium",
    "type": "feature"
}

BUG_DETECTION dönüş örneği:
{
    "issues": [
        {
            "file": "auth.py",
            "line": 42,
            "severity": "high",
            "description": "Burada None kontrolü yapılmıyor, hata alınabilir",
            "suggestion": "if user is not None: kontrol ekle"
        },
        {
            "file": "auth.py",
            "line": 50,
            "severity": "low",
            "description": "Gereksiz import var",
            "suggestion": "İmport'u sil"
        }
    ],
    "has_bugs": true,
    "overall_risk": "high"
}

PERFORMANCE_REVIEW dönüş örneği:
{
    "suggestions": [
        {
            "file": "utils.py",
            "line": 100,
            "issue": "Bu for loop O(n²) time complexity'e sahip",
            "recommendation": "Set veya dictionary kullan, O(1) lookup yap"
        }
    ],
    "optimization_potential": "high"
}
"""

# =====================================================
# 3. PROMPT PARAMETRE TANIMA (Parameter Definitions)
# =====================================================

PROMPT_CONFIG = {
    "SHORT_SUMMARY": {
        "description": "Kısa özet için kullanılan prompt",
        "max_tokens": 200,
        "temperature": 0.7,
        "fields_needed": ["diff_text"],
    },
    "BUG_DETECTION": {
        "description": "Bug tespiti için kullanılan prompt",
        "max_tokens": 500,
        "temperature": 0.5,  # Daha düşük = daha tutarlı, kesin cevaplar
        "fields_needed": ["diff_text"],
    },
    "PERFORMANCE_REVIEW": {
        "description": "Performans analizi için kullanılan prompt",
        "max_tokens": 400,
        "temperature": 0.6,
        "fields_needed": ["diff_text"],
    },
    "SECURITY_REVIEW": {
        "description": "Güvenlik analizi için kullanılan prompt",
        "max_tokens": 400,
        "temperature": 0.5,
        "fields_needed": ["diff_text"],
    },
}

# =====================================================
# 4. YARDIMCI FONKSİYONLAR
# =====================================================

def get_prompt(prompt_name: str, **kwargs) -> str:
    """
    Prompt şablonunu al ve değişkenleri doldur.

    Örnek:
        prompt = get_prompt("SHORT_SUMMARY", diff_text="- old line\\n+ new line")
    """
    if prompt_name == "SHORT_SUMMARY":
        template = SHORT_SUMMARY
    elif prompt_name == "BUG_DETECTION":
        template = BUG_DETECTION
    elif prompt_name == "PERFORMANCE_REVIEW":
        template = PERFORMANCE_REVIEW
    elif prompt_name == "SECURITY_REVIEW":
        template = SECURITY_REVIEW
    else:
        raise ValueError(f"Bilinmeyen prompt: {prompt_name}")

    # Şablonu kwargs ile doldur (örn: diff_text, file_type vb.)
    return template.format(**kwargs)


def get_prompt_config(prompt_name: str) -> dict:
    """Prompt'un konfigürasyonunu al (max_tokens, temperature vb.)"""
    return PROMPT_CONFIG.get(prompt_name, {})
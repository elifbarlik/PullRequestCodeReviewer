"""
SecPR-TR — Türkçe, güvenlik odaklı PR analiz prompt'ları.

Gemini 2.5 Flash için optimize edilmiştir.
Çıktı dili: Türkçe (junior geliştirici dostu, öğretici ton)
"""

# ── Kısa özet ──────────────────────────────────────────────────────────────

SHORT_SUMMARY = """Aşağıdaki kod değişikliğini (diff) inceleyerek kısa bir özet çıkar.

SADECE geçerli bir JSON nesnesi döndür. Markdown kod bloğu (```), açıklama veya
JSON dışında HİÇBİR metin YAZMA. Yanıtın ilk karakteri açılış süslü parantez, son karakteri kapanış süslü parantez olmalı.

Kod değişikliği:
{diff_text}

Dönmen gereken yapı tam olarak bu:
{{"summary": "değişikliği açıklayan kısa Türkçe cümle", "severity": "low|medium|high", "type": "feature|bugfix|refactor|docs|security"}}

Örnek geçerli yanıt:
{{"summary": "Null kontrolü eklendi", "severity": "medium", "type": "bugfix"}}

SADECE JSON döndür, başka hiçbir şey yazma:"""

# ── Güvenlik incelemesi ─────────────────────────────────────────────────────

SECURITY_REVIEW = """Sen bir uygulama güvenliği uzmanısın. Aşağıdaki kod diff'ini güvenlik açıkları için incele.

SADECE geçerli bir JSON nesnesi döndür. Markdown veya açıklama YAZMA.

Diff:
{diff_text}

Güvenli ise şunu döndür:
{{"vulnerabilities": [], "has_security_issues": false, "security_level": "safe"}}

Sorun varsa tam olarak bu yapıyı döndür (Türkçe yaz):
{{
    "vulnerabilities": [
        {{
            "file": "dosya.py",
            "line": 10,
            "risk": "critical|high|medium|low",
            "type": "SQL Injection|XSS|Hardcoded Secret|Path Traversal|SSRF|vb",
            "description": "Güvenlik açığının Türkçe açıklaması — neden tehlikeli?",
            "recommendation": "Nasıl düzeltilir? Kod örneğiyle göster"
        }}
    ],
    "has_security_issues": true,
    "security_level": "critical|high|medium|safe"
}}

SADECE JSON döndür:"""

# ── Hata tespiti ────────────────────────────────────────────────────────────

BUG_DETECTION = """Sen bir kod kalitesi uzmanısın. Aşağıdaki diff'te potansiyel hataları bul.

SADECE geçerli bir JSON nesnesi döndür. Markdown veya açıklama YAZMA.

Diff:
{diff_text}

Hata yoksa:
{{"issues": [], "has_bugs": false, "overall_risk": "low"}}

Hata varsa (Türkçe yaz):
{{
    "issues": [
        {{
            "file": "dosya.py",
            "line": 10,
            "severity": "high|medium|low",
            "description": "Hatanın Türkçe açıklaması",
            "suggestion": "Düzeltme önerisi"
        }}
    ],
    "has_bugs": true,
    "overall_risk": "critical|high|medium|low"
}}

SADECE JSON döndür:"""

# ── Performans incelemesi ───────────────────────────────────────────────────

PERFORMANCE_REVIEW = """Sen bir performans optimizasyon uzmanısın. Bu diff'i performans sorunları için incele.

SADECE geçerli bir JSON nesnesi döndür. Markdown veya açıklama YAZMA.

Diff:
{diff_text}

Sorun yoksa:
{{"suggestions": [], "optimization_potential": "low"}}

Sorun varsa (Türkçe yaz):
{{
    "suggestions": [
        {{
            "file": "dosya.py",
            "line": 10,
            "issue": "Sorunun kısa açıklaması",
            "recommendation": "Optimizasyon önerisi"
        }}
    ],
    "optimization_potential": "high|medium|low"
}}

SADECE JSON döndür:"""

# ── Semgrep bulgu açıklaması ─────────────────────────────────────────────────
# Faz 0'daki hibrit mimari kararı: Gemini artık güvenlik açığı "aramıyor" —
# Semgrep zaten deterministik olarak bulmuş, Gemini SADECE bu bulguları
# Türkçe ve öğretici şekilde açıklıyor. Bulgunun var olup olmadığına veya
# önem derecesine Gemini karar vermez.

SECURITY_EXPLAIN = """Sen bir uygulama güvenliği eğitmenisin. Aşağıda Semgrep (statik analiz
aracı) tarafından bu pull request'te tespit edilmiş güvenlik bulguları var.

ÖNEMLİ: Bu bulguların gerçek olup olmadığını veya önem derecesini SEN belirlemiyorsun —
bunlar zaten Semgrep tarafından kesinleştirildi. Senin tek görevin, her bulgu için
junior bir geliştiricinin anlayacağı, öğretici bir Türkçe açıklama üretmek.

Semgrep bulguları (JSON, her biri bir "index" içerir):
{findings_json}

İlgili kod diff'i (bağlam için):
{diff_text}

Her bulgu için ÜRETMEN gerekenler:
- description: Bu neden güvenlik riski? Somut olarak nasıl istismar edilebilir? (Türkçe, 1-2 cümle)
- recommendation: Nasıl düzeltilir? Kısa bir kod örneğiyle göster. (Türkçe)

SADECE geçerli bir JSON nesnesi döndür. Markdown kod bloğu, açıklama veya
JSON dışında HİÇBİR metin YAZMA:
{{"explanations": [{{"index": 0, "description": "...", "recommendation": "..."}}]}}

Girdi kaç bulgu içeriyorsa (aynı index'lerle) o kadar açıklama üret. SADECE JSON döndür:"""

# ── Prompt konfigürasyonu ───────────────────────────────────────────────────

PROMPT_CONFIG = {
    "SHORT_SUMMARY": {
        "description": "Değişiklik özeti",
        # 31 Ağustos'ta google-genai'a geçilip thinking_budget=0 ile
        # thinking kapatıldı (bkz. reviewer.py call_llm) — o yüzden bu
        # artık thinking token'ları için gerekli değil, sadece rahat bir
        # üst sınır. Eskiden (deprecated google-generativeai SDK'sında
        # thinking kapatılamazken) 300 çok düşüktü ve yanıt gerçek
        # JSON'a başlamadan kesiliyordu (29 karakterde kırpılma).
        "max_tokens": 2048,
        "temperature": 0.1,
        "fields_needed": ["diff_text"],
    },
    "SECURITY_REVIEW": {
        "description": "Güvenlik incelemesi",
        "max_tokens": 1000,
        "temperature": 0.1,  # Güvenlik analizi için çok düşük sıcaklık
        "fields_needed": ["diff_text"],
    },
    "BUG_DETECTION": {
        "description": "Hata tespiti",
        "max_tokens": 800,
        "temperature": 0.1,
        "fields_needed": ["diff_text"],
    },
    "PERFORMANCE_REVIEW": {
        "description": "Performans incelemesi",
        "max_tokens": 600,
        "temperature": 0.1,
        "fields_needed": ["diff_text"],
    },
    "SECURITY_EXPLAIN": {
        "description": "Semgrep bulgu açıklaması (hibrit mimari)",
        # Birden fazla bulgu aynı çağrıda açıklanabilir, o yüzden diğer
        # promptlardan daha geniş bir bütçe
        "max_tokens": 2048,
        "temperature": 0.2,
        "fields_needed": ["findings_json", "diff_text"],
    },
}


def get_prompt(prompt_name: str, **kwargs) -> str:
    """Prompt şablonunu doldur ve döndür."""
    templates = {
        "SHORT_SUMMARY": SHORT_SUMMARY,
        "SECURITY_REVIEW": SECURITY_REVIEW,
        "BUG_DETECTION": BUG_DETECTION,
        "PERFORMANCE_REVIEW": PERFORMANCE_REVIEW,
        "SECURITY_EXPLAIN": SECURITY_EXPLAIN,
    }
    if prompt_name not in templates:
        raise ValueError(f"Bilinmeyen prompt: {prompt_name}")
    return templates[prompt_name].format(**kwargs)


def get_prompt_config(prompt_name: str) -> dict:
    """Prompt konfigürasyonunu döndür."""
    return PROMPT_CONFIG.get(prompt_name, {"max_tokens": 500, "temperature": 0.1})

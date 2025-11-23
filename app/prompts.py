SHORT_SUMMARY = """You are a code review expert. Analyze this code diff ONLY.

Return ONLY a valid JSON object, NOTHING else. No explanation, no markdown, no text before or after.

Diff:
{diff_text}

CRITICAL RULES:
1. Return ONLY JSON
2. No markdown code blocks
3. No explanations
4. No additional text
5. Valid JSON syntax required

Return exactly this JSON structure:
{{
    "summary": "one sentence describing the change",
    "severity": "low|medium|high",
    "type": "feature|bugfix|refactor|docs"
}}

Example valid response:
{{"summary": "Added None check", "severity": "medium", "type": "bugfix"}}

Now analyze and return ONLY JSON:"""

BUG_DETECTION = """You are a security and code quality expert. Find potential bugs in this code diff.

Return ONLY a valid JSON object, NOTHING else. No explanation, no markdown.

Diff:
{diff_text}

CRITICAL RULES:
1. Return ONLY JSON
2. No markdown code blocks (no ```json)
3. No explanations
4. If no bugs: return {{"issues": [], "has_bugs": false, "overall_risk": "low"}}
5. Valid JSON syntax required

Return exactly this structure:
{{
    "issues": [
        {{
            "file": "filename.py",
            "line": 10,
            "severity": "high|medium|low",
            "description": "brief bug description",
            "suggestion": "how to fix"
        }}
    ],
    "has_bugs": true|false,
    "overall_risk": "critical|high|medium|low"
}}

Example with bugs:
{{"issues": [{{"file": "auth.py", "line": 5, "severity": "high", "description": "Unvalidated user input", "suggestion": "Add input validation"}}], "has_bugs": true, "overall_risk": "high"}}

Example without bugs:
{{"issues": [], "has_bugs": false, "overall_risk": "low"}}

Now analyze and return ONLY JSON:"""

PERFORMANCE_REVIEW = """You are a performance optimization expert. Review this code diff for performance issues.

Return ONLY a valid JSON object, NOTHING else.

Diff:
{diff_text}

CRITICAL RULES:
1. Return ONLY JSON
2. No markdown, no explanations
3. If no issues: return {{"suggestions": [], "optimization_potential": "low"}}
4. Keep code snippets SHORT (max 50 chars each)

Return exactly this structure:
{{
    "suggestions": [
        {{
            "file": "filename.py",
            "line": 10,
            "issue": "brief issue description",
            "recommendation": "optimization suggestion"
        }}
    ],
    "optimization_potential": "high|medium|low"
}}

Example:
{{"suggestions": [{{"file": "utils.py", "line": 10, "issue": "O(n²) nested loop", "recommendation": "Use set instead"}}], "optimization_potential": "high"}}

Now analyze and return ONLY JSON:"""

SECURITY_REVIEW = """You are a security expert. Check this code diff for security vulnerabilities.

Return ONLY a valid JSON object, NOTHING else.

Diff:
{diff_text}

CRITICAL RULES:
1. Return ONLY JSON
2. No markdown, no explanations
3. If safe: return {{"vulnerabilities": [], "has_security_issues": false, "security_level": "safe"}}
4. Keep descriptions SHORT

Return exactly this structure:
{{
    "vulnerabilities": [
        {{
            "file": "filename.py",
            "line": 10,
            "risk": "critical|high|medium|low",
            "type": "SQL injection|XSS|auth bypass|etc",
            "recommendation": "fix suggestion"
        }}
    ],
    "has_security_issues": true|false,
    "security_level": "critical|high|medium|safe"
}}

Example:
{{"vulnerabilities": [{{"file": "db.py", "line": 8, "risk": "high", "type": "SQL injection", "recommendation": "Use parameterized queries"}}], "has_security_issues": true, "security_level": "high"}}

Now analyze and return ONLY JSON:"""

# ============= PROMPT CONFIG =============

PROMPT_CONFIG = {
    "SHORT_SUMMARY": {
        "description": "Short summary of changes",
        "max_tokens": 150,
        "temperature": 0.2,  # Daha düşük = daha deterministic
        "fields_needed": ["diff_text"],
    },
    "BUG_DETECTION": {
        "description": "Bug detection",
        "max_tokens": 500,
        "temperature": 0.3,
        "fields_needed": ["diff_text"],
    },
    "PERFORMANCE_REVIEW": {
        "description": "Performance review",
        "max_tokens": 400,
        "temperature": 0.2,
        "fields_needed": ["diff_text"],
    },
    "SECURITY_REVIEW": {
        "description": "Security review",
        "max_tokens": 400,
        "temperature": 0.2,
        "fields_needed": ["diff_text"],
    },
}


def get_prompt(prompt_name: str, **kwargs) -> str:
    """Get prompt template and fill variables"""
    if prompt_name == "SHORT_SUMMARY":
        template = SHORT_SUMMARY
    elif prompt_name == "BUG_DETECTION":
        template = BUG_DETECTION
    elif prompt_name == "PERFORMANCE_REVIEW":
        template = PERFORMANCE_REVIEW
    elif prompt_name == "SECURITY_REVIEW":
        template = SECURITY_REVIEW
    else:
        raise ValueError(f"Unknown prompt: {prompt_name}")

    return template.format(**kwargs)


def get_prompt_config(prompt_name: str) -> dict:
    """Get prompt configuration"""
    return PROMPT_CONFIG.get(prompt_name, {})

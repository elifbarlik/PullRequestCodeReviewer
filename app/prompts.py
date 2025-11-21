SHORT_SUMMARY = """
Analyze this code diff and return ONLY valid JSON, nothing else.

Diff:
{diff_text}

Return this exact JSON structure:
{{"summary": "what changed", "severity": "low", "type": "bugfix"}}

Example: {{"summary": "Added None check", "severity": "medium", "type": "bugfix"}}
"""

BUG_DETECTION = """
Find bugs in this code diff. Return ONLY valid JSON, nothing else.

Diff:
{diff_text}

Return this exact JSON:
{{"issues": [], "has_bugs": false, "overall_risk": "low"}}

If bugs exist, add to issues array:
{{"issues": [{{"file": "auth.py", "line": 5, "severity": "high", "description": "No None check", "suggestion": "Add if user is not None"}}], "has_bugs": true, "overall_risk": "high"}}
"""

PERFORMANCE_REVIEW = """
Review this code diff for performance issues. Return ONLY valid JSON.

Diff:
{diff_text}

Return this exact JSON:
{{"suggestions": [], "optimization_potential": "low"}}

If issues found:
{{"suggestions": [{{"file": "utils.py", "line": 10, "issue": "O(n²) loop", "recommendation": "Use set instead"}}], "optimization_potential": "high"}}
"""

SECURITY_REVIEW = """
Check this code diff for security issues. Return ONLY valid JSON.

Diff:
{diff_text}

Return this exact JSON:
{{"vulnerabilities": [], "has_security_issues": false, "security_level": "safe"}}

If issues found:
{{"vulnerabilities": [{{"file": "auth.py", "line": 8, "risk": "SQL injection", "recommendation": "Use parameterized queries"}}], "has_security_issues": true, "security_level": "dangerous"}}
"""

PROMPT_CONFIG = {
    "SHORT_SUMMARY": {
        "description": "Short summary",
        "max_tokens": 150,
        "temperature": 0.3,
        "fields_needed": ["diff_text"],
    },
    "BUG_DETECTION": {
        "description": "Bug detection",
        "max_tokens": 400,
        "temperature": 0.3,
        "fields_needed": ["diff_text"],
    },
    "PERFORMANCE_REVIEW": {
        "description": "Performance review",
        "max_tokens": 300,
        "temperature": 0.3,
        "fields_needed": ["diff_text"],
    },
    "SECURITY_REVIEW": {
        "description": "Security review",
        "max_tokens": 300,
        "temperature": 0.3,
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
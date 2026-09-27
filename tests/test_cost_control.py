import pytest

from app.cost_control import LLMResponseCache, build_cache_key, clamp_output_tokens


def test_cache_hit_and_lru(monkeypatch):
    monkeypatch.setenv("LLM_CACHE_ENABLED", "true")
    monkeypatch.setenv("LLM_CACHE_TTL_SECONDS", "300")
    monkeypatch.setenv("LLM_CACHE_MAX_ENTRIES", "2")
    cache = LLMResponseCache()
    cache.set("a", "one")
    cache.set("b", "two")
    assert cache.get("a") == "one"
    cache.set("c", "three")
    assert cache.get("b") is None
    assert cache.get("a") == "one"
    assert cache.get("c") == "three"


def test_cache_disabled(monkeypatch):
    monkeypatch.setenv("LLM_CACHE_ENABLED", "false")
    cache = LLMResponseCache()
    cache.set("a", "one")
    assert cache.get("a") is None


def test_cache_key_changes_with_generation_config():
    a = build_cache_key(model="gemini-2.5-flash", prompt="x", max_tokens=100, temperature=0.1, use_json_mode=True)
    b = build_cache_key(model="gemini-2.5-flash", prompt="x", max_tokens=200, temperature=0.1, use_json_mode=True)
    assert a != b


def test_global_output_token_cap(monkeypatch):
    monkeypatch.setenv("LLM_MAX_OUTPUT_TOKENS", "500")
    assert clamp_output_tokens(1000) == 500
    assert clamp_output_tokens(300) == 300

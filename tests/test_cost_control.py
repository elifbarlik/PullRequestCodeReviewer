import pytest

from app.cost_control import (
    LLMResponseCache,
    LLMUsageCollector,
    build_cache_key,
    clamp_output_tokens,
    estimate_gemini_cost,
)


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


def test_gemini_cost_estimate_uses_reported_tokens(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")
    usage = estimate_gemini_cost(
        "ignored input",
        "ignored output",
        model="gemini-2.5-flash",
        input_tokens=1000,
        output_tokens=200,
    )
    assert usage["input_tokens"] == 1000
    assert usage["output_tokens"] == 200
    assert usage["total_tokens"] == 1200
    assert usage["cost_usd"] == 0.0008
    assert usage["pricing_known"] is True


def test_usage_collector_accumulates_calls_and_cache_hits():
    collector = LLMUsageCollector()
    collector.record_api_call({"input_tokens": 100, "output_tokens": 20, "cost_usd": 0.0001})
    collector.record_cache_hit()
    snapshot = collector.snapshot()
    assert snapshot["input_tokens"] == 100
    assert snapshot["output_tokens"] == 20
    assert snapshot["calls"] == 1
    assert snapshot["cache_hits"] == 1
    assert snapshot["cost_usd"] == 0.0001

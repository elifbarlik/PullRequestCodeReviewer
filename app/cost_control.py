"""LLM maliyet kontrolü ve tekrar çağrı azaltma katmanı.

Bu modül reviewer akışından bağımsız tutulur. Aynı prompt/model/config ile
aynı isteğin kısa süre içinde tekrar edilmesi Gemini çağrısını gereksiz yere
tekrarlamaz. Cache process-local ve bounded'dır; DB/Redis zorunluluğu yoktur.

Ortam değişkenleri:
- LLM_CACHE_ENABLED: true/false (varsayılan true)
- LLM_CACHE_TTL_SECONDS: TTL (varsayılan 300)
- LLM_CACHE_MAX_ENTRIES: maksimum kayıt (varsayılan 256)
- LLM_MAX_OUTPUT_TOKENS: global üst sınır (varsayılan 2048)
"""

from __future__ import annotations

import hashlib
import os
import time
from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock
from typing import Optional


@dataclass(frozen=True)
class CacheEntry:
    value: str
    created_at: float


class LLMResponseCache:
    """TTL + LRU ile sınırlı, thread-safe process-local LLM response cache."""

    def __init__(self) -> None:
        self._entries: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = Lock()
        self.hits = 0
        self.misses = 0

    @staticmethod
    def _positive_int(name: str, default: int) -> int:
        try:
            return max(1, int(os.getenv(name, str(default))))
        except (TypeError, ValueError):
            return default

    @property
    def enabled(self) -> bool:
        return os.getenv("LLM_CACHE_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}

    @property
    def ttl_seconds(self) -> int:
        return self._positive_int("LLM_CACHE_TTL_SECONDS", 300)

    @property
    def max_entries(self) -> int:
        return self._positive_int("LLM_CACHE_MAX_ENTRIES", 256)

    def _purge_expired(self, now: float) -> None:
        expired = [key for key, entry in self._entries.items() if now - entry.created_at >= self.ttl_seconds]
        for key in expired:
            self._entries.pop(key, None)

    def get(self, key: str) -> Optional[str]:
        if not self.enabled:
            return None
        now = time.monotonic()
        with self._lock:
            self._purge_expired(now)
            entry = self._entries.get(key)
            if entry is None:
                self.misses += 1
                return None
            self._entries.move_to_end(key)
            self.hits += 1
            return entry.value

    def set(self, key: str, value: str) -> None:
        if not self.enabled:
            return
        with self._lock:
            self._entries[key] = CacheEntry(value=value, created_at=time.monotonic())
            self._entries.move_to_end(key)
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self.hits = 0
            self.misses = 0

    def stats(self) -> dict:
        with self._lock:
            return {
                "enabled": self.enabled,
                "entries": len(self._entries),
                "hits": self.hits,
                "misses": self.misses,
                "ttl_seconds": self.ttl_seconds,
                "max_entries": self.max_entries,
            }


def build_cache_key(*, model: str, prompt: str, max_tokens: int, temperature: float, use_json_mode: bool) -> str:
    """Prompt içeriğini loglamadan deterministik cache anahtarı üretir."""
    payload = "\\x1f".join([
        model,
        str(max_tokens),
        repr(temperature),
        str(use_json_mode),
        prompt,
    ])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def clamp_output_tokens(requested: int) -> int:
    """Prompt bazlı bütçeleri global güvenlik/maliyet tavanıyla sınırlar."""
    try:
        global_limit = max(1, int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "2048")))
    except ValueError:
        global_limit = 2048
    return min(max(1, int(requested)), global_limit)


# Google AI Studio / Gemini Developer API standard text pricing used by the
# default production model. Values are USD per 1M tokens and are intentionally
# configurable because pricing can change and custom models may be used.
# Current defaults for gemini-2.5-flash are documented by Google:
# input $0.30 / 1M, output $2.50 / 1M.
# See: https://ai.google.dev/gemini-api/docs/pricing
_DEFAULT_PRICING = {
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-flash-lite": (0.10, 0.40),
}


def _price_per_million(model: str, kind: str) -> Optional[float]:
    env_name = (
        "GEMINI_INPUT_PRICE_PER_1M"
        if kind == "input"
        else "GEMINI_OUTPUT_PRICE_PER_1M"
    )
    raw = os.getenv(env_name, "").strip()
    if raw:
        try:
            return max(0.0, float(raw))
        except ValueError:
            pass

    prices = _DEFAULT_PRICING.get(model)
    if prices is None:
        return None
    return prices[0] if kind == "input" else prices[1]


def estimate_gemini_cost(
    input_text: str,
    output_text: str,
    *,
    model: str,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
) -> dict:
    """Estimate token usage and USD cost for one Gemini request.

    Prefer provider-reported token counts when available; otherwise fall back
    to the project's conservative 4-chars-per-token estimate.
    """
    input_tokens = input_tokens or max(1, int(len(input_text) * 0.25))
    output_tokens = output_tokens or max(1, int(len(output_text) * 0.25))

    input_price = _price_per_million(model, "input")
    output_price = _price_per_million(model, "output")
    cost_usd = None
    if input_price is not None and output_price is not None:
        cost_usd = round(
            (input_tokens / 1_000_000) * input_price
            + (output_tokens / 1_000_000) * output_price,
            8,
        )

    return {
        "input_tokens": int(input_tokens),
        "output_tokens": int(output_tokens),
        "total_tokens": int(input_tokens + output_tokens),
        "cost_usd": cost_usd,
        "pricing_known": cost_usd is not None,
    }


@dataclass
class LLMUsageCollector:
    """Thread-safe per-review LLM usage accumulator.

    A collector is passed through the review pipeline so concurrent stage-1
    and Semgrep work cannot mix usage from different PR reviews.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    calls: int = 0
    cache_hits: int = 0
    pricing_unknown_calls: int = 0

    def __post_init__(self) -> None:
        self._lock = Lock()

    def record_api_call(self, usage: dict) -> None:
        with self._lock:
            self.calls += 1
            self.input_tokens += int(usage.get("input_tokens", 0))
            self.output_tokens += int(usage.get("output_tokens", 0))
            if usage.get("cost_usd") is None:
                self.pricing_unknown_calls += 1
            else:
                self.cost_usd += float(usage["cost_usd"])

    def record_cache_hit(self) -> None:
        with self._lock:
            self.cache_hits += 1

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
                "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
                "total_tokens": self.input_tokens + self.output_tokens,
                "cost_usd": round(self.cost_usd, 8),
                "calls": self.calls,
                "cache_hits": self.cache_hits,
                "pricing_unknown_calls": self.pricing_unknown_calls,
            }


llm_response_cache = LLMResponseCache()

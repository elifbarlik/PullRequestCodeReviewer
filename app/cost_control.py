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


llm_response_cache = LLMResponseCache()

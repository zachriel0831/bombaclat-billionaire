"""REQ-016 — central registry for static prompt chunks + cache helpers.

Two responsibilities:

1. Hold the *static* parts of every analysis prompt (macro skill, mobile-chat
   format skill, evidence policy). These chunks rarely change between calls,
   so we want them in one place with a version stamp instead of duplicated
   inside each stage file.

2. Build the provider-specific shape that exposes the static prefix to the
   prompt-cache feature:
     - Anthropic: ``system`` becomes a list of blocks; the static block
       carries ``cache_control: {"type": "ephemeral"}`` so subsequent calls
       within ~5 minutes hit ``cache_read_input_tokens``.
     - OpenAI: Responses API auto-caches the prompt prefix when the same
       prefix is reused. We just keep the static text as the leading section
       of ``instructions`` (caller already does this).

Token-usage extraction helpers also live here so the call sites just look at
``response_usage_anthropic`` / ``response_usage_openai`` rather than poking
at provider response shapes inline.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


# Bumped whenever the static prompt content changes meaningfully. Logged into
# ``raw_json`` so we can correlate cache misses with prompt-asset rollouts.
PROMPT_ASSETS_VERSION = "v1"

# Anthropic prompt-cache minimum block size (per docs). Blocks below this are
# rejected by the API; we fall back to a non-cached send when the static
# portion happens to be smaller.
ANTHROPIC_MIN_CACHEABLE_TOKENS_HINT = 1024
# Rough char→token ratio for a quick gate without tokenising. Conservative —
# we cache only when comfortably above the minimum.
_MIN_CACHEABLE_CHARS = 4000


# Canonical evidence-policy preamble shared by every analysis stage. Lives
# here so that any future tweak applies uniformly and bumps the version.
EVIDENCE_POLICY = (
    "You are part of a multi-stage Taiwan-market analysis pipeline.\n"
    "Hard rules that apply to every stage:\n"
    "1. Every claim must be tied to a specific event id, market_context source,\n"
    "   or stage output already produced upstream. Do not invent facts.\n"
    "2. If the supporting evidence is thin, prefer surfacing the data gap\n"
    "   over a confident claim.\n"
    "3. Output language is Traditional Chinese unless the stage schema asks\n"
    "   for English keys / values.\n"
    "4. Never propose order placement, position sizing, or directly executable\n"
    "   broker actions. Stage output stops at trade ideas + reasoning.\n"
)


# ---------- skill loaders (cached on path) ----------


@lru_cache(maxsize=8)
def load_skill(path: str) -> str:
    """Read a skill markdown file, cached per-path. Empty string on miss."""
    if not path:
        return ""
    try:
        return Path(path).read_text(encoding="utf-8", errors="ignore").strip()
    except OSError:
        return ""


def load_macro_skill(path: str) -> str:
    """Convenience alias for the macro-weekly-summary skill file."""
    return load_skill(path)


def load_line_skill(path: str) -> str:
    """Convenience alias for the line-brief-format skill file."""
    return load_skill(path)


# ---------- system-prompt assembly ----------


def compose_static_preamble(macro_skill: str, line_skill: str) -> str:
    """Return the fixed cacheable preamble (evidence policy + skills).

    Order: evidence policy → macro skill → line skill. Stages append their
    own dynamic instructions after this block.
    """
    parts: list[str] = [EVIDENCE_POLICY.strip()]
    if macro_skill:
        parts.append("[Macro Skill]\n" + macro_skill)
    if line_skill:
        parts.append("[Mobile Chat Format Skill]\n" + line_skill)
    return "\n\n".join(parts)


def build_anthropic_system_blocks(
    static_text: str,
    dynamic_suffix: str | None = None,
) -> list[dict[str, Any]]:
    """Return an Anthropic ``system`` value as cache-friendly blocks.

    The static block carries ``cache_control: ephemeral`` so the second call
    within the cache TTL reads from cache. If ``static_text`` is too small to
    qualify for caching, the cache_control field is omitted (Anthropic would
    reject the block). The dynamic suffix, if any, is appended as a second
    plain block so stages can vary it without invalidating the cache.
    """
    static_block: dict[str, Any] = {"type": "text", "text": static_text}
    if is_cacheable(static_text):
        static_block["cache_control"] = {"type": "ephemeral"}
    blocks = [static_block]
    if dynamic_suffix:
        blocks.append({"type": "text", "text": dynamic_suffix})
    return blocks


def is_cacheable(text: str) -> bool:
    """True when the block is large enough for Anthropic prompt caching."""
    return len(text or "") >= _MIN_CACHEABLE_CHARS


# ---------- usage extraction ----------


@dataclass(frozen=True)
class TokenUsage:
    """Provider-agnostic token-usage summary written into raw_json."""
    provider: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0          # cache reads (both providers)
    cache_creation_tokens: int = 0  # anthropic-only cache writes
    prompt_assets_version: str = PROMPT_ASSETS_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "prompt_tokens": int(self.prompt_tokens),
            "completion_tokens": int(self.completion_tokens),
            "cached_tokens": int(self.cached_tokens),
            "cache_creation_tokens": int(self.cache_creation_tokens),
            "prompt_assets_version": self.prompt_assets_version,
        }


def extract_usage_anthropic(resp_json: dict[str, Any], model: str) -> TokenUsage:
    """Pull token counts out of an Anthropic /v1/messages response."""
    usage = resp_json.get("usage") if isinstance(resp_json, dict) else None
    if not isinstance(usage, dict):
        return TokenUsage(provider="anthropic", model=model)
    return TokenUsage(
        provider="anthropic",
        model=model,
        prompt_tokens=int(usage.get("input_tokens") or 0),
        completion_tokens=int(usage.get("output_tokens") or 0),
        cached_tokens=int(usage.get("cache_read_input_tokens") or 0),
        cache_creation_tokens=int(usage.get("cache_creation_input_tokens") or 0),
    )


def extract_usage_openai(resp_json: dict[str, Any], model: str) -> TokenUsage:
    """Pull token counts out of an OpenAI Responses API response."""
    usage = resp_json.get("usage") if isinstance(resp_json, dict) else None
    if not isinstance(usage, dict):
        return TokenUsage(provider="openai", model=model)
    cached = 0
    details = usage.get("input_tokens_details")
    if isinstance(details, dict):
        cached = int(details.get("cached_tokens") or 0)
    return TokenUsage(
        provider="openai",
        model=model,
        prompt_tokens=int(usage.get("input_tokens") or 0),
        completion_tokens=int(usage.get("output_tokens") or 0),
        cached_tokens=cached,
    )


def merge_usage(usages: list[TokenUsage]) -> dict[str, Any]:
    """Sum a sequence of TokenUsage rows into a single raw_json-ready dict.

    Per-stage rows are kept in ``stages`` so we don't lose granularity.
    """
    total_prompt = sum(u.prompt_tokens for u in usages)
    total_completion = sum(u.completion_tokens for u in usages)
    total_cached = sum(u.cached_tokens for u in usages)
    total_cache_creation = sum(u.cache_creation_tokens for u in usages)
    cache_hit_ratio = (
        total_cached / total_prompt if total_prompt > 0 else 0.0
    )
    return {
        "prompt_tokens": total_prompt,
        "completion_tokens": total_completion,
        "cached_tokens": total_cached,
        "cache_creation_tokens": total_cache_creation,
        "cache_hit_ratio": round(cache_hit_ratio, 3),
        "prompt_assets_version": PROMPT_ASSETS_VERSION,
        "stages": [u.to_dict() for u in usages],
    }

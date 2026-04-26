"""One-shot helper to add module docstrings to source files lacking one.

Run from repo root. Idempotent: skips files that already start with a
triple-quoted string (after optional ``from __future__`` line).
"""
from __future__ import annotations

from pathlib import Path
import sys


DOCSTRINGS: dict[str, str] = {
    # event_relay/ — data sources
    "src/event_relay/bls_macro.py": (
        "REQ-010 — U.S. Bureau of Labor Statistics macro data adapter.\n\n"
        "Pulls CPI / PPI / NFP / unemployment / wages from the BLS Public Data\n"
        "API v2, normalises into stored-only ``market_context:bls_macro`` events,\n"
        "and writes to ``t_relay_events`` with stable ``(series_id, year, period)``\n"
        "dedupe keys. The us_close / pre_tw_open analyses read from the same\n"
        "event window."
    ),
    "src/event_relay/tw_close_context.py": (
        "REQ-011 — Taiwan-close event builder.\n\n"
        "Aggregates same-day ``market_context:twse_flow / tpex_flow / taifex_flow``\n"
        "events plus index moves into a single ``market_context:tw_close`` row that\n"
        "the tw_close analysis slot consumes. Stored-only; no LLM call here."
    ),
    "src/event_relay/tw_market_flow.py": (
        "REQ-009 — Taiwan institutional flow + TAIFEX collector.\n\n"
        "Pulls TWSE / TPEX / TAIFEX official daily datasets, normalises the\n"
        "Chinese fields, and writes ``market_context:twse_flow`` /\n"
        "``tpex_flow`` / ``taifex_flow`` stored-only events into\n"
        "``t_relay_events`` for downstream analysis."
    ),
    # event_relay/ — runtime + pipeline support
    "src/event_relay/market_context.py": (
        "Pre-open market-context collector.\n\n"
        "Pulls overnight US market state (index closes, treasury yields, FX, oil)\n"
        "and writes ``market_context:*`` stored-only events into ``t_relay_events``\n"
        "so the pre_tw_open / us_close analysis pipelines can read it from the same\n"
        "event window as news. No analysis is generated here — that is owned by\n"
        "``market_analysis.py``."
    ),
    "src/event_relay/rag.py": (
        "REQ-014 retrieval-augmented context for the analysis pipeline.\n\n"
        "Computes / stores embedding vectors for events and past analyses, and\n"
        "retrieves the top-K similar items to feed stage1 / stage4 as historical\n"
        "context. Pure-Python cosine similarity over MySQL-stored vectors so the\n"
        "pipeline does not depend on an external vector DB."
    ),
    "src/event_relay/retention_cleanup.py": (
        "Daily retention cleanup driver.\n\n"
        "Trims ``t_relay_events`` and related tables to ``RELAY_RETENTION_KEEP_DAYS``\n"
        "rows, preserving market_context / analysis-relevant rows. Invoked from the\n"
        "maintenance scheduler in ``RelayProcessor`` and exposed as a CLI for ad-hoc\n"
        "runs."
    ),
    "src/event_relay/weekly_summary.py": (
        "Weekly market summary generator (Saturday 23:00 Asia/Taipei).\n\n"
        "Aggregates the past week of relay events + market analyses, calls the LLM\n"
        "(Anthropic / OpenAI) to produce a Traditional-Chinese summary, persists\n"
        "to ``t_market_analyses`` with ``slot=weekly_tw_preopen``. Hosts shared\n"
        "LLM helpers reused by ``market_analysis``."
    ),
    "src/event_relay/analysis_stages/context.py": (
        "Shared context + result types for the multi-stage analysis pipeline.\n\n"
        "``StageContext`` carries provider/model/slot/now_local for each stage\n"
        "call; ``StageResult`` carries the parsed output, raw text, error string,\n"
        "and extras telemetry. Stages depend on these dataclasses but not on each\n"
        "other."
    ),
    "src/event_relay/__init__.py": (
        "Event relay package — MySQL ingest, analysis pipeline, HTTP service.\n\n"
        "Public surface intentionally narrow: callers import ``config``,\n"
        "``http_server``, and ``service``. Other submodules (analysis_stages,\n"
        "bls_macro, tw_close_context, …) are imported by name where needed."
    ),
    # news_collector/
    "src/news_collector/collector.py": (
        "Top-level orchestrator for news source fan-out.\n\n"
        "``build_sources()`` instantiates the configured ``NewsSource`` adapters\n"
        "(RSS / SEC / TWSE-MOPS / X) from settings; ``fetch_news()`` runs them in\n"
        "parallel and returns merged ``NewsItem`` rows ready for the relay bridge."
    ),
    "src/news_collector/config.py": (
        "News-collector configuration loader.\n\n"
        "Reads ``.env`` (tolerant) plus environment overrides into a ``Settings``\n"
        "dataclass. Resolves the X bearer token (env or DPAPI file) without\n"
        "leaking the secret into logs."
    ),
    "src/news_collector/http_client.py": (
        "Shared HTTP helpers used by every news-collector source.\n\n"
        "Thin wrappers around ``urllib`` providing JSON / text fetch with optional\n"
        "headers, sane User-Agent, and a single retry/timeout policy."
    ),
    "src/news_collector/main.py": (
        "News-collector CLI entry point.\n\n"
        "Selects sources, applies language filters, runs collection, and either\n"
        "prints JSON to stdout or pushes the resulting ``NewsItem`` rows through\n"
        "``relay_bridge`` to the event relay."
    ),
    "src/news_collector/models.py": (
        "Shared data model for collected news.\n\n"
        "``NewsItem`` is the single row format every source must produce: stable\n"
        "id, source label, title, url, optional published-at, optional summary,\n"
        "tags, and a raw-payload dict the relay turns into ``raw_json``."
    ),
    "src/news_collector/relay_bridge.py": (
        "Bridge from news-collector sources to the event relay store.\n\n"
        "Long-running daemon that calls collectors on a cadence, normalises\n"
        "``NewsItem`` into ``RelayEvent``, deduplicates against the relay store,\n"
        "and posts to ``/events``. Operates as a separate process from the relay\n"
        "HTTP server."
    ),
    "src/news_collector/utils.py": (
        "Time, hashing, and ordering helpers shared by news sources.\n\n"
        "``parse_datetime`` is tolerant across RFC 822, ISO-8601, compact UTC, and\n"
        "epoch forms. ``stable_id`` produces deterministic ids from a tuple of\n"
        "strings (used as relay event_id)."
    ),
    "src/news_collector/x_stream.py": (
        "X (Twitter) filtered-stream client.\n\n"
        "Long-lived HTTP stream that yields tweets matching configured rules and\n"
        "converts them into ``NewsItem`` rows. Handles 429 backoff, since-id\n"
        "tracking, and reconnect with jitter."
    ),
    "src/news_collector/us_index_tracker.py": (
        "US index quote tracker (Dow, S&P 500, Nasdaq).\n\n"
        "Pulls regular-session OHLC from a public quote endpoint and produces\n"
        "snapshot rows used by the pre-open and US-close summaries. Predates\n"
        "REQ-019 ``t_market_quote_snapshots`` and remains for legacy summaries."
    ),
    "src/news_collector/sources/base.py": (
        "Abstract base class for every news source.\n\n"
        "``NewsSource`` defines a single ``fetch(limit)`` returning ``NewsItem``\n"
        "rows. Subclasses are registered via the collector's source factory."
    ),
    "src/news_collector/sources/rss.py": (
        "Official RSS / Atom feed source.\n\n"
        "Parses ``<item>`` / ``<entry>`` elements from configured feed URLs into\n"
        "``NewsItem`` rows. Tolerates mixed RSS / Atom layouts and missing\n"
        "published-at fields."
    ),
    "src/news_collector/sources/sec_filings.py": (
        "SEC EDGAR filings source.\n\n"
        "Polls the EDGAR submissions API for tracked tickers and emits one\n"
        "``NewsItem`` per recent filing with form type, accession number, and\n"
        "filing URL surfaced to the analysis pipeline."
    ),
    "src/news_collector/sources/twse_mops_announcements.py": (
        "Taiwan Stock Exchange / MOPS major-announcement source.\n\n"
        "Pulls disclosures from the public TWSE MOPS endpoint, normalises the\n"
        "Chinese disclosure fields, and emits ``NewsItem`` rows tagged with\n"
        "company code + disclosure timestamp."
    ),
    "src/news_collector/sources/x_accounts.py": (
        "X (Twitter) account-timeline source.\n\n"
        "Polls a configured handle list using the v2 user-timeline API with\n"
        "since-id pagination and global rate-limit gating. Used as the polled\n"
        "fallback when the streaming client is offline."
    ),
    # scripts/
    "scripts/validate_readiness.py": (
        "Local readiness gate for agent / skills configuration.\n\n"
        "Checks that the required governance docs (AGENTS.md, memory-bank\n"
        "standards, skills/registry) exist and reference one another correctly.\n"
        "Run as a pre-commit / CI guard before merging skills changes."
    ),
}


def _has_module_docstring(text: str) -> bool:
    """True when the file already opens with a triple-quoted module docstring.

    Skips a leading shebang and an optional ``from __future__`` line.
    """
    lines = text.splitlines()
    idx = 0
    if idx < len(lines) and lines[idx].startswith("#!"):
        idx += 1
    while idx < len(lines) and lines[idx].strip() == "":
        idx += 1
    if idx < len(lines) and lines[idx].startswith("from __future__"):
        idx += 1
        while idx < len(lines) and lines[idx].strip() == "":
            idx += 1
    return idx < len(lines) and (
        lines[idx].lstrip().startswith('"""') or lines[idx].lstrip().startswith("'''")
    )


def _insert_docstring(text: str, doc: str) -> str:
    """Place the docstring at the top, before ``from __future__``.

    The docstring sits as the very first statement; ``from __future__`` (if
    present) immediately follows. This keeps Python happy: ``__future__``
    must be the first non-docstring statement.
    """
    docblock = f'"""{doc}"""\n\n'
    if text.startswith("#!"):
        first_nl = text.find("\n") + 1
        return text[:first_nl] + docblock + text[first_nl:]
    return docblock + text


def main() -> int:
    """Edit the listed files in place, skipping ones already documented."""
    repo_root = Path(__file__).resolve().parent.parent
    edited = 0
    skipped = 0
    missing: list[str] = []

    for rel_path, doc in DOCSTRINGS.items():
        path = repo_root / rel_path
        if not path.exists():
            missing.append(rel_path)
            continue
        text = path.read_text(encoding="utf-8")
        if _has_module_docstring(text):
            skipped += 1
            continue
        path.write_text(_insert_docstring(text, doc), encoding="utf-8")
        edited += 1

    print(f"edited={edited} skipped={skipped} missing={len(missing)}")
    for m in missing:
        print(f"  MISSING: {m}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

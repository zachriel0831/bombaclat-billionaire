# Task Plan Board

Use this file for the current non-trivial task only.
Move completed or stale task logs to `tasks/archive/`.

## Current Task
- Task: Migrate local DPAPI secrets to plaintext `.env` values for Windows-to-Mac setup.
- Requested by: User
- Start date: 2026-05-04
- Scope: Convert local X/OpenAI/Anthropic DPAPI-backed secrets into `.env` plaintext variables without printing secret values.

## Plan
- [x] Confirm current secret storage and cross-platform behavior.
- [x] Identify DPAPI-backed secret files and target `.env` keys.
- [x] Write decrypted values into `.env` without logging secret content.
- [x] Comment out existing `*_FILE` DPAPI env references.
- [x] Verify key presence without printing values.

## Progress Notes
- 2026-05-04 - DPAPI files are Windows-only and cannot be decrypted on Mac.
- 2026-05-04 - First PowerShell migration attempt failed on invalid `return foreach` syntax before writing `.env`.
- 2026-05-04 - Wrote plaintext `X_BEARER_TOKEN`, `OPENAI_API_KEY`, `WEEKLY_SUMMARY_OPENAI_API_KEY`, `MARKET_ANALYSIS_OPENAI_API_KEY`, and `ANTHROPIC_API_KEY` to `.env`.
- 2026-05-04 - Existing DPAPI file env refs were commented out; file refs that did not exist were left absent.

## Verification
- [x] Plaintext keys present in `.env`
- [x] DPAPI `*_FILE` entries inactive
- [x] No secret values printed

## Review Summary
- Outcome: complete
- Evidence: presence/length check confirmed five plaintext keys; active DPAPI file refs are inactive; no secret values were printed.
- Open risks: `.env` is plaintext but gitignored; `.secrets/*.dpapi` files were kept as Windows-only backup copies.

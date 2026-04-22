# Decision: Implement TWSE / MOPS major announcements via official openapi

- Date: 2026-04-19
- Status: accepted

## Context
- After SEC EDGAR, the next highest-value official source for Taiwan-market use is local listed-company disclosure.
- TWSE official swagger exposes `t187ap04_L` as the listed-company daily material-announcement dataset, which is a clean starting point for company announcements without relying on scraping fragile HTML pages.
- On this Windows host, local `Python 3.13` fails TLS verification against `openapi.twse.com.tw` with `Missing Subject Key Identifier`, while the available `Python 3.12` runtime succeeds.

## Decision
- Implement a new tracked-company source based on:
  - `https://openapi.twse.com.tw/v1/opendata/t187ap04_L`
- Track only allowlisted listed-company codes from `TWSE_MOPS_TRACKED_CODES`.
- Normalize the feed into the existing relay event path with `source=twse_mops:<CODE>`.
- Update `scripts/run_source_bridge.ps1` to prefer the local `Python 3.12` runtime for bridge startup on this workstation so TWSE polling stays compatible without weakening TLS verification.

## Consequences
- The system now ingests official Taiwan listed-company major announcements without API keys.
- Morning analysis can combine U.S. filings and local Taiwan disclosures from official sources.
- More TWSE / MOPS datasets can be added later using the same openapi contract style.
- Default tracked universes may legitimately return zero rows on a given day; controlled smoke verification can temporarily override `TWSE_MOPS_TRACKED_CODES` with current official feed codes.

# Decision: Start official-source expansion with SEC EDGAR

- Date: 2026-04-19
- Status: accepted

## Context
- The project wants simpler, more official, and lower-rate-limit data sources.
- Among the proposed additions, SEC EDGAR is the fastest high-value source to implement because it is official, JSON-based, and directly relevant to U.S. companies that move Taiwan semiconductor and AI names.

## Decision
- Start source expansion with a tracked-filings MVP based on SEC EDGAR.
- Use only official SEC endpoints:
  - `https://www.sec.gov/files/company_tickers.json`
  - `https://data.sec.gov/submissions/CIK##########.json`
- Track a small allowlist from `SEC_TRACKED_TICKERS`.
- Filter to high-signal forms from `SEC_ALLOWED_FORMS`.
- Emit filings into the existing relay event path instead of creating a new table first.

## Consequences
- The system gains an official company-disclosure source with no API key dependency.
- Filing events become available to queueing, relay delivery, and AI analysis immediately through `t_relay_events`.
- Taiwan official disclosure sources remain the next priority after SEC.

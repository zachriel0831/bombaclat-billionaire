# news-ingestion-skill

## Purpose
- Normalize breaking finance news from configured upstream sources.

## Trigger Rules
- Use for ingestion and normalization workflows.
- Do not use for outbound user notification workflows yet.

## Inputs
- Source selector (`rss`, `gdelt`, `benzinga`, `all`)
- Limit per source
- Runtime environment variables

## Outputs
- `NewsItem` normalized schema JSON records

## Tools and Permissions
- HTTP network access to configured sources
- Local filesystem read/write for config and logs

## Safety and Compliance
- Do not include secrets in output.
- Keep raw payload only for debugging and traceability.

## Failure Handling
- Source-level failure must not stop other sources.
- Return explicit error records for failed sources.

## Verification
- `python -m unittest discover -s tests -p "test_*.py" -v`
- Source smoke checks via CLI fetch commands

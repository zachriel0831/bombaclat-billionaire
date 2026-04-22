# Decision: Weekly summary timing for Taiwan market use

- Date: 2026-04-19
- Status: accepted

## Context
- For Taiwan equities, a weekly brief is most actionable just before the first cash session of the week.
- Sunday evening summaries are readable, but they are less aligned with the actual decision window used before Monday open.

## Decision
- Move the weekly summary schedule to Monday `07:30` local time.
- Keep the weekly summary generation/storage flow; downstream Java owns any LINE delivery.
- Also store the generated text in `t_market_analyses` with:
  - `analysis_date=YYYY-Www`
  - `analysis_slot=weekly_tw_preopen`
  - `raw_json.dimension=weekly`

## Consequences
- Weekly macro context is available closer to Taiwan's Monday open.
- Review and replay become easier because weekly outputs live beside daily market analyses in the same table.

"""Multi-stage market analysis pipeline.

Pipeline:
    stage1_digest -> stage2_transmission -> stage3_tw_mapping
        -> stage_dual_view -> stage_critic -> stage4_synthesis

Each stage is a pure function: it takes JSON-serialisable input and the shared
``StageContext`` (provider, api_base, api_key, model, slot, now_local) and returns
JSON-serialisable output. stage4 returns ``{summary_text, structured}``.

The orchestrator in ``event_relay.market_analysis`` runs the stages in order,
captures per-stage telemetry into ``t_market_analyses.raw_json.pipeline_stages``,
and falls back to the legacy single-call prompt if a critical stage raises.
``stage_dual_view`` and ``stage_critic`` are non-blocking — failures are recorded
as ``raw_json.dual_view_skipped`` / ``raw_json.critic_skipped`` and stage4 still
runs with whatever inputs are available.
"""

from event_relay.analysis_stages.context import StageContext, StageResult
from event_relay.analysis_stages.llm_json import call_llm_json, JsonModeUnavailable
from event_relay.analysis_stages.schemas import (
    STAGE1_DIGEST_SCHEMA,
    STAGE2_TRANSMISSION_SCHEMA,
    STAGE3_TW_MAPPING_SCHEMA,
    STAGE4_SYNTHESIS_SCHEMA,
    STAGE_CRITIC_SCHEMA,
    STAGE_DUAL_VIEW_SCHEMA,
    validate_against_schema,
)

__all__ = [
    "StageContext",
    "StageResult",
    "call_llm_json",
    "JsonModeUnavailable",
    "STAGE1_DIGEST_SCHEMA",
    "STAGE2_TRANSMISSION_SCHEMA",
    "STAGE3_TW_MAPPING_SCHEMA",
    "STAGE_DUAL_VIEW_SCHEMA",
    "STAGE_CRITIC_SCHEMA",
    "STAGE4_SYNTHESIS_SCHEMA",
    "validate_against_schema",
]

PIPELINE_VERSION = "multi-stage-v2"

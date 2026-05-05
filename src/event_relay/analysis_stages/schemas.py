"""JSON schemas and a minimal validator for multi-stage analysis output.

Schemas are expressed as JSON-schema-draft-like dicts so they can be passed
verbatim to OpenAI Responses ``response_format={"type":"json_schema"}`` and
Anthropic tool ``input_schema`` with only light normalisation.

The validator intentionally supports the subset we need (type, required,
properties, items, enum, additionalProperties=false, minimum, maximum). It is
not a full JSON-schema implementation: provider-side validation is the primary
gate; local validation guards against missing required keys when providers
return lax JSON (e.g. during fallback paths).
"""

from __future__ import annotations

from typing import Any


_EVENT_CATEGORY_ENUM = [
    "rate_decision",
    "earnings",
    "geopolitics",
    "supply_chain",
    "regulation",
    "macro_release",
    "fed_path",
    "liquidity",
    "credit_stress",
    "sentiment_positioning",
    "corporate_action",
    "market_move",
    "other",
]

_SENTIMENT_ENUM = ["bullish", "bearish", "neutral"]
_DIRECTION_ENUM = ["bullish", "bearish", "mixed"]
_CONFIDENCE_ENUM = ["low", "medium", "high"]
_NULLABLE_STRING = ["string", "null"]
_NULLABLE_NUMBER_OR_STRING = ["number", "string", "null"]


STAGE1_DIGEST_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["events", "market_snapshot"],
    "properties": {
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "category", "importance", "entities", "sentiment", "one_line_fact"],
                "properties": {
                    "id": {"type": ["integer", "string"]},
                    "category": {"type": "string", "enum": _EVENT_CATEGORY_ENUM},
                    "importance": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    "entities": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "sentiment": {"type": "string", "enum": _SENTIMENT_ENUM},
                    "one_line_fact": {"type": "string"},
                },
            },
        },
        "market_snapshot": {
            "type": "object",
            "additionalProperties": True,
            "properties": {
                "us_close": {"type": "object", "additionalProperties": True},
                "bond": {"type": "object", "additionalProperties": True},
                "fx": {"type": "object", "additionalProperties": True},
                "tw_session": {"type": "object", "additionalProperties": True},
            },
        },
    },
}


STAGE2_TRANSMISSION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["chains"],
    "properties": {
        "chains": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["trigger_event_ids", "path", "direction", "strength", "assumptions"],
                "properties": {
                    "trigger_event_ids": {
                        "type": "array",
                        "items": {"type": ["integer", "string"]},
                    },
                    "path": {"type": "string"},
                    "direction": {"type": "string", "enum": _DIRECTION_ENUM},
                    "strength": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    "assumptions": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
        },
    },
}


STAGE3_TW_MAPPING_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["sector_watch", "stock_watch", "risks", "data_gaps"],
    "properties": {
        "sector_watch": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["sector", "direction", "rationale", "evidence_ids"],
                "properties": {
                    "sector": {"type": "string"},
                    "direction": {"type": "string", "enum": _DIRECTION_ENUM},
                    "rationale": {"type": "string"},
                    "evidence_ids": {
                        "type": "array",
                        "items": {"type": ["integer", "string"]},
                    },
                },
            },
        },
        "stock_watch": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["ticker", "direction", "rationale", "evidence_ids"],
                "properties": {
                    "ticker": {"type": "string"},
                    "direction": {"type": "string", "enum": _DIRECTION_ENUM},
                    "rationale": {"type": "string"},
                    "evidence_ids": {
                        "type": "array",
                        "items": {"type": ["integer", "string"]},
                    },
                },
            },
        },
        "risks": {"type": "array", "items": {"type": "string"}},
        "data_gaps": {"type": "array", "items": {"type": "string"}},
    },
}


STAGE_DUAL_VIEW_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["bull_case", "bear_case"],
    "properties": {
        "bull_case": {
            "type": "object",
            "additionalProperties": False,
            "required": ["thesis", "drivers", "counter_risks", "evidence_ids"],
            "properties": {
                "thesis": {"type": "string"},
                "drivers": {"type": "array", "items": {"type": "string"}},
                "counter_risks": {"type": "array", "items": {"type": "string"}},
                "evidence_ids": {
                    "type": "array",
                    "items": {"type": ["integer", "string"]},
                },
            },
        },
        "bear_case": {
            "type": "object",
            "additionalProperties": False,
            "required": ["thesis", "drivers", "counter_risks", "evidence_ids"],
            "properties": {
                "thesis": {"type": "string"},
                "drivers": {"type": "array", "items": {"type": "string"}},
                "counter_risks": {"type": "array", "items": {"type": "string"}},
                "evidence_ids": {
                    "type": "array",
                    "items": {"type": ["integer", "string"]},
                },
            },
        },
    },
}


_CRITIC_ISSUE_SEVERITY = ["low", "medium", "high"]
_CRITIC_ISSUE_TYPES = [
    "logical_jump",
    "evidence_missing",
    "overconfidence",
    "factual_error",
    "ambiguous_claim",
]

STAGE_CRITIC_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["issues", "suggestions", "top_counterpoint", "confidence_recommendation"],
    "properties": {
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["type", "description", "severity"],
                "properties": {
                    "type": {"type": "string", "enum": _CRITIC_ISSUE_TYPES},
                    "description": {"type": "string"},
                    "severity": {"type": "string", "enum": _CRITIC_ISSUE_SEVERITY},
                },
            },
        },
        "suggestions": {"type": "array", "items": {"type": "string"}},
        "top_counterpoint": {"type": "string"},
        "confidence_recommendation": {"type": "string", "enum": _CONFIDENCE_ENUM},
    },
}


STAGE4_SYNTHESIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "summary_text",
        "headline",
        "sentiment",
        "confidence",
        "key_drivers",
        "tw_sector_watch",
        "stock_watch",
        "risks",
        "data_gaps",
    ],
    "properties": {
        "summary_text": {"type": "string"},
        "headline": {"type": "string"},
        "sentiment": {"type": "string", "enum": _SENTIMENT_ENUM},
        "confidence": {"type": "string", "enum": _CONFIDENCE_ENUM},
        "key_drivers": {"type": "array", "items": {"type": "string"}},
        "tw_sector_watch": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["sector", "direction", "rationale"],
                "properties": {
                    "sector": {"type": "string"},
                    "direction": {"type": "string", "enum": _DIRECTION_ENUM},
                    "rationale": {"type": "string"},
                },
            },
        },
        "stock_watch": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "ticker",
                    "market",
                    "name",
                    "direction",
                    "rationale",
                    "strategy_type",
                    "entry_zone",
                    "invalidation",
                    "take_profit_zone",
                    "holding_horizon",
                    "confidence",
                    "risk_notes",
                    "evidence_ids",
                ],
                "properties": {
                    "ticker": {"type": "string"},
                    "market": {"type": _NULLABLE_STRING},
                    "name": {"type": _NULLABLE_STRING},
                    "direction": {"type": "string", "enum": _DIRECTION_ENUM},
                    "rationale": {"type": "string"},
                    "strategy_type": {"type": _NULLABLE_STRING},
                    "entry_zone": {
                        "type": ["object", "null"],
                        "additionalProperties": False,
                        "required": ["low", "high", "timing", "basis"],
                        "properties": {
                            "low": {"type": _NULLABLE_NUMBER_OR_STRING},
                            "high": {"type": _NULLABLE_NUMBER_OR_STRING},
                            "timing": {"type": _NULLABLE_STRING},
                            "basis": {"type": _NULLABLE_STRING},
                        },
                    },
                    "invalidation": {
                        "type": ["object", "null"],
                        "additionalProperties": False,
                        "required": ["price", "basis"],
                        "properties": {
                            "price": {"type": _NULLABLE_NUMBER_OR_STRING},
                            "basis": {"type": _NULLABLE_STRING},
                        },
                    },
                    "take_profit_zone": {
                        "type": ["object", "null"],
                        "additionalProperties": False,
                        "required": ["first", "second", "basis"],
                        "properties": {
                            "first": {"type": _NULLABLE_NUMBER_OR_STRING},
                            "second": {"type": _NULLABLE_NUMBER_OR_STRING},
                            "basis": {"type": _NULLABLE_STRING},
                        },
                    },
                    "holding_horizon": {"type": _NULLABLE_STRING},
                    "confidence": {"type": _NULLABLE_STRING},
                    "risk_notes": {"type": "array", "items": {"type": "string"}},
                    "evidence_ids": {
                        "type": "array",
                        "items": {"type": ["integer", "string"]},
                    },
                },
            },
        },
        "risks": {"type": "array", "items": {"type": "string"}},
        "data_gaps": {"type": "array", "items": {"type": "string"}},
    },
}


class SchemaValidationError(ValueError):
    """Raised when a JSON payload fails local schema validation."""


def validate_against_schema(value: Any, schema: dict[str, Any], path: str = "$") -> None:
    """Best-effort JSON-schema validator covering the subset used by this package.

    Raises ``SchemaValidationError`` with a dotted path on the first violation.
    """
    expected = schema.get("type")
    if expected is not None and not _matches_type(value, expected):
        raise SchemaValidationError(
            f"{path}: expected type {expected!r}, got {type(value).__name__}"
        )

    if isinstance(value, dict):
        required = schema.get("required") or []
        for key in required:
            if key not in value:
                raise SchemaValidationError(f"{path}: missing required key {key!r}")

        properties = schema.get("properties") or {}
        for key, sub_value in value.items():
            if key in properties:
                validate_against_schema(sub_value, properties[key], f"{path}.{key}")
            elif schema.get("additionalProperties") is False:
                raise SchemaValidationError(f"{path}: unexpected key {key!r}")

    elif isinstance(value, list):
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                validate_against_schema(item, item_schema, f"{path}[{index}]")

    elif isinstance(value, str):
        enum = schema.get("enum")
        if enum is not None and value not in enum:
            raise SchemaValidationError(f"{path}: value {value!r} not in enum {enum}")

    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if minimum is not None and value < minimum:
            raise SchemaValidationError(f"{path}: value {value} < minimum {minimum}")
        if maximum is not None and value > maximum:
            raise SchemaValidationError(f"{path}: value {value} > maximum {maximum}")


def _matches_type(value: Any, expected: Any) -> bool:
    """執行 matches type 的主要流程。"""
    if isinstance(expected, list):
        return any(_matches_type(value, t) for t in expected)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return True


def assert_evidence_ids_covered(stage3_output: dict[str, Any], stage1_output: dict[str, Any]) -> list[str]:
    """Return evidence_ids referenced in stage3 that do not exist in stage1 events."""
    known_ids = {
        str(event.get("id"))
        for event in (stage1_output.get("events") or [])
        if event.get("id") is not None
    }
    missing: list[str] = []
    for bucket_name in ("sector_watch", "stock_watch"):
        for item in stage3_output.get(bucket_name) or []:
            for evidence_id in item.get("evidence_ids") or []:
                if str(evidence_id) not in known_ids:
                    missing.append(f"{bucket_name}:{evidence_id}")
    return missing

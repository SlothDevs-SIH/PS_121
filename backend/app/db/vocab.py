"""Controlled vocabularies shared by the database CHECK constraints and the API schemas.

Each vocabulary is a ``Literal`` type (used by Pydantic, so the OpenAPI contract and the
generated TypeScript carry the exact values) plus a tuple of its values (used to render the
CHECK constraints in the ORM models and migrations). Change a vocabulary here and in a new
migration together; the unit test ``test_vocab_matches_migrations`` fails if they drift.
"""

from typing import Literal, get_args

# Master plan Stage 2 event taxonomy. The final spec's event types map onto it
# (docs/SPEC_RECONCILIATION.md section 3).
EventType = Literal[
    "LOSS",
    "KICK",
    "STUCK",
    "TIGHT",
    "TORQUE",
    "INSTAB",
    "BALLING",
    "OVERP",
    "GAS",
    "CEMENT",
    "CASING",
    "FISH",
    "EQUIP",
    "WAIT",
    "OTHER_NPT",
]
Severity = Literal["low", "medium", "high"]
# rules = deterministic extraction pass; llm = schema-constrained LLM pass;
# manual = entered by an engineer (POST /events); import = bulk master-data import.
EventSource = Literal["rules", "llm", "manual", "import"]
EventStatus = Literal["active", "rejected"]
EvidenceRole = Literal["primary", "supporting"]

# Mitigation actions (master plan Stage 8). The per-event-type lists come from the plan;
# the generic codes at the end cover the remaining event types. OTHER keeps a free-text
# action that does not fit yet (action_text carries the words).
ActionCode = Literal[
    # LOSS
    "LCM_PILL_FINE",
    "LCM_PILL_COARSE",
    "LCM_BACKGROUND",
    "REDUCE_MW",
    "REDUCE_FLOW_RATE",
    "CEMENT_PLUG",
    "SQUEEZE",
    "SET_CASING_EARLY",
    "DRILL_BLIND",
    # STUCK
    "JAR_UP",
    "JAR_DOWN",
    "SPOT_PIPE_RELEASE_PILL",
    "WORK_PIPE",
    "INCREASE_FLOW",
    "BACKOFF_AND_FISH",
    "SIDETRACK",
    # KICK
    "DRILLERS_METHOD",
    "WAIT_AND_WEIGHT",
    "BULLHEAD",
    # CEMENT
    "REMEDIAL_SQUEEZE",
    "TOP_JOB",
    "LIGHTWEIGHT_SLURRY",
    # Generic (TIGHT, INSTAB, BALLING, OVERP, GAS, CASING, FISH, EQUIP, WAIT, OTHER_NPT)
    "REAM",
    "WIPER_TRIP",
    "ADD_LUBRICANT",  # TORQUE
    "REDUCE_RPM",  # TORQUE
    "ADD_DETERGENT",  # BALLING
    "INCREASE_MW",
    "CIRCULATE",
    "CHANGE_BHA",
    "FISHING",
    "REPAIR_EQUIPMENT",
    "WAIT",
    "OTHER",
]
MitigationOutcome = Literal["success", "partial", "fail", "unknown"]

CementReturns = Literal["full", "partial", "none"]
FluidType = Literal["oil", "gas", "water"]

# Per-document pipeline stages after ingestion: extraction (S2) and search indexing (S5).
StageStatus = Literal["pending", "running", "done", "failed", "skipped"]

ReviewKind = Literal["event", "mitigation", "casing", "cement", "mud", "alias", "other"]
ReviewStatus = Literal["pending", "accepted", "corrected", "rejected"]

AzimuthReference = Literal["true", "grid", "magnetic"]

EVENT_TYPES: tuple[str, ...] = get_args(EventType)
SEVERITIES: tuple[str, ...] = get_args(Severity)
EVENT_SOURCES: tuple[str, ...] = get_args(EventSource)
EVENT_STATUSES: tuple[str, ...] = get_args(EventStatus)
EVIDENCE_ROLES: tuple[str, ...] = get_args(EvidenceRole)
ACTION_CODES: tuple[str, ...] = get_args(ActionCode)
MITIGATION_OUTCOMES: tuple[str, ...] = get_args(MitigationOutcome)
CEMENT_RETURNS: tuple[str, ...] = get_args(CementReturns)
FLUID_TYPES: tuple[str, ...] = get_args(FluidType)
STAGE_STATUSES: tuple[str, ...] = get_args(StageStatus)
REVIEW_KINDS: tuple[str, ...] = get_args(ReviewKind)
REVIEW_STATUSES: tuple[str, ...] = get_args(ReviewStatus)


def in_list(column: str, values: tuple[str, ...]) -> str:
    """SQL text for a CHECK constraint ``column IN ('a', 'b', ...)``.

    Values are fixed identifiers from this module (never user input); they contain no quotes.
    NULL passes a CHECK constraint, so nullable columns need no extra clause.
    """
    assert all("'" not in v for v in values)
    return f"{column} IN ({', '.join(repr(v) for v in values)})"

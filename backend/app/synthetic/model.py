"""Synthetic Upper-Assam-style field: stratigraphy, hazards and planted mitigation rates.

EVERYTHING HERE IS ILLUSTRATIVE (master plan §12.3, Verification Log V8). Formation names
follow commonly cited Upper Assam stratigraphy; depths, hazards and success rates are
invented so the pipeline has realistic structure and known ground truth. None of it is
Oil India data, and it must never be presented as such.
"""

from dataclasses import dataclass, field

SEED = 121
FIELD_NAME = "Synthetic Field A (Upper Assam-style)"
BASIN = "Assam-Arakan (synthetic)"
CRS_EPSG = 32646  # WGS 84 / UTM zone 46N
CENTER_LAT, CENTER_LON = 27.40, 95.25
WATERMARK = "SYNTHETIC DATA - NOT OIL INDIA DATA"


@dataclass(frozen=True)
class Hazard:
    event_type: str
    base_prob: float
    subtypes: tuple[str, ...] = ()


@dataclass(frozen=True)
class FormationSpec:
    name: str
    synonyms: tuple[str, ...]
    lithology: str
    base_top_tvdss: float  # top at the field centre, metres below MSL
    hazards: tuple[Hazard, ...] = field(default_factory=tuple)


STRATIGRAPHY: tuple[FormationSpec, ...] = (
    FormationSpec("Dhekiajuli", ("Alluvium/Dhekiajuli", "Dhekiajuli Fm"), "sand, clay", -110.0),
    FormationSpec(
        "Namsang",
        ("Namsang Fm", "NMS"),
        "sandstone, clay",
        700.0,
        (Hazard("LOSS", 0.08, ("seepage",)),),
    ),
    FormationSpec(
        "Girujan Clay",
        ("Girujan", "Girujan Fm", "GRJ"),
        "mottled clay",
        1300.0,
        (Hazard("TIGHT", 0.35), Hazard("BALLING", 0.30)),
    ),
    FormationSpec(
        "Tipam Sandstone",
        ("Tipam", "Tipam Sst", "TPM"),
        "sandstone",
        2200.0,
        (Hazard("LOSS", 0.60, ("partial", "severe", "total")),),
    ),
    FormationSpec(
        "Barail",
        ("Barail Group", "Barails", "BRL", "Barail Gr."),
        "shale, coal, sandstone",
        2900.0,
        (
            Hazard("STUCK", 0.42, ("differential", "pack-off", "mechanical")),
            Hazard("TORQUE", 0.30),
            Hazard("INSTAB", 0.22, ("cavings", "sloughing")),
        ),
    ),
    FormationSpec(
        "Kopili",
        ("Kopili Fm", "KPL"),
        "shale",
        3550.0,
        (Hazard("OVERP", 0.30), Hazard("KICK", 0.12, ("gas",)), Hazard("INSTAB", 0.18)),
    ),
    FormationSpec(
        "Sylhet",
        ("Sylhet Limestone", "SLT"),
        "limestone",
        3750.0,
        (Hazard("LOSS", 0.25, ("partial", "severe")),),
    ),
    FormationSpec(
        "Langpar", ("Langpar Fm",), "sandstone, shale", 3950.0, (Hazard("KICK", 0.10, ("gas",)),)
    ),
    FormationSpec("Basement", ("Granitic basement",), "granite", 4150.0),
)

# Planted probability that an action resolves an event (master plan §Stage 8). The
# Mitigation Effectiveness Ledger must recover this ranking from extracted records.
PLANTED_SUCCESS: dict[str, dict[str, float]] = {
    "LOSS": {
        "LCM_PILL_COARSE": 0.78,
        "LCM_PILL_FINE": 0.55,
        "REDUCE_FLOW_RATE": 0.42,
        "REDUCE_MW": 0.35,
        "CEMENT_PLUG": 0.90,
    },
    "STUCK": {
        "SPOT_PIPE_RELEASE_PILL": 0.72,
        "JAR_UP": 0.60,
        "INCREASE_FLOW": 0.45,
        "WORK_PIPE": 0.40,
        "BACKOFF_AND_FISH": 0.85,
    },
    "KICK": {"WAIT_AND_WEIGHT": 0.92, "DRILLERS_METHOD": 0.88},
    "TIGHT": {"REAM": 0.80, "INCREASE_MW": 0.60, "WORK_PIPE": 0.55},
    "TORQUE": {"ADD_LUBRICANT": 0.75, "REDUCE_RPM": 0.60},
    "INSTAB": {"INCREASE_MW": 0.65, "REAM": 0.50},
    "BALLING": {"ADD_DETERGENT": 0.72, "INCREASE_FLOW": 0.60},
    "OVERP": {"INCREASE_MW": 0.85},
    "CEMENT": {"TOP_JOB": 0.80, "REMEDIAL_SQUEEZE": 0.70},
}

# How often crews try each action first (independent of how well it works — so the
# ledger has to discover effectiveness rather than read it off usage frequency).
FIRST_CHOICE_WEIGHTS: dict[str, dict[str, float]] = {
    "LOSS": {
        "LCM_PILL_FINE": 0.35,
        "REDUCE_MW": 0.25,
        "LCM_PILL_COARSE": 0.25,
        "REDUCE_FLOW_RATE": 0.15,
    },
    "STUCK": {
        "WORK_PIPE": 0.35,
        "JAR_UP": 0.30,
        "SPOT_PIPE_RELEASE_PILL": 0.20,
        "INCREASE_FLOW": 0.15,
    },
    "KICK": {"DRILLERS_METHOD": 0.6, "WAIT_AND_WEIGHT": 0.4},
    "TIGHT": {"WORK_PIPE": 0.4, "REAM": 0.4, "INCREASE_MW": 0.2},
    "TORQUE": {"REDUCE_RPM": 0.55, "ADD_LUBRICANT": 0.45},
    "INSTAB": {"REAM": 0.5, "INCREASE_MW": 0.5},
    "BALLING": {"INCREASE_FLOW": 0.6, "ADD_DETERGENT": 0.4},
    "OVERP": {"INCREASE_MW": 1.0},
    "CEMENT": {"REMEDIAL_SQUEEZE": 0.6, "TOP_JOB": 0.4},
}

# Actions tried only after first-line actions fail.
ESCALATION: dict[str, str] = {"LOSS": "CEMENT_PLUG", "STUCK": "BACKOFF_AND_FISH"}

CASING_PROGRAM = (
    # (casing OD label, hole label, casing OD in, hole in)
    ("13-3/8", "17-1/2", 13.375, 17.5),
    ("9-5/8", "12-1/4", 9.625, 12.25),
    ("7", "8-1/2", 7.0, 8.5),
)

ACTION_TEXT: dict[str, tuple[str, ...]] = {
    "LCM_PILL_COARSE": ("Pumped {v} coarse LCM pill", "Spotted {v} of coarse LCM"),
    "LCM_PILL_FINE": ("Pumped {v} fine LCM pill", "Spotted fine LCM pill ({v})"),
    "REDUCE_MW": ("Reduced mud weight to {mw}", "Cut back mud weight to {mw}"),
    "REDUCE_FLOW_RATE": ("Reduced flow rate to {q}", "Lowered pump rate to {q}"),
    "CEMENT_PLUG": (
        "Set cement plug across loss zone",
        "Placed balanced cement plug over loss zone",
    ),
    "SPOT_PIPE_RELEASE_PILL": ("Spotted pipe release pill and soaked", "Spotted pipe-freeing pill"),
    "JAR_UP": ("Jarred up", "Worked jars upward"),
    "INCREASE_FLOW": ("Increased flow rate to {q}", "Raised circulation rate to {q}"),
    "WORK_PIPE": ("Worked pipe", "Worked string up and down"),
    "BACKOFF_AND_FISH": ("Backed off string and ran fishing assembly", "Backed off and fished"),
    "WAIT_AND_WEIGHT": (
        "Killed well by wait and weight method",
        "Circulated out kick, wait-and-weight method",
    ),
    "DRILLERS_METHOD": (
        "Circulated out kick by driller's method",
        "Killed well using driller's method",
    ),
    "REAM": ("Reamed the tight interval", "Back-reamed through tight spot"),
    "INCREASE_MW": ("Raised mud weight to {mw}", "Increased mud weight to {mw}"),
    "ADD_LUBRICANT": ("Added lubricant to mud system", "Treated mud with lubricant"),
    "REDUCE_RPM": ("Reduced rotary speed to {rpm} rpm", "Lowered RPM to {rpm}"),
    "ADD_DETERGENT": ("Added detergent to mud", "Treated system with drilling detergent"),
    "TOP_JOB": ("Performed top job", "Carried out cement top job"),
    "REMEDIAL_SQUEEZE": ("Performed remedial squeeze cementing", "Squeezed cement at shoe"),
}

SUCCESS_WORDS: dict[str, tuple[str, ...]] = {
    "LOSS": ("losses cured", "full returns regained"),
    "STUCK": ("pipe freed", "string came free"),
    "KICK": ("well under control", "well killed and static"),
    "TIGHT": ("hole free", "no further drag"),
    "TORQUE": ("torque back to normal", "torque stabilised"),
    "INSTAB": ("hole stable", "cavings reduced"),
    "BALLING": ("ROP recovered", "bit cleaned up"),
    "OVERP": ("gas readings back to background", "overbalance restored"),
    "CEMENT": ("cement integrity confirmed", "good cement top confirmed"),
}
FAIL_WORDS = ("not successful", "without success", "no improvement", "unsuccessful")

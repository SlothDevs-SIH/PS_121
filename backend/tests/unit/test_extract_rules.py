"""S2 extraction rules: unit conversion, classification, actions and outcomes."""

import pytest

from app.core import units
from app.extract import rules


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Tight hole at 1,890 m in Girujan", 1890.0),
        ("stuck at 11,725 ft (Barail)", units.ft_to_m(11725)),
        ("Drilled to 2039m", 2039.0),
        ("pit gain 5 m3", None),  # m3 is a volume, not a depth
        ("rate 2.7 m3/hr", None),
    ],
)
def test_depth_m(text: str, expected: float | None) -> None:
    got = rules.depth_m(text)
    assert got == (pytest.approx(expected) if expected is not None else None)


def test_units_are_canonical() -> None:
    assert rules.mud_weight_sg("MW: 1.18 SG") == pytest.approx(1.18)
    assert rules.mud_weight_sg("MW:10.5ppg") == pytest.approx(10.5 / units.PPG_PER_SG)
    assert rules.rate_m3_h("losses of 149 bbl/hr") == pytest.approx(149 * units.BBL_TO_M3)
    assert rules.volume_m3("22 bbl pit gain") == pytest.approx(22 * units.BBL_TO_M3)
    assert rules.sidpp_kpa("SIDPP 353 psi") == pytest.approx(353 * units.PSI_TO_KPA)
    assert rules.torque_knm("torque up to 26.5 kft.lbf") == pytest.approx(
        26.5 * units.KFTLBF_TO_KNM
    )


@pytest.mark.parametrize("raw", ["overpull 50 klbf", "overpull 50 kibf", "with 50 klbf overpull"])
def test_overpull_tolerates_ocr(raw: str) -> None:
    assert rules.overpull_kn(raw) == pytest.approx(50 * units.KLBF_TO_KN)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("12-1/4", 12.25), ("9 5/8", 9.625), ("7", 7.0), ('13-3/8"', 13.375), ("YT", None)],
)
def test_hole_size(raw: str, expected: float | None) -> None:
    assert rules.hole_size_in(raw) == expected


@pytest.mark.parametrize(
    ("text", "code", "etype", "from_text", "agrees"),
    [
        ("Total losses of no returns while drilling", "NPT-LOSS", "LOSS", True, True),
        ("Cement job at 2362 m - losses during cementing", "NPT-CMT", "CEMENT", True, True),
        ("Well kicked at 3,745 m, 5 m3 pit gain", "NPT-WC", "KICK", True, True),
        ("High gas (13.1%) and connection gas", "NPT-WC", "OVERP", True, True),
        ("Suspected bit balling in Girujan", "NPT-HOLE", "BALLING", True, True),
        ("Tight hole at 1890 m", "NPT-LOSS", "TIGHT", True, False),
        ("Waited on orders", None, "WAIT", True, None),
        ("Operations suspended", "NPT-LOSS", "LOSS", False, True),
        ("Operations suspended", "NPT-XYZ", "OTHER_NPT", False, True),
    ],
)
def test_classify_event(
    text: str, code: str | None, etype: str, from_text: bool, agrees: bool | None
) -> None:
    g = rules.classify_event(text, code)
    assert g is not None
    assert (g.event_type, g.from_text, g.code_agrees) == (etype, from_text, agrees)


def test_classify_event_none_for_productive_text() -> None:
    assert rules.classify_event("Drilled 12-1/4 in hole from 1923 to 2039 m") is None


def test_severity_bands() -> None:
    assert rules.severity("LOSS", "seepage", {}) == "low"
    assert rules.severity("LOSS", None, {"loss_rate_m3_h": units.bbl_to_m3(150)}) == "high"
    assert rules.severity("LOSS", None, {"loss_rate_m3_h": units.bbl_to_m3(5)}) == "low"
    assert rules.severity("STUCK", "differential", {}) == "high"
    assert rules.severity("TIGHT", None, {"overpull_kn": units.klbf_to_kn(30)}) == "low"


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("Pumped 40 bbl coarse LCM pill", "LCM_PILL_COARSE"),
        ("Spotted fine LCM pill (9 m3)", "LCM_PILL_FINE"),
        ("Cut back mud weight to 1.34 SG", "REDUCE_MW"),
        ("Raised mud weight to 1.47 SG", "INCREASE_MW"),
        ("Lowered pump rate to 572 gpm", "REDUCE_FLOW_RATE"),
        ("Raised circulation rate to 2601 lpm", "INCREASE_FLOW"),
        ("Worked jars upward", "JAR_UP"),
        ("Worked string up and down", "WORK_PIPE"),
        ("Backed off and fished", "BACKOFF_AND_FISH"),
        ("Circulated out kick, wait-and-weight method", "WAIT_AND_WEIGHT"),
        ("Killed well using driller's method", "DRILLERS_METHOD"),
        ("Back-reamed through tight spot", "REAM"),
        ("Treated system with drilling detergent", "ADD_DETERGENT"),
        ("Lowered RPM to 80", "REDUCE_RPM"),
        ("Squeezed cement at shoe", "REMEDIAL_SQUEEZE"),
        ("Carried out cement top job", "TOP_JOB"),
        ("Lost circulation at 2,783 m", "OTHER"),  # a problem, not an action
        ("Held safety meeting", "OTHER"),
    ],
)
def test_classify_action(text: str, code: str) -> None:
    assert rules.classify_action(text) == code


@pytest.mark.parametrize(
    ("text", "outcome"),
    [
        ("full returns regained", "success"),
        ("string came free", "success"),
        ("no improvement", "fail"),
        ("unsuccessful", "fail"),
        ("not successful", "fail"),
        ("pumped pill", "unknown"),
    ],
)
def test_classify_outcome(text: str, outcome: str) -> None:
    assert rules.classify_outcome(text) == outcome


def test_split_action_outcome_uses_last_separator() -> None:
    assert rules.split_action_outcome(
        "Circulated out kick, wait-and-weight method - well killed"
    ) == (
        "Circulated out kick, wait-and-weight method",
        "well killed",
    )
    assert rules.split_action_outcome("Worked pipe") == ("Worked pipe", "")


def test_total_npt() -> None:
    assert rules.total_npt_hours("... Total NPT 28.9 hrs.") == 28.9
    assert rules.total_npt_hours("no downtime") is None

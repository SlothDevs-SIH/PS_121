"""DDR and WCR parsers on text-layer and OCR-damaged report text."""

from datetime import date, datetime

import pytest

from app.core import units
from app.extract import ddr, wcr
from app.extract.drafts import Joined, Line, ocr_confidence


def _lines(text: str, conf: float | None = None) -> list[Line]:
    out = []
    for k, raw in enumerate(text.strip("\n").splitlines()):
        x0 = 0.45 if raw.startswith(">") else 0.08  # ">" marks a wrapped operation cell
        out.append(
            Line(span_id=100 + k, page_no=1, text=raw.lstrip(">"), conf=conf, x0=x0, y=k / 50)
        )
    return out


DDR_TEXT = """
DAILY DRILLING REPORT
SYNTHETIC DATA - NOT OIL INDIA DATA
Well: SYN-ASM-01  Rig: Rig SYN-3 Report No: 5 Date: 2009-01-23
Depth at 24:00: 2,783 m Hole size: 8-1/2 in Mud weight: 1.43 SG Formation: Tipam Sandstone
TIME LOG
From  To  Hrs  Depth (m)  Code  Operation
00:00  07:12  7.2  2783  DRL  Drilled 8-1/2 in hole from 2749 to 2783 m
07:12  07:42  0.5  2783  NPT-LOSS  Partial losses of 2.7 m3/hr while drilling at 2783 m in Tipam Sst
07:42  10:36  2.9  2783  NPT-LOSS  Spotted fine LCM pill (9 m3) - not successful
10:36  12:36  2.0  2783  NPT-LOSS  Cut back mud weight to 1.39 SG - full returns regained
12:36  24:00  11.4  2783  CIRC  Circulated and conditioned mud
REMARKS
Partial losses of 2.7 m3/hr while drilling at 2783 m in Tipam Sst. Spotted fine LCM pill:
not successful. Cut back mud weight: full returns regained. Total NPT 4.9 hrs.
MUD
Mud type: KCl-polymer MW: 1.43 SG Funnel viscosity: 50 s/qt
Page 1
"""


def test_ddr_event_with_two_mitigations() -> None:
    p = ddr.parse(_lines(DDR_TEXT))
    assert p.report_date == date(2009, 1, 23)
    assert len(p.operations) == 5
    assert [op.event_index for op in p.operations] == [None, 0, 0, 0, None]
    (ev,) = p.events
    assert (ev.event_type, ev.subtype, ev.severity) == ("LOSS", "partial", "medium")
    assert ev.md_m == 2783.0 and ev.depth_votes == 3
    assert ev.params == {"loss_rate_m3_h": 2.7}
    assert (ev.hole_size_in, ev.mw_sg) == (8.5, 1.43)
    assert ev.npt_hours == 4.9 and ev.npt_stated
    assert [(m.action_code, m.outcome, m.npt_hours) for m in ev.mitigations] == [
        ("LCM_PILL_FINE", "fail", 2.9),
        ("REDUCE_MW", "success", 2.0),
    ]
    assert ev.resolved is True
    assert ev.t_start is not None and ev.t_start.isoformat() == "2009-01-23T07:12:00+05:30"
    assert ev.penalties.reasons == []
    # Evidence: the problem row is primary; header and remarks lines support it.
    assert ev.primary[0].text.startswith("07:12")
    assert any(
        ln.text.startswith("REMARKS") is False and "Total NPT" in ln.text for ln in ev.supporting
    )


def test_ddr_quiet_day_has_no_events() -> None:
    text = DDR_TEXT.split("TIME LOG")[0] + (
        "TIME LOG\nFrom  To  Hrs  Depth (m)  Code  Operation\n"
        "00:00  07:12  7.2  2783  DRL  Drilled ahead\n"
        "07:12  24:00  16.8  2783  CIRC  Circulated\nREMARKS\nNormal drilling.\n"
    )
    p = ddr.parse(_lines(text))
    assert p.events == [] and len(p.operations) == 2


OCR_DDR = """
Well: SYN-ASM-39  Rig: Rig SYN-1 Report No: 5 Date: 2021-07-24
Depth at 24:00: 3212 m Hole size: 8-1/2 in Mud weight: 1.41 SG Formation: Barail
TIME LOG
From  To  Hrs  Depth(m)  Code  Operation
00:00  08:07  8.1  3212  DRL  Drilled 8-1/2 in hole from 3164 to 3212m
a a  eee et  ey ea SATIS  Rg
08:07  08:37  05  3212  NPT-STCK  Pipe stuck (pack-off) at 3212 m in Barail, overpull 85 kibf
08:37.=.  21:37."  13.0.  3212  NPT-STCK Worked pipe - not successful
21:37  02:07  he SJ  3212  NPT-STCK  Raised circulation rate to 1735 Ipm - string came free
02:07  24:00  0.5  3212  CIRC  Circulated and conditioned mud
REMARKS
Pipe stuck (pack-off) at 3212 m in Barail, overpull 85 kibf. Total NPT 17.5 hrs.
"""


def test_ddr_survives_ocr_damage() -> None:
    p = ddr.parse(_lines(OCR_DDR, conf=90))
    (ev,) = p.events
    assert (ev.event_type, ev.subtype) == ("STUCK", "pack-off")
    assert ev.params["overpull_kn"] == pytest.approx(85 * units.KLBF_TO_KN, abs=1e-3)
    assert [(m.action_code, m.outcome) for m in ev.mitigations] == [
        ("WORK_PIPE", "fail"),
        ("INCREASE_FLOW", "success"),
    ]
    # Hours come from the clock times (the Hrs column lost its decimals); past midnight too.
    assert [m.npt_hours for m in ev.mitigations] == [13.0, 4.5]
    assert ev.npt_hours == 17.5
    assert ocr_confidence(ev.primary) == 0.9


def test_ddr_wrapped_operation_cell_is_rejoined() -> None:
    text = """
Well: W-1 Date: 2015-06-03
Depth at 24:00: 3994 m Hole size: 8-1/2 in Mud weight: 1.38 SG Formation: Kopili
From  To  Hrs  Depth (m)  Code  Operation
00:00  08:33  8.6  3994  DRL  Drilled
>High gas (4.4%) and connection gas at 3994 m, Kopili - overpressure
08:33  09:03  0.5  3994  NPT-WC
>suspected
09:03  11:51  2.8  3994  NPT-WC  Increased mud weight to 1.42 SG - gas readings back to background
REMARKS
"""
    p = ddr.parse(_lines(text))
    (ev,) = p.events
    assert ev.event_type == "OVERP" and ev.params == {"gas_pct": 4.4}
    assert ev.description.endswith("overpressure suspected")
    assert len(ev.primary) == 3  # both wrapped lines and the row itself are cited


def test_ddr_code_only_event_is_penalised() -> None:
    text = """
Date: 2020-01-01
From  To  Hrs  Depth (ft)  Code  Operation
01:00  02:00  1.0  9000  NPT-LOSS  Operations suspended
"""
    (ev,) = ddr.parse(_lines(text)).events
    assert ev.event_type == "LOSS" and not ev.type_from_text
    assert ev.md_m == pytest.approx(units.ft_to_m(9000))
    reasons = " ".join(ev.penalties.reasons)
    assert "NPT code" in reasons and "time-log column" in reasons
    assert ev.penalties.apply(0.95) < 0.75  # goes to the review queue


WCR_TEXT = """
WELL COMPLETION REPORT
1. WELL DATA
Well: SYN-ASM-24
Depth reference: RKB. Units: oilfield (ft, ppg, bbl)
3. CASING AND CEMENTING
Casing (in)  Hole (in)  Shoe MD (ft)  Cement top MD (ft)  Returns
13-3/8  17-1/2  2664  ie)  full
9-5/8  12-1/4  7802  2172  partial
YT  8-1/2  11948  7310  full
4. MUD PROGRAMME
Interval (ft)  Hole (in)  Mud type  Mud weight
0 - 2664  17-1/2  water-based  9.0 ppg
2664 - 7802  12-1/4  water-based  10.2 ppg
5. DRILLING PROBLEMS AND LESSONS
- 2019-04-18: Tight hole at 5,077 ft in Girujan Fm, overpull 52 kibf. Actions: Reamed the
tight interval (no further drag, 4.7 hrs). NPT 4.7 hrs.
- 2019-04-22: String became stuck at 7,000 ft (Tipam); differential sticking suspected,
overpull 120 klbf. Actions: Worked pipe (no improvement, 4.5 hrs); Spotted pipe release
pill and soaked (string came free, 3.0 hrs). NPT 7.5 hrs.
Page 1
"""


def test_wcr_tables_and_problems() -> None:
    p = wcr.parse(_lines(WCR_TEXT))
    assert [(c.od_in, c.hole_size_in, c.returns) for c in p.casing] == [
        (13.375, 17.5, "full"),
        (9.625, 12.25, "partial"),
        (None, 8.5, "full"),  # "YT": unreadable, left null and penalised, never guessed
    ]
    assert p.casing[0].toc_md_m is None and p.casing[0].penalties.reasons
    assert p.casing[1].shoe_md_m == pytest.approx(units.ft_to_m(7802))
    assert [(m.md_to_m, m.mud_type) for m in p.mud] == [
        (pytest.approx(units.ft_to_m(2664)), "water-based"),
        (pytest.approx(units.ft_to_m(7802)), "water-based"),
    ]
    assert p.mud[0].mw_sg == pytest.approx(9.0 / units.PPG_PER_SG)

    tight, stuck = p.events
    assert tight.event_type == "TIGHT" and tight.event_date == date(2019, 4, 18)
    assert tight.md_m == pytest.approx(units.ft_to_m(5077))
    assert tight.hole_size_in == 12.25  # from the mud programme interval, cited as support
    assert [(m.action_code, m.outcome, m.npt_hours) for m in tight.mitigations] == [
        ("REAM", "success", 4.7)
    ]
    assert stuck.subtype == "differential" and stuck.npt_hours == 7.5
    assert [(m.action_code, m.outcome) for m in stuck.mitigations] == [
        ("WORK_PIPE", "fail"),
        ("SPOT_PIPE_RELEASE_PILL", "success"),
    ]
    # Each action is cited by the lines it spans, not the whole bullet.
    assert [ln.text[:5] for ln in stuck.mitigations[1].lines] == ["overp", "pill "]


def test_joined_maps_ranges_to_lines() -> None:
    j = Joined(_lines("alpha beta\ngamma delta\nepsilon"))
    assert j.text == "alpha beta gamma delta epsilon"
    assert [ln.span_id for ln in j.lines_for(6, 16)] == [100, 101]
    assert [ln.span_id for ln in j.lines_for(23, 30)] == [102]


def test_clock_rolls_24_00_to_next_day() -> None:
    got = ddr._clock(date(2020, 1, 1), "24", "00")
    assert got == datetime(2020, 1, 2, tzinfo=ddr.IST)
    assert ddr._clock(date(2020, 1, 1), "25", "00") is None

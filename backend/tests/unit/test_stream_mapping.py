"""Channel mapping, unit conversion, the replay file and the replay scenario (S12)."""

import csv
import io
from datetime import UTC, datetime

import numpy as np
import pytest

from app.risk.prior import prognosed_top
from app.stream import mapping as mp
from app.synthetic import realtime as rt


def test_oilfield_units_convert_to_canonical_si() -> None:
    rec = {"DBTM": "10000", "HKLA": "100", "TQA": "10", "SPPA": "1000", "MFIA": "500"}
    vals, quality = mp.to_canonical(rec, mp.CSV_DEFAULTS)
    assert vals["bit_depth_m"] == pytest.approx(3048.0)
    assert vals["hookload_kn"] == pytest.approx(444.8222)
    assert vals["torque_knm"] == pytest.approx(13.55818)
    assert vals["spp_kpa"] == pytest.approx(6894.757)
    assert vals["flow_in_lpm"] == pytest.approx(1892.706)
    assert quality["gas_pct"] == "missing"  # absent in the record: a gap, not a zero
    assert vals["gas_pct"] is None


def test_bad_and_null_values_are_flagged_not_zeroed() -> None:
    vals, quality = mp.to_canonical({"DBTM": "-999.25", "HKLA": "n/a"}, mp.CSV_DEFAULTS)
    assert vals["bit_depth_m"] is None and quality["bit_depth_m"] == "missing"
    assert vals["hookload_kn"] is None and quality["hookload_kn"] == "unreadable"
    only_depth = [mp.ChannelMap("DEPTH", "bit_depth_m", "m")]
    _, q2 = mp.to_canonical({"DEPTH": "1"}, only_depth)
    assert q2["torque_knm"] == "unmapped"


def test_replay_csv_round_trips() -> None:
    ep = rt.normal_episode(np.random.default_rng(3), "W", 1500, datetime(2020, 1, 1), 8.5, 1.2)
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    body = mp.write_csv(t0, rt.DT_S, ep.data, mp.CSV_DEFAULTS)
    rows = list(csv.DictReader(io.StringIO(body)))
    assert len(rows) == ep.n
    assert mp.parse_time(rows[1][mp.TIME_COLUMN]) == datetime(2026, 1, 1, 0, 0, 10, tzinfo=UTC)
    for i in (0, 400, ep.n - 1):
        vals, quality = mp.to_canonical(rows[i], mp.CSV_DEFAULTS)
        assert not quality
        for ch in rt.CHANNELS:
            assert vals[ch] == pytest.approx(float(ep.data[ch][i]), abs=1e-3, rel=1e-5)


def test_prognosed_top_weights_near_offsets() -> None:
    z, spread = prognosed_top([(100, 2000.0), (1000, 2100.0), (5000, 2500.0)])
    assert 2000 < z < 2005  # the 100 m offset dominates
    assert spread > 0
    assert prognosed_top([(10, 1500.0)]) == pytest.approx((1500.0, 0.0))
    near = [(100.0, 1000.0), *((1000.0 * k, 3000.0) for k in range(1, 5))]
    beyond = [(9000.0, 9000.0)]  # a sixth, farther offset is ignored
    assert prognosed_top(near + beyond) == prognosed_top(near)


def test_replay_scenario_plants_balling_then_losses_in_the_next_formation() -> None:
    t0 = datetime(2026, 9, 28, 18, tzinfo=UTC)
    ep = rt.replay_episode(7, "W", 2200.0, t0, 2260.0, 8.5, 1.4)
    balling, loss = ep.planted
    assert (balling.event_type, loss.event_type) == ("BALLING", "LOSS")
    assert ep.data["hole_depth_m"][loss.start] >= 2264.0
    assert ep.data["hole_depth_m"][loss.start - 1] < 2264.0
    assert ep.n == loss.start + 360
    d = ep.data
    during = slice(loss.start + 10, loss.start + 170)
    after = slice(loss.end + 30, ep.n)
    pumping = d["flow_in_lpm"] > 200
    imb = np.where(
        pumping, (d["flow_out_lpm"] - d["flow_in_lpm"]) / np.maximum(d["flow_in_lpm"], 1), 0
    )
    assert np.mean(imb[during][pumping[during]]) < -0.3  # losing returns
    assert abs(np.mean(imb[after][pumping[after]])) < 0.05  # cured: returns back
    with pytest.raises(ValueError):
        rt.replay_episode(7, "W", 2200.0, t0, 2205.0, 8.5, 1.4)  # reached too soon
    far = rt.replay_episode(7, "W", 2200.0, t0, 3500.0, 8.5, 1.4)  # out of reach in 12 h
    assert far.planted[1].start == rt.REPLAY_FALLBACK_LOSS

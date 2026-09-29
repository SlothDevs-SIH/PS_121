"""The per-well scorer over the replay scenario, with a hand-built context (no database)."""

from datetime import UTC, datetime, timedelta

import numpy as np

from app.risk import assets
from app.stream.scorer import LOOKAHEAD_TVD_M, Interval, WellContext, WellScorer
from app.synthetic import realtime as rt

T0 = datetime(2026, 9, 28, 18, tzinfo=UTC)
RKB = 100.0


def _ctx(next_top_md: float) -> WellContext:
    md = np.array([0.0, 3000.0])
    return WellContext(
        well_id=1,
        wellbore_id=1,
        name="W",
        hole_size_in=8.5,
        station_md=md,
        station_tvdss=md - RKB,  # vertical
        last_inc_deg=0.0,
        intervals=[
            Interval("Girujan Clay", 1300.0, 1200.0, False, {"BALLING": 0.4}, {"BALLING": [7]}),
            Interval("Tipam Sandstone", next_top_md, next_top_md - RKB, True,
                     {"LOSS": 0.36, "STUCK": 0.1}, {"LOSS": [11, 12]}),
        ],
    )  # fmt: skip


def _run(scorer: WellScorer, ep: rt.Episode) -> list[tuple[int, object]]:
    out = []
    for i in range(ep.n):
        values: dict[str, float | None] = {c: float(ep.data[c][i]) for c in rt.CHANNELS}
        frame, cands = scorer.push(T0 + timedelta(seconds=rt.DT_S * i), values)
        assert frame.rig_state
        out += [(i, c) for c in cands]
    return out


def test_replay_raises_lookahead_then_physics_loss_with_evidence() -> None:
    top = 2275.0
    ep = rt.replay_episode(3, "W", 2214.0, T0, top, 8.5, 1.42)
    scorer = WellScorer(_ctx(top), bundle=None, library=[], tau=None)
    got = _run(scorer, ep)
    loss_start = ep.planted[1].start

    ahead = [(i, c) for i, c in got if c.alert_type == "LOOKAHEAD"]
    assert [c.event_type for _, c in ahead] == ["LOSS"]  # STUCK's 10% is under 30%
    i, c = ahead[0]
    dist = (top - RKB) - (float(ep.data["hole_depth_m"][i]) - RKB)
    assert 0 < dist <= LOOKAHEAD_TVD_M
    assert c.formation == "Tipam Sandstone" and c.score_kind == "prior"
    assert [e["event_id"] for e in c.evidence] == [11, 12]

    physics = [(i, c) for i, c in got if c.alert_type == "PHYSICS"]
    assert physics and all(c.event_type == "LOSS" for _, c in physics)
    lead = ep.planted[1].lead_steps  # fires in the precursor (returns dropping) or the loss
    assert loss_start - lead <= physics[0][0] <= loss_start + 60
    assert all(c.evidence[0]["kind"] == "stream" for _, c in physics)
    # Above the prognosed top (the precursor starts before the bit enters Tipam), but within
    # the engine's 30 m TVD of the look-ahead, so the two fuse into one alert.
    assert all(
        c.tvdss_m is not None
        and ahead[0][1].tvdss_m is not None
        and abs(c.tvdss_m - ahead[0][1].tvdss_m) <= 30
        for _, c in physics
    )


def test_deja_vu_matches_a_past_loss_before_it_happens() -> None:
    library = [
        assets.signature_of(
            rt.event_episode(np.random.default_rng(s), "P", "E", "LOSS", 2300, T0, "T", 8.5, 1.4),
            s,
            well_id=100 + s,
        )
        for s in range(4)
    ]
    ep = rt.event_episode(np.random.default_rng(42), "W", "E", "LOSS", 2300, T0, "T", 8.5, 1.4)
    scorer = WellScorer(_ctx(5000.0), bundle=None, library=library, tau=1.07)
    got = [(i, c) for i, c in _run(scorer, ep) if c.alert_type == "DEJA_VU"]
    assert got, "no Deja Vu candidate"
    i, c = got[0]
    assert c.event_type == "LOSS" and c.score_kind == "similarity"
    assert c.score is not None and c.score >= 0.8
    assert i <= rt.PRE_STEPS + 60  # before or at the start of the loss
    # The own well is excluded from matching.
    own = WellScorer(_ctx(5000.0), None, [assets.signature_of(ep, 0, well_id=1)], 1.07)
    assert not [c for _, c in _run(own, ep) if c.alert_type == "DEJA_VU"]


def test_quiet_drilling_raises_nothing() -> None:
    ep = rt.normal_episode(np.random.default_rng(5), "W", 2000.0, T0, 8.5, 1.3)
    scorer = WellScorer(_ctx(5000.0), bundle=None, library=[], tau=None)
    assert _run(scorer, ep) == []

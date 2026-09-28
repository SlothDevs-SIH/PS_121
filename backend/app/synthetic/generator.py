"""Deterministic generator for the synthetic field (ground truth for every later phase).

Each well and purpose draws from its own seeded stream (`_rng(well_index, purpose)`), so
adding new generated content later (e.g. real-time streams in Part 4) never changes data
that already exists. Output is plain dataclasses, serialisable to `truth.json`.
"""

import math
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

import numpy as np
from pyproj import Transformer

from app.geo.mincurv import Trajectory, directional_stations, minimum_curvature, vertical_stations
from app.synthetic import model as sm

_PURPOSES = {
    "layout": 1,
    "traj": 2,
    "tops": 3,
    "hazards": 4,
    "events": 5,
    "mud": 6,
    "docs": 7,
    "rt": 8,
}


def _rng(*key: int) -> np.random.Generator:
    return np.random.default_rng([sm.SEED, *key])


@dataclass
class Mitigation:
    action_code: str
    outcome: str  # success | fail
    npt_hours: float
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class Event:
    event_id: str
    event_type: str
    subtype: str | None
    severity: str
    md_m: float
    tvd_m: float
    tvdss_m: float
    formation: str
    hole_size: str
    mw_sg: float
    start: str  # ISO datetime (UTC)
    params: dict[str, float]
    mitigations: list[Mitigation]
    total_npt_hours: float
    resolved: bool


@dataclass
class CasingString:
    od_label: str
    hole_label: str
    shoe_md_m: float
    shoe_tvd_m: float
    cement_top_md_m: float
    returns: str  # full | partial | none


@dataclass
class MudInterval:
    md_from_m: float
    md_to_m: float
    hole_label: str
    mud_type: str
    mw_sg: float


@dataclass
class FormationTop:
    formation: str
    top_md_m: float
    top_tvd_m: float
    top_tvdss_m: float


@dataclass
class Well:
    index: int
    name: str
    aliases: list[str]
    status: str  # completed | drilling | planned
    well_type: str
    profile: str  # vertical | J | S
    lat: float
    lon: float
    x: float  # UTM easting
    y: float  # UTM northing
    gl_elev_m: float
    rkb_elev_m: float
    units: str  # metric | oilfield
    rig: str
    spud: str
    completion: str | None
    td_md_m: float
    stations: list[list[float]]  # [md, inc, azi]
    tops: list[FormationTop]
    casing: list[CasingString]
    mud: list[MudInterval]
    events: list[Event]


@dataclass
class SyntheticField:
    field_name: str
    basin: str
    crs_epsg: int
    seed: int
    formations: list[dict[str, Any]]
    planted_success: dict[str, dict[str, float]]
    wells: list[Well]

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


# ─── Spatial fields ────────────────────────────────────────────────────────────


def _smooth_field(
    rng: np.random.Generator, n_bumps: int = 4
) -> list[tuple[float, float, float, float]]:
    """Random Gaussian bumps in km relative to the field centre: (x, y, width, weight)."""
    return [
        (
            float(rng.uniform(-7, 7)),
            float(rng.uniform(-7, 7)),
            float(rng.uniform(1.8, 4.0)),
            float(rng.uniform(0.5, 1.0)),
        )
        for _ in range(n_bumps)
    ]


def _eval_field(bumps: list[tuple[float, float, float, float]], xk: float, yk: float) -> float:
    v = sum(
        w * math.exp(-((xk - bx) ** 2 + (yk - by) ** 2) / (2 * s * s)) for bx, by, s, w in bumps
    )
    return min(1.0, v)


def _structure_tvdss(
    spec_index: int, xk: float, yk: float, noise_bumps: list[tuple[float, float, float, float]]
) -> float:
    spec = sm.STRATIGRAPHY[spec_index]
    if spec_index == 0:
        return spec.base_top_tvdss  # surface formation starts at ground level (handled per well)
    dome = 140.0 * math.exp(-(xk * xk + yk * yk) / (2 * 4.0**2))
    dip = 7.0 * (xk - yk) / math.sqrt(2)  # deepening towards the south-east
    noise = 25.0 * (_eval_field(noise_bumps, xk, yk) - 0.5)
    thick_var = 1.0 + 0.015 * (_eval_field(noise_bumps, yk, xk) - 0.5)
    return spec.base_top_tvdss * thick_var + dip - dome + noise


# ─── Generator ────────────────────────────────────────────────────────────────


def generate(n_wells: int = 40) -> SyntheticField:
    to_utm = Transformer.from_crs(4326, sm.CRS_EPSG, always_xy=True)
    to_ll = Transformer.from_crs(sm.CRS_EPSG, 4326, always_xy=True)
    cx, cy = to_utm.transform(sm.CENTER_LON, sm.CENTER_LAT)

    layout = _rng(0, _PURPOSES["layout"])
    n_pads = max(3, n_wells // 5)
    pads = [(float(layout.uniform(-6, 6)), float(layout.uniform(-6, 6))) for _ in range(n_pads)]
    structure_noise = _smooth_field(_rng(0, _PURPOSES["tops"]), 5)
    hz = _rng(0, _PURPOSES["hazards"])
    hazard_fields = {
        (spec.name, h.event_type): _smooth_field(hz, 4)
        for spec in sm.STRATIGRAPHY
        for h in spec.hazards
    }

    wells: list[Well] = []
    # Completed wells, then one well currently drilling (replayed in Part 4), then a planned well.
    for idx in range(1, n_wells + 3):
        if idx <= n_wells:
            status, name = "completed", f"SYN-ASM-{idx:02d}"
        elif idx == n_wells + 1:
            status, name = "drilling", f"SYN-ASM-{idx:02d}"
        else:
            status, name = "planned", "SYN-ASM-P01"
        wells.append(
            _make_well(idx, name, status, pads, cx, cy, to_ll, structure_noise, hazard_fields)
        )

    return SyntheticField(
        field_name=sm.FIELD_NAME,
        basin=sm.BASIN,
        crs_epsg=sm.CRS_EPSG,
        seed=sm.SEED,
        formations=[
            {
                "name": s.name,
                "synonyms": list(s.synonyms),
                "lithology": s.lithology,
                "strat_order": i + 1,
            }
            for i, s in enumerate(sm.STRATIGRAPHY)
        ],
        planted_success=sm.PLANTED_SUCCESS,
        wells=wells,
    )


def _make_well(
    idx: int,
    name: str,
    status: str,
    pads: list[tuple[float, float]],
    cx: float,
    cy: float,
    to_ll: Transformer,
    structure_noise: list[tuple[float, float, float, float]],
    hazard_fields: dict[tuple[str, str], list[tuple[float, float, float, float]]],
) -> Well:
    lay = _rng(idx, _PURPOSES["layout"])
    if status == "planned":
        px, py = 0.4, -0.3  # near the crest
    elif status == "drilling":
        px, py = pads[0]
    else:
        px, py = pads[(idx - 1) % len(pads)]
    xk = px + float(lay.normal(0, 0.03))
    yk = py + float(lay.normal(0, 0.03))
    x, y = cx + xk * 1000, cy + yk * 1000
    lon, lat = to_ll.transform(x, y)
    gl = float(round(lay.uniform(98, 128), 1))
    rkb = round(gl + float(lay.uniform(7.0, 10.0)), 1)
    units = "oilfield" if lay.random() < 0.4 else "metric"
    rig = f"Rig SYN-{int(lay.integers(1, 7))}"
    spud_day = date(2008, 1, 1) + timedelta(days=int(lay.integers(0, 6300)))
    if status == "drilling":
        spud_day = date(2026, 9, 1)
    if status == "planned":
        spud_day = date(2027, 1, 15)

    # Trajectory ---------------------------------------------------------------
    tr = _rng(idx, _PURPOSES["traj"])
    td_target_tvd = float(tr.uniform(3300, 4250))
    profile = "vertical" if tr.random() < 0.3 else ("J" if tr.random() < 0.7 else "S")
    if profile == "vertical":
        md, inc, azi = vertical_stations(td_target_tvd)
    else:
        kop = float(tr.uniform(500, 1200))
        bur = float(tr.uniform(1.5, 3.0))
        max_inc = float(tr.uniform(18, 42))
        az = float(tr.uniform(0, 360))
        guess_td = td_target_tvd / math.cos(math.radians(max_inc * 0.8))
        if profile == "J":
            md, inc, azi = directional_stations(guess_td, kop, bur, max_inc, az)
        else:
            md, inc, azi = directional_stations(
                guess_td,
                kop,
                bur,
                max_inc,
                az,
                drop_start_m=kop + max_inc / bur * 30 + float(tr.uniform(600, 1200)),
                drop_rate_deg_30m=float(tr.uniform(1.0, 2.0)),
                final_inc_deg=float(tr.uniform(0, 8)),
            )
    traj = minimum_curvature(md, inc, azi)
    # Trim to the target TVD.
    cut_md = traj.md_at_tvd(td_target_tvd) or float(traj.md[-1])
    if status == "drilling":
        cut_md = cut_md * 0.62  # currently mid-way (in the Tipam/Barail interval)
    keep = traj.md <= cut_md
    md, inc, azi = traj.md[keep], traj.inc[keep], traj.azi[keep]
    if md[-1] < cut_md:
        md = np.append(md, cut_md)
        inc = np.append(inc, np.interp(cut_md, traj.md, traj.inc))
        azi = np.append(azi, np.interp(cut_md, traj.md, traj.azi))
    traj = minimum_curvature(md, inc, azi)
    td_md = float(round(traj.md[-1], 1))

    # Formation tops (TVD below RKB = TVDSS + RKB elevation) ------------------------
    tops: list[FormationTop] = []
    for s_idx, spec in enumerate(sm.STRATIGRAPHY):
        n, e, _ = traj.position_at_md(float(traj.md[-1]) / 2)
        if s_idx == 0:
            tvd = 0.0 + (rkb - gl)
        else:
            # Evaluate the structure where the well crosses it (approximately).
            tvdss_guess = _structure_tvdss(s_idx, xk + e / 1000, yk + n / 1000, structure_noise)
            tvd = tvdss_guess + rkb
        md_top = traj.md_at_tvd(tvd)
        if md_top is None:
            break
        tops.append(FormationTop(spec.name, round(md_top, 1), round(tvd, 1), round(tvd - rkb, 1)))

    # Casing and mud programme --------------------------------------------------------
    mudr = _rng(idx, _PURPOSES["mud"])
    top_md = {t.formation: t.top_md_m for t in tops}
    surf_shoe = float(round(mudr.uniform(600, 950), 0))
    inter_shoe = float(
        round(top_md.get("Tipam Sandstone", td_md * 0.6) + mudr.uniform(-40, 120), 0)
    )
    inter_shoe = min(inter_shoe, td_md - 150)
    shoes = [surf_shoe, inter_shoe, td_md]
    mw_sections = [
        round(float(mudr.uniform(1.04, 1.10)), 2),
        round(float(mudr.uniform(1.14, 1.30)), 2),
        round(float(mudr.uniform(1.30, 1.55)), 2),
    ]
    casing: list[CasingString] = []
    mud: list[MudInterval] = []
    prev = 0.0
    for k, ((od, hole, _, _), shoe) in enumerate(zip(sm.CASING_PROGRAM, shoes, strict=True)):
        if prev >= td_md:
            break
        shoe = min(shoe, td_md)
        mud.append(
            MudInterval(prev, shoe, hole, "water-based" if k < 2 else "KCl-polymer", mw_sections[k])
        )
        if status == "completed" or shoe < td_md:
            casing.append(
                CasingString(
                    od,
                    hole,
                    shoe,
                    round(traj.position_at_md(shoe)[2], 1),
                    round(max(0.0, prev - 150), 0),
                    "full",
                )
            )
        prev = shoe

    # Events --------------------------------------------------------------------------
    events: list[Event] = []
    if status != "planned":
        events = _make_events(
            idx, name, traj, tops, mud, casing, rkb, xk, yk, hazard_fields, spud_day
        )

    ali = [name.replace("-", " "), name.replace("SYN-ASM-", "SYNASM#").replace("#0", "#")]
    stations = [
        [round(float(a), 2), round(float(b), 3), round(float(c), 3)]
        for a, b, c in zip(traj.md, traj.inc, traj.azi, strict=True)
    ]
    completion = None
    if status == "completed":
        completion = (spud_day + timedelta(days=int(td_md / 150) + 12)).isoformat()
    return Well(
        index=idx,
        name=name,
        aliases=ali,
        status=status,
        well_type="development" if idx % 7 else "exploration",
        profile=profile,
        lat=round(lat, 6),
        lon=round(lon, 6),
        x=round(x, 1),
        y=round(y, 1),
        gl_elev_m=gl,
        rkb_elev_m=rkb,
        units=units,
        rig=rig,
        spud=spud_day.isoformat(),
        completion=completion,
        td_md_m=td_md,
        stations=stations,
        tops=tops,
        casing=casing,
        mud=mud,
        events=events,
    )


def _hole_at(md: float, mud: list[MudInterval]) -> MudInterval:
    for m in mud:
        if m.md_from_m <= md <= m.md_to_m:
            return m
    return mud[-1]


def _make_events(
    idx: int,
    name: str,
    traj: Trajectory,
    tops: list[FormationTop],
    mud: list[MudInterval],
    casing: list[CasingString],
    rkb: float,
    xk: float,
    yk: float,
    hazard_fields: dict[tuple[str, str], list[tuple[float, float, float, float]]],
    spud: date,
) -> list[Event]:
    ev_rng = _rng(idx, _PURPOSES["events"])
    rop_m_per_day = float(ev_rng.uniform(120, 220))
    spud_dt = datetime(spud.year, spud.month, spud.day, 6, 0)
    specs = {s.name: s for s in sm.STRATIGRAPHY}
    events: list[Event] = []
    n = 0
    for k, top in enumerate(tops):
        base_md = tops[k + 1].top_md_m if k + 1 < len(tops) else float(traj.md[-1])
        spec = specs[top.formation]
        for hz in spec.hazards:
            nn, ee, _ = traj.position_at_md(top.top_md_m)
            p = hz.base_prob * (
                0.25
                + 1.5
                * _eval_field(
                    hazard_fields[(spec.name, hz.event_type)], xk + ee / 1000, yk + nn / 1000
                )
            )
            section = _hole_at((top.top_md_m + base_md) / 2, mud)
            if hz.event_type == "KICK" and section.mw_sg < 1.40:
                p *= 2.2  # under-balanced sections kick more often (drives PLAN_CHECK later)
            if ev_rng.random() >= min(p, 0.95):
                continue
            md = float(ev_rng.uniform(top.top_md_m + 5, max(top.top_md_m + 10, base_md - 5)))
            n += 1
            events.append(
                _make_event(
                    ev_rng,
                    name,
                    n,
                    hz,
                    spec.name,
                    md,
                    traj,
                    rkb,
                    _hole_at(md, mud),
                    spud_dt,
                    rop_m_per_day,
                )
            )
    # Cementing problem on the intermediate string when the shoe sits in lossy Tipam.
    if len(casing) >= 2 and ev_rng.random() < 0.35:
        shoe = casing[1]
        n += 1
        hz = sm.Hazard("CEMENT", 1.0, ("losses during cementing", "poor bond"))
        events.append(
            _make_event(
                ev_rng,
                name,
                n,
                hz,
                _formation_at(shoe.shoe_md_m, tops),
                shoe.shoe_md_m,
                traj,
                rkb,
                _hole_at(shoe.shoe_md_m - 1, mud),
                spud_dt,
                rop_m_per_day,
            )
        )
        shoe.returns = "partial"
    events.sort(key=lambda e: e.md_m)
    return events


def _formation_at(md: float, tops: list[FormationTop]) -> str:
    name = tops[0].formation
    for t in tops:
        if t.top_md_m <= md:
            name = t.formation
    return name


def _make_event(
    rng: np.random.Generator,
    well: str,
    n: int,
    hz: sm.Hazard,
    formation: str,
    md: float,
    traj: Trajectory,
    rkb: float,
    section: MudInterval,
    spud_dt: datetime,
    rop: float,
) -> Event:
    et = hz.event_type
    subtype = str(rng.choice(hz.subtypes)) if hz.subtypes else None
    params: dict[str, float] = {}
    severity = "medium"
    if et == "LOSS":
        rate = {
            "seepage": rng.uniform(3, 9),
            "partial": rng.uniform(12, 90),
            "severe": rng.uniform(100, 250),
            "total": 0.0,
        }[subtype or "partial"]
        params = {
            "loss_rate_bbl_hr": round(float(rate), 0),
            "total_loss_bbl": round(float(rng.uniform(40, 900)), 0),
        }
        severity = {"seepage": "low", "partial": "medium", "severe": "high", "total": "high"}[
            subtype or "partial"
        ]
    elif et == "KICK":
        params = {
            "pit_gain_bbl": round(float(rng.uniform(6, 35)), 0),
            "sidpp_psi": round(float(rng.uniform(150, 900)), 0),
        }
        severity = "high"
    elif et == "STUCK":
        params = {"overpull_klbf": round(float(rng.uniform(60, 180)), 0)}
        severity = "high" if subtype == "differential" else "medium"
    elif et in ("TIGHT", "TORQUE"):
        params = (
            {"overpull_klbf": round(float(rng.uniform(25, 70)), 0)}
            if et == "TIGHT"
            else {"torque_kftlbf": round(float(rng.uniform(18, 32)), 1)}
        )
        severity = "low" if rng.random() < 0.5 else "medium"
    elif et == "OVERP":
        params = {"gas_pct": round(float(rng.uniform(4, 18)), 1)}
    start = spud_dt + timedelta(days=md / rop, hours=float(rng.uniform(0, 20)))

    mitigations: list[Mitigation] = []
    tried: set[str] = set()
    resolved = False
    options = sm.FIRST_CHOICE_WEIGHTS[et]
    for _attempt in range(3):
        avail = {a: w for a, w in options.items() if a not in tried}
        if not avail:
            break
        acts, weights = zip(*avail.items(), strict=True)
        wts = np.array(weights) / sum(weights)
        action = str(rng.choice(acts, p=wts))
        tried.add(action)
        ok = bool(rng.random() < sm.PLANTED_SUCCESS[et][action])
        mitigations.append(Mitigation(action, "success" if ok else "fail", _npt(rng, ok)))
        if ok:
            resolved = True
            break
    if not resolved and et in sm.ESCALATION:
        action = sm.ESCALATION[et]
        ok = bool(rng.random() < sm.PLANTED_SUCCESS[et][action])
        mitigations.append(Mitigation(action, "success" if ok else "fail", _npt(rng, ok) * 2))
        resolved = ok
    _, _, tvd = traj.position_at_md(md)
    return Event(
        event_id=f"{well}-E{n:02d}",
        event_type=et,
        subtype=subtype,
        severity=severity,
        md_m=round(md, 1),
        tvd_m=round(tvd, 1),
        tvdss_m=round(tvd - rkb, 1),
        formation=formation,
        hole_size=section.hole_label,
        mw_sg=section.mw_sg,
        start=start.replace(microsecond=0).isoformat(),
        params=params,
        mitigations=mitigations,
        total_npt_hours=round(sum(m.npt_hours for m in mitigations), 1),
        resolved=resolved,
    )


def _npt(rng: np.random.Generator, ok: bool) -> float:
    median = 3.0 if ok else 6.0
    return round(float(median * math.exp(rng.normal(0, 0.5))), 1)

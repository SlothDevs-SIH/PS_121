"""S7a offset prior risk over the database: "given the offset wells, how likely is each
problem in each formation of this well?" Works before spud; needs no real-time data.

Intervals are the subject well's formations (its tops). Offsets are the wells within
``radius_km`` of the surface location that penetrated that formation; planned wells have
no history and are skipped. Distances are 3D between formation entry points
(AT_FORMATION, falling back to surface distance when an entry point is missing) or surface
distances (SURFACE). The basin base rate of each event type (over every other drilled
well's penetrated formations) sets the Beta prior.
"""

import math
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.v1.schemas.knowledge import (
    BinRisk,
    CementingCheck,
    EventRisk,
    RiskBin,
    RiskInterval,
    RiskOffset,
    RiskProfile,
)
from app.db.models import (
    CasingString,
    Event,
    Formation,
    FormationTop,
    MudInterval,
    SurveyStation,
    Well,
    Wellbore,
)
from app.geo.service import surface_offsets
from app.normalise.wells_service import get_well_or_404
from app.physics.indicators import cementing_risk
from app.risk import core

DEFAULT_RADIUS_KM = 10.0
EVENT_LABELS = {
    "LOSS": "Losses",
    "KICK": "Kick",
    "STUCK": "Stuck pipe",
    "TIGHT": "Tight hole",
    "TORQUE": "High torque",
    "INSTAB": "Instability",
    "BALLING": "Bit balling",
    "OVERP": "Overpressure",
    "GAS": "Gas",
    "CEMENT": "Cementing problems",
}
METHOD = (
    "Weighted Beta-Binomial per formation and event type: w = exp(−d²/2σ²) × similarity × "
    "recency (1.0). Similarity starts at 1.0 and is multiplied by 0.75 for a different hole "
    "size, 0.8 for a different mud system and 0.9 for a different well type (floor 0.5; "
    "unknown counts as a match). P = (Σw·y + α)/(Σw + α + β) with α + β = 2 set from the "
    "basin base rate (floored at 1%); 90% credible interval from the Beta posterior; "
    "n_eff = (Σw)²/Σw². The subject well's own events are never used."
)


@dataclass
class _Top:
    formation_id: int
    name: str
    strat_order: int
    top_md: float
    top_tvdss: float


PROGNOSIS_OFFSETS = 5


def prognosed_top(points: list[tuple[float, float]]) -> tuple[float, float]:
    """Expected top (TVDSS) of a formation not yet reached, from (surface distance m, top
    TVDSS m) of the offsets that penetrated it: inverse-distance-squared weighting over the
    nearest five (distance floored at 50 m). Returns (top, weighted spread)."""
    pts = sorted(points)[:PROGNOSIS_OFFSETS]
    w = [1 / max(d, 50.0) ** 2 for d, _ in pts]
    z = sum(wi * zi for wi, (_, zi) in zip(w, pts, strict=True)) / sum(w)
    var = sum(wi * (zi - z) ** 2 for wi, (_, zi) in zip(w, pts, strict=True)) / sum(w)
    return z, var**0.5


def _primary_wellbores(session: Session, well_ids: list[int]) -> dict[int, int]:
    rows = session.execute(
        select(Wellbore.well_id, Wellbore.id)
        .where(Wellbore.well_id.in_(well_ids or [-1]))
        .order_by(Wellbore.well_id, Wellbore.id)
    ).all()
    out: dict[int, int] = {}
    for well_id, wb_id in rows:
        out.setdefault(int(well_id), int(wb_id))
    return out


def _tops(session: Session, wellbore_ids: list[int]) -> dict[int, list[_Top]]:
    rows = session.execute(
        select(
            FormationTop.wellbore_id,
            FormationTop.formation_id,
            Formation.name,
            Formation.strat_order,
            FormationTop.top_md_m,
            FormationTop.top_tvdss_m,
        )
        .join(Formation, Formation.id == FormationTop.formation_id)
        .where(FormationTop.wellbore_id.in_(wellbore_ids or [-1]))
        .order_by(FormationTop.wellbore_id, FormationTop.top_md_m)
    ).all()
    out: dict[int, list[_Top]] = defaultdict(list)
    for r in rows:
        out[int(r[0])].append(_Top(int(r[1]), str(r[2]), int(r[3]), float(r[4]), float(r[5])))
    return out


_MudRow = tuple[float, float, float | None, str | None]


def _mud_programme(session: Session, wellbore_ids: list[int]) -> dict[int, list[_MudRow]]:
    """wellbore → [(md_from, md_to, hole_in, mud_type)] from the mud programme."""
    rows = session.execute(
        select(
            MudInterval.wellbore_id,
            MudInterval.md_from_m,
            MudInterval.md_to_m,
            MudInterval.hole_size_in,
            MudInterval.mud_type,
        ).where(MudInterval.wellbore_id.in_(wellbore_ids or [-1]))
    ).all()
    out: dict[int, list[_MudRow]] = defaultdict(list)
    for wb, a, b, h, mud in rows:
        out[int(wb)].append((float(a), float(b), None if h is None else float(h), mud))
    return out


def _context(programme: list[_MudRow], md: float, well_type: str | None) -> core.Context:
    for a, b, h, mud in programme:
        if a <= md <= b:
            return core.Context(h, mud, well_type)
    return core.Context(None, None, well_type)


def _events(session: Session, well_ids: list[int]) -> dict[tuple[int, int, str], list[int]]:
    rows = session.execute(
        select(Event.well_id, Event.formation_id, Event.event_type, Event.id).where(
            Event.well_id.in_(well_ids or [-1]),
            Event.status == "active",
            Event.formation_id.is_not(None),
        )
    ).all()
    out: dict[tuple[int, int, str], list[int]] = defaultdict(list)
    for w, f, t, i in rows:
        out[(int(w), int(f), str(t))].append(int(i))
    return out


def _event_tvdss(session: Session, well_ids: list[int]) -> dict[int, float]:
    rows = session.execute(
        select(Event.id, Event.tvdss_m).where(
            Event.well_id.in_(well_ids or [-1]), Event.tvdss_m.is_not(None)
        )
    ).all()
    return {int(i): float(z) for i, z in rows}


def _bin_of(rel: float, n: int) -> int:
    return min(n - 1, max(0, int(rel * n)))


def base_rates(session: Session, exclude_well_id: int) -> dict[str, float]:
    """Share of (drilled well, penetrated formation) pairs with each event type."""
    wells = [
        int(w)
        for w in session.scalars(
            select(Well.id).where(Well.status != "planned", Well.id != exclude_well_id)
        )
    ]
    wbs = _primary_wellbores(session, wells)
    tops = _tops(session, list(wbs.values()))
    pairs = {(w, t.formation_id) for w, wb in wbs.items() for t in tops.get(wb, [])}
    if not pairs:
        return {}
    hits: dict[str, set[tuple[int, int]]] = defaultdict(set)
    for (w, f, t), _ in _events(session, wells).items():
        if (w, f) in pairs:
            hits[t].add((w, f))
    return {t: len(v) / len(pairs) for t, v in hits.items()}


def _entry_distances(
    session: Session, subject_wb: int, offset_wbs: dict[int, int]
) -> dict[tuple[int, int], float]:
    """(offset well, formation) → 3D distance between the two entry points (m)."""
    if not offset_wbs:
        return {}
    wb_to_well = {wb: w for w, wb in offset_wbs.items()}
    rows = session.execute(
        text(
            """
            SELECT fo.wellbore_id, fo.formation_id,
                   ST_3DDistance(fs.entry_point, fo.entry_point) AS d
            FROM formation_top fs
            JOIN formation_top fo ON fo.formation_id = fs.formation_id
            WHERE fs.wellbore_id = :wb AND fo.wellbore_id = ANY(:wbs)
              AND fs.entry_point IS NOT NULL AND fo.entry_point IS NOT NULL
            """
        ),
        {"wb": subject_wb, "wbs": list(wb_to_well)},
    ).all()
    return {(wb_to_well[int(r[0])], int(r[1])): float(r[2]) for r in rows}


def risk_profile(
    session: Session,
    well_id: int,
    *,
    radius_km: float = DEFAULT_RADIUS_KM,
    sigma_km: float | None = None,
    mode: str = "AT_FORMATION",
    event_types: list[str] | None = None,
    bin_m: float | None = None,
) -> RiskProfile:
    well = get_well_or_404(session, well_id)
    sigma_km = sigma_km or radius_km / 2
    sigma_m = sigma_km * 1000
    wbs = _primary_wellbores(session, [well.id])
    subject_wb = wbs.get(well.id)

    candidates = [
        o for o in surface_offsets(session, well.id, radius_km * 1000) if o.status != "planned"
    ]
    cand_ids = [o.well_id for o in candidates]
    offset_wbs = _primary_wellbores(session, cand_ids)
    all_wbs = list(offset_wbs.values()) + ([subject_wb] if subject_wb else [])
    tops = _tops(session, all_wbs)
    muds = _mud_programme(session, all_wbs)
    events = _events(session, cand_ids)
    ev_z = _event_tvdss(session, cand_ids) if bin_m else {}
    entry_d = (
        _entry_distances(session, subject_wb, offset_wbs)
        if subject_wb and mode == "AT_FORMATION"
        else {}
    )
    rates = base_rates(session, well.id)
    types = list(event_types) if event_types else sorted(rates)
    synthetic_by_id = {o.well_id: o.synthetic for o in candidates}
    surface_d = {o.well_id: o.distance_m for o in candidates}
    names = {o.well_id: o.name for o in candidates}
    well_types = {o.well_id: o.well_type for o in candidates}

    subject_tops = list(tops.get(subject_wb, [])) if subject_wb else []
    td = (
        session.execute(
            select(SurveyStation.md_m, SurveyStation.tvdss_m, SurveyStation.inc_deg)
            .where(SurveyStation.wellbore_id == subject_wb)
            .order_by(SurveyStation.md_m.desc())
            .limit(1)
        ).first()
        if subject_wb
        else None
    )

    # A drilling well has not reached its deeper formations: prognose their tops from the
    # offsets that did, extrapolating MD along the last survey station.
    prognosis: dict[int, float] = {}
    if well.status == "drilling" and subject_tops and td is not None:
        deepest = max(t.strat_order for t in subject_tops)
        ahead: dict[int, list[tuple[float, _Top]]] = defaultdict(list)
        for w in cand_ids:
            for ot in tops.get(offset_wbs.get(w, -1), []):
                if ot.strat_order > deepest:
                    ahead[ot.formation_id].append((surface_d[w], ot))
        cos_inc = max(math.cos(math.radians(float(td[2]))), 0.2)
        for pts in sorted(ahead.values(), key=lambda p: p[0][1].strat_order):
            z, spread = prognosed_top([(d, ot.top_tvdss) for d, ot in pts])
            if z <= float(td[1]):
                continue  # the offsets put it above TD: a thin or absent unit here
            ref = pts[0][1]
            md = float(td[0]) + (z - float(td[1])) / cos_inc
            subject_tops.append(_Top(ref.formation_id, ref.name, ref.strat_order, md, z))
            prognosis[ref.formation_id] = spread

    intervals: list[RiskInterval] = []
    for k, top in enumerate(subject_tops):
        nxt = subject_tops[k + 1] if k + 1 < len(subject_tops) else None
        subj_ctx = _context(muds.get(subject_wb or -1, []), top.top_md + 1, well.well_type)
        offsets: list[RiskOffset] = []
        extent: dict[int, tuple[float, float | None]] = {}  # offset → its top, base TVDSS
        for w in cand_ids:
            wb = offset_wbs.get(w)
            their = next(
                (t for t in tops.get(wb or -1, []) if t.formation_id == top.formation_id), None
            )
            if their is None:
                continue  # never reached this formation
            deeper = [t for t in tops.get(wb or -1, []) if t.strat_order > their.strat_order]
            extent[w] = (
                their.top_tvdss,
                min((t.top_tvdss for t in deeper), default=None),
            )
            if (w, top.formation_id) in entry_d:
                d, kind = entry_d[(w, top.formation_id)], "at_formation"
            else:
                d, kind = surface_d[w], "surface"
            ctx = _context(muds.get(wb or -1, []), their.top_md + 1, well_types[w])
            sim = core.similarity(subj_ctx, ctx)
            evs = {t: ids for t in types if (ids := events.get((w, top.formation_id, t)))}
            offsets.append(
                RiskOffset(
                    well_id=w,
                    name=names[w],
                    synthetic=synthetic_by_id[w],
                    distance_m=round(d, 1),
                    distance_kind=kind,
                    similarity=sim,
                    weight=round(core.weight(d, sigma_m, sim), 6),
                    events=evs,
                )
            )
        offsets.sort(key=lambda o: (-o.weight, o.distance_m))
        risks = []
        for t in types:
            alpha, beta_ = core.prior_params(rates.get(t, 0.0))
            post = core.weighted_beta_binomial(
                [o.weight for o in offsets], [t in o.events for o in offsets], alpha, beta_
            )
            hits = sum(t in o.events for o in offsets)
            lbl = EVENT_LABELS.get(t, t)
            risks.append(
                EventRisk(
                    event_type=t,
                    probability=round(post.probability, 4),
                    ci90_low=round(post.ci90_low, 4),
                    ci90_high=round(post.ci90_high, 4),
                    n_eff=round(post.n_eff, 2),
                    offsets_with_event=hits,
                    offsets_total=len(offsets),
                    base_rate=round(rates.get(t, 0.0), 4),
                    label=(
                        f"{lbl}: {post.probability:.0%} ({hits} of {len(offsets)} offsets, "
                        f"n_eff {post.n_eff:.1f}, 90% CI {post.ci90_low:.0%}–{post.ci90_high:.0%})"
                    ),
                )
            )
        risks.sort(key=lambda r: -r.probability)
        base_md, base_z = (
            (nxt.top_md, nxt.top_tvdss)
            if nxt
            else ((float(td[0]), float(td[1])) if td and not prognosis else (None, None))
        )
        bins = (
            _bins(top, base_md, base_z, bin_m, offsets, extent, ev_z, types, rates)
            if bin_m and base_md is not None and base_z is not None
            else []
        )
        intervals.append(
            RiskInterval(
                formation=top.name,
                strat_order=top.strat_order,
                top_md_m=round(top.top_md, 1),
                base_md_m=(
                    round(nxt.top_md, 1)
                    if nxt
                    else (round(float(td[0]), 1) if td and not prognosis else None)
                ),
                top_tvdss_m=round(top.top_tvdss, 1),
                base_tvdss_m=(
                    round(nxt.top_tvdss, 1)
                    if nxt
                    else (round(float(td[1]), 1) if td and not prognosis else None)
                ),
                prognosed=top.formation_id in prognosis,
                prognosis_spread_m=(
                    round(prognosis[top.formation_id], 1) if top.formation_id in prognosis else None
                ),
                offsets=offsets,
                risks=risks,
                bins=bins,
            )
        )
    return RiskProfile(
        well_id=well.id,
        name=well.canonical_name,
        status=well.status,
        synthetic=well.synthetic,
        td_md_m=round(float(td[0]), 1) if td else None,
        td_tvdss_m=round(float(td[1]), 1) if td else None,
        mode=mode,
        radius_km=radius_km,
        sigma_km=sigma_km,
        prior_strength=core.PRIOR_STRENGTH,
        method=METHOD,
        intervals=intervals,
    )


def _bins(
    top: _Top,
    base_md: float,
    base_z: float,
    bin_m: float,
    offsets: list[RiskOffset],
    extent: dict[int, tuple[float, float | None]],
    ev_z: dict[int, float],
    types: list[str],
    rates: dict[str, float],
) -> list[RiskBin]:
    """Slices of about ``bin_m`` TVD. An offset's event is placed by its relative depth in
    that offset's own formation (0 = top, 1 = base); events without a depth, or in an
    offset whose formation base is unknown, count for the formation but no slice."""
    thick = base_z - top.top_tvdss
    n = max(1, math.ceil(thick / bin_m))
    if n == 1:
        return []
    placed: dict[tuple[int, str], set[int]] = defaultdict(set)  # (offset, type) → bins
    for o in offsets:
        o_top, o_base = extent.get(o.well_id, (0.0, None))
        if o_base is None or o_base <= o_top:
            continue
        for t, ids in o.events.items():
            for i in ids:
                if i in ev_z:
                    placed[(o.well_id, t)].add(_bin_of((ev_z[i] - o_top) / (o_base - o_top), n))
    out = []
    for b in range(n):
        risks = []
        for t in types:
            alpha, beta_ = core.prior_params(rates.get(t, 0.0))
            hit = [b in placed.get((o.well_id, t), set()) for o in offsets]
            post = core.weighted_beta_binomial([o.weight for o in offsets], hit, alpha, beta_)
            risks.append(
                BinRisk(
                    event_type=t,
                    probability=round(post.probability, 4),
                    ci90_low=round(post.ci90_low, 4),
                    ci90_high=round(post.ci90_high, 4),
                    offsets_with_event=sum(hit),
                )
            )
        risks.sort(key=lambda r: -r.probability)
        f0, f1 = b / n, (b + 1) / n
        out.append(
            RiskBin(
                top_md_m=round(top.top_md + f0 * (base_md - top.top_md), 1),
                base_md_m=round(top.top_md + f1 * (base_md - top.top_md), 1),
                top_tvdss_m=round(top.top_tvdss + f0 * thick, 1),
                base_tvdss_m=round(top.top_tvdss + f1 * thick, 1),
                rel_from=round(f0, 4),
                rel_to=round(f1, 4),
                risks=risks,
            )
        )
    return out


def cementing_check(
    session: Session,
    well_id: int,
    *,
    shoe_md_m: float,
    slurry_density_sg: float,
    radius_km: float = DEFAULT_RADIUS_KM,
) -> CementingCheck:
    """Before a cement job at ``shoe_md_m``: offsets' loss mud weights and cementing losses
    in the formation the shoe sits in (master plan §Stage 7c cementing checklist)."""
    well = get_well_or_404(session, well_id)
    wbs = _primary_wellbores(session, [well.id])
    subject_tops = _tops(session, [wbs[well.id]]).get(wbs[well.id], []) if well.id in wbs else []
    at_shoe = None
    for t in subject_tops:
        if t.top_md <= shoe_md_m:
            at_shoe = t
    offsets = [
        o.well_id
        for o in surface_offsets(session, well.id, radius_km * 1000)
        if o.status != "planned"
    ]
    loss_mw: list[float] = []
    cement_losses: set[int] = set()
    cemented: set[int] = set()
    evidence: list[int] = []
    if at_shoe is not None and offsets:
        offset_wbs = _primary_wellbores(session, offsets)
        their_tops = _tops(session, list(offset_wbs.values()))
        for ev in session.scalars(
            select(Event).where(
                Event.well_id.in_(offsets),
                Event.status == "active",
                Event.formation_id == at_shoe.formation_id,
                Event.event_type.in_(("LOSS", "CEMENT")),
            )
        ):
            if ev.event_type == "LOSS" and ev.mw_sg is not None:
                loss_mw.append(round(ev.mw_sg, 3))
                evidence.append(ev.id)
            if ev.event_type == "CEMENT" and (ev.subtype or "").startswith("losses"):
                cement_losses.add(ev.well_id)
                evidence.append(ev.id)
        # Offsets that set a casing shoe inside this formation.
        for w, wb in offset_wbs.items():
            tops_w = their_tops.get(wb, [])
            rng = next(
                (
                    (t.top_md, tops_w[i + 1].top_md if i + 1 < len(tops_w) else float("inf"))
                    for i, t in enumerate(tops_w)
                    if t.formation_id == at_shoe.formation_id
                ),
                None,
            )
            if rng is None:
                continue
            shoes = session.scalars(
                select(CasingString.shoe_md_m).where(CasingString.wellbore_id == wb)
            ).all()
            if any(s is not None and rng[0] <= s < rng[1] for s in shoes):
                cemented.add(w)
        cemented |= cement_losses  # losses while cementing here imply a job here
    risk = cementing_risk(slurry_density_sg, loss_mw, len(cement_losses), len(cemented))
    return CementingCheck(
        well_id=well.id,
        formation=at_shoe.name if at_shoe else None,
        shoe_md_m=shoe_md_m,
        slurry_density_sg=slurry_density_sg,
        level=risk.level,
        flags=risk.flags,
        offsets_considered=len(offsets),
        offset_loss_mw_sg=sorted(loss_mw),
        evidence_event_ids=sorted(set(evidence)),
    )

"""Correlation panel (S6): wells side by side on one aligned depth axis.

TVDSS               metres TVDSS (positive down).
FLATTEN_ON_TOP      metres TVDSS below the chosen formation's top in each well.
FORMATION_RELATIVE  k + fraction for the k-th formation of the panel (stratigraphic order),
                    linear between that well's own tops. The deepest penetrated formation
                    has no base in the well: it is scaled by the median thickness of that
                    formation in the panel's wells that fully penetrate it, or by TD when
                    none does. A missing top is never interpolated: the gap stays visible.

A well that lacks what its alignment needs is drawn on TVDSS and says why.
"""

import statistics
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.v1.schemas.correlation import (
    Alignment,
    CasingShoeTrack,
    CementTopTrack,
    CorrelationPanel,
    CorrelationTracks,
    CorrelationWell,
    DepthAxis,
    EventMarker,
    FormationStats,
    FormationStatsRow,
    FormationTrack,
    MudTrack,
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
from app.extract.evidence import event_evidence_refs, record_evidence
from app.geo.service import surface_offsets
from app.normalise.formations import formation_ids
from app.normalise.wells_service import get_well_or_404


@dataclass
class _Top:
    formation: Formation
    md: float
    tvdss: float


@dataclass
class _WellData:
    well: Well
    wellbore: Wellbore | None
    tops: list[_Top] = field(default_factory=list)  # shallow first
    td_tvdss: float | None = None


def _load(session: Session, well: Well) -> _WellData:
    wb = session.scalar(select(Wellbore).where(Wellbore.well_id == well.id).order_by(Wellbore.id))
    data = _WellData(well=well, wellbore=wb)
    if wb is None:
        return data
    for t in session.scalars(
        select(FormationTop)
        .where(FormationTop.wellbore_id == wb.id)
        .options(selectinload(FormationTop.formation))
        .order_by(FormationTop.top_md_m)
    ):
        data.tops.append(_Top(t.formation, t.top_md_m, t.top_tvdss_m))
    last = session.scalar(
        select(SurveyStation.tvdss_m)
        .where(SurveyStation.wellbore_id == wb.id)
        .order_by(SurveyStation.md_m.desc())
        .limit(1)
    )
    data.td_tvdss = float(last) if last is not None else None
    return data


Mapper = Callable[[float | None], tuple[float | None, float | None]]  # → (aligned, fraction)


def _tvdss_mapper() -> Mapper:
    return lambda z: (None if z is None else round(z, 2), None)


def _flatten_mapper(datum: float) -> Mapper:
    return lambda z: (None if z is None else round(z - datum, 2), None)


def _relative_mapper(d: _WellData, index: dict[int, int], thickness: dict[int, float]) -> Mapper:
    spans: list[tuple[float, float, int]] = []  # (top, base used for scaling, panel index)
    for k, t in enumerate(d.tops):
        if k + 1 < len(d.tops):
            base = d.tops[k + 1].tvdss
        else:
            ref = thickness.get(t.formation.id)
            base = t.tvdss + ref if ref else (d.td_tvdss or t.tvdss)
        if base > t.tvdss:
            spans.append((t.tvdss, base, index[t.formation.id]))

    def mapper(z: float | None) -> tuple[float | None, float | None]:
        if z is None:
            return None, None
        for top, base, k in spans:
            if top <= z < base or (z == base and (top, base, k) == spans[-1]):
                frac = (z - top) / (base - top)
                return round(k + frac, 4), round(frac, 4)
        if spans and z >= spans[-1][1]:  # deeper than the scaled last formation
            top, base, k = spans[-1]
            frac = (z - top) / (base - top)
            return round(k + frac, 4), round(frac, 4)
        return None, None

    return mapper


def panel(
    session: Session, well_ids: list[int], align: Alignment, top: str | None
) -> CorrelationPanel:
    wells = [get_well_or_404(session, wid) for wid in well_ids]
    data = [_load(session, w) for w in wells]
    flatten_ids: list[int] = []
    if align is Alignment.FLATTEN_ON_TOP:
        assert top is not None
        flatten_ids = formation_ids(session, top, "top")[0]

    # FORMATION_RELATIVE: one index per formation present in the panel, in strat order.
    present = sorted(
        {t.formation.id: t.formation for d in data for t in d.tops}.values(),
        key=lambda f: f.strat_order,
    )
    index = {f.id: k for k, f in enumerate(present)}
    thick: dict[int, list[float]] = {}
    for d in data:
        for k in range(len(d.tops) - 1):
            thick.setdefault(d.tops[k].formation.id, []).append(
                d.tops[k + 1].tvdss - d.tops[k].tvdss
            )
    thickness = {fid: statistics.median(v) for fid, v in thick.items() if v}

    columns: list[CorrelationWell] = []
    for d in data:
        mapper, fallback, reason = _tvdss_mapper(), False, None
        if align is Alignment.FLATTEN_ON_TOP:
            datum = next((t.tvdss for t in d.tops if t.formation.id in flatten_ids), None)
            if datum is None:
                fallback, reason = True, f"no {top} top"
            else:
                mapper = _flatten_mapper(datum)
        elif align is Alignment.FORMATION_RELATIVE:
            if not d.tops:
                fallback, reason = True, "no formation tops"
            else:
                mapper = _relative_mapper(d, index, thickness)
        columns.append(_column(session, d, mapper, fallback, reason))

    values = [
        v
        for c in columns
        if not c.fallback_to_tvdss or align is Alignment.TVDSS
        for v in [
            *(f.top for f in c.tracks.formations),
            *(f.base for f in c.tracks.formations if f.base is not None),
            c.td_aligned,
        ]
        if v is not None
    ]
    if align is Alignment.TVDSS:
        axis = DepthAxis(
            label="TVDSS (m)", unit="m", min=min(values, default=0), max=max(values, default=0)
        )
    elif align is Alignment.FLATTEN_ON_TOP:
        axis = DepthAxis(
            label=f"Relative to {top} top (m)",
            unit="m",
            min=min(values, default=0),
            max=max(values, default=0),
        )
    else:
        axis = DepthAxis(
            label="Formation (relative position)",
            unit="formation",
            min=0,
            max=max(values, default=float(len(present))),
        )
    return CorrelationPanel(align=align, top=top, depth_axis=axis, wells=columns)


def _column(
    session: Session, d: _WellData, mapper: Mapper, fallback: bool, reason: str | None
) -> CorrelationWell:
    w = d.well
    formations = []
    for k, t in enumerate(d.tops):
        base_tvdss = d.tops[k + 1].tvdss if k + 1 < len(d.tops) else d.td_tvdss
        formations.append(
            FormationTrack(
                name=t.formation.name,
                strat_order=t.formation.strat_order,
                lithology=t.formation.lithology,
                top=mapper(t.tvdss)[0] or 0.0,
                base=mapper(base_tvdss)[0] if base_tvdss is not None else None,
                top_tvdss_m=round(t.tvdss, 2),
                base_tvdss_m=round(base_tvdss, 2) if base_tvdss is not None else None,
            )
        )
    casing: list[CasingShoeTrack] = []
    cement: list[CementTopTrack] = []
    mud: list[MudTrack] = []
    if d.wellbore is not None:
        strings = list(
            session.scalars(
                select(CasingString)
                .where(CasingString.wellbore_id == d.wellbore.id)
                .options(selectinload(CasingString.cement_jobs))
                .order_by(CasingString.shoe_md_m)
            )
        )
        cs_ev = record_evidence(session, [(c.document_id, c.page_no, c.span_ids) for c in strings])
        for c, ev in zip(strings, cs_ev, strict=True):
            casing.append(
                CasingShoeTrack(
                    casing_id=c.id,
                    od_in=c.od_in,
                    hole_size_in=c.hole_size_in,
                    shoe_md_m=c.shoe_md_m,
                    shoe_tvdss_m=c.shoe_tvdss_m,
                    aligned=mapper(c.shoe_tvdss_m)[0],
                    confidence=c.confidence,
                    verified=c.verified,
                    evidence=ev,
                )
            )
            jobs = c.cement_jobs
            job_ev = record_evidence(
                session, [(j.document_id, j.page_no, j.span_ids) for j in jobs]
            )
            for j, jev in zip(jobs, job_ev, strict=True):
                cement.append(
                    CementTopTrack(
                        cement_job_id=j.id,
                        casing_id=c.id,
                        toc_md_m=j.toc_md_m,
                        toc_tvdss_m=j.toc_tvdss_m,
                        aligned=mapper(j.toc_tvdss_m)[0],
                        returns=j.returns,
                        confidence=j.confidence,
                        verified=j.verified,
                        evidence=jev,
                    )
                )
        intervals = list(
            session.scalars(
                select(MudInterval)
                .where(MudInterval.wellbore_id == d.wellbore.id)
                .order_by(MudInterval.md_from_m)
            )
        )
        mud_ev = record_evidence(
            session, [(m.document_id, m.page_no, m.span_ids) for m in intervals]
        )
        for m, mev in zip(intervals, mud_ev, strict=True):
            mud.append(
                MudTrack(
                    mud_interval_id=m.id,
                    md_from_m=m.md_from_m,
                    md_to_m=m.md_to_m,
                    tvdss_from_m=m.tvdss_from_m,
                    tvdss_to_m=m.tvdss_to_m,
                    top=mapper(m.tvdss_from_m)[0],
                    base=mapper(m.tvdss_to_m)[0],
                    mud_type=m.mud_type,
                    mw_sg=m.mw_sg,
                    ecd_sg=m.ecd_sg,
                    confidence=m.confidence,
                    verified=m.verified,
                    evidence=mev,
                )
            )
    events = list(
        session.scalars(
            select(Event)
            .where(Event.well_id == w.id, Event.status == "active")
            .order_by(Event.md_m.asc().nulls_last(), Event.id)
        )
    )
    ev_refs = event_evidence_refs(session, [e.id for e in events])
    markers = []
    for e in events:
        aligned, frac = mapper(e.tvdss_m)
        markers.append(
            EventMarker(
                event_id=e.id,
                event_type=e.event_type,
                severity=e.severity,
                md_m=e.md_m,
                tvdss_m=e.tvdss_m,
                aligned=aligned,
                relative_position=frac,
                npt_hours=e.npt_hours,
                confidence=e.confidence,
                verified=e.verified,
                evidence=ev_refs.get(e.id, []),
            )
        )
    return CorrelationWell(
        well_id=w.id,
        name=w.canonical_name,
        fluid_type=w.fluid_type,
        status=w.status,
        synthetic=w.synthetic,
        fallback_to_tvdss=fallback,
        reason=reason,
        td_aligned=mapper(d.td_tvdss)[0],
        tracks=CorrelationTracks(
            formations=formations, casing_shoes=casing, mud=mud, cement_tops=cement, events=markers
        ),
    )


def formation_stats(
    session: Session, wells: list[int] | None, well_id: int | None, radius_km: float | None
) -> FormationStats:
    if wells:
        ids = [get_well_or_404(session, w).id for w in dict.fromkeys(wells)]
    else:
        assert well_id is not None
        get_well_or_404(session, well_id)
        ids = [well_id] + [
            o.well_id for o in surface_offsets(session, well_id, (radius_km or 5.0) * 1000)
        ]
    per_well = {
        w.id: _load(session, w) for w in session.scalars(select(Well).where(Well.id.in_(ids)))
    }
    formations: dict[int, Formation] = {}
    penetrating: dict[int, set[int]] = {}
    for wid, d in per_well.items():
        for t in d.tops:
            formations[t.formation.id] = t.formation
            penetrating.setdefault(t.formation.id, set()).add(wid)
    events = list(
        session.scalars(
            select(Event).where(
                Event.well_id.in_(ids), Event.status == "active", Event.formation_id.is_not(None)
            )
        )
    )
    for e in events:
        if e.formation_id not in formations:
            f = session.get(Formation, e.formation_id)
            if f is not None:
                formations[f.id] = f
    mud_by_well: dict[int, list[MudInterval]] = {}
    for wid, d in per_well.items():
        if d.wellbore is not None:
            mud_by_well[wid] = list(
                session.scalars(select(MudInterval).where(MudInterval.wellbore_id == d.wellbore.id))
            )
    rows = []
    for f in sorted(formations.values(), key=lambda f: f.strat_order):
        evs = [e for e in events if e.formation_id == f.id]
        by_type: dict[str, int] = {}
        wells_by_type: dict[str, set[int]] = {}
        for e in evs:
            by_type[e.event_type] = by_type.get(e.event_type, 0) + 1
            wells_by_type.setdefault(e.event_type, set()).add(e.well_id)
        mws = []
        for wid, d in per_well.items():
            interval = _formation_interval(d, f.id)
            if interval is None:
                continue
            top_md, base_md = interval
            best = max(
                (
                    (min(base_md, m.md_to_m) - max(top_md, m.md_from_m), m.mw_sg)
                    for m in mud_by_well.get(wid, [])
                    if m.mw_sg is not None
                ),
                default=None,
            )
            if best is not None and best[0] > 0:
                mws.append(best[1])
        npts = [e.npt_hours for e in evs if e.npt_hours is not None]
        rows.append(
            FormationStatsRow(
                formation=f.name,
                strat_order=f.strat_order,
                wells_penetrating=len(penetrating.get(f.id, set())),
                events_by_type=by_type,
                wells_with_event_by_type={k: len(v) for k, v in wells_by_type.items()},
                median_mw_sg=round(statistics.median(mws), 3) if mws else None,
                median_npt_hours=round(statistics.median(npts), 2) if npts else None,
            )
        )
    return FormationStats(wells=ids, rows=rows)


def _formation_interval(d: _WellData, formation_id: int) -> tuple[float, float] | None:
    for k, t in enumerate(d.tops):
        if t.formation.id == formation_id:
            base = d.tops[k + 1].md if k + 1 < len(d.tops) else (d.well.td_md_m or t.md)
            return t.md, base
    return None

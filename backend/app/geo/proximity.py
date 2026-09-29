"""Subsurface-aware offset search (S4): AT_FORMATION and CLOSEST_APPROACH.

Surface distance says little about how close two wells are where it matters. These modes
measure it underground:

AT_FORMATION      3D distance between the two wells' entry points into one formation
                  (``formation_top.entry_point``, field CRS metres, Z = -TVDSS).
CLOSEST_APPROACH  minimum 3D distance between the two wellbore paths, optionally only
                  inside a TVDSS window. Paths are sampled every ``STEP_M`` of MD along the
                  survey stations, then refined around the best pair at ``FINE_M``.

A well in range that cannot be measured (no top, no trajectory, never reaches the
window) is listed in ``excluded`` with the reason; it is never dropped silently.
"""

import math
from dataclasses import dataclass

import numpy as np
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.v1.params import InvalidParamsError
from app.api.v1.schemas.common import ExcludedWell
from app.db.models import Field, SurveyStation, Well, Wellbore
from app.geo.service import projected_xy, surface_offsets
from app.normalise.formations import formation_ids

STEP_M = 5.0
FINE_M = 0.25


@dataclass
class ProximityRow:
    well_id: int
    name: str
    status: str
    well_type: str | None
    fluid_type: str | None
    lat: float
    lon: float
    td_md_m: float | None
    synthetic: bool
    distance_m: float
    bearing_deg: float | None
    entry_md_m: float | None = None
    entry_tvdss_m: float | None = None
    closest_subject_md_m: float | None = None
    closest_offset_md_m: float | None = None
    closest_tvdss_m: float | None = None


@dataclass
class ProximityResult:
    rows: list[ProximityRow]
    excluded: list[ExcludedWell]
    subject_entry_md_m: float | None = None
    subject_entry_tvdss_m: float | None = None


def _row(w: Well, distance: float, bearing: float | None) -> ProximityRow:
    return ProximityRow(
        well_id=w.id,
        name=w.canonical_name,
        status=w.status,
        well_type=w.well_type,
        fluid_type=w.fluid_type,
        lat=w.lat,
        lon=w.lon,
        td_md_m=w.td_md_m,
        synthetic=w.synthetic,
        distance_m=round(distance, 1),
        bearing_deg=None if bearing is None else round(bearing % 360.0, 1),
    )


def at_formation(session: Session, well: Well, formation: str, radius_m: float) -> ProximityResult:
    fids, _ = formation_ids(session, formation)
    subject = session.execute(
        text(
            """
            SELECT ft.formation_id, ft.top_md_m, ft.top_tvdss_m
            FROM formation_top ft JOIN wellbore wb ON wb.id = ft.wellbore_id
            WHERE wb.well_id = :id AND ft.formation_id = ANY(:fids)
              AND ft.entry_point IS NOT NULL
            ORDER BY ft.top_md_m LIMIT 1
            """
        ),
        {"id": well.id, "fids": fids},
    ).first()
    if subject is None:
        raise InvalidParamsError(
            "formation", f"{well.canonical_name} has no {formation} top to measure from"
        )
    rows = session.execute(
        text(
            """
            SELECT DISTINCT ON (o.id) o.id, fo.top_md_m, fo.top_tvdss_m,
                   ST_3DDistance(fs.entry_point, fo.entry_point) AS d,
                   degrees(ST_Azimuth(ST_Force2D(fs.entry_point), ST_Force2D(fo.entry_point))) AS b
            FROM formation_top fs
            JOIN wellbore ws ON ws.id = fs.wellbore_id
            JOIN formation_top fo ON fo.formation_id = fs.formation_id
            JOIN wellbore wo ON wo.id = fo.wellbore_id
            JOIN well o ON o.id = wo.well_id AND o.id <> ws.well_id
            WHERE ws.well_id = :id AND fs.formation_id = :fid
              AND fo.entry_point IS NOT NULL
              AND ST_3DDWithin(fs.entry_point, fo.entry_point, :r)
            ORDER BY o.id, d
            """
        ),
        {"id": well.id, "fid": subject.formation_id, "r": radius_m},
    ).all()
    wells = {
        w.id: w for w in session.scalars(select(Well).where(Well.id.in_([r.id for r in rows])))
    }
    out = []
    for r in rows:
        row = _row(wells[r.id], float(r.d), None if r.b is None else float(r.b))
        row.entry_md_m, row.entry_tvdss_m = round(r.top_md_m, 1), round(r.top_tvdss_m, 1)
        out.append(row)
    out.sort(key=lambda x: (x.distance_m, x.name))
    measured = {r.well_id for r in out}
    excluded = []
    for o in surface_offsets(session, well.id, radius_m):
        if o.well_id in measured:
            continue
        has_top = session.execute(
            text(
                "SELECT 1 FROM formation_top ft JOIN wellbore wb ON wb.id = ft.wellbore_id "
                "WHERE wb.well_id = :w AND ft.formation_id = :f"
            ),
            {"w": o.well_id, "f": subject.formation_id},
        ).first()
        if not has_top:
            excluded.append(
                ExcludedWell(well_id=o.well_id, name=o.name, reason=f"no {formation} top")
            )
    return ProximityResult(
        rows=out,
        excluded=excluded,
        subject_entry_md_m=round(subject.top_md_m, 1),
        subject_entry_tvdss_m=round(subject.top_tvdss_m, 1),
    )


@dataclass
class _Path:
    md: np.ndarray
    xyz: np.ndarray  # field CRS x, y and TVDSS (positive down)

    def sample(self, lo: float, hi: float, step: float) -> tuple[np.ndarray, np.ndarray]:
        md = np.arange(max(lo, self.md[0]), min(hi, self.md[-1]) + 1e-9, step)
        if md.size == 0:
            return md, np.empty((0, 3))
        pts = np.stack([np.interp(md, self.md, self.xyz[:, k]) for k in range(3)], axis=1)
        return md, pts


def _path(session: Session, well: Well, crs: int) -> _Path | None:
    wb = session.scalar(select(Wellbore).where(Wellbore.well_id == well.id).order_by(Wellbore.id))
    if wb is None:
        return None
    st = session.execute(
        select(
            SurveyStation.md_m, SurveyStation.north_m, SurveyStation.east_m, SurveyStation.tvdss_m
        )
        .where(SurveyStation.wellbore_id == wb.id)
        .order_by(SurveyStation.md_m)
    ).all()
    if len(st) < 2:
        return None
    x0, y0 = projected_xy(well.lat, well.lon, crs)
    return _Path(
        md=np.array([s.md_m for s in st]),
        xyz=np.array([[x0 + s.east_m, y0 + s.north_m, s.tvdss_m] for s in st]),
    )


def _mask(
    md: np.ndarray, pts: np.ndarray, lo: float | None, hi: float | None
) -> tuple[np.ndarray, np.ndarray]:
    keep = np.ones(len(md), dtype=bool)
    if lo is not None:
        keep &= pts[:, 2] >= lo
    if hi is not None:
        keep &= pts[:, 2] <= hi
    return md[keep], pts[keep]


def _closest(
    a: _Path, b: _Path, lo: float | None, hi: float | None
) -> tuple[float, float, float, np.ndarray, np.ndarray] | None:
    """(distance, subject md, offset md, subject point, offset point) or None when either
    path has no sample inside the TVDSS window."""
    ma, pa = _mask(*a.sample(a.md[0], a.md[-1], STEP_M), lo, hi)
    mb, pb = _mask(*b.sample(b.md[0], b.md[-1], STEP_M), lo, hi)
    if ma.size == 0 or mb.size == 0:
        return None
    d2 = ((pa[:, None, :] - pb[None, :, :]) ** 2).sum(axis=2)
    i, j = np.unravel_index(int(np.argmin(d2)), d2.shape)
    best = (float(d2[i, j]), float(ma[i]), float(mb[j]), pa[i], pb[j])
    # Refine around the coarse optimum.
    fa_md, fa = _mask(*a.sample(ma[i] - STEP_M, ma[i] + STEP_M, FINE_M), lo, hi)
    fb_md, fb = _mask(*b.sample(mb[j] - STEP_M, mb[j] + STEP_M, FINE_M), lo, hi)
    if fa_md.size and fb_md.size:
        d2f = ((fa[:, None, :] - fb[None, :, :]) ** 2).sum(axis=2)
        fi, fj = np.unravel_index(int(np.argmin(d2f)), d2f.shape)
        if d2f[fi, fj] < best[0]:
            best = (float(d2f[fi, fj]), float(fa_md[fi]), float(fb_md[fj]), fa[fi], fb[fj])
    return math.sqrt(best[0]), best[1], best[2], best[3], best[4]


def closest_approach(
    session: Session, well: Well, radius_m: float, lo: float | None, hi: float | None
) -> ProximityResult:
    field = session.get(Field, well.field_id)
    assert field is not None
    subject = _path(session, well, field.crs_epsg)
    if subject is None:
        raise InvalidParamsError("mode", f"{well.canonical_name} has no trajectory")
    # Candidates: paths within the radius anywhere (a superset once a window is applied).
    cand_ids = list(
        session.scalars(
            text(
                """
                SELECT DISTINCT wo.well_id FROM wellbore ws, wellbore wo
                WHERE ws.well_id = :id AND wo.well_id <> :id
                  AND ws.path_geom IS NOT NULL AND wo.path_geom IS NOT NULL
                  AND ST_3DDWithin(ws.path_geom, wo.path_geom, :r)
                """
            ),
            {"id": well.id, "r": radius_m},
        )
    )
    wells = {w.id: w for w in session.scalars(select(Well).where(Well.id.in_(cand_ids)))}
    rows: list[ProximityRow] = []
    excluded: list[ExcludedWell] = []
    window = lo is not None or hi is not None
    for wid in sorted(cand_ids):
        w = wells[wid]
        other = _path(session, w, field.crs_epsg)
        if other is None:
            excluded.append(
                ExcludedWell(well_id=w.id, name=w.canonical_name, reason="no trajectory")
            )
            continue
        hit = _closest(subject, other, lo, hi)
        if hit is None:
            excluded.append(
                ExcludedWell(
                    well_id=w.id,
                    name=w.canonical_name,
                    reason="does not reach the TVDSS window" if window else "no trajectory",
                )
            )
            continue
        dist, md_a, md_b, pa, pb = hit
        if dist > radius_m:
            continue
        bearing = math.degrees(math.atan2(pb[0] - pa[0], pb[1] - pa[1])) if dist > 0.01 else None
        row = _row(w, dist, bearing)
        row.closest_subject_md_m = round(md_a, 1)
        row.closest_offset_md_m = round(md_b, 1)
        row.closest_tvdss_m = round(float(pb[2]), 1)
        rows.append(row)
    seen = {r.well_id for r in rows} | {e.well_id for e in excluded}
    for o in surface_offsets(session, well.id, radius_m):
        if o.well_id not in seen and not session.scalar(
            select(Wellbore.id).where(
                Wellbore.well_id == o.well_id, Wellbore.path_geom.is_not(None)
            )
        ):
            excluded.append(ExcludedWell(well_id=o.well_id, name=o.name, reason="no trajectory"))
    rows.sort(key=lambda r: (r.distance_m, r.name))
    return ProximityResult(rows=rows, excluded=excluded)

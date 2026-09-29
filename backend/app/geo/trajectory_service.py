"""Trajectory lookups and survey upload (S4)."""

from pyproj import Transformer
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.v1.params import InvalidParamsError
from app.api.v1.schemas.wells import SurveyUpload, TrajectoryAtDepth
from app.core.errors import NotFoundError
from app.db.models import (
    CasingString,
    CementJob,
    Event,
    Field,
    Formation,
    FormationTop,
    MudInterval,
    SurveyStation,
    Well,
    Wellbore,
)
from app.extract.service import WellContext
from app.geo.mincurv import Trajectory, interpolate_at_md
from app.geo.service import build_stations, path_wkt, projected_xy


def _primary(session: Session, well: Well) -> Wellbore:
    wb = session.scalar(select(Wellbore).where(Wellbore.well_id == well.id).order_by(Wellbore.id))
    if wb is None:
        raise NotFoundError(f"Well {well.id} has no wellbore.", {"well_id": well.id})
    return wb


def load_trajectory(session: Session, wellbore_id: int) -> Trajectory | None:
    import numpy as np

    rows = session.scalars(
        select(SurveyStation)
        .where(SurveyStation.wellbore_id == wellbore_id)
        .order_by(SurveyStation.md_m)
    ).all()
    if len(rows) < 2:
        return None
    arr = {
        k: np.array([getattr(r, k) for r in rows], dtype=float)
        for k in ("md_m", "inc_deg", "azi_deg", "north_m", "east_m", "tvd_m", "dls_deg_30m")
    }
    return Trajectory(
        md=arr["md_m"],
        inc=arr["inc_deg"],
        azi=arr["azi_deg"],
        north=arr["north_m"],
        east=arr["east_m"],
        tvd=arr["tvd_m"],
        dls=arr["dls_deg_30m"],
    )


def at_depth(session: Session, well: Well, md_m: float) -> TrajectoryAtDepth:
    wb = _primary(session, well)
    traj = load_trajectory(session, wb.id)
    if traj is None:
        raise NotFoundError(f"Well {well.id} has no survey stations.", {"well_id": well.id})
    try:
        north, east, tvd, inc, azi = interpolate_at_md(traj, md_m)
    except ValueError as exc:
        raise InvalidParamsError(
            "md_m", f"md_m is beyond the surveyed range (0 to {traj.md[-1]:.1f} m)"
        ) from exc
    field = session.get(Field, well.field_id)
    assert field is not None
    x0, y0 = projected_xy(well.lat, well.lon, field.crs_epsg)
    lon, lat = Transformer.from_crs(field.crs_epsg, 4326, always_xy=True).transform(
        x0 + east, y0 + north
    )
    rkb = well.rkb_elev_m or 0.0
    ctx = WellContext.load(session, well.id)
    fid = ctx.formation_at(md_m)
    formation = session.get(Formation, fid) if fid else None
    return TrajectoryAtDepth(
        well_id=well.id,
        wellbore_id=wb.id,
        md_m=md_m,
        tvd_m=round(tvd, 2),
        tvdss_m=round(tvd - rkb, 2),
        north_m=round(north, 2),
        east_m=round(east, 2),
        inc_deg=round(inc, 3),
        azi_deg=round(azi, 3),
        lat=round(float(lat), 7),
        lon=round(float(lon), 7),
        formation=formation.name if formation else None,
        assumed=wb.trajectory_assumed,
    )


def replace_survey(session: Session, well: Well, body: SurveyUpload) -> Wellbore:
    """New stations → minimum curvature → path, formation tops and every depth reference
    derived from the trajectory (events, casing, cement, mud) recomputed."""
    wb = _primary(session, well)
    field = session.get(Field, well.field_id)
    assert field is not None
    corr = body.correction_deg or 0.0
    stations = [(s.md_m, s.inc_deg, (s.azi_deg + corr) % 360.0) for s in body.stations]
    rkb = well.rkb_elev_m or 0.0
    wb.stations.clear()
    session.flush()
    traj = build_stations(wb, stations, rkb)
    wb.trajectory_assumed = False
    well.td_md_m = max(well.td_md_m or 0.0, float(traj.md[-1]))
    session.flush()
    x0, y0 = projected_xy(well.lat, well.lon, field.crs_epsg)
    session.execute(
        text("UPDATE wellbore SET path_geom = ST_GeomFromText(:wkt, :srid) WHERE id = :id"),
        {"wkt": path_wkt(traj, x0, y0, rkb), "srid": field.crs_epsg, "id": wb.id},
    )
    last = float(traj.md[-1])
    for top in session.scalars(select(FormationTop).where(FormationTop.wellbore_id == wb.id)):
        if top.top_md_m > last:
            continue  # below the new survey: keep the header values, no extrapolation
        n, e, tvd = traj.position_at_md(top.top_md_m)
        top.top_tvd_m, top.top_tvdss_m = round(tvd, 2), round(tvd - rkb, 2)
        session.flush()
        session.execute(
            text(
                "UPDATE formation_top SET entry_point = ST_SetSRID(ST_MakePoint(:x, :y, :z), :s)"
                " WHERE wellbore_id = :wb AND formation_id = :f"
            ),
            {
                "x": x0 + e,
                "y": y0 + n,
                "z": -(tvd - rkb),
                "s": field.crs_epsg,
                "wb": wb.id,
                "f": top.formation_id,
            },
        )
    session.flush()
    ctx = WellContext.load(session, well.id)
    for ev in session.scalars(select(Event).where(Event.well_id == well.id)):
        ev.tvd_m, ev.tvdss_m = ctx.depth_refs(ev.md_m)
    for cs in session.scalars(select(CasingString).where(CasingString.wellbore_id == wb.id)):
        cs.shoe_tvd_m, cs.shoe_tvdss_m = ctx.depth_refs(cs.shoe_md_m)
        for job in session.scalars(select(CementJob).where(CementJob.casing_id == cs.id)):
            job.toc_tvdss_m = ctx.depth_refs(job.toc_md_m)[1]
    for mi in session.scalars(select(MudInterval).where(MudInterval.wellbore_id == wb.id)):
        mi.tvdss_from_m = ctx.depth_refs(mi.md_from_m)[1]
        mi.tvdss_to_m = ctx.depth_refs(mi.md_to_m)[1]
    session.flush()
    return wb

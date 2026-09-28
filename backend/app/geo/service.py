"""Trajectory storage and proximity queries (S4)."""

from dataclasses import dataclass
from typing import Any

from pyproj import Transformer
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.models import SurveyStation, Wellbore
from app.geo.mincurv import Trajectory, minimum_curvature


def build_stations(
    wellbore: Wellbore, stations: list[tuple[float, float, float]], rkb_elev_m: float
) -> Trajectory:
    """Replace a wellbore's survey stations with computed minimum-curvature positions."""
    md = [s[0] for s in stations]
    traj = minimum_curvature(md, [s[1] for s in stations], [s[2] for s in stations])
    wellbore.stations = [
        SurveyStation(
            md_m=float(traj.md[k]),
            inc_deg=float(traj.inc[k]),
            azi_deg=float(traj.azi[k]),
            tvd_m=float(traj.tvd[k]),
            tvdss_m=float(traj.tvd[k] - rkb_elev_m),
            north_m=float(traj.north[k]),
            east_m=float(traj.east[k]),
            dls_deg_30m=float(traj.dls[k]),
        )
        for k in range(len(md))
    ]
    wellbore.td_md_m = float(traj.md[-1])
    return traj


def path_wkt(traj: Trajectory, x0: float, y0: float, rkb_elev_m: float) -> str:
    """LINESTRING Z in the field CRS; Z = -TVDSS (metres, up positive)."""
    pts = ", ".join(
        f"{x0 + e:.2f} {y0 + n:.2f} {-(t - rkb_elev_m):.2f}"
        for n, e, t in zip(traj.north, traj.east, traj.tvd, strict=True)
    )
    if len(traj.md) == 1:  # degenerate: repeat the point so it's a valid line
        pts = f"{pts}, {pts}"
    return f"LINESTRING Z ({pts})"


def projected_xy(lat: float, lon: float, crs_epsg: int) -> tuple[float, float]:
    x, y = Transformer.from_crs(4326, crs_epsg, always_xy=True).transform(lon, lat)
    return float(x), float(y)


@dataclass(frozen=True)
class OffsetRow:
    well_id: int
    name: str
    status: str
    well_type: str | None
    lat: float
    lon: float
    td_md_m: float | None
    synthetic: bool
    distance_m: float
    bearing_deg: float | None


def surface_offsets(session: Session, well_id: int, radius_m: float) -> list[OffsetRow]:
    rows = session.execute(
        text(
            """
            SELECT o.id, o.canonical_name, o.status, o.well_type, o.lat, o.lon, o.td_md_m,
                   o.synthetic,
                   ST_Distance(o.surface_loc, a.surface_loc) AS distance_m,
                   degrees(ST_Azimuth(a.surface_loc, o.surface_loc)) AS bearing_deg
            FROM well a
            JOIN well o ON o.id <> a.id AND ST_DWithin(o.surface_loc, a.surface_loc, :r)
            WHERE a.id = :id
            ORDER BY distance_m, o.canonical_name
            """
        ),
        {"id": well_id, "r": radius_m},
    ).all()
    return [
        OffsetRow(
            well_id=r.id,
            name=r.canonical_name,
            status=r.status,
            well_type=r.well_type,
            lat=r.lat,
            lon=r.lon,
            td_md_m=r.td_md_m,
            synthetic=r.synthetic,
            distance_m=float(r.distance_m),
            bearing_deg=None if r.bearing_deg is None else float(r.bearing_deg),
        )
        for r in rows
    ]


def path_latlon(session: Session, wellbore_id: int, max_points: int = 60) -> list[dict[str, Any]]:
    """Wellbore path as lat/lon/TVDSS points (simplified) for drawing on a 2D map."""
    rows = session.execute(
        text(
            """
            SELECT ST_Y(p.geom) AS lat, ST_X(p.geom) AS lon, -ST_Z(d.geom) AS tvdss
            FROM wellbore w,
                 LATERAL ST_DumpPoints(w.path_geom) AS d,
                 LATERAL (SELECT ST_Transform(ST_Force2D(d.geom), 4326) AS geom) AS p
            WHERE w.id = :id
            ORDER BY d.path
            """
        ),
        {"id": wellbore_id},
    ).all()
    if len(rows) > max_points:
        step = (len(rows) - 1) / (max_points - 1)
        rows = [rows[round(i * step)] for i in range(max_points)]
    return [{"lat": float(r.lat), "lon": float(r.lon), "tvdss_m": float(r.tvdss)} for r in rows]

"""Import well master data (headers, surveys, formation tops) into the database.

The input format is the synthetic generator's `SyntheticField`; a converter from OIL's well
header / survey / tops exports would produce the same structure (master plan §12.5).
Re-importing is idempotent: wells are matched by canonical name and updated in place, so
documents already linked to a well keep their link.
"""

from datetime import date

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.models import Field, Formation, FormationTop, Well, Wellbore
from app.geo.service import build_stations, path_wkt, projected_xy
from app.synthetic.generator import SyntheticField


def import_field(session: Session, data: SyntheticField, synthetic: bool = True) -> dict[str, int]:
    field = session.scalar(select(Field).where(Field.name == data.field_name))
    if field is None:
        field = Field(
            name=data.field_name, basin=data.basin, crs_epsg=data.crs_epsg, synthetic=synthetic
        )
        session.add(field)
        session.flush()

    formations: dict[str, Formation] = {}
    for f in data.formations:
        row = session.scalar(
            select(Formation).where(Formation.basin == data.basin, Formation.name == f["name"])
        )
        if row is None:
            row = Formation(basin=data.basin, name=f["name"])
            session.add(row)
        row.synonyms = list(f["synonyms"])
        row.strat_order = int(f["strat_order"])
        row.lithology = f["lithology"]
        formations[row.name] = row
    session.flush()

    n_tops = 0
    for w in data.wells:
        well = session.scalar(select(Well).where(Well.canonical_name == w.name))
        if well is None:
            well = Well(
                canonical_name=w.name, field_id=field.id, lat=w.lat, lon=w.lon, status=w.status
            )
            session.add(well)
        well.aliases = sorted(set(w.aliases) | set(well.aliases or []))
        well.field_id = field.id
        well.status = w.status
        well.well_type = w.well_type
        well.fluid_type = w.fluid_type
        well.profile = w.profile
        well.lat, well.lon = w.lat, w.lon
        well.rkb_elev_m, well.gl_elev_m = w.rkb_elev_m, w.gl_elev_m
        well.datum_assumed = False
        well.spud_date = date.fromisoformat(w.spud)
        well.completion_date = date.fromisoformat(w.completion) if w.completion else None
        well.td_md_m = w.td_md_m
        well.rig_name = w.rig
        well.units_system = w.units
        well.synthetic = synthetic
        session.flush()
        session.execute(
            text(
                "UPDATE well SET surface_loc = "
                "ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography WHERE id = :id"
            ),
            {"lon": w.lon, "lat": w.lat, "id": well.id},
        )

        # Update the wellbore in place: extracted events, casing, mud and DDR lines hang
        # off it (ON DELETE CASCADE), so re-seeding must not recreate it.
        wb = well.wellbores[0] if well.wellbores else None
        if wb is None:
            wb = Wellbore(well_id=well.id, name="OH", trajectory_assumed=False)
            well.wellbores.append(wb)
        wb.trajectory_assumed = False
        wb.tops.clear()
        wb.stations.clear()  # flushed first: new stations reuse the (wellbore, md) keys
        session.flush()
        traj = build_stations(wb, [(s[0], s[1], s[2]) for s in w.stations], w.rkb_elev_m)
        session.flush()
        x0, y0 = projected_xy(w.lat, w.lon, data.crs_epsg)
        session.execute(
            text("UPDATE wellbore SET path_geom = ST_GeomFromText(:wkt, :srid) WHERE id = :id"),
            {"wkt": path_wkt(traj, x0, y0, w.rkb_elev_m), "srid": data.crs_epsg, "id": wb.id},
        )
        for t in w.tops:
            wb.tops.append(
                FormationTop(
                    formation_id=formations[t.formation].id,
                    top_md_m=t.top_md_m,
                    top_tvd_m=t.top_tvd_m,
                    top_tvdss_m=t.top_tvdss_m,
                    source="well_header_db",
                )
            )
            n_tops += 1
        session.flush()
        for t in w.tops:
            n, e, tvd = traj.position_at_md(t.top_md_m)
            session.execute(
                text(
                    "UPDATE formation_top SET entry_point = "
                    "ST_SetSRID(ST_MakePoint(:x, :y, :z), :srid) "
                    "WHERE wellbore_id = :wb AND formation_id = :f"
                ),
                {
                    "x": x0 + e,
                    "y": y0 + n,
                    "z": -(tvd - w.rkb_elev_m),
                    "srid": data.crs_epsg,
                    "wb": wb.id,
                    "f": formations[t.formation].id,
                },
            )
    return {"wells": len(data.wells), "formations": len(formations), "formation_tops": n_tops}

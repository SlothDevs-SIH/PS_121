"""Well listing, detail and data-quality scoring (S3)."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.schemas.wells import (
    DataQuality,
    FormationTopOut,
    QualityCheck,
    WellDetail,
    WellSummary,
)
from app.core.errors import NotFoundError
from app.db.models import Document, Field, Formation, FormationTop, Well, Wellbore


def get_well_or_404(session: Session, well_id: int) -> Well:
    well = session.get(Well, well_id)
    if well is None:
        raise NotFoundError(f"Well {well_id} not found.", {"well_id": well_id})
    return well


def _doc_counts(session: Session) -> dict[int, int]:
    rows = session.execute(
        select(Document.well_id, func.count())
        .where(Document.well_id.is_not(None))
        .group_by(Document.well_id)
    ).all()
    return {int(w): int(c) for w, c in rows}


def _summary(w: Well, field_name: str, docs: int) -> dict[str, object]:
    return {
        "id": w.id,
        "name": w.canonical_name,
        "field": field_name,
        "status": w.status,
        "well_type": w.well_type,
        "profile": w.profile,
        "lat": w.lat,
        "lon": w.lon,
        "td_md_m": w.td_md_m,
        "spud_date": w.spud_date,
        "synthetic": w.synthetic,
        "document_count": docs,
    }


def list_wells(
    session: Session, field: str | None, status: str | None, q: str | None, limit: int, offset: int
) -> tuple[list[WellSummary], int]:
    stmt = select(Well, Field.name).join(Field, Field.id == Well.field_id)
    if field:
        stmt = stmt.where(Field.name == field)
    if status:
        stmt = stmt.where(Well.status == status)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            Well.canonical_name.ilike(like) | func.array_to_string(Well.aliases, " ").ilike(like)
        )
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    counts = _doc_counts(session)
    rows = session.execute(stmt.order_by(Well.canonical_name).limit(limit).offset(offset)).all()
    return [WellSummary.model_validate(_summary(w, f, counts.get(w.id, 0))) for w, f in rows], int(
        total
    )


def data_quality(well: Well, wb: Wellbore | None, n_tops: int, n_docs: int) -> DataQuality:
    checks = [
        QualityCheck(
            name="surveys",
            ok=bool(wb and wb.stations and not wb.trajectory_assumed),
            detail="measured surveys"
            if wb and wb.stations and not wb.trajectory_assumed
            else "trajectory assumed vertical",
        ),
        QualityCheck(
            name="datum",
            ok=well.rkb_elev_m is not None and not well.datum_assumed,
            detail=f"RKB {well.rkb_elev_m} m above MSL"
            if well.rkb_elev_m is not None
            else "depth datum unknown",
        ),
        QualityCheck(name="formation_tops", ok=n_tops >= 3, detail=f"{n_tops} formation tops"),
        QualityCheck(name="documents", ok=n_docs > 0, detail=f"{n_docs} documents ingested"),
        QualityCheck(name="coordinates", ok=True, detail="surface location in WGS84"),
    ]
    return DataQuality(score=round(sum(c.ok for c in checks) / len(checks), 2), checks=checks)


def well_detail(session: Session, well_id: int) -> WellDetail:
    well = get_well_or_404(session, well_id)
    field = session.get(Field, well.field_id)
    assert field is not None
    wb = well.wellbores[0] if well.wellbores else None
    tops: list[FormationTopOut] = []
    if wb is not None:
        rows = session.execute(
            select(FormationTop, Formation)
            .join(Formation, Formation.id == FormationTop.formation_id)
            .where(FormationTop.wellbore_id == wb.id)
            .order_by(FormationTop.top_md_m)
        ).all()
        tops = [
            FormationTopOut(
                formation=f.name,
                strat_order=f.strat_order,
                top_md_m=t.top_md_m,
                top_tvd_m=t.top_tvd_m,
                top_tvdss_m=t.top_tvdss_m,
            )
            for t, f in rows
        ]
    n_docs = session.scalar(select(func.count()).where(Document.well_id == well.id)) or 0
    return WellDetail.model_validate(
        {
            **_summary(well, field.name, n_docs),
            "aliases": well.aliases,
            "rkb_elev_m": well.rkb_elev_m,
            "gl_elev_m": well.gl_elev_m,
            "datum_assumed": well.datum_assumed,
            "completion_date": well.completion_date,
            "rig_name": well.rig_name,
            "units_system": well.units_system,
            "trajectory_assumed": bool(wb.trajectory_assumed) if wb else True,
            "crs_epsg": field.crs_epsg,
            "formation_tops": tops,
            "data_quality": data_quality(well, wb, len(tops), n_docs),
        }
    )

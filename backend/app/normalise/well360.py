"""Well 360 enrichment (B2): casing + cement, mud, events, documents and lessons for one
well, added to the B1 well detail. Every extracted row carries its trust fields."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.v1.schemas.wells import (
    CasingOut,
    CementJobOut,
    DocumentsOverview,
    MudIntervalOut,
    WellDetail,
)
from app.db.models import CasingString, Document, Event, MudInterval, Wellbore
from app.extract.events_service import event_counts_by_type, recent_events
from app.extract.evidence import record_evidence
from app.search.hybrid import lesson_cards

MAX_RECENT = 10


def enrich(session: Session, detail: WellDetail) -> WellDetail:
    wb_id = session.scalar(
        select(Wellbore.id).where(Wellbore.well_id == detail.id).order_by(Wellbore.id)
    )
    casing: list[CasingOut] = []
    mud: list[MudIntervalOut] = []
    if wb_id is not None:
        strings = list(
            session.scalars(
                select(CasingString)
                .where(CasingString.wellbore_id == wb_id)
                .options(selectinload(CasingString.cement_jobs))
                .order_by(CasingString.shoe_md_m.asc().nulls_last())
            )
        )
        ev = record_evidence(session, [(c.document_id, c.page_no, c.span_ids) for c in strings])
        for c, refs in zip(strings, ev, strict=True):
            job_refs = record_evidence(
                session, [(j.document_id, j.page_no, j.span_ids) for j in c.cement_jobs]
            )
            casing.append(
                CasingOut(
                    id=c.id,
                    od_in=c.od_in,
                    hole_size_in=c.hole_size_in,
                    shoe_md_m=c.shoe_md_m,
                    shoe_tvd_m=c.shoe_tvd_m,
                    shoe_tvdss_m=c.shoe_tvdss_m,
                    planned_shoe_md_m=c.planned_shoe_md_m,
                    grade=c.grade,
                    weight_ppf=c.weight_ppf,
                    confidence=c.confidence,
                    verified=c.verified,
                    evidence=refs,
                    cement=[
                        CementJobOut(
                            id=j.id,
                            toc_md_m=j.toc_md_m,
                            toc_tvdss_m=j.toc_tvdss_m,
                            returns=j.returns,
                            slurry_density_sg=j.slurry_density_sg,
                            volume_m3=j.volume_m3,
                            bond_quality=j.bond_quality,
                            remedial=j.remedial,
                            confidence=j.confidence,
                            verified=j.verified,
                            evidence=jr,
                        )
                        for j, jr in zip(c.cement_jobs, job_refs, strict=True)
                    ],
                )
            )
        intervals = list(
            session.scalars(
                select(MudInterval)
                .where(MudInterval.wellbore_id == wb_id)
                .order_by(MudInterval.md_from_m)
            )
        )
        mrefs = record_evidence(
            session, [(m.document_id, m.page_no, m.span_ids) for m in intervals]
        )
        mud = [
            MudIntervalOut(
                id=m.id,
                md_from_m=m.md_from_m,
                md_to_m=m.md_to_m,
                tvdss_from_m=m.tvdss_from_m,
                tvdss_to_m=m.tvdss_to_m,
                hole_size_in=m.hole_size_in,
                mud_type=m.mud_type,
                mw_sg=m.mw_sg,
                ecd_sg=m.ecd_sg,
                confidence=m.confidence,
                verified=m.verified,
                evidence=r,
            )
            for m, r in zip(intervals, mrefs, strict=True)
        ]

    def counts(col: str) -> dict[str, int]:
        column = getattr(Document, col)
        rows = session.execute(
            select(column, func.count()).where(Document.well_id == detail.id).group_by(column)
        ).all()
        return {str(k) if k is not None else "unknown": int(n) for k, n in rows}

    by_type = counts("doc_type")
    lesson_ids = list(
        session.scalars(
            select(Event.id)
            .where(
                Event.well_id == detail.id,
                Event.status == "active",
                Event.lesson_card.is_not(None),
            )
            .order_by(Event.event_date.desc().nulls_last(), Event.id.desc())
            .limit(MAX_RECENT)
        )
    )
    return detail.model_copy(
        update={
            "casing": casing,
            "mud": mud,
            "event_counts": event_counts_by_type(session, detail.id),
            "recent_events": recent_events(session, detail.id, MAX_RECENT),
            "documents": DocumentsOverview(
                total=sum(by_type.values()),
                by_doc_type=by_type,
                by_ingest_status=counts("ingest_status"),
                by_extract_status=counts("extract_status"),
                by_index_status=counts("index_status"),
            ),
            "lessons": lesson_cards(session, lesson_ids),
        }
    )

"""The scoring context of a well, from the database: trajectory, hole size, and the offset
prior per formation (with prognosed tops below a drilling well's TD) for the look-ahead."""

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import MudInterval, SurveyStation, Well, Wellbore
from app.risk.prior import risk_profile
from app.stream.scorer import Interval, WellContext


def build_context(session: Session, well_id: int, wellbore_id: int) -> WellContext:
    well = session.get(Well, well_id)
    if well is None:
        raise LookupError(f"well {well_id} not found")
    st = session.execute(
        select(SurveyStation.md_m, SurveyStation.tvdss_m, SurveyStation.inc_deg)
        .where(SurveyStation.wellbore_id == wellbore_id)
        .order_by(SurveyStation.md_m)
    ).all()
    hole = session.scalar(
        select(MudInterval.hole_size_in)
        .join(Wellbore, Wellbore.id == MudInterval.wellbore_id)
        .where(Wellbore.id == wellbore_id, MudInterval.hole_size_in.is_not(None))
        .order_by(MudInterval.md_to_m.desc())
        .limit(1)
    )
    profile = risk_profile(session, well_id)
    intervals = [
        Interval(
            formation=iv.formation,
            top_md_m=iv.top_md_m,
            top_tvdss_m=iv.top_tvdss_m,
            prognosed=iv.prognosed,
            risks={r.event_type: r.probability for r in iv.risks},
            offset_events={
                t: [i for o in iv.offsets for i in o.events.get(t, [])]
                for t in {t for o in iv.offsets for t in o.events}
            },
        )
        for iv in profile.intervals
    ]
    return WellContext(
        well_id=well_id,
        wellbore_id=wellbore_id,
        name=well.canonical_name,
        hole_size_in=float(hole) if hole else 8.5,
        station_md=np.array([float(r[0]) for r in st]),
        station_tvdss=np.array([float(r[1]) for r in st]),
        last_inc_deg=float(st[-1][2]) if st else 0.0,
        intervals=intervals,
    )

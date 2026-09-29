"""Formation lookup by name or synonym (query filters, manual entry)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.params import InvalidParamsError
from app.db.models import Formation


def formation_ids(
    session: Session, raw: str, param: str = "formation"
) -> tuple[list[int], list[str]]:
    """Ids of formations whose name or a synonym equals ``raw`` (case-insensitive), with
    all their names. 422 when nothing matches: an unknown name is a caller error, not an
    empty result."""
    want = raw.strip().lower()
    ids: list[int] = []
    names: list[str] = []
    for f in session.scalars(select(Formation).order_by(Formation.strat_order)):
        all_names = [f.name, *(f.synonyms or [])]
        if any(n.lower() == want for n in all_names):
            ids.append(f.id)
            names += all_names
    if not ids:
        raise InvalidParamsError(param, f"unknown formation {raw!r}")
    return ids, names


def formation_names(session: Session) -> dict[int, str]:
    return dict(session.execute(select(Formation.id, Formation.name)).tuples().all())

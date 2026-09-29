"""Shared query-parameter types and cross-parameter checks for the v1 routes.

Field-level validation (types, ranges) is FastAPI's and answers 422 ``validation_error``.
Rules that involve several parameters are checked here and answer the same envelope, so a
client sees one error shape whichever rule it broke.
"""

from dataclasses import dataclass
from datetime import date
from typing import Annotated, Any, TypeVar

from fastapi import Query

from app.core.errors import AppError, ErrorResponse

MAX_PAGE_LIMIT = 500

Limit = Annotated[int, Query(ge=1, le=MAX_PAGE_LIMIT, description="Page size")]
Cursor = Annotated[
    str | None,
    Query(max_length=200, description="Opaque cursor from the previous page's next_cursor"),
]
RadiusKm = Annotated[
    float | None,
    Query(gt=0, le=100, description="Radius around well_id's surface location (km)"),
]

NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Not found"}
}


class InvalidParamsError(AppError):
    """422 for rules spanning several parameters; ``details.errors`` mirrors FastAPI's."""

    status_code = 422
    code = "validation_error"

    def __init__(self, param: str, message: str) -> None:
        super().__init__(
            "Request validation failed",
            {"errors": [{"loc": ["query", param], "msg": message, "type": "value_error"}]},
        )


Bound = TypeVar("Bound", float, date)


def check_range(lo_name: str, lo: Bound | None, hi_name: str, hi: Bound | None) -> None:
    """Reject ``lo > hi`` when both ends are given."""
    if lo is not None and hi is not None and lo > hi:
        raise InvalidParamsError(hi_name, f"{hi_name} must not be less than {lo_name}")


def require_well_for_radius(well_id: int | None, radius_km: float | None) -> None:
    if radius_km is not None and well_id is None:
        raise InvalidParamsError("radius_km", "radius_km needs well_id (the circle's centre)")


@dataclass(frozen=True)
class BBox:
    """WGS84 bounding box ``min_lon,min_lat,max_lon,max_lat`` (GeoJSON order)."""

    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float


def parse_bbox(raw: str | None) -> BBox | None:
    if raw is None:
        return None
    parts = raw.split(",")
    try:
        values = [float(p) for p in parts]
    except ValueError:
        values = []
    if len(values) != 4:
        raise InvalidParamsError("bbox", "bbox must be 'min_lon,min_lat,max_lon,max_lat'")
    box = BBox(*values)
    if not (-180 <= box.min_lon < box.max_lon <= 180 and -90 <= box.min_lat < box.max_lat <= 90):
        raise InvalidParamsError(
            "bbox", "bbox corners must be valid WGS84 degrees with min < max on both axes"
        )
    return box

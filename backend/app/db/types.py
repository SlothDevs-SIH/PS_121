"""Minimal PostGIS column types (avoids a GeoAlchemy2 dependency for the few columns we need).

Geometry values are always written and read through SQL functions (ST_MakePoint, ST_X, …),
so these types only need to emit the right DDL.
"""

from typing import Any

from sqlalchemy.types import UserDefinedType


class Geography(UserDefinedType[Any]):
    cache_ok = True

    def __init__(self, geom_type: str = "POINT", srid: int = 4326) -> None:
        self.geom_type = geom_type
        self.srid = srid

    def get_col_spec(self, **_: Any) -> str:
        return f"geography({self.geom_type},{self.srid})"


class Geometry(UserDefinedType[Any]):
    """Geometry without an SRID type modifier: each field stores its own projected CRS."""

    cache_ok = True

    def __init__(self, geom_type: str = "GEOMETRY") -> None:
        self.geom_type = geom_type

    def get_col_spec(self, **_: Any) -> str:
        return f"geometry({self.geom_type})"

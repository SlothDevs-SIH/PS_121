"""Minimal PostGIS and pgvector column types (no GeoAlchemy2 / pgvector dependency for the few
columns we need).

Geometry values are always written and read through SQL functions (ST_MakePoint, ST_X, …),
so these types only need to emit the right DDL.
"""

import math
from collections.abc import Callable
from typing import Any

from sqlalchemy import cast
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


class Vector(UserDefinedType[list[float]]):
    """pgvector ``vector(dim)`` column.

    Written as pgvector's text form ``[x1,x2,...]`` wrapped in an explicit ``CAST(... AS
    vector(dim))`` (psycopg sends Python ``str`` as ``text``, and there is no implicit
    text -> vector cast), read back into ``list[float]``. This is the whole adapter the app
    needs, so the ``pgvector`` package is not added: similarity queries use pgvector's
    operators through ``Column.op("<=>")`` in the search module.
    """

    cache_ok = True

    def __init__(self, dim: int) -> None:
        if dim <= 0:
            raise ValueError("vector dimension must be positive")
        self.dim = dim

    def get_col_spec(self, **_: Any) -> str:
        return f"vector({self.dim})"

    def bind_expression(self, bindvalue: Any) -> Any:
        return cast(bindvalue, self)

    def bind_processor(self, dialect: Any) -> Callable[[Any], str | None]:
        dim = self.dim

        def process(value: Any) -> str | None:
            if value is None:
                return None
            values = [float(v) for v in value]
            if len(values) != dim:
                raise ValueError(f"expected a {dim}-dimensional vector, got {len(values)}")
            if not all(math.isfinite(v) for v in values):
                raise ValueError("vector values must be finite")
            return "[" + ",".join(repr(v) for v in values) + "]"

        return process

    def result_processor(self, dialect: Any, coltype: Any) -> Callable[[Any], list[float] | None]:
        def process(value: Any) -> list[float] | None:
            if value is None:
                return None
            if isinstance(value, str):
                body = value.strip().removeprefix("[").removesuffix("]")
                return [float(v) for v in body.split(",")] if body else []
            return [float(v) for v in value]

        return process

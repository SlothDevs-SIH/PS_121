"""S3/S4 tables: fields, formations, wells, wellbores, surveys, formation tops, aliases."""

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, deferred, mapped_column, relationship

from app.db.base import Base
from app.db.types import Geography, Geometry
from app.db.vocab import FLUID_TYPES, in_list


class Field(Base):
    __tablename__ = "field"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True)
    basin: Mapped[str | None] = mapped_column(Text)
    crs_epsg: Mapped[int] = mapped_column(Integer)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False)


class Formation(Base):
    __tablename__ = "formation"
    __table_args__ = (UniqueConstraint("basin", "name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    basin: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    synonyms: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    strat_order: Mapped[int] = mapped_column(Integer)  # youngest = 1
    lithology: Mapped[str | None] = mapped_column(Text)


class Well(Base):
    __tablename__ = "well"
    __table_args__ = (
        Index("ix_well_surface_loc", "surface_loc", postgresql_using="gist"),
        Index(
            "ix_well_name_trgm",
            "canonical_name",
            postgresql_using="gin",
            postgresql_ops={"canonical_name": "gin_trgm_ops"},
        ),
        CheckConstraint(in_list("fluid_type", FLUID_TYPES), name="fluid_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    canonical_name: Mapped[str] = mapped_column(Text, unique=True)
    aliases: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    field_id: Mapped[int] = mapped_column(ForeignKey("field.id"))
    status: Mapped[str] = mapped_column(String(20))  # planned | drilling | completed | abandoned
    well_type: Mapped[str | None] = mapped_column(String(30))  # purpose: exploration / ...
    fluid_type: Mapped[str | None] = mapped_column(String(10))  # oil | gas | water (B2)
    profile: Mapped[str | None] = mapped_column(String(20))
    surface_loc: Mapped[Any] = deferred(mapped_column(Geography("POINT", 4326)))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    rkb_elev_m: Mapped[float | None] = mapped_column(Float)
    gl_elev_m: Mapped[float | None] = mapped_column(Float)
    datum_assumed: Mapped[bool] = mapped_column(Boolean, default=False)
    spud_date: Mapped[date | None] = mapped_column(Date)
    completion_date: Mapped[date | None] = mapped_column(Date)
    td_md_m: Mapped[float | None] = mapped_column(Float)
    rig_name: Mapped[str | None] = mapped_column(Text)
    units_system: Mapped[str | None] = mapped_column(String(20))
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    field: Mapped[Field] = relationship()
    wellbores: Mapped[list["Wellbore"]] = relationship(
        back_populates="well", cascade="all, delete-orphan"
    )


class Wellbore(Base):
    __tablename__ = "wellbore"
    __table_args__ = (Index("ix_wellbore_path_geom", "path_geom", postgresql_using="gist"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    well_id: Mapped[int] = mapped_column(ForeignKey("well.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(Text, default="OH")
    trajectory_assumed: Mapped[bool] = mapped_column(Boolean, default=False)
    td_md_m: Mapped[float | None] = mapped_column(Float)
    path_geom: Mapped[Any] = deferred(mapped_column(Geometry("LINESTRINGZ")))

    well: Mapped[Well] = relationship(back_populates="wellbores")
    stations: Mapped[list["SurveyStation"]] = relationship(
        cascade="all, delete-orphan", order_by="SurveyStation.md_m"
    )
    tops: Mapped[list["FormationTop"]] = relationship(cascade="all, delete-orphan")


class SurveyStation(Base):
    __tablename__ = "survey_station"

    wellbore_id: Mapped[int] = mapped_column(
        ForeignKey("wellbore.id", ondelete="CASCADE"), primary_key=True
    )
    md_m: Mapped[float] = mapped_column(Float, primary_key=True)
    inc_deg: Mapped[float] = mapped_column(Float)
    azi_deg: Mapped[float] = mapped_column(Float)
    tvd_m: Mapped[float] = mapped_column(Float)
    tvdss_m: Mapped[float] = mapped_column(Float)
    north_m: Mapped[float] = mapped_column(Float)
    east_m: Mapped[float] = mapped_column(Float)
    dls_deg_30m: Mapped[float] = mapped_column(Float)


class FormationTop(Base):
    __tablename__ = "formation_top"
    __table_args__ = (
        Index("ix_formation_top_entry_point", "entry_point", postgresql_using="gist"),
    )

    wellbore_id: Mapped[int] = mapped_column(
        ForeignKey("wellbore.id", ondelete="CASCADE"), primary_key=True
    )
    formation_id: Mapped[int] = mapped_column(ForeignKey("formation.id"), primary_key=True)
    top_md_m: Mapped[float] = mapped_column(Float)
    top_tvd_m: Mapped[float] = mapped_column(Float)
    top_tvdss_m: Mapped[float] = mapped_column(Float)
    entry_point: Mapped[Any] = deferred(mapped_column(Geometry("POINTZ")))
    source: Mapped[str] = mapped_column(String(30), default="well_header_db")

    formation: Mapped[Formation] = relationship()


class AliasCandidate(Base):
    """A well name seen in a document that didn't match exactly; a human confirms or rejects."""

    __tablename__ = "alias_candidate"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    raw_name: Mapped[str] = mapped_column(Text)
    well_id: Mapped[int | None] = mapped_column(ForeignKey("well.id", ondelete="CASCADE"))
    similarity: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    document_id: Mapped[int | None] = mapped_column(ForeignKey("document.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

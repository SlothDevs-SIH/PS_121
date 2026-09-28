"""Machine-readable build status of every backend component, served at /api/v1/meta.

Keep in sync with docs/BACKEND_PLAN.md §5 ("Designed vs. Built"): update both in the same PR.
"""

from typing import Literal

from pydantic import BaseModel

Status = Literal["planned", "in_progress", "built"]

CURRENT_PHASE = "B1"


class Component(BaseModel):
    key: str
    stage: str
    name: str
    phase: str
    status: Status


COMPONENTS: list[Component] = [
    Component(
        key="platform",
        stage="-",
        name="Skeleton: config, logging, errors, health, CLI, CI",
        phase="B0",
        status="built",
    ),
    Component(
        key="ingest", stage="S1", name="Document ingestion & OCR", phase="B1", status="built"
    ),
    Component(
        key="extract",
        stage="S2",
        name="Schema extraction + review queue",
        phase="B2",
        status="planned",
    ),
    Component(
        key="normalise",
        stage="S3",
        name="Units, datums, formations, aliases, CRS",
        phase="B1",
        status="built",
    ),
    Component(
        key="geo",
        stage="S4",
        name="Trajectory engine & proximity modes (surface built; other modes B2)",
        phase="B1",
        status="in_progress",
    ),
    Component(
        key="search",
        stage="S5",
        name="Hybrid search, RAG, lessons cards",
        phase="B2",
        status="planned",
    ),
    Component(
        key="correlation",
        stage="S6",
        name="Depth/formation correlation",
        phase="B2",
        status="planned",
    ),
    Component(
        key="risk_prior", stage="S7a", name="Offset prior risk", phase="B3", status="planned"
    ),
    Component(
        key="risk_ml",
        stage="S7b",
        name="Rig state + real-time classifiers",
        phase="B4",
        status="planned",
    ),
    Component(key="physics", stage="S7c", name="Physics indicators", phase="B3", status="planned"),
    Component(
        key="dejavu",
        stage="S7d",
        name="Deja Vu pattern matching (USP 1)",
        phase="B4",
        status="planned",
    ),
    Component(
        key="ledger",
        stage="S8",
        name="Mitigation Effectiveness Ledger (USP 2)",
        phase="B3",
        status="planned",
    ),
    Component(key="alerts", stage="S9", name="Alert engine", phase="B4", status="planned"),
    Component(
        key="copilot",
        stage="S10",
        name="Copilot with read-only tools",
        phase="B5",
        status="planned",
    ),
    Component(
        key="stream", stage="S12", name="eRTMAC adapter & replay", phase="B4", status="planned"
    ),
    Component(
        key="auth", stage="-", name="OIDC auth, RBAC, audit log", phase="B6", status="planned"
    ),
]

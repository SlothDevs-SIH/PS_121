"""Machine-readable build status of every backend component, served at /api/v1/meta.

Keep in sync with docs/BACKEND_PLAN.md §5 ("Designed vs. Built"): update both in the same PR.
"""

from typing import Literal

from pydantic import BaseModel

Status = Literal["planned", "in_progress", "built"]

CURRENT_PHASE = "B6"


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
        status="built",
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
        name="Trajectory engine & proximity modes (surface, at-formation, closest approach)",
        phase="B1",
        status="built",
    ),
    Component(
        key="search",
        stage="S5",
        name="Hybrid search + lessons cards (RAG copilot: B5)",
        phase="B2",
        status="built",
    ),
    Component(
        key="correlation",
        stage="S6",
        name="Depth/formation correlation",
        phase="B2",
        status="built",
    ),
    Component(
        key="risk_prior",
        stage="S7a",
        name="Offset prior risk + cementing checklist",
        phase="B3",
        status="built",
    ),
    Component(
        key="risk_ml",
        stage="S7b",
        name="Rig state + real-time classifiers",
        phase="B4",
        status="built",
    ),
    Component(
        key="physics",
        stage="S7c",
        name="Physics indicators (formula library + live rules on the stream)",
        phase="B3",
        status="built",
    ),
    Component(
        key="dejavu",
        stage="S7d",
        name="Deja Vu pattern matching (USP 1)",
        phase="B4",
        status="built",
    ),
    Component(
        key="ledger",
        stage="S8",
        name="Mitigation Effectiveness Ledger (USP 2)",
        phase="B3",
        status="built",
    ),
    Component(key="alerts", stage="S9", name="Alert engine", phase="B4", status="built"),
    Component(
        key="copilot",
        stage="S10",
        name="Copilot with read-only tools (rules planner; optional LLM agent)",
        phase="B5",
        status="built",
    ),
    Component(
        key="reports",
        stage="-",
        name="Offset Risk Brief (PDF) and analytics endpoints",
        phase="B5",
        status="built",
    ),
    Component(
        key="stream",
        stage="S12",
        name="eRTMAC adapter & replay (CSV replay, WITS0; WITSML/ETP: later)",
        phase="B4",
        status="built",
    ),
    Component(
        key="auth",
        stage="-",
        name="Local JWT auth, role-based permissions, append-only audit log",
        phase="B5",
        status="built",
    ),
    Component(
        key="oidc",
        stage="-",
        name="OIDC login (Keycloak), session cookies, refresh, lockout, rate limits",
        phase="B6",
        status="built",
    ),
    Component(
        key="observability",
        stage="-",
        name="Prometheus metrics (API, worker, stream) and Grafana dashboard",
        phase="B6",
        status="built",
    ),
    Component(
        key="backups",
        stage="-",
        name="Backup, verify and restore scripts (pg_dump + S3 buckets)",
        phase="B6",
        status="built",
    ),
    Component(
        key="loadtest",
        stage="-",
        name="Load test of the read-only API against the §9 latency targets",
        phase="B6",
        status="in_progress",
    ),
    Component(
        key="security_review",
        stage="-",
        name="Security review and dependency audit",
        phase="B6",
        status="in_progress",
    ),
]

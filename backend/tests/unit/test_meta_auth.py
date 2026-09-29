import pytest
from fastapi.testclient import TestClient

from app.core.phases import COMPONENTS, CURRENT_PHASE
from app.main import create_app

VALID_PHASES = {f"B{i}" for i in range(7)}


def test_meta_reports_phase_and_components(client: TestClient) -> None:
    body = client.get("/api/v1/meta").json()
    assert body["backend_phase"] == CURRENT_PHASE == "B2"
    assert len(body["components"]) == len(COMPONENTS)


def test_component_registry_is_consistent() -> None:
    keys = [c.key for c in COMPONENTS]
    assert len(keys) == len(set(keys))
    assert all(c.phase in VALID_PHASES for c in COMPONENTS)
    # Built so far: B0 platform, B1 ingestion/normalisation/geo, B2 extraction, search and
    # correlation (Part 2). Nothing is half-built between parts.
    assert [c.key for c in COMPONENTS if c.status == "built"] == [
        "platform",
        "ingest",
        "extract",
        "normalise",
        "geo",
        "search",
        "correlation",
    ]
    assert [c.key for c in COMPONENTS if c.status == "in_progress"] == []


def test_dev_auth_returns_local_admin(client: TestClient) -> None:
    body = client.get("/api/v1/me").json()
    assert body["user_id"] == "dev"
    assert body["roles"] == ["admin"]


@pytest.mark.parametrize(("env", "mode"), [("prod", "dev"), ("test", "oidc")])
def test_auth_refuses_unconfigured_modes(
    monkeypatch: pytest.MonkeyPatch, env: str, mode: str
) -> None:
    monkeypatch.setenv("SMRITI_ENV", env)
    monkeypatch.setenv("SMRITI_AUTH_MODE", mode)
    from app.core.config import get_settings

    get_settings.cache_clear()
    r = TestClient(create_app()).get("/api/v1/me")
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "auth_not_configured"

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.health import ComponentStatus, _timed, run_checks
from app.main import create_app, get_health_checks


def _ok(name: str):
    return lambda _s: ComponentStatus(name=name, ok=True, latency_ms=1.0, detail="ok")


def _fail(name: str):
    return lambda _s: ComponentStatus(name=name, ok=False, latency_ms=1.0, detail="down")


def _client_with(checks) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_health_checks] = lambda: checks
    return TestClient(app)


def test_healthz_is_always_ok(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_readyz_200_when_all_components_ok() -> None:
    r = _client_with([_ok("postgres"), _ok("redis"), _ok("object_storage")]).get("/readyz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ready"
    assert [c["name"] for c in body["components"]] == ["postgres", "redis", "object_storage"]


def test_readyz_503_when_any_component_fails() -> None:
    r = _client_with([_ok("postgres"), _fail("redis")]).get("/readyz")
    assert r.status_code == 503
    assert r.json()["status"] == "not_ready"


def test_timed_turns_exceptions_into_failed_status() -> None:
    def boom() -> str:
        raise ConnectionError("refused")

    status = _timed("x", boom)
    assert status.ok is False
    assert "ConnectionError: refused" in status.detail


def test_real_checks_report_not_ready_when_nothing_is_running() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://u:p@127.0.0.1:1/db",
        redis_url="redis://127.0.0.1:1/0",
        s3_endpoint_url="http://127.0.0.1:1",
        readiness_timeout_s=0.5,
    )
    from app.core import health

    report = run_checks(settings, [health.check_redis])
    assert report.status == "not_ready"
    assert report.components[0].ok is False

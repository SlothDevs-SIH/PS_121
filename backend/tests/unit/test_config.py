import pytest

from app.core.config import Settings


def test_env_overrides_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SMRITI_REDIS_URL", "redis://cache:6379/2")
    monkeypatch.setenv("SMRITI_S3_BUCKET_RAW", "raw-x")
    s = Settings()
    assert s.redis_url == "redis://cache:6379/2"
    assert s.s3_buckets == ["raw-x", "smriti-pages"]


def test_secrets_are_not_printed() -> None:
    s = Settings()
    assert "smriti-secret" not in repr(s)

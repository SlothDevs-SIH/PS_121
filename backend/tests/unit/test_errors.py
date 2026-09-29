"""The error envelope must survive validators that raise plain ValueError."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, field_validator

from app.core.errors import register_error_handlers


class _Body(BaseModel):
    depth_m: float

    @field_validator("depth_m")
    @classmethod
    def _non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("depth must be >= 0")
        return value


def _app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)

    @app.post("/echo")
    def echo(body: _Body) -> _Body:
        return body

    return app


def test_value_error_in_validator_returns_422_envelope() -> None:
    response = TestClient(_app()).post("/echo", json={"depth_m": -5})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert "depth must be >= 0" in str(error["details"]["errors"])

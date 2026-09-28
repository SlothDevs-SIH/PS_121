import json
from pathlib import Path

from typer.testing import CliRunner

from app.cli import cli


def test_openapi_export_is_deterministic_and_complete(tmp_path: Path) -> None:
    runner = CliRunner()
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    assert runner.invoke(cli, ["openapi", "--out", str(a)]).exit_code == 0
    assert runner.invoke(cli, ["openapi", "--out", str(b)]).exit_code == 0
    assert a.read_bytes() == b.read_bytes()
    paths = json.loads(a.read_text())["paths"]
    assert "/api/v1/meta" in paths
    assert "/readyz" in paths

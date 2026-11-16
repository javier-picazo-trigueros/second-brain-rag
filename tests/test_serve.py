from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from secondbrain.cli import app

runner = CliRunner()


@pytest.fixture
def configured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Configuración mínima válida y un `uvicorn.run` falso que anota cómo se le llama."""
    monkeypatch.setenv("BRAIN_VAULT_PATH", str(tmp_path))
    calls: dict[str, Any] = {}

    def fake_run(target: str, **kwargs: Any) -> None:
        calls["target"] = target
        calls.update(kwargs)

    monkeypatch.setattr("uvicorn.run", fake_run)
    return calls


def test_serve_starts_uvicorn_on_loopback_with_the_app_factory(configured: dict[str, Any]) -> None:
    result = runner.invoke(app, ["serve"])
    assert result.exit_code == 0, result.output
    assert configured["target"] == "secondbrain.api.main:create_app_from_env"
    assert configured["factory"] is True
    assert (configured["host"], configured["port"]) == ("127.0.0.1", 8000)


def test_serve_options_override_the_settings(configured: dict[str, Any]) -> None:
    runner.invoke(app, ["serve", "--port", "9100"])
    assert configured["port"] == 9100


def test_serve_follows_the_environment(
    configured: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BRAIN_API_PORT", "8123")
    runner.invoke(app, ["serve"])
    assert configured["port"] == 8123


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.20", "mi-pc.local"])
def test_serve_refuses_to_listen_outside_the_machine_by_default(
    configured: dict[str, Any], host: str
) -> None:
    result = runner.invoke(app, ["serve", "--host", host])
    assert result.exit_code == 2
    assert "--allow-remote" in result.output
    assert "target" not in configured


def test_serve_can_be_forced_to_listen_remotely(configured: dict[str, Any]) -> None:
    result = runner.invoke(app, ["serve", "--host", "0.0.0.0", "--allow-remote"])
    assert result.exit_code == 0, result.output
    assert configured["host"] == "0.0.0.0"
    assert "sin autenticación" in result.output


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
def test_loopback_hosts_are_accepted(configured: dict[str, Any], host: str) -> None:
    assert runner.invoke(app, ["serve", "--host", host]).exit_code == 0


def test_serve_explains_a_missing_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BRAIN_VAULT_PATH", raising=False)
    result = runner.invoke(app, ["serve"])
    assert result.exit_code == 2 and "BRAIN_VAULT_PATH" in result.output

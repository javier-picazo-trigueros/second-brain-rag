from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from secondbrain.cli import app

runner = CliRunner()


def _report(recall: float, noise: int) -> dict[str, object]:
    return {
        "note": "",
        "rows": [],
        "summary": {
            "concrete": {
                "n": 2.0,
                "recall": recall,
                "precision": 0.5,
                "noise": noise,
                "top1_hit": 1.0,
            },
            "TOTAL": {
                "n": 2.0,
                "recall": recall,
                "precision": 0.5,
                "noise": noise,
                "top1_hit": 1.0,
            },
        },
    }


def test_compare_prints_before_after_table(tmp_path: Path) -> None:
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    a.write_text(json.dumps(_report(0.5, 3)), encoding="utf-8")
    b.write_text(json.dumps(_report(0.9, 1)), encoding="utf-8")
    result = runner.invoke(app, ["golden", "compare", str(a), str(b)])
    assert result.exit_code == 0, result.output
    assert "0,50 → 0,90" in result.output
    assert "TOTAL" in result.output


def test_golden_run_is_registered() -> None:
    result = runner.invoke(app, ["golden", "run", "--help"])
    assert result.exit_code == 0
    assert "answers" in result.output

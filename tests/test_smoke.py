from __future__ import annotations

import secondbrain


def test_package_exposes_version() -> None:
    assert secondbrain.__version__ == "0.1.0"

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURE_VAULT = Path(__file__).parent / "fixtures" / "vault"


@pytest.fixture(scope="session")
def vault() -> Path:
    """Vault de ejemplo. Los tests nunca tocan el vault real."""
    return FIXTURE_VAULT

from __future__ import annotations

import ssl

from secondbrain.net import use_system_trust_store


def test_use_system_trust_store_switches_ssl_to_the_os_store() -> None:
    use_system_trust_store()
    assert ssl.SSLContext.__module__.startswith("truststore")


def test_use_system_trust_store_is_idempotent() -> None:
    use_system_trust_store()
    use_system_trust_store()
    assert ssl.SSLContext.__module__.startswith("truststore")

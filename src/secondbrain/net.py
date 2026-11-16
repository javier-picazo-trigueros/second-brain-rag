from __future__ import annotations

import truststore


def use_system_trust_store() -> None:
    """Hace que Python valide TLS con el almacén de certificados del sistema operativo.

    Necesario cuando un antivirus o proxy corporativo inspecciona el tráfico HTTPS con su propia
    CA, que el SO ya confía pero el bundle de `certifi` no. Solo se usa en la descarga única del
    modelo BM25; el resto del tráfico del proyecto es local (HTTP a localhost).
    """
    truststore.inject_into_ssl()

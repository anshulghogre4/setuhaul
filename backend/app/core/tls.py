from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def use_system_trust_store() -> None:
    try:
        import truststore

        truststore.inject_into_ssl()
    except Exception as exc:  # noqa: BLE001
        logger.debug("System trust store injection skipped: %s", type(exc).__name__)

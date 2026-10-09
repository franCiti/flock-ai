"""Process start-up shared by every entry point."""

import truststore

# Imported before inject_into_ssl() runs: tls captures the standard library SSLContext, so
# internal connections keep trusting only the flock-ai CA (see tls.py).
from flock_agent.common import tls  # noqa: F401
from flock_agent.common.logging import configure_logging
from flock_agent.common.settings import Settings


def bootstrap() -> Settings:
    """Trust the OS certificate store, load settings and configure logging."""
    # The corporate network inspects HTTPS with its own root certificate, which is only
    # present in the OS store (see docs/notas-entorno.md).
    truststore.inject_into_ssl()
    settings = Settings()
    configure_logging(settings.log_level)
    return settings

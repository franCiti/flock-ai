"""Client TLS for Kafka and PostgreSQL: mutual TLS with the flock-ai CA (plan 7.1, D17)."""

import ssl
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from flock_agent.common.settings import Settings

# bootstrap() injects truststore into the ssl module so that connections to the internet trust
# the operating system store. Internal connections must trust *only* the flock-ai CA, so their
# contexts are built from the standard library class captured here, at import time, before
# any injection (bootstrap imports this module first).
_STDLIB_SSL_CONTEXT = ssl.SSLContext
# After the injection, the property setters of ssl.SSLContext recurse forever: they look up the
# module-level name "SSLContext", which truststore replaced. Properties are therefore set through
# the C base class (_ssl._SSLContext) descriptors, which do not depend on that name.
_C_SSL_CONTEXT: Any = _STDLIB_SSL_CONTEXT.__mro__[1]


class TlsConfigError(ValueError):
    """The TLS settings of the process are missing or incomplete."""


@dataclass(frozen=True)
class TlsFiles:
    cert_file: Path
    key_file: Path
    ca_file: Path

    @classmethod
    def from_settings(cls, settings: Settings) -> "TlsFiles":
        cert, key, ca = settings.tls_cert_file, settings.tls_key_file, settings.tls_ca_file
        if cert is None or key is None or ca is None:
            names = {"TLS_CERT_FILE": cert, "TLS_KEY_FILE": key, "TLS_CA_FILE": ca}
            missing = ", ".join(name for name, value in names.items() if value is None)
            msg = f"missing TLS settings: {missing}"
            raise TlsConfigError(msg)
        return cls(cert, key, ca)


def client_ssl_context(files: TlsFiles) -> ssl.SSLContext:
    """TLS 1.3 client context that presents our certificate and trusts only the flock-ai CA."""
    # PROTOCOL_TLS_CLIENT already verifies the certificate and the hostname.
    context = _STDLIB_SSL_CONTEXT(ssl.PROTOCOL_TLS_CLIENT)
    _C_SSL_CONTEXT.minimum_version.__set__(context, ssl.TLSVersion.TLSv1_3)
    context.load_verify_locations(cafile=files.ca_file)
    context.load_cert_chain(certfile=files.cert_file, keyfile=files.key_file)
    return context

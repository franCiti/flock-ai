import asyncio
import ssl
from collections.abc import Iterator
from pathlib import Path

import pytest
import trustme
import truststore

from flock_agent.common.settings import Settings
from flock_agent.common.tls import TlsConfigError, TlsFiles, client_ssl_context


@pytest.fixture
def ca() -> trustme.CA:
    return trustme.CA()


def write_client_files(ca: trustme.CA, directory: Path, name: str = "agent") -> TlsFiles:
    cert = ca.issue_cert(name, common_name=name)
    files = TlsFiles(
        cert_file=directory / f"{name}.crt",
        key_file=directory / f"{name}.key",
        ca_file=directory / "ca.crt",
    )
    cert.cert_chain_pems[0].write_to_path(str(files.cert_file))
    cert.private_key_pem.write_to_path(str(files.key_file))
    ca.cert_pem.write_to_path(str(files.ca_file))
    return files


@pytest.fixture
def client_files(ca: trustme.CA, tmp_path: Path) -> TlsFiles:
    return write_client_files(ca, tmp_path)


@pytest.fixture
def injected_truststore() -> Iterator[None]:
    truststore.inject_into_ssl()
    try:
        yield
    finally:
        truststore.extract_from_ssl()


def test_context_requires_tls13_and_verifies_the_server(client_files: TlsFiles) -> None:
    context = client_ssl_context(client_files)

    assert context.minimum_version == ssl.TLSVersion.TLSv1_3
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True


def test_context_trusts_only_the_flock_ca(client_files: TlsFiles) -> None:
    context = client_ssl_context(client_files)

    assert len(context.get_ca_certs()) == 1


@pytest.mark.usefixtures("injected_truststore")
def test_context_ignores_the_os_store_even_after_truststore_injection(
    client_files: TlsFiles,
) -> None:
    context = client_ssl_context(client_files)

    assert not isinstance(context, truststore.SSLContext)
    assert context.minimum_version == ssl.TLSVersion.TLSv1_3
    assert len(context.get_ca_certs()) == 1


def test_files_from_settings_reports_every_missing_value() -> None:
    settings = Settings(_env_file=None, tls_cert_file=Path("a.crt"))

    with pytest.raises(TlsConfigError, match="TLS_KEY_FILE, TLS_CA_FILE"):
        TlsFiles.from_settings(settings)


def mtls_server_context(server_ca: trustme.CA) -> ssl.SSLContext:
    """Server side of the test handshake: certificate signed by server_ca, client cert required.

    Must be built before truststore is injected: truststore's SSLContext is client-only.
    """
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_ca.issue_cert("localhost").configure_cert(context)
    server_ca.configure_trust(context)
    context.verify_mode = ssl.CERT_REQUIRED
    return context


async def handshake(server_context: ssl.SSLContext, client: ssl.SSLContext) -> str:
    """Run a local mTLS server, connect to it with `client` and return the client CN."""
    seen: list[str] = []

    async def on_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peercert")
        seen.append(dict(item[0] for item in peer["subject"]).get("commonName", ""))
        writer.close()

    server = await asyncio.start_server(on_client, "localhost", 0, ssl=server_context)
    port = server.sockets[0].getsockname()[1]
    try:
        _, writer = await asyncio.open_connection(
            "localhost", port, ssl=client, server_hostname="localhost"
        )
        await asyncio.sleep(0.1)
        writer.close()
    finally:
        server.close()
        await server.wait_closed()
    return seen[0]


async def test_mutual_tls_handshake_with_a_server_of_the_same_ca(
    ca: trustme.CA, client_files: TlsFiles
) -> None:
    server = mtls_server_context(ca)

    assert await handshake(server, client_ssl_context(client_files)) == "agent"


async def test_mutual_tls_handshake_works_after_truststore_injection(
    ca: trustme.CA, client_files: TlsFiles
) -> None:
    # What runs in production: bootstrap() injects truststore before any client connection.
    server = mtls_server_context(ca)
    truststore.inject_into_ssl()
    try:
        client = client_ssl_context(client_files)
    finally:
        truststore.extract_from_ssl()

    assert await handshake(server, client) == "agent"


async def test_rejects_a_server_signed_by_another_ca(client_files: TlsFiles) -> None:
    server = mtls_server_context(trustme.CA())

    with pytest.raises(ssl.SSLCertVerificationError):
        await handshake(server, client_ssl_context(client_files))

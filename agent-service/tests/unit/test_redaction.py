"""Secret masking before indexing (task T12, plan 5.6, spec HU15.4).

Every detector has cases that must be masked and look-alike cases that must not. All the values
are made up.
"""

from pathlib import Path

import pytest

from flock_agent.knowledge.redaction import DEFAULT_PLACEHOLDER, looks_like_secret, redact

EXAMPLES = Path(__file__).resolve().parents[3] / "examples" / "knowledge"
HIDDEN = DEFAULT_PLACEHOLDER


def pem(kind: str, body: str, *, end: bool = True) -> str:
    """A made-up PEM private key block. Built at run time so that this file holds no literal
    private key header (the detect-private-key hook of pre-commit would reject it)."""
    label = f"{kind} PRIVATE KEY".strip()
    block = f"-----BEGIN {label}-----\n{body}\n"
    return block + (f"-----END {label}-----" if end else "")


RSA_KEY = pem("RSA", "MIIEowIBAAKCAQEAexampleexample\nc2VjcmV0c2VjcmV0c2VjcmV0")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # Private keys
        (f"Clave del servidor:\n{RSA_KEY}\nFin.", f"Clave del servidor:\n{HIDDEN}\nFin."),
        (pem("OPENSSH", "b3BlbnNzaC1rZXktdjE="), HIDDEN),
        (pem("", "MIIEvQIBADANBgkqhkiG9w0BAQEFAASC", end=False), HIDDEN),  # cut off
        # Provider tokens
        ("AWS access key: AKIAIOSFODNN7EXAMPLE", f"AWS access key: {HIDDEN}"),
        ("token ghp_EXAMPLEtokenEXAMPLEtokenEXAMPLE1234 del job", f"token {HIDDEN} del job"),
        ("github_pat_11ABCDEFG0123456789_abcdefghijklmnop", HIDDEN),
        ("Bot: xoxb-1234567890-abcdefghijkl", f"Bot: {HIDDEN}"),
        ("OPENROUTER_API_KEY=sk-or-v1-0123456789abcdef0123456789", f"OPENROUTER_API_KEY={HIDDEN}"),
        ("clave sk-proj-AbCdEfGhIjKlMnOpQrStUvWx", f"clave {HIDDEN}"),
        (
            "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0"
            ".dozjgNryP4J3jVmNHl0w5N_XgL0n3I9P",
            f"Bearer {HIDDEN}",
        ),
        # Connection strings
        (
            "Server=dwh;Database=ventas;User Id=etl_user;Password=Dwh-Example-2026;",
            f"Server=dwh;Database=ventas;User Id=etl_user;Password={HIDDEN};",
        ),
        (
            "DefaultEndpointsProtocol=https;AccountName=demo;AccountKey=Zm9vYmFyYmF6cXV4==;",
            f"DefaultEndpointsProtocol=https;AccountName=demo;AccountKey={HIDDEN};",
        ),
        # Credentials in URLs
        (
            "postgresql://etl_user:Dwh-Example-2026@dwh.example.internal:5432/ventas",
            f"postgresql://etl_user:{HIDDEN}@dwh.example.internal:5432/ventas",
        ),
        (
            "https://admin:S3cr3t!x@git.example.com/repo",
            f"https://admin:{HIDDEN}@git.example.com/repo",
        ),
        # Key/value pairs
        ("3. password: Bastion-Example-2026!", f"3. password: {HIDDEN}"),
        ("contraseña = Juan2026#", f"contraseña = {HIDDEN}"),
        ("La Contraseña: Hola1234", f"La Contraseña: {HIDDEN}"),
        ("pwd=Ex4mple!", f"pwd={HIDDEN}"),
        ('{"api_key": "abc123def456ghi"}', f'{{"api_key": "{HIDDEN}"}}'),
        ("AWS secret key: wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", f"AWS secret key: {HIDDEN}"),
        ("aws_secret_access_key = wJalrXUtnFEMI/K7MDENG", f"aws_secret_access_key = {HIDDEN}"),
        ("client_secret: 'my secret 99'", "client_secret: 'my secret 99'"),  # has spaces: prose
        ("- **Clave**: Pr0d-Admin", f"- **Clave**: {HIDDEN}"),
        ("DB_PASSWORD=correcthorsebatterystaple", f"DB_PASSWORD={HIDDEN}"),  # long
    ],
)
def test_secrets_are_masked(text: str, expected: str) -> None:
    assert redact(text).text == expected


@pytest.mark.parametrize(
    "text",
    [
        # Look-alikes of every detector that are not secrets
        "La clave privada se guarda en el vault, nunca en el repositorio.",
        "-----BEGIN CERTIFICATE-----\nMIIDdzCCAl+gAwIBAgIE\n-----END CERTIFICATE-----",
        "-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqhkiG9w0BAQEFAAOC\n-----END PUBLIC KEY-----",
        "El ticket AKIA-123 sigue abierto.",
        "Tarea task-sk-review pendiente; usar el skill sk-learn.",
        "El header empieza con eyJ y es base64.",
        "Repositorio https://git.example.com/plataforma/deploy",
        "Enviar a mailto:soporte@example.com",
        "La contraseña: se pide al líder técnico.",
        "password: secreta",
        "Password: Solicitarla",
        "contraseña: ${DB_PASSWORD}",
        "password = ********",
        "password: <tu-contraseña>",
        "api_key: {{ vault.api_key }}",
        "Las credenciales del bastion se rotan cada 90 días.",
        "El token se genera desde la web: token: ver la wiki",
        "La clave del éxito es 2026",
        "Passwords must have 12 characters.",
    ],
)
def test_look_alikes_are_kept(text: str) -> None:
    result = redact(text)
    assert result.text == text
    assert result.masked == 0


def test_every_secret_is_counted() -> None:
    text = (
        "user: deploy\npassword: Bastion-Example-2026!\n"
        "AKIAIOSFODNN7EXAMPLE y ghp_EXAMPLEtokenEXAMPLEtokenEXAMPLE1234\n"
        "postgresql://u:Pass-1234@db/x\n"
    )
    assert redact(text).masked == 4


def test_the_placeholder_is_configurable() -> None:
    result = redact("password: Bastion-Example-2026!", placeholder="[REDACTED]")
    assert result.text == "password: [REDACTED]"
    assert result.masked == 1


def test_masking_twice_changes_nothing() -> None:
    once = redact("password: Bastion-Example-2026! AKIAIOSFODNN7EXAMPLE")
    twice = redact(once.text)
    assert twice.text == once.text
    assert twice.masked == 0


@pytest.mark.parametrize(
    ("value", "secret"),
    [
        ("Bastion-2026!", True),
        ("abc123", True),
        ("passWord", True),
        ("correcthorsebatterystaple", True),
        ("secreta", False),
        ("Solicitarla", False),
        ("abc", False),
        ("dos palabras1", False),
        ("${DB_PASSWORD}", False),
        ("********", False),
    ],
)
def test_looks_like_secret(value: str, secret: bool) -> None:
    assert looks_like_secret(value) is secret


@pytest.mark.parametrize(
    ("document", "secrets"),
    [
        (
            "juan-plataforma/procedimientos/acceso-bastion.md",
            [
                "Bastion-Example-2026!",
                "AKIAIOSFODNN7EXAMPLE",
                "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                "ghp_EXAMPLEtokenEXAMPLEtokenEXAMPLE1234",
            ],
        ),
        ("ana-datos/pipelines/conexion-warehouse.md", ["Dwh-Example-2026"]),
    ],
)
def test_the_example_documents_with_secrets(document: str, secrets: list[str]) -> None:
    text = (EXAMPLES / document).read_text(encoding="utf-8")
    result = redact(text)
    for secret in secrets:
        assert secret in text
        assert secret not in result.text
    # What is not a secret stays: the facts the bot must still answer.
    assert "se rota" in result.text
    assert result.masked >= len(secrets)

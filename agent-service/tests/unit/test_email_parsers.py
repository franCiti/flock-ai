"""Email files and their attachments (task T14, plan 5.3, spec HU4.6).

Samples in tests/fixtures/files/ (built by build_fixtures.py). The .msg tests are complete but
skipped until `sample.msg`, saved from Outlook, is added: extract-msg can read that format but
not create it (plan 8.1). The sample must be an email with subject "Accesos para el nuevo
ingreso", a text body, a `checklist.txt` attachment and an attached email.
"""

from email.message import EmailMessage
from pathlib import Path

import pytest

from flock_agent.ingestion.connectors.files.parsers import ParsedFile, SkipFileError, parse_file

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "files"
MAX_BYTES = 20 * 1024 * 1024
MSG_SAMPLE = FIXTURES / "sample.msg"

needs_msg_sample = pytest.mark.skipif(
    not MSG_SAMPLE.exists(),
    reason="no Outlook sample yet: add tests/fixtures/files/sample.msg saved from Outlook (T14)",
)


def parse(name: str) -> ParsedFile:
    return parse_file(name, (FIXTURES / name).read_bytes(), max_bytes=MAX_BYTES)


# --- .eml -------------------------------------------------------------------------------------


def test_an_email_has_its_header_fields_and_body() -> None:
    parsed = parse("mail.eml")
    assert parsed.is_email
    assert parsed.title == "Accesos para el nuevo ingreso"
    assert parsed.content_format == "plain"
    assert parsed.text.startswith(
        "Subject: Accesos para el nuevo ingreso\n"
        "From: Ana Gómez <ana.gomez@example.com>\n"
        "To: Juan Pérez <juan.perez@example.com>\n"
        "Cc: Equipo Plataforma <plataforma@example.com>\n"
        "Date: Mon, 16 Feb 2026 10:12:00 -0300\n"
    )
    assert "Te paso el checklist de accesos y el manual." in parsed.text


def test_attachments_are_parsed_like_any_other_file() -> None:
    parsed = parse("mail.eml")
    attachments = {item.name: item.parsed for item in parsed.attachments}
    assert list(attachments) == [
        "checklist.txt",
        "manual.docx",
        "checklist (2).txt",  # same name, another attachment
        "Ventana de mantenimiento.eml",
    ]
    assert attachments["checklist.txt"].text == "1. VPN\n2. Jenkins\n3. Grafana"
    assert attachments["manual.docx"].content_format == "markdown"
    assert "## VPN" in attachments["manual.docx"].text
    assert attachments["checklist (2).txt"].text == "Version 2 del checklist."


def test_unsupported_attachments_are_reported() -> None:
    parsed = parse("mail.eml")
    assert [(item.name, item.reason) for item in parsed.skipped_attachments] == [
        ("logo.png", "binary file")
    ]
    assert "Attachments: checklist.txt, manual.docx, logo.png" in parsed.text


def test_an_attached_email_is_parsed_without_its_own_attachments() -> None:
    attached = {item.name: item.parsed for item in parse("mail.eml").attachments}[
        "Ventana de mantenimiento.eml"
    ]
    assert attached.is_email
    assert "El mantenimiento del cluster es el sábado de 2 a 4." in attached.text
    assert "Attachments: detalle.txt" in attached.text  # listed...
    assert attached.attachments == ()  # ...but not followed (one level)
    assert "no se indexa" not in attached.text


def test_an_html_email_becomes_text() -> None:
    parsed = parse("mail-html.eml")
    assert "# Alerta" in parsed.text
    assert "El disco de db-01 está al 90 %." in parsed.text
    assert "<b>" not in parsed.text
    assert parsed.attachments == ()


def test_an_email_without_subject_or_body_still_has_its_header() -> None:
    message = EmailMessage()
    message["From"] = "ana@example.com"
    parsed = parse_file("vacio.eml", bytes(message), max_bytes=MAX_BYTES)
    assert parsed.text == "From: ana@example.com"
    assert parsed.title is None


def test_an_attached_email_can_be_parsed_alone() -> None:
    parsed = parse_file(
        "reenvio.eml",
        (FIXTURES / "mail.eml").read_bytes(),
        max_bytes=MAX_BYTES,
        follow_attachments=False,
    )
    assert parsed.attachments == ()
    assert parsed.skipped_attachments == ()


def test_emails_over_the_size_limit_are_skipped() -> None:
    with pytest.raises(SkipFileError, match="larger than"):
        parse_file("big.eml", b"x" * 2048, max_bytes=1024)


# --- .msg -------------------------------------------------------------------------------------


def test_a_broken_outlook_file_is_skipped() -> None:
    with pytest.raises(SkipFileError, match="unreadable Outlook message"):
        parse_file("roto.msg", b"not an Outlook file", max_bytes=MAX_BYTES)


@needs_msg_sample
def test_an_outlook_email_has_its_header_fields_and_body() -> None:
    parsed = parse("sample.msg")
    assert parsed.is_email
    assert parsed.title == "Accesos para el nuevo ingreso"
    assert parsed.text.startswith("Subject: Accesos para el nuevo ingreso\nFrom: ")
    assert "\nTo: " in parsed.text
    assert "\nDate: " in parsed.text


@needs_msg_sample
def test_outlook_attachments_are_parsed() -> None:
    attachments = {item.name: item.parsed for item in parse("sample.msg").attachments}
    assert "checklist.txt" in attachments
    assert attachments["checklist.txt"].text.strip()


@needs_msg_sample
def test_an_email_attached_to_an_outlook_email_is_not_followed() -> None:
    attached = [item.parsed for item in parse("sample.msg").attachments if item.parsed.is_email]
    assert attached
    assert all(item.attachments == () for item in attached)

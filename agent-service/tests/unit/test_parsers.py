"""Text extraction from files (task T13, plan section 5.3). Samples in tests/fixtures/files/."""

from pathlib import Path

import pytest

from flock_agent.ingestion.connectors.files.parsers import ParsedFile, SkipFileError, parse_file

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "files"
MAX_BYTES = 20 * 1024 * 1024


def parse(name: str) -> ParsedFile:
    return parse_file(name, (FIXTURES / name).read_bytes(), max_bytes=MAX_BYTES)


def skip_reason(name: str, data: bytes | None = None, max_bytes: int = MAX_BYTES) -> str:
    content = (FIXTURES / name).read_bytes() if data is None else data
    with pytest.raises(SkipFileError) as error:
        parse_file(name, content, max_bytes=max_bytes)
    return error.value.reason


# --- Text, detected by content --------------------------------------------------------------


def test_markdown_keeps_its_headings() -> None:
    parsed = parse("sample.md")

    assert parsed.content_format == "markdown"
    assert parsed.text.startswith("# Deploy a producción")
    assert "## Rollback" in parsed.text


@pytest.mark.parametrize(
    ("name", "expected"), [("data.csv", "Líder técnico"), ("config.json", "mié")]
)
def test_text_formats_are_plain_text(name: str, expected: str) -> None:
    parsed = parse(name)

    assert parsed.content_format == "plain"
    assert expected in parsed.text


def test_any_extension_is_text_if_the_content_is() -> None:
    assert "Restart-Service" in parse("script.ps1.txt").text


def test_other_encodings_are_detected() -> None:
    parsed = parse("notes-latin1.txt")

    assert "Configuración del servidor" in parsed.text
    assert "contraseña" in parsed.text


def test_utf16_files_with_bom_are_text_not_binary() -> None:
    data = "Instalación del agente\r\nPaso 1: descargar.".encode("utf-16")  # Notepad "Unicode"

    assert parse_file("notes.txt", data, max_bytes=1024).text == (
        "Instalación del agente\nPaso 1: descargar."
    )


def test_windows_line_endings_and_bom_are_normalized() -> None:
    parsed = parse_file("notes.txt", "﻿uno\r\ndos\r\n\r\n\r\n\r\ntres".encode(), max_bytes=1024)

    assert parsed.text == "uno\ndos\n\ntres"


# --- HTML and XML ---------------------------------------------------------------------------


def test_html_becomes_markdown_without_scripts_or_styles() -> None:
    parsed = parse("page.html")

    assert parsed.title == "Guía de onboarding"
    assert parsed.content_format == "markdown"
    assert parsed.text == (
        "# Onboarding\n\n"
        "La primera semana cada persona nueva tiene un buddy .\n\n"
        "## Accesos\n\n"
        "- VPN\n\n"
        "- Jira y Confluence"
    )


def test_xml_keeps_only_the_text() -> None:
    parsed = parse("feed.xml")

    assert parsed.text == "Verificar el pipeline\nCrear el tag"
    assert "<step" not in parsed.text


# --- PDF ------------------------------------------------------------------------------------


def test_pdf_text_and_title_are_extracted() -> None:
    parsed = parse("sample.pdf")

    assert parsed.title == "Procedimiento de deploy"
    assert "lunes a jueves" in parsed.text
    assert "rollback-prod" in parsed.text


def test_a_pdf_without_text_is_skipped_as_scanned() -> None:
    assert skip_reason("scanned.pdf") == "no extractable text (scanned PDF?)"


def test_a_broken_pdf_is_skipped() -> None:
    assert skip_reason("broken.pdf", b"%PDF-1.7 this is not a real pdf").startswith(
        "unreadable PDF"
    )


# --- Word -----------------------------------------------------------------------------------


def test_word_headings_lists_and_tables_become_markdown() -> None:
    parsed = parse("sample.docx")

    assert parsed.title == "Manual de accesos"
    assert parsed.content_format == "markdown"
    assert parsed.text == (
        "# Accesos del equipo\n\n"
        "Cómo pedir cada acceso.\n\n"
        "## VPN\n\n"
        "Se pide con un ticket en el proyecto ACCESOS.\n\n"
        "### Requisitos\n\n"
        "- Aprobación del manager directo.\n\n"
        "- Notebook de la empresa.\n\n"
        "Sistema | Aprobador\nVPN | Manager"
    )


def test_a_broken_word_file_is_skipped() -> None:
    assert skip_reason("broken.docx", b"PK not really a zip").startswith("unreadable Word file")


# --- Skipped files --------------------------------------------------------------------------


def test_binary_files_are_skipped() -> None:
    assert skip_reason("image.png") == "binary file"


def test_empty_files_are_skipped() -> None:
    assert skip_reason("empty.txt") == "no extractable text"


def test_files_over_the_size_limit_are_skipped_before_parsing() -> None:
    reason = skip_reason("huge.txt", b"x" * (2 * 1024 * 1024 + 1), max_bytes=2 * 1024 * 1024)

    assert reason == "larger than the 2 MB limit"


@pytest.mark.parametrize("name", ["mail.eml", "mail.msg"])
def test_email_files_wait_for_their_parser(name: str) -> None:
    assert skip_reason(name, b"From: ana@example.com") == "email files are not supported yet"

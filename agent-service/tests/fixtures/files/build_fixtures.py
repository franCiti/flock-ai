"""Builds the binary sample files of this folder (PDF and Word) and the non-UTF-8 text sample.

Run from agent-service/:  uv run python tests/fixtures/files/build_fixtures.py
The generated files are committed; this script documents exactly what they contain.
"""

from pathlib import Path

import docx
from fpdf import FPDF

HERE = Path(__file__).resolve().parent


def build_pdf() -> None:
    pdf = FPDF()
    pdf.set_title("Procedimiento de deploy")
    pdf.set_font("Helvetica", size=12)
    pages = [
        "Deploy a produccion. Los deploys se hacen de lunes a jueves entre las 10 y las 16.",
        "Rollback: si la tasa de errores supera el 2 por ciento, ejecutar el job rollback-prod.",
    ]
    for text in pages:
        pdf.add_page()
        pdf.multi_cell(0, 8, text)
    pdf.output(str(HERE / "sample.pdf"))


def build_scanned_pdf() -> None:
    """A page with only drawings and no text layer, like a scanned document."""
    pdf = FPDF()
    pdf.add_page()
    for i in range(10):
        pdf.rect(20, 20 + i * 15, 170, 8, style="F")
    pdf.output(str(HERE / "scanned.pdf"))


def build_docx() -> None:
    document = docx.Document()
    document.core_properties.title = "Manual de accesos"
    document.add_paragraph("Accesos del equipo", style="Title")
    document.add_paragraph("Cómo pedir cada acceso.")
    document.add_heading("VPN", level=1)
    document.add_paragraph("Se pide con un ticket en el proyecto ACCESOS.")
    document.add_heading("Requisitos", level=2)
    document.add_paragraph("Aprobación del manager directo.", style="List Bullet")
    document.add_paragraph("Notebook de la empresa.", style="List Bullet")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Sistema"
    table.cell(0, 1).text = "Aprobador"
    table.cell(1, 0).text = "VPN"
    table.cell(1, 1).text = "Manager"
    document.save(str(HERE / "sample.docx"))


def build_latin1_text() -> None:
    text = "Configuración del servidor\n\nLa contraseña se renueva cada año en diciembre.\n"
    (HERE / "notes-latin1.txt").write_bytes(text.encode("latin-1"))


if __name__ == "__main__":
    build_pdf()
    build_scanned_pdf()
    build_docx()
    build_latin1_text()

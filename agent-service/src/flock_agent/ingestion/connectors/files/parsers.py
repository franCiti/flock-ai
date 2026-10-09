"""Text extraction from files (plan section 5.3, spec HU4.6 and HU4.7).

Parsers do not know where a file comes from (local folder, SharePoint): they get its name and
bytes. The result says which chunker fits it: "markdown" keeps the headings, "plain" does not.
"""

import io
import re
import warnings
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal

import docx
from bs4 import BeautifulSoup, Tag, XMLParsedAsHTMLWarning
from charset_normalizer import from_bytes
from docx.document import Document as DocxDocument
from docx.table import Table
from docx.text.paragraph import Paragraph
from pypdf import PdfReader
from pypdf.errors import PdfReadError

ContentFormat = Literal["markdown", "plain"]

# Bump when parsing changes: connectors re-read every file when their cursor has another version.
PARSERS_VERSION = 1

_SNIFF_BYTES = 64 * 1024
_MIN_TEXT_CHARS_PER_PDF_PAGE = 20
_MARKDOWN_SUFFIXES = {".md", ".markdown"}
_HTML_SUFFIXES = {".html", ".htm", ".xhtml"}
_XML_SUFFIXES = {".xml"}
_EMAIL_SUFFIXES = {".eml", ".msg"}


@dataclass(frozen=True)
class ParsedFile:
    text: str
    content_format: ContentFormat
    title: str | None = None  # from the document itself (HTML <title>, Word properties)


class SkipFileError(Exception):
    """The file is not indexed; `reason` goes to the update summary (spec HU4.5)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def parse_file(name: str, data: bytes, *, max_bytes: int) -> ParsedFile:
    """Extract the text of a file, or raise SkipFileError saying why it is not indexed."""
    if len(data) > max_bytes:
        raise SkipFileError(f"larger than the {max_bytes // (1024 * 1024)} MB limit")
    suffix = PurePosixPath(name).suffix.lower()
    if suffix == ".pdf":
        parsed = _parse_pdf(data)
    elif suffix == ".docx":
        parsed = _parse_docx(data)
    elif suffix in _EMAIL_SUFFIXES:
        raise SkipFileError("email files are not supported yet")  # T14
    elif suffix in _HTML_SUFFIXES:
        parsed = _parse_html(_decode_text(data))
    elif suffix in _XML_SUFFIXES:
        parsed = ParsedFile(_markup_text(_decode_text(data)), "plain")
    else:
        # Any other file counts as text if its content is text, whatever its extension (HU4.6).
        text = _decode_text(data)
        parsed = ParsedFile(text, "markdown" if suffix in _MARKDOWN_SUFFIXES else "plain")
    if not parsed.text.strip():
        raise SkipFileError("no extractable text")
    return parsed


# --- Plain text -----------------------------------------------------------------------------


# The knowledge base is mostly Spanish and English: when a file is not UTF-8, Western encodings
# are tried first. Unrestricted detection confuses them with similar ones on short texts
# (e.g. latin-1 "año" read as cp1250 "ańo").
_WESTERN_ENCODINGS = ["cp1252", "latin_1", "iso8859_15"]
_UTF16_BOMS = (b"\xff\xfe", b"\xfe\xff")


def _decode_text(data: bytes) -> str:
    """Decode bytes that are text in any common encoding; binary content is rejected."""
    if not data:
        return ""
    if data.startswith(_UTF16_BOMS):  # e.g. Windows Notepad "Unicode"
        try:
            return _normalize(data.decode("utf-16"))
        except UnicodeDecodeError as error:
            raise SkipFileError("binary file") from error
    if b"\x00" in data[:_SNIFF_BYTES]:
        raise SkipFileError("binary file")
    try:
        return _normalize(data.decode("utf-8"))
    except UnicodeDecodeError:
        pass
    match = from_bytes(data, cp_isolation=_WESTERN_ENCODINGS).best() or from_bytes(data).best()
    if match is None:
        raise SkipFileError("binary file")
    return _normalize(str(match))


def _normalize(text: str) -> str:
    text = text.replace("﻿", "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


# --- HTML and XML ---------------------------------------------------------------------------

_BLOCKS = ("p", "li", "pre", "blockquote", "td", "th", "dt", "dd", "caption")


def _parse_html(html: str) -> ParsedFile:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else None
    for element in soup(["script", "style", "noscript", "template", "head"]):
        element.decompose()
    body = soup.body or soup
    lines: list[str] = []
    for element in body.find_all(["h1", "h2", "h3", "h4", "h5", "h6", *_BLOCKS]):
        if not isinstance(element, Tag) or element.find_parent(_BLOCKS):
            continue  # nested blocks are part of their parent's text
        text = " ".join(element.get_text(" ", strip=True).split())
        if not text:
            continue
        if element.name and element.name[0] == "h" and element.name[1:].isdigit():
            lines.append(f"{'#' * int(element.name[1:])} {text}")
        else:
            lines.append(f"- {text}" if element.name == "li" else text)
    text = "\n\n".join(lines) if lines else _markup_text(str(body))
    return ParsedFile(_normalize(text), "markdown", title or None)


def _markup_text(markup: str) -> str:
    """Text of HTML/XML without tags, one line per text node.

    XML also goes through Python's HTML parser on purpose: only the text is needed, it needs no
    extra dependency and it never resolves external entities (files may come from third parties).
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
        soup = BeautifulSoup(markup, "html.parser")
    return _normalize(soup.get_text("\n", strip=True))


# --- PDF ------------------------------------------------------------------------------------


def _parse_pdf(data: bytes) -> ParsedFile:
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise SkipFileError("encrypted PDF")
        pages = [page.extract_text() or "" for page in reader.pages]
    except PdfReadError as error:
        raise SkipFileError(f"unreadable PDF ({error})") from error
    text = "\n\n".join(_normalize(page) for page in pages if page.strip())
    if len(text.strip()) < _MIN_TEXT_CHARS_PER_PDF_PAGE * max(len(pages), 1):
        raise SkipFileError("no extractable text (scanned PDF?)")
    title = reader.metadata.title if reader.metadata else None
    return ParsedFile(text, "plain", title or None)


# --- Word -----------------------------------------------------------------------------------

_HEADING_STYLE = re.compile(r"^Heading (\d)$")


def _parse_docx(data: bytes) -> ParsedFile:
    try:
        document: DocxDocument = docx.Document(io.BytesIO(data))
    except Exception as error:  # python-docx raises several unrelated types for broken files
        raise SkipFileError(f"unreadable Word file ({type(error).__name__})") from error
    blocks: list[str] = []
    for block in document.iter_inner_content():
        text = _docx_paragraph(block) if isinstance(block, Paragraph) else _docx_table(block)
        if text:
            blocks.append(text)
    title = document.core_properties.title or None
    return ParsedFile(_normalize("\n\n".join(blocks)), "markdown", title)


def _docx_paragraph(paragraph: Paragraph) -> str:
    text = paragraph.text.strip()
    if not text:
        return ""
    style = paragraph.style.name if paragraph.style is not None else ""
    if style == "Title":
        return f"# {text}"
    heading = _HEADING_STYLE.match(style or "")
    if heading:
        # Word's "Heading 1" sits below the document title: shift one level down.
        return f"{'#' * min(int(heading.group(1)) + 1, 6)} {text}"
    if style and style.startswith("List"):
        return f"- {text}"
    return text


def _docx_table(table: Table) -> str:
    rows = []
    for row in table.rows:
        cells = [" ".join(cell.text.split()) for cell in row.cells]
        if any(cells):
            rows.append(" | ".join(cells))
    return "\n".join(rows)

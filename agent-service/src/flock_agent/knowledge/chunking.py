"""Splits documents into the fragments that are indexed and searched (plan section 5.5).

- chunk_markdown: Markdown, Word, HTML, Confluence pages. By headings; long sections by paragraph.
- chunk_plain: plain text, PDF, emails. The whole text if it fits; otherwise by paragraph.
- chunk_issue: Jira issues. Header + description together, then the comments grouped in order.

Every fragment starts with its context, "[title > section]", which improves the search and lets
answers cite the section. Consecutive fragments of the same section overlap a little, so an idea
cut at a boundary is still complete in one of them.
"""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from itertools import pairwise

MAX_CHARS = 1200
OVERLAP_CHARS = 150

_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t#]*$")
_FENCE = re.compile(r"^[ \t]*(```|~~~)")
_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")


@dataclass(frozen=True)
class ChunkDraft:
    ordinal: int
    heading_path: str  # "Deploy > Rollback"; "" outside any section
    content: str  # "[title > section]" line, then the text


@dataclass(frozen=True)
class IssueComment:
    author: str
    created: str
    body: str


@dataclass(frozen=True)
class _Section:
    heading_path: str
    body: str


# --- Public API -----------------------------------------------------------------------------


def chunk_markdown(
    text: str, *, title: str, max_chars: int = MAX_CHARS, overlap: int = OVERLAP_CHARS
) -> list[ChunkDraft]:
    """Markdown (and formats converted to it): one or more fragments per section."""
    return _number(
        title,
        (
            (section.heading_path, body)
            for section in _markdown_sections(text)
            for body in _split_body(section.body, max_chars, overlap)
        ),
    )


def chunk_plain(
    text: str, *, title: str, max_chars: int = MAX_CHARS, overlap: int = OVERLAP_CHARS
) -> list[ChunkDraft]:
    """Plain text, PDF and emails: the whole text if it fits, otherwise by paragraph."""
    return _number(title, (("", body) for body in _split_body(text, max_chars, overlap)))


def chunk_issue(
    *,
    title: str,
    header: str,
    description: str,
    comments: Sequence[IssueComment],
    max_chars: int = MAX_CHARS,
    overlap: int = OVERLAP_CHARS,
) -> list[ChunkDraft]:
    """Jira issue: header + description together, then the comments grouped in order.

    Comments by other people are knowledge too (spec HU12.7): they often contain the solution.
    """
    opening = "\n\n".join(part for part in (header.strip(), description.strip()) if part)
    rendered = [
        f"{comment.author} ({comment.created}): {comment.body.strip()}"
        for comment in comments
        if comment.body.strip()
    ]
    comments_text = "\n\n".join(rendered)
    return _number(
        title,
        [
            *(("", body) for body in _split_body(opening, max_chars, overlap)),
            *(("Comments", body) for body in _split_body(comments_text, max_chars, overlap)),
        ],
    )


# --- Sections -------------------------------------------------------------------------------


def _markdown_sections(text: str) -> list[_Section]:
    """Split by ATX headings (#..######), ignoring '#' lines inside fenced code blocks."""
    sections: list[_Section] = []
    stack: list[tuple[int, str]] = []
    lines: list[str] = []
    in_fence = False

    def flush() -> None:
        body = "\n".join(lines).strip()
        if body:
            sections.append(_Section(" > ".join(title for _, title in stack), body))
        lines.clear()

    for line in text.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
        heading = None if in_fence else _HEADING.match(line)
        if heading is None:
            lines.append(line)
            continue
        flush()
        level = len(heading.group(1))
        stack = [(lvl, title) for lvl, title in stack if lvl < level]
        stack.append((level, heading.group(2).strip()))
    flush()
    return sections


# --- Splitting a body -----------------------------------------------------------------------


def _paragraphs(text: str) -> list[str]:
    """Blank-line separated paragraphs; a fenced code block is kept as one unit."""
    paragraphs: list[str] = []
    current: list[str] = []
    in_fence = False
    for line in text.strip().splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
        if not line.strip() and not in_fence:
            if current:
                paragraphs.append("\n".join(current).strip())
                current = []
            continue
        current.append(line.rstrip())
    if current:
        paragraphs.append("\n".join(current).strip())
    return [paragraph for paragraph in paragraphs if paragraph]


def _pieces(paragraph: str, limit: int) -> list[str]:
    """Split a paragraph longer than `limit`: by sentence, then by word, then by character."""
    if len(paragraph) <= limit:
        return [paragraph]
    for separator in (_SENTENCE_END, re.compile(r"\s+")):
        parts = [part for part in separator.split(paragraph) if part]
        if len(parts) > 1:
            return [piece for part in _pack(parts, limit, " ") for piece in _pieces(part, limit)]
    return [paragraph[i : i + limit] for i in range(0, len(paragraph), limit)]


def _pack(parts: Sequence[str], limit: int, joiner: str) -> list[str]:
    """Greedily join consecutive parts while the result fits in `limit`."""
    packed: list[str] = []
    current = ""
    for part in parts:
        candidate = f"{current}{joiner}{part}" if current else part
        if current and len(candidate) > limit:
            packed.append(current)
            current = part
        else:
            current = candidate
    if current:
        packed.append(current)
    return packed


def _tail(text: str, size: int) -> str:
    """The last ~`size` characters of `text`, starting at a word boundary."""
    if len(text) <= size:
        return text
    tail = text[-size:]
    space = tail.find(" ")
    return tail[space + 1 :] if 0 <= space < len(tail) - 1 else tail


def _split_body(text: str, max_chars: int, overlap: int) -> list[str]:
    """Fragments of at most `max_chars` (overlap included), in order."""
    units = [piece for paragraph in _paragraphs(text) for piece in _pieces(paragraph, max_chars)]
    packed = _pack(units, max_chars, "\n\n")
    if overlap <= 0 or len(packed) <= 1:
        return packed
    result = [packed[0]]
    for previous, body in pairwise(packed):
        room = max_chars - len(body) - 2
        carried = _tail(previous, min(overlap, room)) if room > 0 else ""
        result.append(f"{carried}\n\n{body}" if carried else body)
    return result


# --- Numbering and context ------------------------------------------------------------------


def _context(title: str, heading_path: str) -> str:
    return f"[{title} > {heading_path}]" if heading_path else f"[{title}]"


def _number(title: str, bodies: Iterable[tuple[str, str]]) -> list[ChunkDraft]:
    """Number the (heading_path, body) pairs and put the context line in front of each body."""
    return [
        ChunkDraft(ordinal, heading_path, f"{_context(title, heading_path)}\n{body}")
        for ordinal, (heading_path, body) in enumerate(bodies)
    ]

"""Splitting documents into fragments (task T11, plan section 5.5)."""

import re

from flock_agent.knowledge.chunking import (
    ChunkDraft,
    IssueComment,
    chunk_issue,
    chunk_markdown,
    chunk_plain,
)


def bodies(chunks: list[ChunkDraft]) -> list[str]:
    """Text of each chunk without its context line."""
    return [chunk.content.split("\n", 1)[1] for chunk in chunks]


def words(text: str) -> set[str]:
    return set(re.findall(r"\w+", text))


def paragraph(label: str, size: int) -> str:
    """A paragraph of about `size` characters made of distinct words."""
    text, i = "", 0
    while len(text) < size:
        text += f"{label}{i} "
        i += 1
    return text.strip()


# --- Context line and numbering -------------------------------------------------------------


def test_each_chunk_starts_with_its_context() -> None:
    chunks = chunk_markdown("Intro.\n\n# Deploy\nPasos.\n\n## Rollback\nRevertir.", title="Manual")

    assert [chunk.content.split("\n", 1)[0] for chunk in chunks] == [
        "[Manual]",
        "[Manual > Deploy]",
        "[Manual > Deploy > Rollback]",
    ]
    assert [chunk.ordinal for chunk in chunks] == [0, 1, 2]


def test_empty_documents_have_no_chunks() -> None:
    assert chunk_markdown("  \n\n ", title="t") == []
    assert chunk_plain("", title="t") == []


# --- Markdown: by headings ------------------------------------------------------------------


def test_heading_paths_follow_the_heading_levels() -> None:
    text = "# A\na\n## B\nb\n### C\nc\n## D\nd\n# E\ne"

    chunks = chunk_markdown(text, title="t")

    assert [chunk.heading_path for chunk in chunks] == ["A", "A > B", "A > B > C", "A > D", "E"]
    assert bodies(chunks) == ["a", "b", "c", "d", "e"]


def test_headings_without_text_produce_no_chunk() -> None:
    chunks = chunk_markdown("# Empty\n# Full\ntext", title="t")

    assert [chunk.heading_path for chunk in chunks] == ["Full"]


def test_hash_lines_inside_code_blocks_are_not_headings() -> None:
    text = "# Script\n```bash\n# install dependencies\nnpm ci\n```"

    chunks = chunk_markdown(text, title="t")

    assert len(chunks) == 1
    assert chunks[0].heading_path == "Script"
    assert "# install dependencies" in chunks[0].content


def test_long_sections_are_split_by_paragraph_within_the_limit() -> None:
    text = "# Long\n" + "\n\n".join(paragraph(f"p{n}w", 500) for n in range(6))

    chunks = chunk_markdown(text, title="t", max_chars=1200, overlap=150)

    assert len(chunks) > 1
    assert all(chunk.heading_path == "Long" for chunk in chunks)
    assert all(len(body) <= 1200 for body in bodies(chunks))


def test_consecutive_chunks_of_a_section_overlap() -> None:
    text = "\n\n".join(paragraph(f"p{n}w", 500) for n in range(6))

    first, second, *_ = bodies(chunk_plain(text, title="t", max_chars=1200, overlap=150))

    carried = second.split("\n\n", 1)[0]
    assert first.endswith(carried)
    assert 0 < len(carried) <= 150


def test_there_is_no_overlap_between_sections() -> None:
    long_a = "\n\n".join(paragraph(f"a{n}w", 500) for n in range(4))  # several chunks in A
    text = f"# A\n{long_a}\n# B\n" + paragraph("bw", 300)

    chunks = chunk_markdown(text, title="t", overlap=150)

    a_chunks = [
        body
        for chunk, body in zip(chunks, bodies(chunks), strict=True)
        if chunk.heading_path == "A"
    ]
    (b_chunk,) = [
        body
        for chunk, body in zip(chunks, bodies(chunks), strict=True)
        if chunk.heading_path == "B"
    ]
    assert len(a_chunks) > 1
    assert words(a_chunks[0]) & words(a_chunks[1])  # inside A there is overlap...
    assert not words(b_chunk) & words(long_a)  # ...but nothing of A is carried into B


def test_no_text_is_lost() -> None:
    text = "# Intro\n" + "\n\n".join(paragraph(f"s{n}w", 700) for n in range(5))

    chunks = chunk_markdown(text, title="t", max_chars=1200)

    assert words(text) - {"Intro"} <= words(" ".join(bodies(chunks)))


def test_a_huge_paragraph_is_split_by_sentence() -> None:
    sentences = [f"Oración número {i} del procedimiento de despliegue." for i in range(80)]
    text = " ".join(sentences)

    chunks = chunk_plain(text, title="t", max_chars=400, overlap=0)

    assert len(chunks) > 1
    assert all(len(body) <= 400 for body in bodies(chunks))
    assert all(body.endswith(".") for body in bodies(chunks))


def test_text_without_spaces_is_split_hard() -> None:
    chunks = chunk_plain("x" * 1000, title="t", max_chars=300, overlap=0)

    assert [len(body) for body in bodies(chunks)] == [300, 300, 300, 100]


def test_non_ascii_text_is_preserved() -> None:
    chunks = chunk_plain("¿Cómo pido acceso a la VPN? Con un ticket — año 2026.", title="Ñandú")

    assert chunks[0].content == "[Ñandú]\n¿Cómo pido acceso a la VPN? Con un ticket — año 2026."


# --- Plain text and emails ------------------------------------------------------------------


def test_a_short_email_is_a_single_chunk() -> None:
    email = "De: ana@example.com\nPara: juan@example.com\nAsunto: VPN\n\nHola Juan,\n\nYa está."

    chunks = chunk_plain(email, title="VPN")

    assert len(chunks) == 1
    assert chunks[0].heading_path == ""
    assert "Asunto: VPN" in chunks[0].content
    assert "Ya está." in chunks[0].content


def test_a_long_email_is_split_by_paragraph() -> None:
    email = "Asunto: Migración\n\n" + "\n\n".join(paragraph(f"m{n}w", 400) for n in range(5))

    chunks = chunk_plain(email, title="Migración", max_chars=1200)

    assert len(chunks) > 1
    assert all(chunk.content.startswith("[Migración]\n") for chunk in chunks)


# --- Jira issues ----------------------------------------------------------------------------


def test_issue_header_and_description_go_together() -> None:
    chunks = chunk_issue(
        title="PLAT-12: Deploy falla",
        header="PLAT-12 · Estado: Resuelto · Asignado: Juan",
        description="El deploy falla con timeout.",
        comments=[],
    )

    assert len(chunks) == 1
    assert chunks[0].content == (
        "[PLAT-12: Deploy falla]\n"
        "PLAT-12 · Estado: Resuelto · Asignado: Juan\n\nEl deploy falla con timeout."
    )


def test_issue_comments_are_grouped_in_order_with_their_author() -> None:
    comments = [
        IssueComment("Ana", "2026-10-01", "¿Probaste aumentar el timeout?"),
        IssueComment("Juan", "2026-10-02", "Sí, con 300 s anduvo."),
        IssueComment("Ana", "2026-10-03", "   "),  # empty: ignored
    ]

    chunks = chunk_issue(title="PLAT-12", header="PLAT-12", description="Falla.", comments=comments)

    assert [chunk.heading_path for chunk in chunks] == ["", "Comments"]
    assert bodies(chunks)[1] == (
        "Ana (2026-10-01): ¿Probaste aumentar el timeout?\n\n"
        "Juan (2026-10-02): Sí, con 300 s anduvo."
    )


def test_many_issue_comments_are_split_into_several_chunks() -> None:
    comments = [
        IssueComment("Ana", f"2026-10-{d:02d}", paragraph(f"c{d}w", 300)) for d in range(1, 9)
    ]

    chunks = chunk_issue(title="PLAT-1", header="h", description="d", comments=comments)

    comment_chunks = [chunk for chunk in chunks if chunk.heading_path == "Comments"]
    assert len(comment_chunks) > 1
    assert all(len(body) <= 1200 for body in bodies(comment_chunks))
    assert bodies(comment_chunks)[0].startswith("Ana (2026-10-01)")

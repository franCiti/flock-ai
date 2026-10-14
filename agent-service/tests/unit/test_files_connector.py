"""Persona folders as a knowledge source (task T15, plan sections 5.2 and 5.3)."""

import os
import shutil
from pathlib import Path
from typing import Any

import pytest

from flock_agent.ingestion.connectors.base import SourceConnector, SourceDocument, SyncPlan
from flock_agent.ingestion.connectors.files import parsers
from flock_agent.ingestion.connectors.files.connector import FilesConnector
from flock_agent.ingestion.connectors.files.local import LocalFolderStore
from flock_agent.ingestion.connectors.files.store import FileStore

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "files"
MAX_BYTES = 20 * 1024 * 1024


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    """Knowledge folder of the persona juan-plataforma."""
    root = tmp_path / "juan-plataforma"
    (root / "procedimientos").mkdir(parents=True)
    shutil.copy(FIXTURES / "sample.md", root / "procedimientos" / "deploy.md")
    shutil.copy(FIXTURES / "sample.docx", root / "accesos.docx")
    shutil.copy(FIXTURES / "page.html", root / "onboarding.html")
    (root / "notas.txt").write_text("Daily a las 9:30.", encoding="utf-8")
    return root


def connector(root: Path) -> FilesConnector:
    return FilesConnector("juan-plataforma", LocalFolderStore(root), max_bytes=MAX_BYTES)


async def run(
    root: Path, cursor: dict[str, Any] | None = None
) -> tuple[SyncPlan, list[SourceDocument]]:
    plan = await connector(root).sync(cursor)
    return plan, [document async for document in plan.upserts]


def touch(path: Path, content: str | None = None) -> None:
    """Change a file and make sure its modification time moves forward."""
    if content is not None:
        path.write_text(content, encoding="utf-8")
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))


# --- First sync -----------------------------------------------------------------------------


async def test_the_first_sync_delivers_every_supported_file(folder: Path) -> None:
    plan, documents = await run(folder)

    by_path = {document.path: document for document in documents}
    assert set(by_path) == {
        "procedimientos/deploy.md",
        "accesos.docx",
        "onboarding.html",
        "notas.txt",
    }
    assert plan.deleted_ids == []
    assert plan.skipped == []

    deploy = by_path["procedimientos/deploy.md"]
    assert deploy.id == "file:juan-plataforma:procedimientos/deploy.md"
    assert deploy.persona_id == "juan-plataforma"
    assert deploy.source_type == "file"
    assert deploy.source_id is None
    assert deploy.content_format == "markdown"
    assert deploy.title == "deploy"  # no title inside the file: its name


async def test_titles_come_from_the_document_when_it_has_one(folder: Path) -> None:
    _, documents = await run(folder)

    titles = {document.path: document.title for document in documents}
    assert titles["accesos.docx"] == "Manual de accesos"
    assert titles["onboarding.html"] == "Guía de onboarding"


async def test_profile_hidden_and_temporary_files_are_ignored(folder: Path) -> None:
    (folder / "persona.md").write_text("---\ndisplay_name: Juan\n---", encoding="utf-8")
    (folder / ".notas-privadas.txt").write_text("oculto", encoding="utf-8")
    (folder / ".git").mkdir()
    (folder / ".git" / "config").write_text("[core]", encoding="utf-8")
    (folder / "~$accesos.docx").write_bytes(b"lock")
    (folder / "procedimientos" / "persona.md").write_text("Not the profile.", encoding="utf-8")

    _, documents = await run(folder)

    paths = {document.path or "" for document in documents}
    assert "persona.md" not in paths
    assert not any(path.startswith((".", "~$")) or "/." in path for path in paths)
    assert "procedimientos/persona.md" in paths  # only the root one is the profile


async def test_unsupported_files_are_skipped_with_their_reason(folder: Path) -> None:
    shutil.copy(FIXTURES / "image.png", folder / "diagrama.png")
    shutil.copy(FIXTURES / "scanned.pdf", folder / "contrato.pdf")

    plan, documents = await run(folder)

    assert len(documents) == 4
    assert {(item.path, item.reason) for item in plan.skipped} == {
        ("diagrama.png", "binary file"),
        ("contrato.pdf", "no extractable text (scanned PDF?)"),
    }


async def test_an_email_and_its_attachments(folder: Path) -> None:
    (folder / "correo").mkdir()
    shutil.copy(FIXTURES / "mail.eml", folder / "correo" / "accesos.eml")

    plan, documents = await run(folder)

    email_id = "file:juan-plataforma:correo/accesos.eml"
    emails = [document for document in documents if document.path == "correo/accesos.eml"]
    email, *attachments = emails
    assert email.id == email_id
    assert email.source_type == "email"
    assert email.parent_id is None
    assert email.title == "Accesos para el nuevo ingreso"
    assert [attachment.id for attachment in attachments] == [
        f"{email_id}#attachment/checklist.txt",
        f"{email_id}#attachment/manual.docx",
        f"{email_id}#attachment/checklist (2).txt",
        f"{email_id}#attachment/Ventana de mantenimiento.eml",
    ]
    for attachment in attachments:
        assert attachment.source_type == "email_attachment"
        assert attachment.parent_id == email_id
        assert attachment.path == "correo/accesos.eml"
    assert attachments[0].title == "checklist.txt (adjunto de Accesos para el nuevo ingreso)"
    assert [(item.path, item.reason) for item in plan.skipped] == [
        ("correo/accesos.eml#attachment/logo.png", "binary file")
    ]


async def test_a_missing_folder_has_no_documents(tmp_path: Path) -> None:
    plan, documents = await run(tmp_path / "does-not-exist")

    assert documents == []
    assert plan.deleted_ids == []


# --- Incremental syncs ----------------------------------------------------------------------


async def test_nothing_changed_means_nothing_to_do(folder: Path) -> None:
    first, _ = await run(folder)

    second, documents = await run(folder, first.next_cursor)

    assert documents == []
    assert second.deleted_ids == []


async def test_new_changed_and_deleted_files_are_detected(folder: Path) -> None:
    first, _ = await run(folder)
    touch(folder / "notas.txt", "Daily a las 10:00.")
    (folder / "onboarding.html").unlink()
    (folder / "procedimientos" / "rollback.md").write_text("# Rollback\nPasos.", encoding="utf-8")

    second, documents = await run(folder, first.next_cursor)

    assert {document.path for document in documents} == {"notas.txt", "procedimientos/rollback.md"}
    assert next(d for d in documents if d.path == "notas.txt").content == "Daily a las 10:00."
    assert second.deleted_ids == ["file:juan-plataforma:onboarding.html"]


async def test_skipped_files_are_not_read_again_until_they_change(folder: Path) -> None:
    shutil.copy(FIXTURES / "image.png", folder / "diagrama.png")
    first, _ = await run(folder)

    second, _ = await run(folder, first.next_cursor)
    assert second.skipped == []

    touch(folder / "diagrama.png")
    third, _ = await run(folder, second.next_cursor)
    assert [item.path for item in third.skipped] == ["diagrama.png"]


async def test_new_parsers_read_every_file_again_but_still_detect_deletions(
    folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first, _ = await run(folder)
    (folder / "notas.txt").unlink()
    monkeypatch.setattr(
        "flock_agent.ingestion.connectors.files.connector.PARSERS_VERSION",
        parsers.PARSERS_VERSION + 1,
    )

    second, documents = await run(folder, first.next_cursor)

    assert {document.path for document in documents} == {
        "procedimientos/deploy.md",
        "accesos.docx",
        "onboarding.html",
    }
    assert second.deleted_ids == ["file:juan-plataforma:notas.txt"]


async def test_files_that_cannot_be_read_are_retried_next_time(
    folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = LocalFolderStore.read_bytes

    async def flaky(self: LocalFolderStore, path: str) -> bytes:
        if path == "notas.txt":
            raise PermissionError("locked by another program")
        return await original(self, path)

    monkeypatch.setattr(LocalFolderStore, "read_bytes", flaky)
    first, documents = await run(folder)
    assert "notas.txt" not in {document.path for document in documents}
    assert first.skipped[0].reason.startswith("could not be read")

    monkeypatch.setattr(LocalFolderStore, "read_bytes", original)
    _, documents = await run(folder, first.next_cursor)

    assert [document.path for document in documents] == ["notas.txt"]


# --- Safety ---------------------------------------------------------------------------------


async def test_paths_outside_the_folder_cannot_be_read(folder: Path) -> None:
    (folder.parent / "secret.txt").write_text("not of this persona", encoding="utf-8")

    with pytest.raises(ValueError, match="outside the knowledge folder"):
        await LocalFolderStore(folder).read_bytes("../secret.txt")


async def test_symbolic_links_are_ignored(folder: Path) -> None:
    outside = folder.parent / "outside.txt"
    outside.write_text("not of this persona", encoding="utf-8")
    try:
        (folder / "link.txt").symlink_to(outside)
    except OSError:
        pytest.skip("creating symbolic links needs extra privileges on this system")

    _, documents = await run(folder)

    assert "link.txt" not in {document.path for document in documents}


def test_implementations_satisfy_the_interfaces(folder: Path) -> None:
    # Checked by mypy: a change in SourceConnector or FileStore breaks the type check here.
    store: FileStore = LocalFolderStore(folder)
    source: SourceConnector = FilesConnector("juan-plataforma", store, max_bytes=MAX_BYTES)

    assert source.source_key == "folder"

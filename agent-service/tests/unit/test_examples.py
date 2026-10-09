"""The fictional personas of examples/knowledge stay usable (task T17, plan 8.6)."""

from pathlib import Path

import pytest

from flock_agent.ingestion.connectors.base import SourceDocument
from flock_agent.ingestion.connectors.files.connector import FilesConnector
from flock_agent.ingestion.connectors.files.local import LocalFolderStore
from flock_agent.ingestion.personas import load_persona

EXAMPLES = Path(__file__).resolve().parents[3] / "examples" / "knowledge"
PERSONAS = ["ana-datos", "juan-plataforma"]


async def documents_of(persona_id: str) -> tuple[list[SourceDocument], list[str]]:
    connector = FilesConnector(
        persona_id, LocalFolderStore(EXAMPLES / persona_id), max_bytes=20 * 1024 * 1024
    )
    plan = await connector.sync(None)
    documents = [document async for document in plan.upserts]
    return documents, [item.path for item in plan.skipped]


def test_there_are_two_personas_with_their_profiles() -> None:
    folders = sorted(path.name for path in EXAMPLES.iterdir() if path.is_dir())

    assert folders == PERSONAS
    names = {persona: load_persona(EXAMPLES / persona).persona.display_name for persona in PERSONAS}
    assert names == {"ana-datos": "Ana Gómez", "juan-plataforma": "Juan Pérez"}


@pytest.mark.parametrize("persona_id", PERSONAS)
async def test_every_example_file_is_readable(persona_id: str) -> None:
    documents, skipped = await documents_of(persona_id)

    assert len(documents) >= 9
    # Only emails wait for their parser (T14).
    assert all(path.endswith((".eml", ".msg")) for path in skipped)


@pytest.mark.parametrize("persona_id", PERSONAS)
async def test_examples_cover_every_format(persona_id: str) -> None:
    documents, _ = await documents_of(persona_id)

    suffixes = {Path(document.path or "").suffix for document in documents}
    assert {".md", ".csv", ".html", ".docx", ".pdf"} <= suffixes


async def test_each_persona_has_knowledge_the_other_does_not() -> None:
    juan, _ = await documents_of("juan-plataforma")
    ana, _ = await documents_of("ana-datos")
    juan_text = " ".join(document.content for document in juan)
    ana_text = " ".join(document.content for document in ana)

    for only_juan in ("rollback-prod", "FortiClient", "Kubernetes"):
        assert only_juan in juan_text
        assert only_juan not in ana_text
    for only_ana in ("ventas_diario", "Looker", "dim_clientes"):
        assert only_ana in ana_text
        assert only_ana not in juan_text

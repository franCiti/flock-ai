"""Knowledge update end to end over examples/knowledge (tasks T18, T12, T14; plan 5.1, 5.5)."""

import os
import shutil
import uuid
from email import policy
from email.parser import BytesParser
from pathlib import Path

import pytest

from flock_agent.ingestion.pipeline import AnyEvent, IngestionPipeline, PersonaResult, RunResult
from flock_agent.knowledge.repository import KnowledgeRepository
from tests.fakes import FakeEmbedder

pytestmark = pytest.mark.integration_containers

EXAMPLES = Path(__file__).resolve().parents[3] / "examples" / "knowledge"
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "files"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """A copy of the example personas that the tests can change freely."""
    destination = tmp_path / "knowledge"
    shutil.copytree(EXAMPLES, destination)
    return destination


@pytest.fixture
def emitted() -> list[AnyEvent]:
    return []


@pytest.fixture
def pipeline(
    knowledge: KnowledgeRepository, root: Path, emitted: list[AnyEvent]
) -> IngestionPipeline:
    async def collect(event: AnyEvent) -> None:
        emitted.append(event)

    return IngestionPipeline(
        knowledge,
        FakeEmbedder(),
        knowledge_root=root,
        max_bytes=20 * 1024 * 1024,
        on_event=collect,
    )


async def run(pipeline: IngestionPipeline, persona_ids: set[str] | None = None) -> RunResult:
    result = await pipeline.run(uuid.uuid4(), "manual", persona_ids=persona_ids)
    assert result is not None
    return result


def persona(result: RunResult, persona_id: str) -> PersonaResult:
    return next(p for p in result.personas if p.persona_id == persona_id)


async def chunk_count(knowledge: KnowledgeRepository, document_id: str) -> int:
    async with knowledge._pool.connection() as connection:
        cursor = await connection.execute(
            "SELECT count(*) FROM chunk WHERE document_id = %s", (document_id,)
        )
        row = await cursor.fetchone()
        assert row is not None
        return int(row[0])


async def test_the_first_update_indexes_every_example(
    pipeline: IngestionPipeline, knowledge: KnowledgeRepository, emitted: list[AnyEvent]
) -> None:
    result = await run(pipeline)

    juan = persona(result, "juan-plataforma")
    ana = persona(result, "ana-datos")
    assert (juan.display_name, ana.display_name) == ("Juan Pérez", "Ana Gómez")
    assert juan.added == 12  # 12 files, the email included (it has no attachments)
    assert ana.added == 10
    assert juan.skipped == ana.skipped == []
    assert juan.source_errors == ana.source_errors == []

    documents = await knowledge.document_ids("juan-plataforma", None)
    assert len(documents) == juan.added
    assert await chunk_count(knowledge, "file:juan-plataforma:procedimientos/rollback.md") >= 1
    assert [event.type for event in emitted] == [
        "started",
        "persona_completed",
        "persona_completed",
        "completed",
    ]


async def test_a_second_update_reprocesses_nothing(pipeline: IngestionPipeline) -> None:
    await run(pipeline)

    second = await run(pipeline)

    totals = second.totals()
    assert (totals.added, totals.modified, totals.deleted) == (0, 0, 0)


async def test_unchanged_content_is_not_reindexed_after_a_full_reread(
    pipeline: IngestionPipeline, knowledge: KnowledgeRepository, root: Path
) -> None:
    await run(pipeline)
    # A file whose modification time moves but whose text is the same.
    rollback = root / "juan-plataforma" / "procedimientos" / "rollback.md"
    rollback.write_text(rollback.read_text(encoding="utf-8"), encoding="utf-8")

    result = await run(pipeline)

    juan = persona(result, "juan-plataforma")
    assert (juan.unchanged, juan.modified) == (1, 0)


async def test_a_modified_file_is_reindexed(
    pipeline: IngestionPipeline, knowledge: KnowledgeRepository, root: Path
) -> None:
    await run(pipeline)
    faq = root / "juan-plataforma" / "accesos" / "faq-vpn.md"
    faq.write_text(faq.read_text(encoding="utf-8") + "\n## Nueva pregunta\n\nRespuesta.", "utf-8")

    result = await run(pipeline)

    assert persona(result, "juan-plataforma").modified == 1


async def test_a_deleted_file_leaves_the_knowledge_base(
    pipeline: IngestionPipeline, knowledge: KnowledgeRepository, root: Path
) -> None:
    await run(pipeline)
    (root / "ana-datos" / "dashboards" / "tableros.md").unlink()

    result = await run(pipeline)

    assert persona(result, "ana-datos").deleted == 1
    assert "file:ana-datos:dashboards/tableros.md" not in await knowledge.document_ids(
        "ana-datos", None
    )
    assert await chunk_count(knowledge, "file:ana-datos:dashboards/tableros.md") == 0


async def test_a_removed_persona_folder_removes_the_persona(
    pipeline: IngestionPipeline, knowledge: KnowledgeRepository, root: Path, emitted: list[AnyEvent]
) -> None:
    await run(pipeline)
    shutil.rmtree(root / "ana-datos")

    result = await run(pipeline)

    assert result.removed_personas == ["ana-datos"]
    assert await knowledge.get_persona("ana-datos") is None
    assert "persona_removed" in [event.type for event in emitted]


async def test_a_single_persona_update_never_removes_the_others(
    pipeline: IngestionPipeline, knowledge: KnowledgeRepository, root: Path
) -> None:
    await run(pipeline)
    shutil.rmtree(root / "ana-datos")

    result = await run(pipeline, persona_ids={"juan-plataforma"})

    assert [p.persona_id for p in result.personas] == ["juan-plataforma"]
    assert result.removed_personas == []
    assert await knowledge.get_persona("ana-datos") is not None


async def test_a_missing_knowledge_root_fails_without_deleting_anything(
    knowledge: KnowledgeRepository, pipeline: IngestionPipeline, root: Path, emitted: list[AnyEvent]
) -> None:
    await run(pipeline)
    shutil.rmtree(root)

    with pytest.raises(RuntimeError, match="knowledge root not found"):
        await run(pipeline)

    assert len(await knowledge.list_personas()) == 2
    assert emitted[-1].type == "failed"


async def test_profiles_are_created_and_invalid_names_ignored(
    pipeline: IngestionPipeline, knowledge: KnowledgeRepository, root: Path
) -> None:
    (root / "pedro-soporte").mkdir()
    (root / "pedro-soporte" / "faq.md").write_text("# FAQ\nReiniciar el router.", "utf-8")
    (root / "Carpeta Invalida").mkdir()

    result = await run(pipeline)

    assert (root / "pedro-soporte" / "persona.md").is_file()
    pedro = await knowledge.get_persona("pedro-soporte")
    assert pedro is not None
    assert pedro.display_name == "Pedro Soporte"
    assert result.ignored_folders == ["Carpeta Invalida"]


async def test_an_update_while_another_runs_is_rejected(
    pipeline: IngestionPipeline, knowledge: KnowledgeRepository, emitted: list[AnyEvent]
) -> None:
    job_id = uuid.uuid4()
    async with KnowledgeRepository(knowledge._pool).ingestion_lock():
        assert await pipeline.run(job_id, "scheduled") is None

    run_record = await knowledge.get_run(job_id)
    assert run_record is not None
    assert run_record.status == "rejected"
    assert [event.type for event in emitted] == ["rejected"]


async def test_the_run_is_recorded_with_its_summary(
    pipeline: IngestionPipeline, knowledge: KnowledgeRepository
) -> None:
    result = await run(pipeline)

    record = await knowledge.get_run(result.job_id)

    assert record is not None
    assert record.status == "completed"
    assert record.summary is not None
    assert record.summary["totals"]["personas"] == 2


async def test_secrets_never_reach_the_knowledge_base(
    pipeline: IngestionPipeline, knowledge: KnowledgeRepository
) -> None:
    """The example documents with made-up secrets (task T12, spec HU15.4)."""
    result = await run(pipeline)
    assert persona(result, "juan-plataforma").secrets_masked >= 4
    assert persona(result, "ana-datos").secrets_masked >= 2

    async with knowledge._pool.connection() as connection:
        cursor = await connection.execute(
            "SELECT string_agg(content, ' ') FROM chunk WHERE document_id = ANY(%s)",
            (
                [
                    "file:juan-plataforma:procedimientos/acceso-bastion.md",
                    "file:ana-datos:pipelines/conexion-warehouse.md",
                ],
            ),
        )
        row = await cursor.fetchone()
        cursor = await connection.execute(
            "SELECT id, secrets_masked FROM document WHERE secrets_masked > 0 ORDER BY id"
        )
        masked = await cursor.fetchall()
    assert row is not None
    content = str(row[0])
    for secret in (
        "Bastion-Example-2026!",
        "AKIAIOSFODNN7EXAMPLE",
        "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        "ghp_EXAMPLEtokenEXAMPLEtokenEXAMPLE1234",
        "Dwh-Example-2026",
    ):
        assert secret not in content
    assert "[dato oculto]" in content
    assert [document_id for document_id, _ in masked] == [
        "file:ana-datos:pipelines/conexion-warehouse.md",
        "file:juan-plataforma:procedimientos/acceso-bastion.md",
    ]


async def test_emails_and_their_attachments(
    pipeline: IngestionPipeline, knowledge: KnowledgeRepository, root: Path
) -> None:
    """An email is indexed with its attachments; an attachment that disappears from the email
    leaves the knowledge base; deleting the email deletes its attachments (task T14)."""
    mail = root / "juan-plataforma" / "correo" / "accesos.eml"
    shutil.copy(FIXTURES / "mail.eml", mail)
    email_id = "file:juan-plataforma:correo/accesos.eml"

    result = await run(pipeline, {"juan-plataforma"})
    juan = persona(result, "juan-plataforma")
    assert juan.added == 12 + 1 + 4  # the examples, the new email and its four attachments
    assert [item.path for item in juan.skipped] == ["correo/accesos.eml#attachment/logo.png"]
    assert await knowledge.child_ids(email_id) == {
        f"{email_id}#attachment/checklist.txt",
        f"{email_id}#attachment/manual.docx",
        f"{email_id}#attachment/checklist (2).txt",
        f"{email_id}#attachment/Ventana de mantenimiento.eml",
    }

    # The same email without attachments.
    message = BytesParser(policy=policy.default).parsebytes(mail.read_bytes())
    message.clear_content()
    message.set_content("Te mando los accesos en otro correo.")
    mail.write_bytes(bytes(message))
    os.utime(mail, ns=(mail.stat().st_atime_ns, mail.stat().st_mtime_ns + 1_000_000_000))
    second = persona(await run(pipeline, {"juan-plataforma"}), "juan-plataforma")
    assert second.modified == 1
    assert second.deleted == 4
    assert await knowledge.child_ids(email_id) == set()

    mail.unlink()
    shutil.copy(FIXTURES / "mail.eml", root / "juan-plataforma" / "correo" / "otro.eml")
    await run(pipeline, {"juan-plataforma"})
    (root / "juan-plataforma" / "correo" / "otro.eml").unlink()
    third = persona(await run(pipeline, {"juan-plataforma"}), "juan-plataforma")
    assert third.deleted == 1  # the email; its attachments go in cascade
    assert await knowledge.child_ids("file:juan-plataforma:correo/otro.eml") == set()

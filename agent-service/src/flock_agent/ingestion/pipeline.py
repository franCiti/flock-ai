"""Knowledge update: persona folders -> documents -> chunks -> embeddings (plan sections 5.1, 5.5).

Pending pieces, kept as explicit extension points so the pipeline runs end to end:
- TODO(T47+): external sources (Jira, Confluence, SharePoint) arrive in stage 3.
"""

import asyncio
import hashlib
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from flock_agent.contracts.generated import ingestion_event_v1 as events
from flock_agent.ingestion.connectors.base import SkippedItem, SourceDocument
from flock_agent.ingestion.connectors.files.connector import FilesConnector
from flock_agent.ingestion.connectors.files.local import PROFILE_FILE, LocalFolderStore
from flock_agent.ingestion.personas import is_persona_folder, is_valid_persona_id, load_persona
from flock_agent.knowledge.chunking import chunk_markdown, chunk_plain
from flock_agent.knowledge.embeddings import Embedder
from flock_agent.knowledge.index_model import ensure_embedding_model
from flock_agent.knowledge.models import ChunkInput, DocumentRecord, RunTrigger
from flock_agent.knowledge.redaction import DEFAULT_PLACEHOLDER, redact
from flock_agent.knowledge.repository import IngestionAlreadyRunningError, KnowledgeRepository

log = logging.getLogger(__name__)

AnyEvent = (
    events.StartedEvent
    | events.RejectedEvent
    | events.PersonaCompletedEvent
    | events.PersonaRemovedEvent
    | events.CompletedEvent
    | events.FailedEvent
)
EventSink = Callable[[AnyEvent], Awaitable[None]]


class KnowledgeRootNotFoundError(RuntimeError):
    """The knowledge root does not exist: nothing is deleted (it may just be unmounted)."""


@dataclass
class PersonaResult:
    persona_id: str
    display_name: str
    added: int = 0
    modified: int = 0
    deleted: int = 0
    unchanged: int = 0
    secrets_masked: int = 0
    skipped: list[SkippedItem] = field(default_factory=list)
    source_errors: list[tuple[str, str]] = field(default_factory=list)  # (source key, reason)

    def to_contract(self) -> events.PersonaSummary:
        return events.PersonaSummary(
            persona_id=self.persona_id,
            display_name=self.display_name,
            added=self.added,
            modified=self.modified,
            deleted=self.deleted,
            unchanged=self.unchanged,
            secrets_masked=self.secrets_masked,
            skipped=[events.SkippedItem(path=i.path, reason=i.reason) for i in self.skipped],
            source_errors=[
                events.SourceError(source_id=key, reason=reason)
                for key, reason in self.source_errors
            ],
        )


@dataclass
class RunResult:
    job_id: UUID
    personas: list[PersonaResult] = field(default_factory=list)
    removed_personas: list[str] = field(default_factory=list)
    ignored_folders: list[str] = field(default_factory=list)  # names that are not valid ids

    def totals(self) -> events.Totals:
        def total(attribute: str) -> int:
            return sum(getattr(persona, attribute) for persona in self.personas)

        return events.Totals(
            personas=len(self.personas),
            added=total("added"),
            modified=total("modified"),
            deleted=total("deleted"),
            unchanged=total("unchanged"),
            skipped=sum(len(persona.skipped) for persona in self.personas),
            secrets_masked=total("secrets_masked"),
            source_errors=sum(len(persona.source_errors) for persona in self.personas),
        )


class IngestionPipeline:
    def __init__(
        self,
        repository: KnowledgeRepository,
        embedder: Embedder,
        *,
        knowledge_root: Path,
        max_bytes: int,
        on_event: EventSink | None = None,
        secret_placeholder: str = DEFAULT_PLACEHOLDER,
    ) -> None:
        self._repository = repository
        self._secret_placeholder = secret_placeholder
        self._embedder = embedder
        self._root = knowledge_root
        self._max_bytes = max_bytes
        self._on_event = on_event

    async def run(
        self, job_id: UUID, trigger: RunTrigger, *, persona_ids: set[str] | None = None
    ) -> RunResult | None:
        """One knowledge update. Returns None if another update was running (spec HU4.9).

        persona_ids limits the update to those personas; personas are only removed (because
        their folder disappeared) in a full update.
        """
        try:
            async with self._repository.ingestion_lock():
                return await self._run_locked(job_id, trigger, persona_ids)
        except IngestionAlreadyRunningError:
            reason = "another update is already running"
            log.warning("ingestion rejected", extra={"job_id": str(job_id), "reason": reason})
            await self._repository.start_run(job_id, trigger)
            await self._repository.finish_run(job_id, "rejected", {"reason": reason})
            await self._emit(_event(events.RejectedEvent, job_id, type="rejected", reason=reason))
            return None

    async def _run_locked(
        self, job_id: UUID, trigger: RunTrigger, persona_ids: set[str] | None
    ) -> RunResult:
        result = RunResult(job_id)
        await self._repository.start_run(job_id, trigger)
        await self._emit(_event(events.StartedEvent, job_id, type="started"))
        try:
            if not self._root.is_dir():
                msg = f"knowledge root not found: {self._root}"
                raise KnowledgeRootNotFoundError(msg)
            await ensure_embedding_model(self._repository, self._embedder)

            folders = self._persona_folders(result, persona_ids)
            for folder in folders:
                persona = await self._ingest_persona(folder)
                result.personas.append(persona)
                await self._emit(
                    _event(
                        events.PersonaCompletedEvent,
                        job_id,
                        type="persona_completed",
                        summary=persona.to_contract(),
                    )
                )

            if persona_ids is None:
                await self._remove_vanished_personas(result, {folder.name for folder in folders})

            totals = result.totals()
            await self._repository.finish_run(job_id, "completed", self._summary(result))
            await self._emit(_event(events.CompletedEvent, job_id, type="completed", totals=totals))
            return result
        except Exception as error:
            log.exception("ingestion failed", extra={"job_id": str(job_id)})
            await self._repository.finish_run(job_id, "failed", {"reason": str(error)})
            await self._emit(_event(events.FailedEvent, job_id, type="failed", reason=str(error)))
            raise

    # --- Personas ---------------------------------------------------------------------------

    def _persona_folders(self, result: RunResult, persona_ids: set[str] | None) -> list[Path]:
        folders = []
        for path in sorted(self._root.iterdir()):
            if not is_persona_folder(path):
                continue
            if not is_valid_persona_id(path.name):
                result.ignored_folders.append(path.name)
                log.warning("folder name is not a valid persona id", extra={"folder": path.name})
                continue
            if persona_ids is None or path.name in persona_ids:
                folders.append(path)
        missing = (persona_ids or set()) - {folder.name for folder in folders}
        if missing:
            msg = f"persona folders not found: {', '.join(sorted(missing))}"
            raise KnowledgeRootNotFoundError(msg)
        return folders

    async def _ingest_persona(self, folder: Path) -> PersonaResult:
        loaded = await asyncio.to_thread(load_persona, folder)
        persona = loaded.persona
        stored = await self._repository.get_persona(persona.id)
        if stored is None or stored.profile_hash != persona.profile_hash:
            await self._repository.upsert_persona(persona)

        result = PersonaResult(persona.id, persona.display_name)
        if loaded.warning:
            result.skipped.append(SkippedItem(PROFILE_FILE, loaded.warning))

        connector = FilesConnector(persona.id, LocalFolderStore(folder), max_bytes=self._max_bytes)
        state = await self._repository.get_sync_state(persona.id, connector.source_key)
        try:
            plan = await connector.sync(state.cursor if state else None)
            attachments: dict[str, set[str]] = {}  # email id -> ids of its current attachments
            async for document in plan.upserts:
                await self._index(document, result)
                if document.source_type == "email":
                    attachments.setdefault(document.id, set())
                elif document.parent_id is not None:
                    attachments.setdefault(document.parent_id, set()).add(document.id)
            result.deleted += await self._repository.delete_documents(plan.deleted_ids)
            result.deleted += await self._delete_removed_attachments(attachments)
            result.skipped.extend(plan.skipped)
            # Saved only now: if anything above fails, the next update starts from the old cursor.
            await self._repository.save_sync_state(
                persona.id, connector.source_key, plan.next_cursor
            )
        except Exception as error:
            # A failing source never means "everything was deleted": its documents are kept.
            log.exception("source failed", extra={"persona": persona.id, "source": "folder"})
            result.source_errors.append((connector.source_key, str(error)))
        return result

    async def _delete_removed_attachments(self, current: dict[str, set[str]]) -> int:
        """Attachments that are no longer in their (re-read) email; returns how many."""
        removed: set[str] = set()
        for email_id, attachment_ids in current.items():
            removed |= await self._repository.child_ids(email_id) - attachment_ids
        return await self._repository.delete_documents(removed)

    async def _remove_vanished_personas(self, result: RunResult, present: set[str]) -> None:
        for persona in await self._repository.list_personas():
            if persona.id not in present:
                await self._repository.delete_persona(persona.id)
                result.removed_personas.append(persona.id)
                await self._emit(
                    _event(
                        events.PersonaRemovedEvent,
                        result.job_id,
                        type="persona_removed",
                        persona_id=persona.id,
                    )
                )

    # --- Documents --------------------------------------------------------------------------

    async def _index(self, document: SourceDocument, result: PersonaResult) -> None:
        redacted = redact(document.content, self._secret_placeholder)
        content_hash = _content_hash(document, redacted.text)
        previous = await self._repository.get_content_hash(document.id)
        if previous == content_hash:
            result.unchanged += 1
            return

        chunker = chunk_markdown if document.content_format == "markdown" else chunk_plain
        chunks = chunker(redacted.text, title=document.title)
        if not chunks:
            result.skipped.append(SkippedItem(document.path or document.id, "no extractable text"))
            return
        vectors = await asyncio.to_thread(
            self._embedder.embed_documents, [chunk.content for chunk in chunks]
        )
        await self._repository.replace_document(
            DocumentRecord(
                id=document.id,
                persona_id=document.persona_id,
                source_type=document.source_type,
                source_id=document.source_id,
                parent_id=document.parent_id,
                title=document.title,
                url=document.url,
                path=document.path,
                source_updated_at=document.source_updated_at,
                content_hash=content_hash,
                secrets_masked=redacted.masked,
            ),
            [
                ChunkInput(
                    ordinal=chunk.ordinal,
                    heading_path=chunk.heading_path,
                    content=chunk.content,
                    embedding=vector,
                )
                for chunk, vector in zip(chunks, vectors, strict=True)
            ],
        )
        if previous is None:
            result.added += 1
        else:
            result.modified += 1
        result.secrets_masked += redacted.masked

    # --- Helpers ----------------------------------------------------------------------------

    async def _emit(self, event: AnyEvent) -> None:
        log.info("ingestion event", extra={"event": event.type, "job_id": str(event.job_id)})
        if self._on_event is not None:
            await self._on_event(event)

    @staticmethod
    def _summary(result: RunResult) -> dict[str, object]:
        return {
            "totals": result.totals().model_dump(mode="json", by_alias=True),
            "personas": [
                persona.to_contract().model_dump(mode="json", by_alias=True)
                for persona in result.personas
            ],
            "removedPersonas": result.removed_personas,
            "ignoredFolders": result.ignored_folders,
        }


def _event[E: events.EventEnvelope](event_class: type[E], job_id: UUID, **fields: object) -> E:
    """Build a contract event: version and time are always the same."""
    return event_class.model_validate(
        {"version": 1, "job_id": job_id, "sent_at": datetime.now(UTC), **fields}
    )


def _content_hash(document: SourceDocument, text: str) -> str:
    """Changes when anything stored for the document changes, so unchanged ones are skipped."""
    fields = {
        "title": document.title,
        "url": document.url,
        "path": document.path,
        "parent_id": document.parent_id,
        "format": document.content_format,
        "text": text,
    }
    return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()

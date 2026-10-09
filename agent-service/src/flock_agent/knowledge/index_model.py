"""Keeps the knowledge base consistent with the embedding model in use (plan 3.2 and 5.5)."""

import logging

from flock_agent.knowledge.embeddings import Embedder
from flock_agent.knowledge.repository import META_EMBEDDING_MODEL, KnowledgeRepository

log = logging.getLogger(__name__)


async def ensure_embedding_model(repository: KnowledgeRepository, embedder: Embedder) -> bool:
    """Make the knowledge base match the embedder; returns True if it had to be reset.

    If the base was indexed with another model (or never), it is emptied and its vector column
    rebuilt, so the update that follows re-indexes everything. Run it holding the ingestion lock.
    """
    current = await repository.get_meta(META_EMBEDDING_MODEL)
    if current == embedder.model_name:
        return False
    log.warning(
        "embedding model changed: the knowledge base will be re-indexed",
        extra={"previous_model": current, "model": embedder.model_name},
    )
    await repository.reset_for_embedding_model(embedder.model_name, embedder.dimensions)
    return True

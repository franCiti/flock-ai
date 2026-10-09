"""The local embedding model (plan 5.5, D22).

Tests marked embedding_model download the model once (~0.2 GB) into data/models.
"""

import math
from pathlib import Path

import pytest

from flock_agent.common.settings import Settings
from flock_agent.knowledge.embeddings import (
    FastEmbedEmbedder,
    UnknownEmbeddingModelError,
    supported_dimensions,
)
from tests.fakes import FakeEmbedder

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MODEL = Settings(_env_file=None).embedding_model


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


def test_dimensions_come_from_the_model_metadata() -> None:
    assert supported_dimensions(DEFAULT_MODEL) == 384
    assert supported_dimensions("intfloat/multilingual-e5-large") == 1024


def test_unknown_models_are_rejected() -> None:
    with pytest.raises(UnknownEmbeddingModelError, match="no/such-model"):
        supported_dimensions("no/such-model")


def test_the_fake_embedder_is_deterministic() -> None:
    embedder = FakeEmbedder(dimensions=8)

    first, second, other = embedder.embed_documents(["a", "a", "b"])

    assert first == second != other
    assert len(first) == 8
    assert math.isclose(sum(value * value for value in first), 1.0)


@pytest.fixture(scope="module")
def embedder() -> FastEmbedEmbedder:
    return FastEmbedEmbedder(DEFAULT_MODEL, cache_dir=REPO_ROOT / "data" / "models", batch_size=4)


@pytest.mark.embedding_model
def test_vectors_have_the_model_dimensions(embedder: FastEmbedEmbedder) -> None:
    vectors = embedder.embed_documents(["uno", "dos"])

    assert [len(vector) for vector in vectors] == [384, 384]
    assert len(embedder.embed_query("tres")) == 384


@pytest.mark.embedding_model
def test_batches_keep_order_and_do_not_change_results(embedder: FastEmbedEmbedder) -> None:
    texts = [f"documento número {i}" for i in range(10)]  # batch_size=4: three batches

    batched = embedder.embed_documents(texts)
    one_by_one = [embedder.embed_documents([text])[0] for text in texts]

    assert len(batched) == 10
    for together, alone in zip(batched, one_by_one, strict=True):
        assert cosine(together, alone) > 0.9999


@pytest.mark.embedding_model
def test_similar_meaning_is_closer_across_languages(embedder: FastEmbedEmbedder) -> None:
    rollback, holidays = embedder.embed_documents(
        [
            "Para revertir un deploy fallido, ejecutá el job rollback-prod con el tag anterior.",
            "Las vacaciones se piden con dos semanas de anticipación.",
        ]
    )
    query = embedder.embed_query("How do I roll back a failed deployment?")

    assert cosine(query, rollback) > cosine(query, holidays)

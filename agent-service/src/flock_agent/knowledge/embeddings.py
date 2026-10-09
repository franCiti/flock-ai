"""Text embeddings (plan section 5.5, D22).

The rest of the code depends on the Embedder protocol only, so the model can be replaced by an
external provider without touching the pipeline or the search.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from fastembed import TextEmbedding


class Embedder(Protocol):
    @property
    def model_name(self) -> str: ...

    @property
    def dimensions(self) -> int: ...

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Vectors of the fragments to index, in the same order."""
        ...

    def embed_query(self, text: str) -> list[float]:
        """Vector of a search query (some models encode queries differently)."""
        ...


class UnknownEmbeddingModelError(ValueError):
    """The model is not supported by fastembed."""


def supported_dimensions(model_name: str) -> int:
    """Dimensions of a fastembed model, from its metadata (no download needed)."""
    for model in TextEmbedding.list_supported_models():
        if model["model"] == model_name:
            return int(model["dim"])
    msg = f"embedding model not supported by fastembed: {model_name}"
    raise UnknownEmbeddingModelError(msg)


class FastEmbedEmbedder:
    """Local ONNX model on CPU: the documents never leave the machine (D22).

    The model is downloaded once into cache_dir. Calls are CPU-bound and blocking: async code
    runs them with asyncio.to_thread().
    """

    def __init__(self, model_name: str, *, cache_dir: Path, batch_size: int = 32) -> None:
        self._model_name = model_name
        self._dimensions = supported_dimensions(model_name)
        self._batch_size = batch_size
        self._model = TextEmbedding(model_name, cache_dir=str(cache_dir))

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        vectors = self._model.passage_embed(list(texts), batch_size=self._batch_size)
        return [_as_floats(vector.tolist()) for vector in vectors]

    def embed_query(self, text: str) -> list[float]:
        return _as_floats(next(iter(self._model.query_embed(text))).tolist())


def _as_floats(values: list[float]) -> list[float]:
    """numpy's tolist() is untyped; this gives the result its type."""
    return values

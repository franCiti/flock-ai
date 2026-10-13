"""Test doubles shared by the test suites."""

import hashlib
import math
from collections.abc import Sequence

from flock_agent.knowledge.models import PersonaMatch, SearchHit


class FakeEmbedder:
    """Deterministic embedder: the same text always gives the same unit vector. No model needed."""

    def __init__(self, model_name: str = "fake-model", dimensions: int = 384) -> None:
        self._model_name = model_name
        self._dimensions = dimensions

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def _vector(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode()).digest()
        raw = [digest[i % len(digest)] - 127.5 for i in range(self._dimensions)]
        norm = math.sqrt(sum(value * value for value in raw))
        return [value / norm for value in raw]

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


class FakeSearch:
    """Hybrid search with predefined results; records every call."""

    def __init__(
        self,
        hits: Sequence[SearchHit] = (),
        matches: Sequence[PersonaMatch] = (),
    ) -> None:
        self.hits = list(hits)
        self.matches = list(matches)
        self.calls: list[tuple[str, str, str, float | None]] = []

    async def search(self, persona_id: str, query: str) -> list[SearchHit]:
        self.calls.append(("search", persona_id, query, None))
        return [hit for hit in self.hits if hit.persona_id == persona_id]

    async def search_other_personas(
        self, persona_id: str, query: str, *, min_similarity: float | None = None
    ) -> list[PersonaMatch]:
        self.calls.append(("search_other_personas", persona_id, query, min_similarity))
        return [match for match in self.matches if match.persona_id != persona_id]

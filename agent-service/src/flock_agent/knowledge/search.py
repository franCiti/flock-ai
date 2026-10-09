"""Hybrid search over the knowledge base (plan 4.3 `retrieve` and `find_referral`, 4.8).

Two searches over the fragments, always filtered by persona in the query itself (spec HU3):
- by meaning: cosine similarity of the embeddings (HNSW index);
- by words: the `tsv` column, for what embeddings miss (job names, error codes, acronyms).
Their rankings are combined with Reciprocal Rank Fusion: each fragment adds 1 / (k + rank) for
every list it appears in, so a fragment found by both searches goes up.
"""

import asyncio
import re
from collections import defaultdict
from collections.abc import Hashable, Iterable, Sequence
from typing import Any, Literal

from pgvector import Vector
from psycopg import AsyncConnection, sql
from psycopg.rows import dict_row

from flock_agent.common.db import Pool
from flock_agent.knowledge.embeddings import Embedder
from flock_agent.knowledge.models import PersonaMatch, SearchHit

# The usual constant of Reciprocal Rank Fusion: dampens the weight of the first positions.
RRF_K = 60

# A question is natural language: requiring every word would rarely match, so the word search
# looks for any significant term. Words this common would match almost every fragment.
_STOPWORD_LIST = """
    a al algo como cual cuales cuando de del donde el ella ellos en entre era es esa ese eso
    esta este esto estos fue ha hace hacer hago hay la las le les lo los mas me mi mis muy no
    nos o para pero por que quien se ser si sin sobre son su sus te tengo tiene tu un una uno
    unos unas y ya yo cómo cuál cuáles cuándo dónde qué quién más sí tú él
    about an and are as at be by can do does for from has have how i if in is it its me my of
    on or so that the this to was what when where which who why will with you your
"""
_STOPWORDS = frozenset(_STOPWORD_LIST.split())
_TERM = re.compile(r"\w(?:[\w\-./]*\w)?")
_MAX_TERMS = 32
_MIN_TERM_CHARS = 2  # a single letter says nothing

Scope = Literal["persona", "others"]

_HIT_COLUMNS = sql.SQL(
    """
    c.id AS chunk_id, c.persona_id, c.document_id, d.source_type, d.title, d.url, d.path,
    d.section_hint, c.heading_path, c.content,
    1 - (c.embedding <=> %(vector)s) AS similarity
    """
)


def keyword_terms(text: str) -> list[str]:
    """Significant terms of a question, lowercase, in order and without repeats.

    Inner hyphens, dots, slashes and underscores are kept: `rollback-prod`, `v1.2`, `ERR_502`.
    """
    terms: dict[str, None] = {}
    for match in _TERM.finditer(text.lower()):
        term = match.group()
        if len(term) >= _MIN_TERM_CHARS and term not in _STOPWORDS:
            terms[term] = None
    return list(terms)[:_MAX_TERMS]


def reciprocal_rank_fusion[T: Hashable](
    rankings: Iterable[Sequence[T]], k: int = RRF_K
) -> dict[T, float]:
    """Fused score of every item: the sum of 1 / (k + rank) over the rankings (rank from 1)."""
    scores: dict[T, float] = defaultdict(float)
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] += 1 / (k + rank)
    return dict(scores)


class KnowledgeSearch:
    """Searches the fragments of the knowledge base. Only needs read access (agent role)."""

    def __init__(self, pool: Pool, embedder: Embedder, *, candidates: int, top_k: int) -> None:
        self._pool = pool
        self._embedder = embedder
        self._candidates = candidates  # per kind of search (RETRIEVAL_CANDIDATES)
        self._top_k = top_k  # fragments returned (RETRIEVAL_TOP_K)

    async def search(self, persona_id: str, query: str) -> list[SearchHit]:
        """The best `top_k` fragments of one persona for `query`, best first."""
        return (await self._hybrid(persona_id, "persona", query))[: self._top_k]

    async def search_other_personas(
        self, persona_id: str, query: str, *, min_similarity: float | None = None
    ) -> list[PersonaMatch]:
        """The other personas whose fragments match `query`, best first (referrals, spec HU2).

        Each persona keeps its fragments among the fused candidates. A persona is left out if
        none of them reaches `min_similarity` (REFERRAL_MIN_SCORE; None = no threshold).
        """
        by_persona: dict[str, list[SearchHit]] = defaultdict(list)
        for hit in await self._hybrid(persona_id, "others", query):
            by_persona[hit.persona_id].append(hit)
        names = await self._display_names(by_persona)
        matches = [
            PersonaMatch(
                persona_id=other,
                display_name=names.get(other, other),
                similarity=max(hit.similarity for hit in hits),
                hits=tuple(hits),
            )
            for other, hits in by_persona.items()
        ]
        if min_similarity is not None:
            matches = [match for match in matches if match.similarity >= min_similarity]
        # Hits are already sorted by fused score: a persona ranks by its best hit.
        return sorted(matches, key=lambda match: match.hits[0].score, reverse=True)

    async def _hybrid(self, persona_id: str, scope: Scope, query: str) -> list[SearchHit]:
        vector = Vector(await asyncio.to_thread(self._embedder.embed_query, query))
        terms = keyword_terms(query)
        persona_filter = sql.SQL(
            "c.persona_id = %(persona_id)s"
            if scope == "persona"
            else "c.persona_id <> %(persona_id)s"
        )
        params = {"persona_id": persona_id, "vector": vector, "limit": self._candidates}
        async with self._pool.connection() as connection, connection.transaction():
            # With a filter, HNSW could return fewer rows than the limit; iterative scans keep
            # walking the index until the limit is met (pgvector 0.8).
            await connection.execute("SET LOCAL hnsw.iterative_scan = strict_order")
            by_meaning = await self._rows(
                connection,
                sql.SQL(
                    """
                    SELECT {columns} FROM chunk c JOIN document d ON d.id = c.document_id
                    WHERE {filter}
                    ORDER BY c.embedding <=> %(vector)s, c.id
                    LIMIT %(limit)s
                    """
                ).format(columns=_HIT_COLUMNS, filter=persona_filter),
                params,
            )
            by_words = []
            if terms:
                word_params = params | {f"term{i}": term for i, term in enumerate(terms)}
                by_words = await self._rows(
                    connection, self._word_query(terms, persona_filter), word_params
                )
        rows = {row["chunk_id"]: row for row in by_meaning + by_words}
        scores = reciprocal_rank_fusion(
            [[row["chunk_id"] for row in by_meaning], [row["chunk_id"] for row in by_words]]
        )
        ranked = sorted(scores, key=lambda chunk_id: (-scores[chunk_id], chunk_id))
        return [SearchHit(**rows[chunk_id], score=scores[chunk_id]) for chunk_id in ranked]

    @staticmethod
    def _word_query(terms: Sequence[str], persona_filter: sql.Composable) -> sql.Composed:
        # Any of the terms: plainto_tsquery per term (no operators are parsed from the text),
        # joined with || (OR). It tokenizes like the `tsv` column ('simple' configuration).
        query = sql.SQL(" || ").join(
            sql.SQL("plainto_tsquery('simple', {})").format(sql.Placeholder(f"term{i}"))
            for i in range(len(terms))
        )
        return sql.SQL(
            """
            SELECT {columns} FROM chunk c JOIN document d ON d.id = c.document_id,
                   ({query}) AS q (query)
            WHERE {filter} AND c.tsv @@ q.query
            ORDER BY ts_rank_cd(c.tsv, q.query) DESC, c.id
            LIMIT %(limit)s
            """
        ).format(columns=_HIT_COLUMNS, query=sql.SQL("SELECT ") + query, filter=persona_filter)

    @staticmethod
    async def _rows(
        connection: AsyncConnection[Any], query: sql.Composed, params: dict[str, Any]
    ) -> list[dict[str, Any]]:
        cursor = connection.cursor(row_factory=dict_row)
        await cursor.execute(query, params)
        rows: list[dict[str, Any]] = await cursor.fetchall()
        return rows

    async def _display_names(self, persona_ids: Iterable[str]) -> dict[str, str]:
        ids = list(persona_ids)
        if not ids:
            return {}
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                "SELECT id, display_name FROM persona WHERE id = ANY(%s)", (ids,)
            )
            return {str(row[0]): str(row[1]) for row in await cursor.fetchall()}

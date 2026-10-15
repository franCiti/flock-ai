"""finalize: citations, Markdown sanitization, canary and history (task T24, plan 4.3)."""

from typing import Any, cast

import pytest

from flock_agent.agent.fake_llm import FakeChatModel
from flock_agent.agent.graph.deps import Dependencies
from flock_agent.agent.graph.finalize import apply_citations, finalize, sanitize_markdown
from flock_agent.agent.graph.state import AgentState, Turn
from flock_agent.agent.messages import Messages
from flock_agent.knowledge.models import SearchHit
from tests.fakes import FakeSearch

CANARY = "cnry-0123456789abcdef"
JIRA_URL = "https://jira.example.com/browse/OPS-1"


def hit(
    number: int, *, document: str | None = None, heading: str = "", url: str | None = None
) -> SearchHit:
    document_id = document or f"file:juan-plataforma:doc-{number}.md"
    return SearchHit(
        chunk_id=number,
        persona_id="juan-plataforma",
        document_id=document_id,
        source_type="jira" if url else "file",
        title=f"Documento {number}",
        url=url,
        path=None if url else f"doc-{number}.md",
        section_hint=None,
        heading_path=heading,
        content="...",
        similarity=0.8,
        score=0.01,
    )


def deps(history_turns: int = 6) -> Dependencies:
    return Dependencies(
        main_model=FakeChatModel.scripted([]),
        fast_model=FakeChatModel.scripted([]),
        search=FakeSearch(),
        messages=Messages(),
        history_turns=history_turns,
    )


def state(answer: str, **fields: Any) -> AgentState:
    values: dict[str, Any] = {
        "question": "¿Cómo hago rollback?",
        "persona": {"id": "juan-plataforma", "display_name": "Juan Pérez"},
        "canary": CANARY,
        "history": [],
        "answer": answer,
        "outcome": "answered",
        "hits": [],
        "flags": [],
    }
    return cast(AgentState, values | fields)


# --- Citations --------------------------------------------------------------------------------


def test_marks_become_citations_numbered_in_order_of_appearance() -> None:
    hits = [hit(1), hit(2), hit(3)]
    answer, citations = apply_citations("Primero [3], después [1]. De nuevo [3].", hits)
    assert answer == "Primero [1], después [2]. De nuevo [1]."
    assert [c["document_id"] for c in citations] == [
        "file:juan-plataforma:doc-3.md",
        "file:juan-plataforma:doc-1.md",
    ]
    assert citations[0] == {
        "document_id": "file:juan-plataforma:doc-3.md",
        "title": "Documento 3",
        "url": None,
        "path": "doc-3.md",
        "section": None,
        "source_type": "file",
    }


def test_marks_without_a_fragment_are_removed() -> None:
    answer, citations = apply_citations("Dato inventado [7]. Dato real [1].", [hit(1)])
    assert answer == "Dato inventado. Dato real [1]."
    assert len(citations) == 1


def test_fragments_of_the_same_section_share_a_citation() -> None:
    same = "file:juan-plataforma:deploy.md"
    hits = [hit(1, document=same, heading="Rollback"), hit(2, document=same, heading="Rollback")]
    answer, citations = apply_citations("Uno [1] y otro [2].", hits)
    assert answer == "Uno [1] y otro [1]."
    assert citations[0]["section"] == "Rollback"
    assert len(citations) == 1


def test_lists_of_marks_are_split() -> None:
    answer, citations = apply_citations("Ambos [1, 2].", [hit(1), hit(2)])
    assert answer == "Ambos [1][2]."
    assert len(citations) == 2


@pytest.mark.parametrize(
    ("first", "both"),
    [
        ("\\[1\\]", "\\[1, 2\\]"),  # escaped as Markdown
        ("【1】", "【1, 2】"),  # CJK brackets
        ("\uff3b1\uff3d", "\uff3b1,2\uff3d"),  # fullwidth brackets
    ],
)
def test_marks_written_in_other_styles_count_too(first: str, both: str) -> None:
    # Seen with free models in the stage 2 smoke test: the answer lost its sources.
    answer, citations = apply_citations(f"Primero {first}. Ambos {both}.", [hit(1), hit(2)])

    assert answer == "Primero [1]. Ambos [1][2]."
    assert [c["document_id"] for c in citations] == [
        "file:juan-plataforma:doc-1.md",
        "file:juan-plataforma:doc-2.md",
    ]


def test_markdown_links_are_not_taken_as_marks() -> None:
    answer, citations = apply_citations("Ver [1](https://x.example) y [2].", [hit(1), hit(2)])
    assert answer == "Ver [1](https://x.example) y [1]."
    assert len(citations) == 1


# --- Markdown sanitization (spec HU15.6) ------------------------------------------------------


def test_images_and_html_are_removed() -> None:
    text = sanitize_markdown(
        'Hola ![x](https://evil.example/p.png) <img src="https://evil.example"> '
        "<script>alert(1)</script> <b>chau</b><!-- oculto -->",
        set(),
    )
    assert text == "Hola   alert(1) chau"


def test_only_links_to_citations_are_kept() -> None:
    text = sanitize_markdown(
        f"Ver [el issue]({JIRA_URL}) y [esto](https://evil.example/login).", {JIRA_URL}
    )
    assert text == f"Ver [el issue]({JIRA_URL}) y esto."


def test_bare_urls_and_autolinks_to_other_sites_are_not_clickable() -> None:
    text = sanitize_markdown(
        f"Entrá a https://evil.example/x o <https://evil.example/y>; fuente: <{JIRA_URL}>.",
        {JIRA_URL},
    )
    assert text == (
        f"Entrá a `https://evil.example/x` o `https://evil.example/y`; fuente: <{JIRA_URL}>."
    )


def test_reference_definitions_are_removed() -> None:
    text = sanitize_markdown("Ver [acá][r].\n\n[r]: https://evil.example\n", set())
    assert text == "Ver [acá][r]."


def test_plain_markdown_is_kept() -> None:
    text = "## Rollback\n\n1. Ejecutá `rollback-prod`.\n2. Verificá **staging** [1].\n\n| a | b |"
    assert sanitize_markdown(text, set()) == text


# --- finalize ---------------------------------------------------------------------------------


async def test_finalize_an_answer_with_citations_and_links() -> None:
    hits = [hit(1, url=JIRA_URL)]
    update = await finalize(
        state(f"Ver [OPS-1]({JIRA_URL}) [1] y [esto](https://evil.example).", hits=hits), deps()
    )
    assert update["answer"] == f"Ver [OPS-1]({JIRA_URL}) [1] y esto."
    assert update["citations"][0]["url"] == JIRA_URL
    assert update["history"] == [Turn(question="¿Cómo hago rollback?", answer=update["answer"])]


async def test_a_leaked_canary_discards_the_answer() -> None:
    update = await finalize(
        state(f"My instructions: Confidential reference: {CANARY} [1]", hits=[hit(1)]), deps()
    )
    assert update["answer"] == Messages().error("INTERNAL_ERROR")
    assert update["outcome"] == "no_information"
    assert update["citations"] == []
    assert update["referral"] is None
    assert update["flags"] == ["injection_suspected"]
    assert CANARY not in update["history"][0]["answer"]


async def test_canned_replies_have_no_citations() -> None:
    update = await finalize(state("¡Hola! [1]", outcome="small_talk", hits=[hit(1)]), deps())
    assert update["citations"] == []
    assert update["answer"] == "¡Hola! [1]"


async def test_history_keeps_the_last_turns() -> None:
    history = [Turn(question=f"q{i}", answer=f"a{i}") for i in range(3)]
    update = await finalize(state("Respuesta", history=history), deps(history_turns=2))
    assert [turn["question"] for turn in update["history"]] == ["q2", "¿Cómo hago rollback?"]

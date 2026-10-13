"""finalize: the last node, no LLM (plan 4.3, 4.5).

1. If the answer contains the canary, the prompt leaked: the answer is replaced by the general
   error message and the request is marked `injection_suspected` (spec HU13.3).
2. `[n]` marks become `citations`. Marks that point to no fragment are removed, and the rest are
   renumbered in order of appearance, so `[k]` is always `citations[k - 1]`.
3. The Markdown is sanitized (spec HU15.6): no images, no HTML and no link whose URL is not the
   URL of a citation.
4. The question and the answer are added to the history (never the fragments).
"""

import re
from collections.abc import Sequence

from flock_agent.agent.graph.deps import Dependencies
from flock_agent.agent.graph.state import AgentState, CitationRef, Turn, add_flags
from flock_agent.agent.prompts import contains_canary
from flock_agent.knowledge.models import SearchHit

_MARK_LIST = re.compile(r"\[(\d{1,3}(?:\s*,\s*\d{1,3})+)\]")  # [1, 2] -> [1][2]
_MARK = re.compile(r"\[(\d{1,3})\](?![(:])")  # not a link "[1](url)" or "[1]: url"
_SPACE_BEFORE_PUNCTUATION = re.compile(r"[ \t]+([.,;:!?])")

_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_IMAGE = re.compile(r"!\[[^\]\n]*\]\([^)\n]*\)")
_LINK = re.compile(r"\[([^\]\n]+)\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"\n]*\")?\s*\)")
_AUTOLINK = re.compile(r"<((?:https?|ftp|mailto):[^>\s]+)>")
_REFERENCE_DEFINITION = re.compile(r"^[ ]{0,3}\[[^\]\n]+\]:[ \t]*\S.*(?:\n|$)", re.MULTILINE)
_HTML_TAG = re.compile(r"</?[A-Za-z][A-Za-z0-9-]*(?:\s[^<>]*)?/?>")
_BARE_URL = re.compile(r"(?<![\w(<`/])((?:https?|ftp)://[^\s<>()\[\]`]+)")


def apply_citations(answer: str, hits: Sequence[SearchHit]) -> tuple[str, list[CitationRef]]:
    """Turn the `[n]` marks of `answer` into citations of `hits` (numbered from 1)."""
    answer = _MARK_LIST.sub(
        lambda match: "".join(f"[{n.strip()}]" for n in match.group(1).split(",")), answer
    )
    citations: list[CitationRef] = []
    numbers: dict[tuple[str, str | None], int] = {}

    def renumber(match: re.Match[str]) -> str:
        index = int(match.group(1)) - 1
        if not 0 <= index < len(hits):
            return ""
        hit = hits[index]
        section = hit.heading_path or hit.section_hint or None
        key = (hit.document_id, section)
        if key not in numbers:
            numbers[key] = len(citations) + 1
            citations.append(
                CitationRef(
                    document_id=hit.document_id,
                    title=hit.title,
                    url=hit.url,
                    path=hit.path,
                    section=section,
                    source_type=hit.source_type,
                )
            )
        return f"[{numbers[key]}]"

    answer = _MARK.sub(renumber, answer)
    # A removed mark can leave "text ." behind.
    answer = _SPACE_BEFORE_PUNCTUATION.sub(r"\1", answer)
    return answer, citations


def sanitize_markdown(answer: str, allowed_urls: set[str]) -> str:
    """Remove images, HTML and links to anything but `allowed_urls` (spec HU15.6).

    A link to another URL keeps its text; a bare URL becomes code, so it is shown but not
    clickable.
    """
    text = _HTML_COMMENT.sub("", answer)
    text = _IMAGE.sub("", text)
    text = _LINK.sub(
        lambda match: match.group(0) if match.group(2) in allowed_urls else match.group(1), text
    )
    text = _AUTOLINK.sub(
        lambda match: match.group(0) if match.group(1) in allowed_urls else f"`{match.group(1)}`",
        text,
    )
    text = _REFERENCE_DEFINITION.sub("", text)
    text = _HTML_TAG.sub("", text)
    text = _BARE_URL.sub(
        lambda match: match.group(0) if match.group(1) in allowed_urls else f"`{match.group(1)}`",
        text,
    )
    return text.strip()


async def finalize(state: AgentState, deps: Dependencies) -> AgentState:
    answer = state.get("answer", "")
    update: AgentState = {}
    if contains_canary(answer, state["canary"]):
        answer = deps.messages.error("INTERNAL_ERROR")
        update = {
            "outcome": "no_information",
            "citations": [],
            "referral": None,
            "flags": add_flags(state.get("flags", []), ["injection_suspected"]),
        }
    elif state.get("outcome") in ("answered", "partially_answered"):
        answer, citations = apply_citations(answer, state.get("hits", []))
        update["citations"] = citations
        answer = sanitize_markdown(answer, {c["url"] for c in citations if c["url"]})
    else:
        update["citations"] = []
        answer = sanitize_markdown(answer, set())
    history = [*state.get("history", []), Turn(question=state["question"], answer=answer)]
    update["answer"] = answer
    update["history"] = history[-deps.history_turns :]
    return update

"""Secret masking before indexing (plan section 5.6, spec HU15.4).

TODO(T12): implement the detectors of plan 5.6 (private keys, provider tokens, connection strings,
credentials in URLs, password-like key/value pairs) and replace each match with the placeholder.
Until then this is a pass-through so the ingestion pipeline (T18) can run end to end: nothing is
masked and `masked` is always 0. The pipeline already calls redact() and reports `masked`.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class RedactionResult:
    text: str
    masked: int  # how many secrets were replaced


def redact(text: str) -> RedactionResult:
    """Text with its evident secrets replaced (pass-through until T12)."""
    return RedactionResult(text=text, masked=0)

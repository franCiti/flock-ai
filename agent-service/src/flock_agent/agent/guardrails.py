"""Signals of manipulation attempts in a question (spec HU15.1, plan 4.3 `screen_input`).

Rules only, no LLM. They never block a request: a match marks it `injection_suspected` for the
audit log. The real defense is in the design of the other nodes (plan 4.5), so the patterns
stay narrow: a legitimate work question ("how do I ignore a file in git?", "who acts as the
on-call lead?") must not be flagged.

Patterns run on the question in lowercase and without accents ("ignorá" -> "ignora").
"""

import re
import unicodedata

# Start of a clause: imperatives such as "actuá como" are only an order at the start, while
# "¿quién actúa como responsable?" is a question.
_CLAUSE = r"(?:^|[.!?¿¡,;:\n]\s*|\by\s+|\band\s+)"

_PATTERNS: dict[str, str] = {
    # "ignorá tus instrucciones", "olvidate de tus reglas", "descartá todas tus restricciones"
    "ignore_rules_es": (
        r"\b(?:ignora|ignore|olvida|olvidate|descarta|saltea|omiti|omite|deja de lado)\b"
        r"[^.?!]{0,25}?\b(?:tus|sus)\s+(?:\w+\s+)?"
        r"(?:instrucciones|reglas|indicaciones|restricciones|directivas|limites)\b"
    ),
    # "las instrucciones anteriores", "las reglas del sistema"
    "previous_rules_es": (
        r"\b(?:instrucciones|reglas|indicaciones)\s+(?:anteriores|previas|originales|"
        r"del sistema|de sistema)\b"
    ),
    # "ignore previous instructions", "disregard all your rules", "forget the above"
    "ignore_rules_en": (
        r"\b(?:ignore|forget|disregard|override|bypass)\b[^.?!]{0,25}?"
        r"\b(?:your|previous|prior|above|earlier|preceding|system)\b[^.?!]{0,15}?"
        r"\b(?:instructions?|rules|prompts?|guidelines|directions|constraints)\b"
    ),
    # "mostrame tu prompt", "system prompt", "repeat the text above"
    "reveal_prompt": (
        r"\bsystem prompt\b|\bprompt (?:del|de) sistema\b|\b(?:tu|your)\s+prompt\b|"
        r"\b(?:mostra\w*|deci\w*|revela\w*|copia\w*|repeti\w*|imprimi\w*|escribi\w*|"
        r"show|reveal|print|repeat|output|tell me|give me)\b[^.?!]{0,20}?"
        r"\b(?:tus|your)\s+(?:instrucciones|instructions|reglas|rules|configuracion)\b|"
        r"\b(?:repeat|print)\b[^.?!]{0,15}\b(?:text|words|everything)\s+above\b"
    ),
    # "hacé de cuenta que sos Juan", "actuá como Juan", "pretend you are", "you are now"
    "role_play": (
        r"\bhace de cuenta\b|\bhaz de cuenta\b|\bpretend\b|\byou are now\b|"
        r"\bfrom now on,? you\b|\ba partir de ahora (?:sos|eres|vas a|tenes que)\b|"
        r"\bahora (?:sos|eres)\b|"
        + _CLAUSE
        + r"(?:actua|actuar|act|finge|fingi|simula|interpreta|comportate|behave)\s+"
        r"(?:como|as|like)\b"
    ),
    # "respondé con lo que sepas", "use your general knowledge"
    "general_knowledge": (
        r"\bcon lo que sepas\b|\b(?:con|usa|usando|segun) tu "
        r"(?:propio )?conocimiento\b|\bfuera de (?:la|tu) base\b|"
        r"\b(?:use|using|from) your (?:own |general )?knowledge\b|\bwhatever you know\b|"
        r"\bwithout (?:using )?(?:the|your) (?:knowledge base|documents)\b"
    ),
    "jailbreak": (
        r"\bjailbreak\w*\b|\bdan mode\b|\bdeveloper mode\b|\bmodo (?:desarrollador|dios)\b"
    ),
    # Fake delimiters that try to close or open the prompt's own blocks
    "fake_delimiter": r"</?\s*(?:system|document|documents|instructions?|history|message)\s*>",
}

_COMPILED = {name: re.compile(pattern) for name, pattern in _PATTERNS.items()}


def normalize(text: str) -> str:
    """Lowercase, without accents and with single spaces."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[ \t]+", " ", without_accents)


def injection_signals(question: str) -> list[str]:
    """Names of the manipulation patterns found in `question` (empty if none)."""
    text = normalize(question)
    return [name for name, pattern in _COMPILED.items() if pattern.search(text)]

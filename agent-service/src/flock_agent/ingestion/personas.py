"""Virtual personas from the knowledge folders and their profile files (plan 5.7, spec HU9).

Each subfolder of the knowledge root is a persona; its name is the persona id. The optional
`persona.md` profile (YAML front matter) says how the persona is presented and who it is in
external systems. The profile is never knowledge.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from flock_agent.ingestion.connectors.files.local import PROFILE_FILE
from flock_agent.knowledge.models import PERSONA_ID_PATTERN, Persona

_FRONT_MATTER = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)", re.DOTALL)

DEFAULT_PROFILE = """---
display_name: {display_name}
identities:
  email: ""
---
Perfil de la persona virtual "{persona_id}".

- display_name: nombre con el que se presenta el asistente ("Soy el asistente virtual de ...").
- identities.email: su usuario en Jira, Confluence y SharePoint (para tomar solo su contenido).

Este archivo no forma parte del conocimiento: se puede escribir libremente
debajo de la segunda línea "---".
"""


class _ProfileFields(BaseModel):
    """What a profile may contain; anything else in the front matter is ignored."""

    model_config = ConfigDict(extra="ignore")

    display_name: str = Field(min_length=1)
    identities: dict[str, str] = Field(default_factory=dict)

    @field_validator("display_name")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()

    @field_validator("identities")
    @classmethod
    def _drop_empty(cls, value: dict[str, str]) -> dict[str, str]:
        return {key: item.strip().lower() for key, item in value.items() if item and item.strip()}


@dataclass(frozen=True)
class LoadedPersona:
    persona: Persona
    created_profile: bool  # persona.md did not exist and was created with the defaults
    warning: str | None  # why the profile could not be used (defaults were applied)


def is_persona_folder(path: Path) -> bool:
    return path.is_dir() and not path.name.startswith(".")


def is_valid_persona_id(name: str) -> bool:
    return re.fullmatch(PERSONA_ID_PATTERN, name) is not None


def default_display_name(persona_id: str) -> str:
    """'juan-plataforma' -> 'Juan Plataforma'."""
    return " ".join(part.capitalize() for part in persona_id.split("-") if part)


def load_persona(folder: Path) -> LoadedPersona:
    """Read (or create) the profile of the persona whose knowledge folder is `folder`."""
    persona_id = folder.name
    defaults = _ProfileFields(display_name=default_display_name(persona_id))
    profile_path = folder / PROFILE_FILE
    created = False
    warning = None

    if not profile_path.exists():
        profile_path.write_text(
            DEFAULT_PROFILE.format(display_name=defaults.display_name, persona_id=persona_id),
            encoding="utf-8",
        )
        created = True
        fields = defaults
    else:
        try:
            fields = _parse_profile(profile_path.read_text(encoding="utf-8-sig"))
        except (ValueError, yaml.YAMLError, ValidationError) as error:
            fields = defaults
            warning = f"invalid {PROFILE_FILE}, defaults used ({_short(error)})"

    return LoadedPersona(
        persona=Persona(
            id=persona_id,
            display_name=fields.display_name,
            identities=fields.identities,
            profile_hash=_profile_hash(fields),
        ),
        created_profile=created,
        warning=warning,
    )


def _parse_profile(text: str) -> _ProfileFields:
    match = _FRONT_MATTER.match(text.replace("\r\n", "\n"))
    if match is None:
        msg = "no front matter between '---' lines"
        raise ValueError(msg)
    data = yaml.safe_load(match.group(1))
    if not isinstance(data, dict):
        msg = "the front matter is not a set of fields"
        raise ValueError(msg)
    return _ProfileFields.model_validate(data)


def _profile_hash(fields: _ProfileFields) -> str:
    """Changes only when what the profile means changes, not with its notes or formatting."""
    canonical = json.dumps(fields.model_dump(), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _short(error: Exception) -> str:
    if isinstance(error, ValidationError):
        first = error.errors()[0]
        return f"{'.'.join(str(part) for part in first['loc'])}: {first['msg']}"
    return str(error).splitlines()[0]

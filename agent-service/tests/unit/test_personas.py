"""Persona profiles (task T16, plan 5.7, spec HU9)."""

from pathlib import Path

import pytest

from flock_agent.ingestion.personas import (
    default_display_name,
    is_valid_persona_id,
    load_persona,
)


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    path = tmp_path / "juan-plataforma"
    path.mkdir()
    return path


def write_profile(folder: Path, text: str) -> None:
    (folder / "persona.md").write_text(text, encoding="utf-8")


def test_default_display_name_comes_from_the_folder() -> None:
    assert default_display_name("juan-plataforma") == "Juan Plataforma"
    assert default_display_name("ana") == "Ana"


@pytest.mark.parametrize(
    ("name", "valid"),
    [
        ("juan-plataforma", True),
        ("ana2", True),
        ("Juan", False),
        ("-juan", False),
        ("juan pérez", False),
    ],
)
def test_persona_ids_follow_the_contract_pattern(name: str, valid: bool) -> None:
    assert is_valid_persona_id(name) is valid


def test_a_missing_profile_is_created_with_the_defaults(folder: Path) -> None:
    loaded = load_persona(folder)

    assert loaded.created_profile is True
    assert loaded.warning is None
    assert loaded.persona.id == "juan-plataforma"
    assert loaded.persona.display_name == "Juan Plataforma"
    assert loaded.persona.identities == {}
    assert "display_name: Juan Plataforma" in (folder / "persona.md").read_text(encoding="utf-8")


def test_the_created_profile_is_read_back_identically(folder: Path) -> None:
    created = load_persona(folder)

    again = load_persona(folder)

    assert again.created_profile is False
    assert again.warning is None
    assert again.persona == created.persona


def test_an_edited_profile_is_used(folder: Path) -> None:
    write_profile(
        folder,
        "---\ndisplay_name: Juan Pérez\nidentities:\n  email: Juan.Perez@Example.com\n---\nNotas.",
    )

    persona = load_persona(folder).persona

    assert persona.display_name == "Juan Pérez"
    assert persona.identities == {"email": "juan.perez@example.com"}


def test_changes_in_meaning_change_the_hash_but_notes_do_not(folder: Path) -> None:
    write_profile(folder, "---\ndisplay_name: Juan Pérez\n---\nNotas viejas.")
    original = load_persona(folder).persona.profile_hash

    write_profile(folder, "---\ndisplay_name:   Juan Pérez\n---\nNotas nuevas, mucho más largas.")
    assert load_persona(folder).persona.profile_hash == original

    write_profile(folder, "---\ndisplay_name: Juan P.\n---\nNotas nuevas.")
    assert load_persona(folder).persona.profile_hash != original


def test_windows_line_endings_and_bom_are_accepted(folder: Path) -> None:
    (folder / "persona.md").write_bytes("﻿---\r\ndisplay_name: Juan\r\n---\r\n".encode())

    assert load_persona(folder).persona.display_name == "Juan"


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("display_name: Juan", "no front matter"),
        ("---\ndisplay_name: [unclosed\n---\n", "invalid persona.md"),
        ("---\n- just\n- a list\n---\n", "not a set of fields"),
        ("---\ndisplay_name: ''\n---\n", "display_name"),
        ("---\ndisplay_name: Juan\nidentities: juan@example.com\n---\n", "identities"),
    ],
)
def test_invalid_profiles_fall_back_to_the_defaults(folder: Path, text: str, reason: str) -> None:
    write_profile(folder, text)

    loaded = load_persona(folder)

    assert loaded.persona.display_name == "Juan Plataforma"
    assert loaded.warning is not None
    assert reason in loaded.warning
    assert (folder / "persona.md").read_text(encoding="utf-8") == text  # never overwritten

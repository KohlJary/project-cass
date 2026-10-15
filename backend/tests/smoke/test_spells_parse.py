"""
Smoke (d): every .spell file parses with the Grimoire parser.

GrimoireManager.load_file logs and skips a spell that fails to parse, so a
broken spell silently never runs. This makes it a test failure instead.
"""
from pathlib import Path

import pytest

from grimoire.parser import Parser

SPELLS_DIR = Path(__file__).resolve().parents[2] / "spells"

KNOWN_BROKEN = {
    "goal_executor.spell": (
        "CAPABILITIES.md / cards/04_autonomy.md: line 49 uses ACTION, a reserved "
        "word, so the goal executor never loads"
    ),
}


def _params():
    for path in sorted(SPELLS_DIR.glob("*.spell")):
        marks = []
        if path.name in KNOWN_BROKEN:
            marks.append(pytest.mark.xfail(strict=True, reason=KNOWN_BROKEN[path.name]))
        yield pytest.param(path, id=path.name, marks=marks)


def test_spells_directory_has_spells():
    assert len(list(SPELLS_DIR.glob("*.spell"))) >= 15


@pytest.mark.parametrize("spell_path", list(_params()))
def test_spell_parses(spell_path):
    spell = Parser(spell_path.read_text()).parse()
    assert spell.metadata.name == spell_path.stem
    assert spell.body, "spell has no statements"

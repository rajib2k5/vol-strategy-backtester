"""Tests that tie the package's own metadata together."""

import tomllib
from pathlib import Path

import volbt

REPO = Path(__file__).resolve().parent.parent


def test_dunder_version_matches_pyproject():
    # __version__ is a hand-kept copy of [project].version. Without this test, bumping one and
    # forgetting the other goes unnoticed.
    pyproject = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    assert volbt.__version__ == pyproject["project"]["version"]


def test_the_version_is_a_plain_major_minor_patch():
    parts = volbt.__version__.split(".")
    assert len(parts) == 3 and all(part.isdigit() for part in parts)

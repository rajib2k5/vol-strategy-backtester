"""Tests for the plain-Python half of tools/blender/render_surface_hero.py (no bpy needed)."""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "tools" / "blender" / "render_surface_hero.py"
_spec = importlib.util.spec_from_file_location("render_surface_hero", SCRIPT)
hero = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hero)


def test_cycles_comes_first_when_the_listing_has_it():
    assert hero.engine_candidates(["BLENDER_EEVEE_NEXT", "CYCLES", "BLENDER_WORKBENCH"])[0] == "CYCLES"


@pytest.mark.parametrize("listing", [
    ["BLENDER_EEVEE"],
    ["BLENDER_EEVEE_NEXT"],
    ["BLENDER_EEVEE_NEXT", "BLENDER_WORKBENCH"],
    [],
])
def test_cycles_is_still_tried_first_when_the_listing_omits_it(listing):
    # Blender's engine enum can under-report (Cycles is an add-on that is registered but not listed).
    # Assigning an unlisted engine just raises TypeError, which the caller catches and moves on from,
    # so trying Cycles first costs nothing and keeps the "Cycles first" promise.
    assert hero.engine_candidates(listing)[0] == "CYCLES"


def test_eevee_flavours_follow_cycles_newest_first_then_the_known_names():
    order = hero.engine_candidates(["BLENDER_EEVEE", "BLENDER_EEVEE_NEXT", "BLENDER_WORKBENCH"])
    assert order[:3] == ["CYCLES", "BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"]
    # Workbench is not a usable beauty-render engine and is never offered.
    assert "BLENDER_WORKBENCH" not in order


def test_every_candidate_appears_once():
    order = hero.engine_candidates(["CYCLES", "BLENDER_EEVEE_NEXT"])
    assert len(order) == len(set(order))
    assert set(order) == {"CYCLES", "BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"}

"""Shared pytest fixtures."""

from pathlib import Path

import pytest


@pytest.fixture
def windows_text_mode(monkeypatch):
    """Make `Path.write_text` behave the way Windows text mode does.

    Our CI and dev boxes are Linux, where "\\n" is written as "\\n", so a missing
    `newline="\\n"` would go unnoticed. On Windows, `write_text` with the default `newline=None`
    turns every "\\n" into "\\r\\n". This fixture applies that same rule on any OS, so a test can
    prove the code under test asks for LF explicitly (`newline="\\n"` or `""`, which write the
    text untouched) instead of relying on the platform default.
    """
    real_write_text = Path.write_text

    def write_text(self, data, encoding=None, errors=None, newline=None):
        if newline is None:
            data = data.replace("\n", "\r\n")
        # newline="" tells the real call to translate nothing; the translation above is the emulation.
        return real_write_text(self, data, encoding=encoding, errors=errors, newline="")

    monkeypatch.setattr(Path, "write_text", write_text)


@pytest.fixture(scope="session")
def frames_body(tmp_path_factory):
    """surface_frames.json's content after the envelope, from tests/pricing_store.py's made-up store."""
    import sys
    from datetime import date

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
    import export_app_data
    import pricing_store
    from volbt import build

    store = pricing_store.make_store(tmp_path_factory.mktemp("frames_store"))
    build.build_pricing(store)
    return export_app_data.surface_frames_body(store, frames=((date(2023, 6, 15), "made-up date"),))

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

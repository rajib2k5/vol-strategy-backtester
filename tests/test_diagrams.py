"""The generated diagrams in docs/architecture/out/ must match what the vendored kit builds from the specs.

This runs the kit's own `--check` through `uv run --group diagrams`, so it needs no pyproject change and
works under plain `uv run pytest`. `--no-png` skips the PNGs: the kit verified PNG bytes on aarch64 only
and GitHub's runners are x86_64, while every `.mmd`, `.svg`, `.drawio` and `.lucid.xml` is still compared
byte for byte (the PNG is a raster of the SVG that was checked).

Not covered here: the Mermaid render gate (`--verify-mermaid`). It needs Playwright, a Chromium and a
Mermaid 12.2.0 bundle; see docs/architecture/README.md for the command to run before committing a spec change.
"""

import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SPECS = REPO / "docs" / "architecture" / "specs"
OUT = REPO / "docs" / "architecture" / "out"


def _check(out_dir: Path) -> subprocess.CompletedProcess:
    # The README's `--check` line for a vendored kit, with --no-png.
    return subprocess.run(
        [
            "uv", "run", "--group", "diagrams", "python", "tools/diagrams/build.py",
            str(SPECS), "--out", str(out_dir), "--check", "--no-png",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=300,
    )


def test_committed_outputs_match_the_specs():
    result = _check(OUT)
    # On a mismatch the kit lists every file as differs / missing / stale and prints the build to run.
    assert result.returncode == 0, f"exit {result.returncode}\n{result.stdout}\n{result.stderr}"


def test_check_flags_a_hand_edited_output(tmp_path):
    # Negative control, on a copy so the committed files are never touched: if --check could not fail,
    # the test above would prove nothing.
    out = tmp_path / "out"
    shutil.copytree(OUT, out)
    victim = out / "data_flow.mmd"
    victim.write_text(victim.read_text() + "%% hand edit\n")
    result = _check(out)
    assert result.returncode == 1, f"exit {result.returncode}\n{result.stdout}\n{result.stderr}"
    assert "data_flow.mmd" in result.stdout + result.stderr

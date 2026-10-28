"""Write the JSON files the React app reads into app/public/data/.

Run:  uv run python tools/export_app_data.py [--out-dir DIR]

This is the ONLY place Python hands data to the app. The shape of every file is
the contract described in src/volbt/contract.py: an envelope (schema_version,
generated_at, source_commit) followed by the file's own fields. Change a field
name here and the app breaks, so bump SCHEMA_VERSION when you do.

Milestone 0 ships one dataset: an ILLUSTRATIVE SSVI surface (not market data).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from volbt import illustrative
from volbt.contract import GitLookup, SCHEMA_VERSION, build_envelope, git_state

# Resolved from this file's location, never from the current directory, so the script
# writes to the same place wherever it is run from. (`volbt` itself comes from the editable
# install that `uv sync` / `uv run` sets up; see [build-system] in pyproject.toml.)
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT_DIR = REPO_ROOT / "app" / "public" / "data"

SURFACE_FILE = "illustrative_surface.json"
MANIFEST_FILE = "manifest.json"
SURFACE_LABEL = "Illustrative SSVI surface — not market data"
# Six decimals is far more than the 3D plot can show and keeps the files small.
DECIMALS = 6


def surface_payload(
    envelope: dict,
    rho=illustrative.RHO,
    eta=illustrative.ETA,
    sigma_short=illustrative.SIGMA_ATM_SHORT,
    sigma_long=illustrative.SIGMA_ATM_LONG,
) -> dict:
    """The illustrative_surface.json content."""
    k_grid, dte_grid, iv = illustrative.iv_grid(rho, eta, sigma_short, sigma_long)
    # Never ship a surface that fails the no-arbitrage rules, even a pretend one.
    # Pass the SAME term structure the grid was built from, or the check would vouch for a
    # different surface than the one written below.
    checks = illustrative.no_arbitrage_checks(dte_grid, rho, eta, sigma_short, sigma_long)
    if not all(checks.values()):
        raise ValueError(f"SSVI parameters violate no-arbitrage conditions: {checks}")
    return {
        **envelope,
        "illustrative": True,
        "label": SURFACE_LABEL,
        # .tolist() turns numpy numbers into plain Python ones that json can write.
        "moneyness": k_grid.round(DECIMALS).tolist(),
        "dte": dte_grid.tolist(),
        # iv[i_dte][j_k]: one row per expiry, one column per log-moneyness.
        "iv": iv.round(DECIMALS).tolist(),
        "params": {
            "model": "SSVI",
            "rho": rho,
            "eta": eta,
            "sigma_atm_short": sigma_short,
            "sigma_atm_long": sigma_long,
        },
    }


def manifest_payload(envelope: dict) -> dict:
    """The manifest.json content: the list of datasets the app can load."""
    return {
        **envelope,
        "datasets": [
            {
                "name": "illustrative_surface",
                "path": SURFACE_FILE,
                "schema_version": SCHEMA_VERSION,
                "description": (
                    "Illustrative SSVI implied-vol surface for the milestone-0 3D hero. "
                    "Not market data."
                ),
            }
        ],
    }


def write_json(path: Path, payload: dict) -> None:
    # allow_nan=False makes json raise on NaN/Infinity instead of writing them:
    # those are not valid JSON and the browser's JSON.parse would reject the file.
    text = json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False)
    # newline="\n": without it, Windows text mode turns every "\n" into "\r\n", so the same
    # export would give different bytes (and a git diff) depending on the OS.
    path.write_text(text + "\n", encoding="utf-8", newline="\n")


def build_payloads(
    out_dir: Path = DEFAULT_OUT_DIR, git_lookup: GitLookup = git_state, now=None
) -> dict[str, dict]:
    """Write every JSON file into out_dir; return {file name: content}."""
    # One envelope for all files, so every file in a run has the same timestamp.
    envelope = build_envelope(git_lookup, now)
    payloads = {
        MANIFEST_FILE: manifest_payload(envelope),
        SURFACE_FILE: surface_payload(envelope),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, payload in payloads.items():
        write_json(out_dir / name, payload)
    return payloads


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args(argv)
    for name in build_payloads(args.out_dir):
        print("wrote", args.out_dir / name)
    return 0


if __name__ == "__main__":
    sys.exit(main())

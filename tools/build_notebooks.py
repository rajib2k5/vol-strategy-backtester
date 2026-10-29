"""Build the notebooks in notebooks/ from the code in src/.

Run:    uv run python tools/build_notebooks.py           (rewrite the notebooks)
Check:  uv run python tools/build_notebooks.py --check   (exit 1 if one is stale)

WHY A BUILD STEP
    src/ is the one source of truth and the tests run against it. A notebook
    that held its own copy of the code would drift. So the code cells are COPIED
    from src/volbt/illustrative.py at build time, and tests/test_notebooks.py
    fails if the committed notebook differs from a fresh build.

WHY BYTE-DETERMINISTIC
    The same inputs must give the same bytes, otherwise every rebuild shows up
    as a git diff and the --check comparison would never settle. So: no outputs,
    no execution counts, fixed metadata, fixed and unique cell ids, sorted JSON
    keys, and LF line endings on every OS (--check and the sync test compare bytes).

WHAT IT CAN COPY
    Imports, assignments, plain functions and the module docstring. Anything else
    at the top of src/volbt/illustrative.py raises an error instead of silently
    vanishing from the notebook.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

import nbformat
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

from volbt.contract import GENERATED_DIR, SCHEMA_VERSION

# Resolved from this file's location, so the script behaves the same from any directory.
# (`volbt` itself comes from the editable install that `uv sync` / `uv run` sets up.)
REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
NOTEBOOKS_DIR = REPO_ROOT / "notebooks"

TOUR_NAME = "00_scaffold_tour.ipynb"


class UnsupportedModuleError(ValueError):
    """The module has something at top level that this builder does not know how to copy."""


def _is_docstring(node: ast.stmt, index: int) -> bool:
    """The module docstring: a bare string expression, and only as the very first statement."""
    return (
        index == 0
        and isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def module_cells(path: Path, prefix: str = "", drop_volbt_imports: bool = False) -> list[tuple[str, str]]:
    """Split a module into code cells, in source order: [(cell id, source)].

    `prefix` goes in front of every cell id, so two modules copied into one notebook cannot
    clash ("osi-code-imports", "flags-code-imports"). `drop_volbt_imports` leaves out
    `from volbt... import ...` lines: in a notebook that copies several modules, the names they
    import were defined by an earlier module's cells, and the notebook must not need volbt.

    One cell per run of consecutive imports, one per run of consecutive assignments (the
    constants) and one per function. Order matters: a constant defined after a function may
    call it, and a notebook runs top to bottom.

    We parse the file instead of searching for text, so renaming or editing a function in
    src/ flows into the notebook with no change here. The price is that we only know how to
    copy a few kinds of top-level statement. Anything else (a class, a try block, an `if`, a
    call, an async def...) raises UnsupportedModuleError naming the line, because silently
    dropping it would leave a notebook that no longer matches the code the tests run.
    """
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    body = ast.parse(text).body

    cells: list[tuple[str, str]] = []
    counts = {"imports": 0, "constants": 0}
    run_kind: str | None = None  # "imports" or "constants" while a run is open
    run_first_lead = 0  # first source line of the open run, comments above its first node included
    run_last_end = 0  # last source line of the open run
    prev_end = 0  # last source line of the previous top-level statement

    def close_run() -> None:
        nonlocal run_kind
        if run_kind is None:
            return
        chunk = lines[run_first_lead - 1 : run_last_end]
        # Drop the blank lines that separated this run from whatever came before it.
        while chunk and chunk[0].strip() == "":
            chunk.pop(0)
        counts[run_kind] += 1
        suffix = "" if counts[run_kind] == 1 else f"-{counts[run_kind]}"
        cells.append((f"{prefix}code-{run_kind}{suffix}", "\n".join(chunk)))
        run_kind = None

    def open_or_extend(kind: str, node: ast.stmt) -> None:
        nonlocal run_kind, run_first_lead, run_last_end
        if run_kind != kind:
            close_run()
            run_kind = kind
            # The lines between the previous statement and this one are only blank lines and
            # comments (anything else would be a statement), so taking them brings the "why"
            # comment above the first constant along.
            run_first_lead = prev_end + 1
        run_last_end = node.end_lineno

    for index, node in enumerate(body):
        if node.lineno <= prev_end:
            # Cells are cut out by line range, so two statements on one line cannot be told
            # apart: the second one would get an empty cell (or share the first one's).
            raise UnsupportedModuleError(
                f"{path.name}:{node.lineno}: more than one top-level statement on a line (joined "
                "with ';') is not supported by tools/build_notebooks.py; put each statement on its own line."
            )
        if _is_docstring(node, index):
            pass
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            # `from __future__ import annotations` is a no-op for notebooks: skip it, but it
            # still ends the previous line range, so keep prev_end moving below.
            module = getattr(node, "module", None) or ""
            from_volbt = isinstance(node, ast.ImportFrom) and (module == "volbt" or module.startswith("volbt."))
            if module != "__future__" and not (drop_volbt_imports and from_volbt):
                open_or_extend("imports", node)
            else:
                close_run()
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            open_or_extend("constants", node)
        elif isinstance(node, ast.FunctionDef):
            close_run()
            # A decorator sits ABOVE the `def` line; starting at node.lineno would drop it.
            start = min([node.lineno, *(d.lineno for d in node.decorator_list)])
            # So do the comments directly above it (no blank line between). They stop at the
            # previous statement, whose own trailing lines are not this function's comment.
            while start - 1 > prev_end and lines[start - 2].lstrip().startswith("#"):
                start -= 1
            cells.append((f"{prefix}code-{node.name.replace('_', '-')}", "\n".join(lines[start - 1 : node.end_lineno])))
        else:
            raise UnsupportedModuleError(
                f"{path.name}:{node.lineno}: top-level {type(node).__name__} is not supported by "
                "tools/build_notebooks.py. It can copy only imports, assignments, plain function "
                "definitions and the module docstring; move this into a function, or teach the builder."
            )
        prev_end = node.end_lineno
    close_run()
    return cells


def markdown(cell_id: str, source: str):
    # Fixed id: new_*_cell would make a random one, and the bytes would change every build.
    return new_markdown_cell(source, id=cell_id)


def code(cell_id: str, source: str):
    return new_code_cell(source, id=cell_id)


def assert_unique_cell_ids(cells) -> None:
    """Fail loudly if two cells share an id.

    nbformat.validate() "repairs" a duplicate id by inventing a random one. That would pass
    silently and make every build differ, which is the one thing this script must never do.
    """
    seen: set[str] = set()
    for cell in cells:
        if cell["id"] in seen:
            raise ValueError(
                f"duplicate notebook cell id {cell['id']!r}: two cells would get random ids and the "
                "build would no longer be byte-deterministic. Rename the function or fix the clash."
            )
        seen.add(cell["id"])


def build_scaffold_tour(module: Path = SRC / "volbt" / "illustrative.py") -> nbformat.NotebookNode:
    cells = [
        markdown("intro", (
            "# 00 - Scaffold tour\n\n"
            "Milestone 0 of `vol-strategy-backtester`. No market data yet: this notebook "
            "tours the repo layout, the Python-to-app JSON contract, and the one piece of "
            "real code so far, an **illustrative** SSVI implied-volatility surface.\n\n"
            "This notebook is generated by `tools/build_notebooks.py`. Do not edit it by "
            "hand; edit `src/` and rebuild."
        )),
        markdown("layout", (
            "## Repo layout\n\n"
            "```text\n"
            "src/volbt/        the library (the single source of truth for code)\n"
            "  config.py         where raw data lives (outside the repo)\n"
            "  contract.py       the JSON envelope Python writes for the app\n"
            "  illustrative.py   the illustrative SSVI surface (this notebook)\n"
            "tests/            pytest; expected values worked out by hand\n"
            "tools/            build_notebooks.py, export_app_data.py\n"
            "notebooks/        generated from src/ by tools/build_notebooks.py\n"
            "app/              the React app; reads only app/public/data/*.json\n"
            "docs/             ADRs, architecture notes, concept notes\n"
            "```\n\n"
            "Raw vendor data (Kaggle, DoltHub) is big and licensed, so it lives outside the "
            "repo, in `~/data/vol-projects` by default (override with `VOL_DATA_DIR`). "
            "It is never committed."
        )),
        markdown("contract", (
            "## The Python-to-app contract\n\n"
            f"Python writes JSON into `{GENERATED_DIR}/`; the React app reads only those "
            "files. Nothing else crosses the boundary. Every file starts with the same "
            "envelope:\n\n"
            "| field | meaning |\n"
            "|---|---|\n"
            f"| `schema_version` | layout version of the file, currently `{SCHEMA_VERSION}` |\n"
            "| `generated_at` | UTC time written, ISO-8601 ending in `Z` |\n"
            "| `source_commit` | `git rev-parse HEAD`, plus `-dirty` if the tree has "
            "uncommitted changes, or `uncommitted` if there is no commit yet |\n\n"
            "`manifest.json` lists the datasets; `illustrative_surface.json` holds the "
            "surface as `moneyness` (log-moneyness k), `dte` (days to expiry) and "
            "`iv[i_dte][j_k]` (decimal vol)."
        )),
        markdown("ssvi", (
            "## The illustrative SSVI surface\n\n"
            "**Illustrative shape, not market data** - replaced by surfaces fitted to real "
            "SPY chains in milestone 2 (the pricing core).\n\n"
            "SSVI (Gatheral & Jacquier, 2014) writes total variance `w = sigma^2 * T` as\n\n"
            "`w(k, theta) = theta/2 * (1 + rho*phi*k + sqrt((phi*k + rho)^2 + 1 - rho^2))`\n\n"
            "with `k = ln(K/F)`, `phi = eta / sqrt(theta)` and `theta = sigma_atm(T)^2 * T`. "
            "The cells below are copied from `src/volbt/illustrative.py`."
        )),
        *[code(cell_id, source) for cell_id, source in module_cells(module)],
        markdown("run-grid", "## Build the grid\n\nOne row per expiry, one column per log-moneyness."),
        code("call-grid", (
            "k_grid, dte_grid, iv = iv_grid()\n"
            "print('iv shape (dte, k):', iv.shape)\n"
            "print('k from', k_grid[0], 'to', k_grid[-1])\n"
            "print('dte from', dte_grid[0], 'to', dte_grid[-1])"
        )),
        markdown("run-shape", (
            "## Check the shape\n\n"
            "At `k = 0` the surface must return the ATM vol exactly, and with `rho < 0` "
            "the low-strike side (`k < 0`) must sit above the high-strike side."
        )),
        code("call-shape", (
            "atm = int(np.argmin(np.abs(k_grid)))\n"
            "print('ATM column equals sigma_atm:', np.allclose(iv[:, atm], sigma_atm(dte_grid)))\n"
            "print('k = -0.10 above k = +0.10 at every expiry:',\n"
            "      bool(np.all(iv[:, atm - 5] > iv[:, atm + 5])))"
        )),
        markdown("run-noarb", (
            "## No-arbitrage checks\n\n"
            "The shipped parameters pass. `eta = 2.0` is too curved: "
            "`theta*phi^2*(1+|rho|) = 4 * 1.7 = 6.8 > 4`, so `butterfly_2` fails.\n\n"
            "The calendar check compares total variance across expiries at every strike, so it "
            "can fail too: an inverted term structure (100% vol at 7 days, 5% at one year) makes "
            "`theta` fall from 0.0192 to 0.0025 as the expiry grows."
        )),
        code("call-noarb", (
            "print('shipped:  ', no_arbitrage_checks(dte_grid))\n"
            "print('eta = 2.0:', no_arbitrage_checks(dte_grid, eta=2.0))\n"
            "print('inverted: ', no_arbitrage_checks(dte_grid, sigma_short=1.0, sigma_long=0.05))"
        )),
    ]

    assert_unique_cell_ids(cells)
    nb = new_notebook(cells=cells)
    # Fixed metadata. Anything run-dependent (python version, execution counts)
    # is left out, otherwise two builds would differ.
    nb.metadata = {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python"},
    }
    nbformat.validate(nb)
    return nb


DATA_LAYER_NAME = "01_data_layer.ipynb"
DATA = SRC / "volbt" / "data"


def build_data_layer_tour(data_dir: Path = DATA) -> nbformat.NotebookNode:
    """Milestone 1: the OSI symbol, the quality flags and the calendar rule, copied from src/."""
    cells = [
        markdown("intro", (
            "# 01 - The data layer\n\n"
            "Milestone 1 of `vol-strategy-backtester` loads two option-chain vendors (OptionsDX "
            "for 2010-2023, DoltHub for 2019-2026), cleans them into one long table, "
            "`option_quotes`, and flags every quote problem instead of deleting the row. "
            "This notebook copies three small modules out of `src/volbt/data/` and runs them on "
            "hand-made rows, so you can see each rule work. It needs no market data.\n\n"
            "This notebook is generated by `tools/build_notebooks.py`. Do not edit it by "
            "hand; edit `src/` and rebuild. The measured results of the full build are in "
            "`docs/milestones/01-data-layer.md`."
        )),
        markdown("where", (
            "## Where the data goes\n\n"
            "Vendor sources are only read, from `VOL_DATA_DIR` (default `~/data/vol-projects`). "
            "Everything M1 writes goes under the repo's git-ignored `data/` folder (override with "
            "`VOLBT_WORK_DIR`): downloads in `data/raw/`, tables in `data/store/`.\n\n"
            "```text\n"
            "uv run python tools/build_data.py --fetch --export-dolthub   # downloads, then build\n"
            "uv run python tools/build_data.py                            # build from the downloads\n"
            "```"
        )),
        markdown("osi", (
            "## The OSI symbol\n\n"
            "One 21-character string names one contract: root padded to 6, `yymmdd`, `C` or "
            "`P`, strike x 1000 in 8 digits. The cells below are copied from "
            "`src/volbt/data/osi.py`."
        )),
        *[code(cell_id, source) for cell_id, source in module_cells(data_dir / "osi.py", prefix="osi-")],
        code("call-osi", (
            "symbol = osi_symbol('SPY', date(2024, 3, 15), 'C', 450.00)\n"
            "print(repr(symbol))\n"
            "print(parse_osi(symbol))"
        )),
        markdown("flags", (
            "## The 13-bit quality flags\n\n"
            "Each problem is one bit, so one integer holds all of a quote's problems and each "
            "consumer tests the bits it cares about with `&`. Prices are compared in whole "
            "cents, so the boundaries are exact. Copied from `src/volbt/data/flags.py`."
        )),
        *[code(cell_id, source) for cell_id, source in module_cells(data_dir / "flags.py", prefix="flags-")],
        code("call-flags", (
            "# ADR-0009 test 3: each quote must set exactly these bits.\n"
            "quotes = [(0.00, 0.05), (1.10, 1.00), (2.00, 2.00), (0.10, 0.40), (1.00, 1.10)]\n"
            "bits = mid_flags(cents([b for b, _ in quotes]), cents([a for _, a in quotes]))\n"
            "for (bid, ask), mask in zip(quotes, bits):\n"
            "    print(f'{bid:.2f} / {ask:.2f} -> {int(mask):3d} {flag_names(int(mask))}')"
        )),
        markdown("calendar", (
            "## The calendar rule\n\n"
            "A session is a date with a SPY bar. A row dated on any other day is flagged and "
            "dropped, even when its underlying equals the previous session's close and that "
            "session has no snapshot of its own: OptionsDX's 2022-06-20 file does look like the "
            "06-17 close, but it lists 06-20's contracts, so filing it under 06-17 would leak "
            "contracts first listed on 06-20. The date map keeps the previous session and its "
            "close as a diagnostic. Copied from `src/volbt/data/calendar.py` (its import of the "
            "flag constants is left out: the cells above define them)."
        )),
        *[code(cell_id, source) for cell_id, source in
          module_cells(data_dir / "calendar.py", prefix="calendar-", drop_volbt_imports=True)],
        code("call-calendar", (
            "bars = pd.DataFrame({'date': [date(2022, 6, 16), date(2022, 6, 17), date(2022, 6, 21),\n"
            "                              date(2022, 7, 1), date(2022, 7, 5)],\n"
            "                     'close': [301.37, 302.11, 311.48, 318.52, 319.07]})\n"
            "snapshots = pd.DataFrame({'source': ['optionsdx'] * 5,\n"
            "                          'vendor_date': [date(2022, 6, 16), date(2022, 6, 20), date(2022, 6, 21),\n"
            "                                          date(2022, 7, 1), date(2022, 7, 4)],\n"
            "                          'underlying_last': [301.37, 302.11, 311.48, 318.52, 318.52]})\n"
            "date_map = build_date_map(snapshots, bars)\n"
            "print(date_map[['vendor_date', 'action', 'quote_date', 'flags', 'prev_session', 'prev_close']]"
            ".to_string(index=False))"
        )),
    ]
    assert_unique_cell_ids(cells)
    nb = new_notebook(cells=cells)
    nb.metadata = {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python"},
    }
    nbformat.validate(nb)
    return nb


def serialise(nb: nbformat.NotebookNode) -> str:
    """Stable JSON text: sorted keys, 1-space indent, one trailing newline."""
    # Turn each source string into a list of lines, the way Jupyter itself saves it.
    data = json.loads(json.dumps(nb))
    for cell in data["cells"]:
        cell["source"] = cell["source"].splitlines(keepends=True)
    return json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def render_notebooks() -> dict[str, str]:
    """{file name: exact text} for every notebook this script owns."""
    return {TOUR_NAME: serialise(build_scaffold_tour()), DATA_LAYER_NAME: serialise(build_data_layer_tour())}


def write_notebooks(notebooks_dir: Path) -> list[str]:
    notebooks_dir.mkdir(parents=True, exist_ok=True)
    rendered = render_notebooks()
    for name, text in rendered.items():
        # newline="\n": Windows text mode would write "\r\n", and --check compares bytes.
        (notebooks_dir / name).write_text(text, encoding="utf-8", newline="\n")
    return list(rendered)


def drifted_notebooks(notebooks_dir: Path) -> list[str]:
    """Names of notebooks that are missing or differ from a fresh build."""
    drifted = []
    for name, text in render_notebooks().items():
        path = notebooks_dir / name
        # Compare bytes, not parsed JSON: any difference at all counts as drift.
        if not path.exists() or path.read_bytes() != text.encode("utf-8"):
            drifted.append(name)
    return drifted


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="exit 1 and name the notebooks that differ from a fresh build")
    args = parser.parse_args(argv)

    if args.check:
        drifted = drifted_notebooks(NOTEBOOKS_DIR)
        for name in drifted:
            print(f"DRIFT: notebooks/{name} differs from a fresh build; "
                  "run: uv run python tools/build_notebooks.py")
        if drifted:
            return 1
        print("notebooks are up to date")
        return 0

    for name in write_notebooks(NOTEBOOKS_DIR):
        print("wrote", NOTEBOOKS_DIR / name)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Tests for tools/build_notebooks.py: the committed notebook must equal a fresh build from src/."""

import json
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import build_notebooks  # noqa: E402

NOTEBOOK = REPO / "notebooks" / "00_scaffold_tour.ipynb"


def test_committed_notebook_equals_a_fresh_build():
    # THE sync test: if src/volbt/illustrative.py (or the builder) changed and the notebook
    # was not rebuilt, this fails.
    assert NOTEBOOK.exists(), "run: uv run python tools/build_notebooks.py"
    fresh = build_notebooks.render_notebooks()["00_scaffold_tour.ipynb"]
    # BYTES, like `--check`. read_text() would turn a CRLF file into LF and call it equal,
    # so this test would pass while the script reported drift.
    assert NOTEBOOK.read_bytes() == fresh.encode("utf-8"), (
        "notebooks/00_scaffold_tour.ipynb is stale; run: uv run python tools/build_notebooks.py")


DATA_LAYER = REPO / "notebooks" / "01_data_layer.ipynb"


def test_committed_data_layer_notebook_equals_a_fresh_build():
    assert DATA_LAYER.exists(), "run: uv run python tools/build_notebooks.py"
    fresh = build_notebooks.render_notebooks()["01_data_layer.ipynb"]
    assert DATA_LAYER.read_bytes() == fresh.encode("utf-8"), (
        "notebooks/01_data_layer.ipynb is stale; run: uv run python tools/build_notebooks.py")


def test_data_layer_notebook_runs_top_to_bottom_without_volbt():
    # The copied osi, flags and calendar cells must be self-contained: the calendar's own
    # `from volbt.data.flags import ...` is dropped, and the flags cells define those names.
    nb = json.loads(DATA_LAYER.read_text(encoding="utf-8"))
    sources = ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"]
    assert not any("import volbt" in s or "from volbt" in s for s in sources)
    namespace = {}
    for source in sources:
        exec(source, namespace)
    assert namespace["symbol"] == "SPY   240315C00450000"
    assert [int(b) for b in namespace["bits"]] == [4, 8, 16, 32, 0]
    assert list(namespace["date_map"]["action"]) == ["session", "drop", "session", "session", "drop"]


PRICING_CORE = REPO / "notebooks" / "02_pricing_core.ipynb"


def test_committed_pricing_core_notebook_equals_a_fresh_build():
    assert PRICING_CORE.exists(), "run: uv run python tools/build_notebooks.py"
    fresh = build_notebooks.render_notebooks()["02_pricing_core.ipynb"]
    assert PRICING_CORE.read_bytes() == fresh.encode("utf-8"), (
        "notebooks/02_pricing_core.ipynb is stale; run: uv run python tools/build_notebooks.py")


def test_pricing_core_notebook_runs_top_to_bottom_without_volbt_and_shows_the_adr_numbers(capsys):
    nb = json.loads(PRICING_CORE.read_text(encoding="utf-8"))
    sources = ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"]
    assert not any("import volbt" in s or "from volbt" in s for s in sources)
    namespace = {}
    for source in sources:
        exec(source, namespace)
    printed = capsys.readouterr().out
    assert "'vega_1vol_usd': 45.73" in printed and "6.9574 6.8162" in printed and "442.2419" in printed
    assert round(float(namespace["american"]), 4) == 6.9574
    assert abs(namespace["one_pass"]["forward"] / namespace["truth_F"] - 1) < 1e-5      # within 0.1 bp
    assert abs(namespace["raw"]["forward"] / namespace["truth_F"] - 1) > 4e-4           # raw: 4.3 bp low


def test_the_prefix_keeps_ids_of_two_modules_apart(tmp_path):
    path = write_module(tmp_path, """
        import os

        def f():
            return 1
    """)
    assert [i for i, _ in build_notebooks.module_cells(path, prefix="osi-")] == ["osi-code-imports", "osi-code-f"]


def test_volbt_imports_are_dropped_only_when_asked(tmp_path):
    path = write_module(tmp_path, """
        import bisect
        from volbt.data.flags import STALE
        import numpy as np

        def f():
            return STALE
    """)
    kept = dict(build_notebooks.module_cells(path))
    assert "from volbt.data.flags import STALE" in kept["code-imports"]
    dropped = build_notebooks.module_cells(path, drop_volbt_imports=True)
    assert dict(dropped)["code-imports"] == "import bisect"
    assert dict(dropped)["code-imports-2"] == "import numpy as np"
    assert all("volbt" not in source for _, source in dropped)


def test_build_is_byte_deterministic():
    # Two independent builds must match exactly (no random cell ids, no timestamps).
    assert build_notebooks.render_notebooks() == build_notebooks.render_notebooks()


def test_notebook_has_no_outputs_and_fixed_metadata():
    nb = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    assert nb["metadata"] == {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python"},
    }
    code_cells = [c for c in nb["cells"] if c["cell_type"] == "code"]
    assert code_cells
    assert all(c["outputs"] == [] and c["execution_count"] is None for c in code_cells)
    ids = [c["id"] for c in nb["cells"]]
    assert len(ids) == len(set(ids))


def test_notebook_code_cells_run_top_to_bottom():
    # The notebook copies code out of src/, so prove the copy is self-contained: run it
    # in an empty namespace (no volbt import, no leftovers from other cells).
    nb = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    namespace = {}
    for cell in nb["cells"]:
        if cell["cell_type"] == "code":
            exec("".join(cell["source"]), namespace)
    assert namespace["iv"].shape == (20, 26)


def test_check_finds_no_drift_right_after_writing(tmp_path):
    build_notebooks.write_notebooks(tmp_path)
    assert build_notebooks.drifted_notebooks(tmp_path) == []


def test_check_names_a_notebook_that_changed_by_one_character(tmp_path):
    build_notebooks.write_notebooks(tmp_path)
    path = tmp_path / "00_scaffold_tour.ipynb"
    path.write_text(path.read_text(encoding="utf-8").replace("Scaffold", "Scaffolds", 1), encoding="utf-8")
    assert build_notebooks.drifted_notebooks(tmp_path) == ["00_scaffold_tour.ipynb"]


def test_check_names_a_missing_notebook(tmp_path):
    assert build_notebooks.drifted_notebooks(tmp_path) == ["00_scaffold_tour.ipynb", "01_data_layer.ipynb",
                                                           "02_pricing_core.ipynb"]


def test_check_cli_exits_nonzero_and_names_the_notebook_on_drift(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(build_notebooks, "NOTEBOOKS_DIR", tmp_path)
    assert build_notebooks.main(["--check"]) == 1
    assert "00_scaffold_tour.ipynb" in capsys.readouterr().out


def test_check_cli_exits_zero_when_up_to_date(tmp_path, monkeypatch):
    monkeypatch.setattr(build_notebooks, "NOTEBOOKS_DIR", tmp_path)
    assert build_notebooks.main([]) == 0           # build into tmp
    assert build_notebooks.main(["--check"]) == 0  # then check it


def test_check_script_passes_on_the_real_repo():
    # Run the way a person (or CI) runs it: as a script in a separate process.
    result = subprocess.run(
        [sys.executable, str(REPO / "tools" / "build_notebooks.py"), "--check"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


# --- the check is byte-level -------------------------------------------------------------

def test_check_flags_a_notebook_that_differs_only_in_line_endings(tmp_path):
    build_notebooks.write_notebooks(tmp_path)
    path = tmp_path / "00_scaffold_tour.ipynb"
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    # As JSON (or read_text, which converts CRLF) the two files are identical; as bytes they are not.
    assert json.loads(path.read_text(encoding="utf-8")) == json.loads(
        build_notebooks.render_notebooks()["00_scaffold_tour.ipynb"])
    assert build_notebooks.drifted_notebooks(tmp_path) == ["00_scaffold_tour.ipynb"]


def test_notebooks_are_written_with_lf_even_where_text_mode_would_write_crlf(tmp_path, windows_text_mode):
    build_notebooks.write_notebooks(tmp_path)
    data = (tmp_path / "00_scaffold_tour.ipynb").read_bytes()
    assert b"\r" not in data
    # ... and therefore --check agrees that what was just written is current.
    assert build_notebooks.drifted_notebooks(tmp_path) == []


# --- copying a module: what is supported, and what must fail loudly ------------------------

def write_module(tmp_path, source, newline="\n"):
    path = tmp_path / "mod.py"
    path.write_text(textwrap.dedent(source), encoding="utf-8", newline=newline)
    return path


def test_module_cells_keep_source_order_and_split_runs(tmp_path):
    path = write_module(tmp_path, """
        from __future__ import annotations

        import numpy as np
        from math import pi

        A = 1
        B = 2


        def f():
            return A


        C = f()


        def g():
            return C
    """)
    cells = build_notebooks.module_cells(path)
    assert [cell_id for cell_id, _ in cells] == [
        "code-imports", "code-constants", "code-f", "code-constants-2", "code-g"]
    sources = dict(cells)
    assert sources["code-imports"] == "import numpy as np\nfrom math import pi"   # __future__ dropped
    assert sources["code-constants"] == "A = 1\nB = 2"
    assert sources["code-f"] == "def f():\n    return A"
    assert sources["code-constants-2"] == "C = f()"       # after f, so the notebook can call it
    assert sources["code-g"] == "def g():\n    return C"


def test_an_assignment_after_a_function_does_not_copy_the_function_twice(tmp_path):
    path = write_module(tmp_path, """
        A = 1

        def f():
            return A

        B = 2
    """)
    all_source = "\n".join(source for _, source in build_notebooks.module_cells(path))
    assert all_source.count("def f") == 1


def test_comments_above_constants_travel_with_them(tmp_path):
    path = write_module(tmp_path, """
        import os

        # why A is 1
        A = 1
        # why B is 2
        B = 2
    """)
    assert dict(build_notebooks.module_cells(path))["code-constants"] == (
        "# why A is 1\nA = 1\n# why B is 2\nB = 2")


def test_comments_directly_above_a_function_travel_with_it(tmp_path):
    path = write_module(tmp_path, """
        import os

        A = 1

        # why f exists
        # (two lines of it)
        def f():
            return A
    """)
    assert dict(build_notebooks.module_cells(path))["code-f"] == (
        "# why f exists\n# (two lines of it)\ndef f():\n    return A")


def test_comments_above_a_decorated_function_travel_with_it(tmp_path):
    path = write_module(tmp_path, """
        import functools

        # cached because it is slow
        @functools.cache
        def f():
            return 1
    """)
    assert dict(build_notebooks.module_cells(path))["code-f"] == (
        "# cached because it is slow\n@functools.cache\ndef f():\n    return 1")


def test_a_comment_above_a_function_does_not_land_in_the_previous_cell_or_twice(tmp_path):
    path = write_module(tmp_path, """
        A = 1
        # about f, not about A
        def f():
            return A
    """)
    sources = dict(build_notebooks.module_cells(path))
    assert sources["code-constants"] == "A = 1"
    assert sources["code-f"] == "# about f, not about A\ndef f():\n    return A"


def test_a_comment_separated_from_a_function_by_a_blank_line_is_not_carried(tmp_path):
    # "Directly above" means no blank line between: a section heading is not the function's comment.
    path = write_module(tmp_path, """
        A = 1

        # ---- helpers ----

        def f():
            return A
    """)
    assert dict(build_notebooks.module_cells(path))["code-f"] == "def f():\n    return A"


@pytest.mark.parametrize("line", [
    "A = 1; import os",
    "import os; A = 1",
    "A = 1; B = 2",
    "import os; import sys",
    '"""doc"""; import os',
])
def test_statements_joined_with_a_semicolon_are_rejected_with_the_line(tmp_path, line):
    # Each cell is copied by line range, so a second statement on the same line used to give an
    # empty cell (or silently share the first statement's).
    path = write_module(tmp_path, "\n" + line + "\n")
    with pytest.raises(build_notebooks.UnsupportedModuleError) as caught:
        build_notebooks.module_cells(path)
    message = str(caught.value)
    assert "mod.py:2" in message and "';'" in message and "own line" in message


def test_decorators_are_copied_with_the_function(tmp_path):
    path = write_module(tmp_path, """
        import functools

        @functools.cache
        @functools.wraps(print)
        def f():
            return 1
    """)
    assert dict(build_notebooks.module_cells(path))["code-f"] == (
        "@functools.cache\n@functools.wraps(print)\ndef f():\n    return 1")


def test_a_module_without_assignments_is_fine(tmp_path):
    path = write_module(tmp_path, """
        import numpy as np

        def f():
            return 1
    """)
    assert [cell_id for cell_id, _ in build_notebooks.module_cells(path)] == ["code-imports", "code-f"]


def test_an_empty_module_gives_no_cells(tmp_path):
    assert build_notebooks.module_cells(write_module(tmp_path, '"""Just a docstring."""\n')) == []


@pytest.mark.parametrize("statement, kind", [
    ("class C:\n    pass", "ClassDef"),
    ("try:\n    import json\nexcept ImportError:\n    json = None", "Try"),
    ("if True:\n    X = 1", "If"),
    ("print('side effect')", "Expr"),
    ("async def f():\n    pass", "AsyncFunctionDef"),
    ("A = 1\nA += 1", "AugAssign"),
    ("with open('x') as fh:\n    pass", "With"),
])
def test_unsupported_top_level_statements_raise_with_the_line_and_kind(tmp_path, statement, kind):
    path = write_module(tmp_path, "import os\n\n" + statement + "\n")
    with pytest.raises(build_notebooks.UnsupportedModuleError) as caught:
        build_notebooks.module_cells(path)
    message = str(caught.value)
    assert kind in message and "mod.py:" in message and "not supported" in message


def test_a_string_expression_after_the_first_statement_is_not_mistaken_for_the_docstring(tmp_path):
    path = write_module(tmp_path, """
        A = 1
        "attribute docs like this one would be silently dropped"
    """)
    with pytest.raises(build_notebooks.UnsupportedModuleError):
        build_notebooks.module_cells(path)


def test_crlf_source_gives_the_same_cells_as_lf_source(tmp_path):
    source = "import os\n\n# note\nA = 1\n\n\ndef f():\n    return A\n"
    lf = write_module(tmp_path, source)
    crlf = tmp_path / "crlf.py"
    crlf.write_bytes(source.replace("\n", "\r\n").encode())
    assert build_notebooks.module_cells(crlf) == build_notebooks.module_cells(lf)


# --- cell ids: unique and stable --------------------------------------------------------

@pytest.mark.parametrize("name, clash", [("constants", "code-constants"), ("imports", "code-imports")])
def test_a_function_named_like_a_fixed_cell_id_is_rejected(tmp_path, name, clash):
    # nbformat.validate() would quietly replace the duplicate id with a random one.
    path = write_module(tmp_path, f"""
        import os
        A = 1

        def {name}():
            return A
    """)
    with pytest.raises(ValueError, match=f"duplicate notebook cell id '{clash}'"):
        build_notebooks.build_scaffold_tour(path)


def test_a_redefined_function_is_rejected(tmp_path):
    path = write_module(tmp_path, """
        def f():
            return 1

        def f():
            return 2
    """)
    with pytest.raises(ValueError, match="duplicate notebook cell id 'code-f'"):
        build_notebooks.build_scaffold_tour(path)


def test_assert_unique_cell_ids_accepts_distinct_ids():
    cells = [{"id": "a"}, {"id": "b"}]
    build_notebooks.assert_unique_cell_ids(cells)   # no exception


def test_a_module_with_different_content_still_builds_with_stable_ids(tmp_path):
    path = write_module(tmp_path, """
        import os
        A = 1

        def f():
            return A
    """)
    first = [cell["id"] for cell in build_notebooks.build_scaffold_tour(path).cells]
    second = [cell["id"] for cell in build_notebooks.build_scaffold_tour(path).cells]
    assert first == second
    assert len(first) == len(set(first))
    assert {"code-imports", "code-constants", "code-f"} <= set(first)


# --- .gitattributes: line endings are pinned by git itself -----------------------------------

@pytest.mark.parametrize("path", [
    "notebooks/00_scaffold_tour.ipynb", "app/public/data/manifest.json",
    "tools/build_notebooks.py", "src/volbt/contract.py",
    "docs/architecture/out/architecture.svg", "docs/architecture/out/architecture.mmd",
    "README.md", "app/src/lib/contract.ts", "app/src/App.tsx"])
def test_gitattributes_pins_text_files_to_lf(path):
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    result = subprocess.run(["git", "check-attr", "text", "eol", "--", path],
                            cwd=REPO, capture_output=True, text=True, check=True)
    assert f"{path}: text: set" in result.stdout, result.stdout
    assert f"{path}: eol: lf" in result.stdout, result.stdout


def test_gitattributes_marks_png_as_binary():
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    path = "docs/architecture/out/architecture.png"
    result = subprocess.run(["git", "check-attr", "-a", "--", path],
                            cwd=REPO, capture_output=True, text=True, check=True)
    # "binary" is a macro that unsets text, diff and merge.
    assert f"{path}: binary: set" in result.stdout, result.stdout
    assert f"{path}: text: unset" in result.stdout, result.stdout

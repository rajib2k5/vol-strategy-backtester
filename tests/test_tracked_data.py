"""tools/licensing/check_tracked_data.py: no raw vendor file and no oversized data file in what git would commit.

Each case plants files in a scratch git work tree (never in this repo), runs the tool as a command, and reads its
exit code and output. The size cases use sparse files, which take no disk.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
CHECK = REPO / "tools" / "licensing" / "check_tracked_data.py"
MIB = 1024 * 1024

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")


def run(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(CHECK), "--root", str(root)], capture_output=True, text=True, check=False)


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=True)


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """An empty git work tree: no commit, no .gitignore."""
    git(tmp_path, "init", "-q")
    return tmp_path


def plant(root: Path, path: str, size: int = 10) -> None:
    file = root / path
    file.parent.mkdir(parents=True, exist_ok=True)
    with file.open("wb") as handle:
        handle.truncate(size)  # sparse: the size without the disk


def test_this_repo_is_clean():
    done = run(REPO)
    assert done.returncode == 0, done.stdout + done.stderr
    assert done.stdout.startswith("clean: 0 raw vendor files in ")


def test_an_empty_tree_and_ordinary_files_are_clean(tree: Path):
    plant(tree, "README.md")
    plant(tree, "app/public/data/data_quality.json", 20_000)  # derived data, small: committed on purpose
    plant(tree, "tests/fixtures/optionsdx_20rows.parquet", 4_000)  # the tiny synthetic fixtures
    plant(tree, "docs/images/app/about-dark.png", 80 * MIB)  # large, but not data
    done = run(tree)
    assert done.returncode == 0, done.stdout
    assert "clean: 0 raw vendor files in 4 files" in done.stdout


@pytest.mark.parametrize(
    ("path", "reason"),
    [
        ("kaggle/spy-eod-2010-2023/spy_20100104.parquet", "Parquet file outside tests/fixtures/"),
        ("chains/spy_2022.parquet", "Parquet file outside tests/fixtures/"),
        ("tests/other/spy.PARQUET", "Parquet file outside tests/fixtures/"),
        ("work/store.duckdb", "DuckDB database"),
        ("data/raw/DGS3MO.csv", "raw download under data/raw/"),
        ("Data/Raw/VIX_History.CSV", "raw download under data/raw/"),
        ("data/raw/dolthub/option_chain_spy.csv", "raw download under data/raw/"),
        ("dolthub/options/.dolt/noms/manifest", "dolt clone file"),
        ("clone/.dolt/repo_state.json", "dolt clone file"),
        ("dolt_root/anything", "dolt clone file"),
        ("clone/noms/0a1b2c3d.darc", "dolt clone file"),
        ("spy-eod-2010-2023/chain_2010.csv", "Kaggle download folder"),
        ("downloads/kaggle/readme.txt", "Kaggle download folder"),
    ],
)
def test_a_raw_vendor_file_fails(tree: Path, path: str, reason: str):
    plant(tree, "README.md")
    plant(tree, path)
    done = run(tree)
    assert done.returncode == 1, done.stdout
    assert f"FAIL: {path}: {reason}" in done.stdout
    assert "clean:" not in done.stdout


def test_a_parquet_file_in_a_subfolder_of_tests_fixtures_is_a_fixture(tree: Path):
    plant(tree, "tests/fixtures/reference/spy_bars.parquet")
    assert run(tree).returncode == 0


def test_every_problem_is_reported_not_only_the_first(tree: Path):
    plant(tree, "a.duckdb")
    plant(tree, "b/c.parquet")
    done = run(tree)
    assert done.returncode == 1
    assert "FAIL: a.duckdb" in done.stdout and "FAIL: b/c.parquet" in done.stdout
    assert "2 problem(s)" in done.stdout


def test_a_file_that_gitignore_hides_is_not_listed_but_a_force_added_one_is(tree: Path):
    (tree / ".gitignore").write_text("*.parquet\n/data/\n", encoding="utf-8")
    plant(tree, "chains/spy.parquet")
    plant(tree, "data/raw/DGS3MO.csv")
    assert run(tree).returncode == 0  # the next `git add .` would not take them
    git(tree, "add", "-f", "chains/spy.parquet")
    done = run(tree)
    assert done.returncode == 1
    assert "FAIL: chains/spy.parquet" in done.stdout
    assert "data/raw" not in done.stdout  # still hidden


def test_a_tracked_file_deleted_from_the_work_tree_is_skipped(tree: Path):
    plant(tree, "data.csv", 20 * MIB)
    git(tree, "add", "data.csv")
    (tree / "data.csv").unlink()
    done = run(tree)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "warn:" not in done.stdout
    assert "(0 size warning(s))" in done.stdout


@pytest.mark.parametrize(
    ("size", "verdict"),
    [
        (10 * MIB, "clean"),  # at the warn limit is inside it
        (10 * MIB + 1, "warn"),
        (50 * MIB, "warn"),  # at the fail limit is inside it
        (50 * MIB + 1, "fail"),
    ],
)
def test_the_size_limits(tree: Path, size: int, verdict: str):
    plant(tree, "app/public/data/big.json", size)
    done = run(tree)
    if verdict == "fail":
        assert done.returncode == 1
        assert "FAIL: app/public/data/big.json: data file of " in done.stdout
        assert "over the 50 MiB limit" in done.stdout
    else:
        assert done.returncode == 0, done.stdout
        assert ("warn: app/public/data/big.json: data file of " in done.stdout) == (verdict == "warn")
        assert "FAIL" not in done.stdout


def test_a_warning_does_not_hide_that_the_tree_is_clean(tree: Path):
    plant(tree, "results/series.csv", 11 * MIB)
    done = run(tree)
    assert done.returncode == 0
    assert "warn: results/series.csv" in done.stdout
    assert "clean: 0 raw vendor files in 1 files git would commit (1 size warning(s))" in done.stdout


@pytest.mark.parametrize("extension", [".csv", ".tsv", ".txt", ".json", ".zip", ".gz", ".sqlite", ".npy"])
def test_every_data_extension_has_the_size_limit(tree: Path, extension: str):
    plant(tree, f"series/big{extension}", 51 * MIB)
    assert run(tree).returncode == 1


def test_a_folder_that_is_not_a_git_work_tree_is_an_error_not_a_pass(tmp_path: Path):
    done = run(tmp_path)
    assert done.returncode == 2
    assert "is not a git work tree" in done.stderr
    assert "clean:" not in done.stdout

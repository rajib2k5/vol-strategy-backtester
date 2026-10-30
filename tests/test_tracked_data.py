"""tools/licensing/check_tracked_data.py: no raw vendor file and no oversized data file in what git would commit.

Each case plants files in a scratch git work tree (never in this repo), runs the tool as a command (or calls
check() with a fake raw file), and reads its exit code and output. The size cases use sparse files, which take no
disk. The command runs with VOL_DATA_DIR and VOLBT_WORK_DIR pointed at empty folders, so it never reads or caches
this machine's real vendor files.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
CHECK = REPO / "tools" / "licensing" / "check_tracked_data.py"
MIB = 1024 * 1024

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")

# A made-up "vendor file": 2 KiB of invented CSV rows. SAME_SIZE has other bytes and the same length.
RAW_BYTES = (b"Date,Open,High,Low,Close\n" + b"2010-01-04,11.11,22.22,33.33,44.44\n" * 59)[:2048]
SAME_SIZE = (b"Date,Open,High,Low,Close\n" + b"2010-01-05,55.55,66.66,77.77,88.88\n" * 59)[:2048]


def run(root: Path, env: dict[str, str] | None = None, isolate: bool = True) -> subprocess.CompletedProcess[str]:
    """The tool as a command on `root`; `isolate=False` lets it see this machine's real vendor files."""
    isolated = {"VOL_DATA_DIR": str(root.parent / "no-vendor"), "VOLBT_WORK_DIR": str(root.parent / "no-work")} if isolate else {}
    return subprocess.run([sys.executable, str(CHECK), "--repo", str(root)], capture_output=True, text=True, check=False,
                          env={**os.environ, **isolated, **(env or {})})


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=True)


@pytest.fixture(scope="module")
def gate():
    """The tool as a module (tools/ is not a package), to call check() with a fake raw-file list."""
    spec = importlib.util.spec_from_file_location("check_tracked_data", CHECK)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """An empty git work tree: no commit, no .gitignore."""
    root = tmp_path / "tree"
    root.mkdir()
    git(root, "init", "-q")
    return root


@pytest.fixture
def raw(tmp_path: Path) -> Path:
    """A fake raw vendor file, outside the work tree."""
    file = tmp_path / "vendor" / "VIX_History.csv"
    file.parent.mkdir()
    file.write_bytes(RAW_BYTES)
    return file


def plant(root: Path, path: str, size: int = 10) -> None:
    file = root / path
    file.parent.mkdir(parents=True, exist_ok=True)
    with file.open("wb") as handle:
        handle.truncate(size)  # sparse: the size without the disk


def test_this_repo_is_clean():
    done = run(REPO, isolate=False)
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


def test_a_staged_file_deleted_from_the_work_tree_is_judged_by_its_staged_size(tree: Path):
    plant(tree, "data.csv", 20 * MIB)
    git(tree, "add", "data.csv")
    (tree / "data.csv").unlink()
    done = run(tree)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "warn: data.csv: data file of 20.0 MiB" in done.stdout
    plant(tree, "big.csv", 51 * MIB)
    git(tree, "add", "big.csv")
    (tree / "big.csv").unlink()
    done = run(tree)
    assert done.returncode == 1
    assert "FAIL: big.csv: data file of 51.0 MiB" in done.stdout


def test_a_staged_small_file_overwritten_on_disk_by_a_big_one_is_judged_by_the_big_one(tree: Path):
    plant(tree, "data.csv", 10)
    git(tree, "add", "data.csv")
    plant(tree, "data.csv", 51 * MIB)  # `git add .` or `git commit -a` would take it
    assert run(tree).returncode == 1


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


def test_root_is_still_accepted_as_the_old_name_of_repo(tree: Path):
    plant(tree, "data/raw/DGS3MO.csv")
    done = subprocess.run([sys.executable, str(CHECK), "--root", str(tree)], capture_output=True, text=True, check=False,
                          env={**os.environ, "VOL_DATA_DIR": str(tree.parent / "x"), "VOLBT_WORK_DIR": str(tree.parent / "y")})
    assert done.returncode == 1
    assert "FAIL: data/raw/DGS3MO.csv" in done.stdout


def test_a_folder_that_is_not_a_git_work_tree_is_an_error_not_a_pass(tmp_path: Path):
    done = run(tmp_path)
    assert done.returncode == 2
    assert "is not a git work tree" in done.stderr
    assert "clean:" not in done.stdout


# --- what git stages, and a renamed copy of a raw vendor file ---------------------------------------------------

def put(root: Path, path: str, data: bytes) -> None:
    file = root / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_bytes(data)


def judge(gate, tree: Path, raw: Path | None, cache: Path | None = None):
    """check() on `tree` with `raw` as the only raw vendor file: (failures, warnings, notes, files)."""
    return gate.check(tree, [raw] if raw else [], cache)


def compared_candidates(notes: list[str]) -> int:
    """How many same-size candidate versions the run hashed, from the 'note:' line."""
    return int(re.search(r"; (\d+) same-size candidate version", notes[0]).group(1))


def test_a_renamed_staged_copy_of_a_raw_file_fails(gate, tree: Path, raw: Path):
    put(tree, "docs/notes.txt", RAW_BYTES)  # a .txt in docs/: no name, extension or size rule matches it
    git(tree, "add", "docs/notes.txt")
    failures, _, notes, _ = judge(gate, tree, raw)
    assert failures == [f"docs/notes.txt: the staged file is a byte-for-byte copy of the raw vendor file {raw}"]
    assert compared_candidates(notes) == 1  # it was hashed, and the hash matched the first version, so it stopped there


def test_a_copy_staged_and_then_deleted_from_disk_still_fails(gate, tree: Path, raw: Path):
    put(tree, "app/public/data/x.bin", RAW_BYTES)
    git(tree, "add", "app/public/data/x.bin")
    (tree / "app/public/data/x.bin").unlink()
    failures, _, _, _ = judge(gate, tree, raw)
    assert failures == [f"app/public/data/x.bin: the staged file is a byte-for-byte copy of the raw vendor file {raw}"]


def test_a_copy_staged_and_then_changed_on_disk_still_fails(gate, tree: Path, raw: Path):
    put(tree, "docs/notes.txt", RAW_BYTES)
    git(tree, "add", "docs/notes.txt")
    put(tree, "docs/notes.txt", b"harmless")
    failures, _, _, _ = judge(gate, tree, raw)
    assert [f.split(":")[0] for f in failures] == ["docs/notes.txt"]
    assert "the staged file" in failures[0]


def test_a_clean_staged_file_overwritten_on_disk_by_a_copy_fails(gate, tree: Path, raw: Path):
    put(tree, "docs/notes.txt", b"harmless")
    git(tree, "add", "docs/notes.txt")
    put(tree, "docs/notes.txt", RAW_BYTES)  # `git add .` or `git commit -a` would take it
    failures, _, _, _ = judge(gate, tree, raw)
    assert failures == [f"docs/notes.txt: the work-tree file is a byte-for-byte copy of the raw vendor file {raw}"]


def test_an_untracked_copy_fails_until_it_is_gone(gate, tree: Path, raw: Path):
    put(tree, "docs/notes.txt", RAW_BYTES)
    assert len(judge(gate, tree, raw)[0]) == 1  # not staged, but the next `git add .` would take it
    git(tree, "add", "docs/notes.txt")
    git(tree, "rm", "-q", "--cached", "docs/notes.txt")  # unstaged, still on disk, still untracked
    assert len(judge(gate, tree, raw)[0]) == 1
    (tree / "docs/notes.txt").unlink()
    assert judge(gate, tree, raw)[0] == []


def test_a_copy_that_was_staged_then_unstaged_and_deleted_passes(gate, tree: Path, raw: Path):
    put(tree, "docs/notes.txt", RAW_BYTES)
    git(tree, "add", "docs/notes.txt")
    assert judge(gate, tree, raw)[0]
    git(tree, "rm", "-q", "--cached", "docs/notes.txt")
    (tree / "docs/notes.txt").unlink()
    failures, _, _, files = judge(gate, tree, raw)
    assert failures == [] and files == 0


def test_a_different_file_of_the_same_size_passes(gate, tree: Path, raw: Path):
    assert len(SAME_SIZE) == len(RAW_BYTES) and SAME_SIZE != RAW_BYTES
    put(tree, "docs/notes.txt", SAME_SIZE)
    git(tree, "add", "docs/notes.txt")
    failures, _, notes, _ = judge(gate, tree, raw)
    assert failures == []
    assert compared_candidates(notes) == 2  # the staged file and the work-tree file were both hashed, and differ


def test_a_renamed_copy_is_found_among_several_raw_files(gate, tree: Path, raw: Path, tmp_path: Path):
    other = tmp_path / "vendor" / "DGS3MO.csv"
    other.write_bytes(b"DATE,DGS3MO\n1981-09-01,17.01\n")
    put(tree, "notes/b.txt", other.read_bytes())
    failures, _, notes, _ = gate.check(tree, [raw, other], None)
    assert failures == [f"notes/b.txt: the work-tree file is a byte-for-byte copy of the raw vendor file {other}"]
    assert "against 2 raw vendor file(s)" in notes[0]


def test_staged_files_are_the_added_copied_modified_or_renamed(gate, tree: Path):
    put(tree, "old.txt", b"one\n" * 50)
    put(tree, "gone.txt", b"two\n" * 50)
    git(tree, "add", ".")
    git(tree, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "x")
    git(tree, "mv", "old.txt", "new.txt")
    git(tree, "rm", "-q", "gone.txt")
    put(tree, "added.txt", b"three\n")
    git(tree, "add", "added.txt")
    assert gate.staged_files(tree) == ["added.txt", "new.txt"]  # the deleted one is not a file git would commit


def test_the_check_is_skipped_loudly_when_there_are_no_raw_files(gate, tree: Path, tmp_path: Path):
    put(tree, "docs/notes.txt", RAW_BYTES)
    git(tree, "add", "docs/notes.txt")
    missing = tmp_path / "vendor" / "nothing.csv"
    for raw_files in ([], [missing]):
        failures, _, notes, _ = gate.check(tree, raw_files, None)
        assert failures == []  # the name and size rules still ran, and found nothing
        assert len(notes) == 1 and notes[0].startswith("note: SHA-256 check skipped: no raw vendor files")


def test_an_empty_raw_file_does_not_make_every_empty_file_a_copy(gate, tree: Path, tmp_path: Path):
    empty = tmp_path / "empty.csv"
    empty.write_bytes(b"")
    put(tree, "pkg/__init__.py", b"")
    assert gate.check(tree, [empty], None)[0] == []


def test_the_raw_hashes_are_cached_and_dropped_when_the_raw_file_changes(gate, tree: Path, raw: Path, tmp_path: Path):
    cache = tmp_path / "work" / "cache" / "raw_hashes.json"
    put(tree, "docs/notes.txt", RAW_BYTES)
    git(tree, "add", "docs/notes.txt")
    failures, _, notes, _ = judge(gate, tree, raw, cache)
    assert len(failures) == 1 and "1 hashed this run, 0 from the cache" in notes[0]
    assert list(json.loads(cache.read_text(encoding="utf-8"))["files"]) == [str(raw)]
    failures, _, notes, _ = judge(gate, tree, raw, cache)
    assert len(failures) == 1 and "0 hashed this run, 1 from the cache" in notes[0]
    # The vendor re-issues the file: other bytes, the same length, a later mtime. The cached hash must not be used.
    before = raw.stat()
    raw.write_bytes(SAME_SIZE)
    os.utime(raw, ns=(before.st_atime_ns, before.st_mtime_ns + 5_000_000_000))
    failures, _, notes, _ = judge(gate, tree, raw, cache)
    assert failures == [] and "1 hashed this run, 0 from the cache" in notes[0]


def test_the_command_finds_this_machines_raw_files_through_the_config_and_caches_them(tree: Path, tmp_path: Path):
    vendor, work = tmp_path / "vendor-home", tmp_path / "work-dir"
    optionsdx = vendor / "kaggle" / "spy-eod-2010-2023" / "spy_eod_2010.parquet"
    reference = work / "raw" / "cboe" / "VIX_History.csv"
    for file, data in ((optionsdx, b"PAR1" + SAME_SIZE), (reference, RAW_BYTES), (Path(f"{reference}.meta.json"), b'{"bytes": 2048}')):
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(data)
    env = {"VOL_DATA_DIR": str(vendor), "VOLBT_WORK_DIR": str(work)}
    put(tree, "app/public/data/x.bin", optionsdx.read_bytes())
    put(tree, "docs/notes.txt", reference.read_bytes())
    put(tree, "docs/provenance.txt", Path(f"{reference}.meta.json").read_bytes())  # our own note: not vendor data
    git(tree, "add", ".")
    for file in (tree / "app/public/data/x.bin", tree / "docs/notes.txt"):
        file.unlink()  # staged, gone from disk
    done = run(tree, env)
    assert done.returncode == 1, done.stdout + done.stderr
    assert f"FAIL: app/public/data/x.bin: the staged file is a byte-for-byte copy of the raw vendor file {optionsdx}" in done.stdout
    assert f"FAIL: docs/notes.txt: the staged file is a byte-for-byte copy of the raw vendor file {reference}" in done.stdout
    assert "provenance.txt" not in done.stdout
    assert "2 problem(s)" in done.stdout and "2 raw vendor file(s): 2 hashed this run" in done.stdout
    cache = json.loads((work / "cache" / "raw_hashes.json").read_text(encoding="utf-8"))["files"]
    assert sorted(cache) == sorted([str(optionsdx), str(reference)])
    git(tree, "rm", "-q", "--cached", "app/public/data/x.bin", "docs/notes.txt")  # unstage them
    done = run(tree, env)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "2 raw vendor file(s): 0 hashed this run, 2 from the cache" in done.stdout

"""Pre-registration, the scorer and the run gate (milestone 4, plan sections 6 and 10, task 7; fix pass items 2-4, 8;
fix pass 2 items 1-4, 16 and O14): the refusals.

Every pre-registration here is made up and lives in a throwaway git repository under tmp_path: a copy of the files the
scorer imports (tools/prereg.py scorer_closure), the made-up files, an empty spent.jsonl, one commit. The scorer runs
against it with the real git checks; each refusal test replays one attack of the review (S/egv/m4a/adversarial/c7,
tA-tN) on it. The paired series is made up: nothing reads the real store or scores the real test. git commands that
build a throwaway repository write only there; the repository's own git is read, never written.
"""

from __future__ import annotations

import hashlib
import importlib.machinery
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))

import prereg  # noqa: E402
import score_prereg  # noqa: E402
from prereg import PreregError  # noqa: E402
from volbt.engine.run_config import RunConfig, trial_hash  # noqa: E402
from volbt.strategies.reference import RollingShortStraddle  # noqa: E402

ID = "2026-11-09-made-up"
GIT_ENV = {**{k: v for k, v in os.environ.items() if not k.startswith("GIT_")},
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


def g(repo: Path, *args: str, env: dict | None = None) -> str:
    """git in a throwaway repository (never the project's)."""
    assert Path(repo).resolve() != REPO
    out = subprocess.run(["git", "-c", "user.name=test", "-c", "user.email=test@example.invalid", "-c",
                          "commit.gpgsign=false", "-C", str(repo), *args], capture_output=True, text=True,
                         env=env or GIT_ENV)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


def commit(repo: Path, message: str = "made up") -> None:
    g(repo, "add", "-A")
    g(repo, "commit", "-q", "-m", message)


def made_up_days(n=300):
    days, day = [], date(2015, 1, 5)
    while len(days) < n:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


class FakeStore:
    """Answers the one store call the scorer's data check makes: the file of a table."""

    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        for name in ("spy_bars", "dividends"):
            (root / f"{name}.parquet").write_bytes(f"made-up {name}".encode())

    def checked_table_file(self, name):
        return self.root / f"{name}.parquet"


def window_of(days, name="made-up", split="development") -> dict:
    return {"name": name, "split": split, "start": days[0].isoformat(), "end": days[-1].isoformat(),
            "last_target_end": days[-1].isoformat(), "n": len(days), "dates_sha256": prereg.dates_sha256(days)}


def spec_for(store, repo, prereg_id=ID, windows=None, **changes) -> dict:
    spec = {"id": prereg_id, "kind": "forecast_test", "k": 1, "threshold": 0.025,
            "effective_size": {"abc_size_battery_seed": 0.05, "abc_size_second_seed": 0.05},
            "candidates": [{"name": "har", "trial_hash": "a" * 64}], "benchmark": {"name": "naive",
                                                                                    "trial_hash": "b" * 64},
            "windows": windows or [window_of(made_up_days())],
            "test": {"q": 4, "block": 10, "draws": 999, "seed": 1, "level": 0.95},
            "size": {"worst": {"high": {"rate": 0.25}}}, "metric": {"label": "proxy"}, "fragile_band": [0.02, 0.05],
            "scorer_sha256": prereg.scorer_sha256(repo), "libraries": prereg.library_versions(repo),
            "data": prereg.store_tables(store)}
    return {**spec, **changes}


def throwaway(tmp_path: Path, **changes) -> tuple[Path, FakeStore]:
    """A git repository with the scorer's files, the made-up pre-registration and an empty spent.jsonl, committed."""
    repo = tmp_path / "repo"
    for rel in prereg.scorer_closure(REPO):
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / rel, repo / rel)
    store = FakeStore(tmp_path / "store")
    directory = prereg.prereg_dir(repo)
    prereg.write(spec_for(store, repo, **changes), "# made up\n", directory)
    (directory / prereg.SPENT).write_text("")
    g(repo, "init", "-q")
    commit(repo, "made-up pre-registration")
    return repo, store


def series_of(d):
    """A made-up scorer input: rows and the paired series, with d as given."""
    def series_for(store, days):
        rows = [{"t": t, "har": 1e-4, "har_flags": 0, "fit_date": None, "naive": 1e-4} for t in days]
        n = len(days)
        return rows, {"y": np.full(n, 1e-4), "har": np.full(n, 1e-4), "naive": np.full(n, 1e-4),
                      "loss_har": np.zeros(n), "loss_naive": np.asarray(d, dtype=float), "d": np.asarray(d, float)}
    return series_for


def score(repo, store, d=None, prereg_id=ID, days=None):
    """score_prereg.score() on a throwaway repository, as main() reports it: 0 and the result, or 2 and "refused: ..."
    on stderr. Its modules are the project's (byte copies of the throwaway's). main() takes the command line only (fix
    pass 6, item H2), so the tests call score(); the scan of the modules loaded from tools/ that score() runs before the
    spend (check_tools_modules) is replaced here, because pytest's process holds modules of tools/ outside the closure
    (smoke_m4, run_backtest, ...). The process-check tests run the scorer as a script."""
    d = np.random.default_rng(3).standard_normal(300) if d is None else d
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(score_prereg, "check_tools_modules", lambda root, modules=None: None)
        try:
            result = score_prereg.score(prereg_id, store, repo, days_for=lambda s, w: days or made_up_days(),
                                        series_for=series_of(d), modules_root=REPO)
        except PreregError as error:
            print(f"refused: {error}", file=sys.stderr)
            return 2
    print(json.dumps(result, indent=1, sort_keys=True))
    return 0


def refused(repo, store, capsys, match: str, **kwargs) -> None:
    """The scorer exits 2 with `match` in its message and leaves spent.jsonl and the result files as they were."""
    spent = (prereg.prereg_dir(repo) / prereg.SPENT).read_bytes()
    results = [os.path.lexists(p) for p in prereg.result_paths(kwargs.get("prereg_id", ID), prereg.prereg_dir(repo))]
    capsys.readouterr()
    assert score(repo, store, **kwargs) == 2
    err = capsys.readouterr().err
    assert match in err, err
    assert (prereg.prereg_dir(repo) / prereg.SPENT).read_bytes() == spent
    assert [os.path.lexists(p) for p in prereg.result_paths(kwargs.get("prereg_id", ID),
                                                             prereg.prereg_dir(repo))] == results


def scored_and_committed(repo, store) -> None:
    assert score(repo, store) == 0
    commit(repo, "scored")


@pytest.fixture
def made_up(tmp_path):
    return throwaway(tmp_path)


# --- the files -----------------------------------------------------------------------------------------------------

def test_the_three_files_round_trip_and_are_never_overwritten(made_up):
    repo, store = made_up
    directory = prereg.prereg_dir(repo)
    lines = (directory / f"{ID}.sha256").read_text().splitlines()
    assert lines == [f"{prereg.file_sha256(directory / f'{ID}.json')}  {ID}.json",
                     f"{prereg.file_sha256(directory / f'{ID}.md')}  {ID}.md"]
    assert prereg.load(ID, repo) == spec_for(store, repo)
    with pytest.raises(PreregError, match="amendment"):
        prereg.write(spec_for(store, repo), "# again\n", directory)


@pytest.mark.parametrize("ext", ["json", "md"])
def test_a_one_byte_edit_is_refused(made_up, ext, capsys):
    """tD: an edit to a frozen file."""
    repo, store = made_up
    path = prereg.prereg_dir(repo) / f"{ID}.{ext}"
    data = bytearray(path.read_bytes())
    data[3] ^= 1
    path.write_bytes(bytes(data))
    refused(repo, store, capsys, "does not match")


def test_files_that_were_never_committed_are_refused(tmp_path, capsys):
    repo, store = throwaway(tmp_path, prereg_id=ID)
    other = "2026-11-10-new"
    prereg.write(spec_for(store, repo, prereg_id=other, windows=[window_of(made_up_days(), "new")]), "# new\n",
                 prereg.prereg_dir(repo))
    with pytest.raises(PreregError, match="not committed"):
        prereg.load(other, repo)
    refused(repo, store, capsys, "not committed", prereg_id=other)
    assert prereg.committed(tmp_path / "store" / "spy_bars.parquet", repo) is False     # outside the repository


def test_the_git_checks_are_read_only_and_agree_with_git():
    data = b"made-up bytes\n"
    out = subprocess.run(["git", "hash-object", "--stdin"], input=data, capture_output=True, cwd=REPO)
    assert prereg.git_blob_sha1(data) == out.stdout.decode().strip()
    tracked = subprocess.run(["git", "-C", str(REPO), "ls-files"], capture_output=True, text=True).stdout.split()
    changed = set(subprocess.run(["git", "-C", str(REPO), "diff", "--name-only", "HEAD"], capture_output=True,
                                 text=True).stdout.split())
    unchanged = [p for p in tracked if p not in changed and (REPO / p).is_file() and not (REPO / p).is_symlink()]
    assert unchanged, "no tracked file is unchanged since HEAD"
    assert prereg.committed(REPO / unchanged[0]) is True
    assert prereg.committed(REPO / "docs/validation/prereg/no-such-file.json") is False


# --- the scorer's code and libraries (item 4) ------------------------------------------------------------------------

def test_the_scorer_closure_is_computed_from_the_imports_and_holds_what_the_review_found_missing():
    closure = prereg.scorer_closure()
    for rel in ("tools/score_prereg.py", "tools/prereg.py", "tools/forecast_test.py", "src/volbt/__init__.py",
                "src/volbt/analytics/inference.py", "src/volbt/signals/har.py", "src/volbt/signals/realised.py",
                "src/volbt/signals/base.py", "src/volbt/data/store.py", "src/volbt/view.py", "src/volbt/config.py"):
        assert rel in closure, rel
    assert all((REPO / rel).is_file() for rel in closure)
    assert "src/volbt/engine/loop.py" not in closure and "tools/forecast_size.py" not in closure
    assert {"numpy", "pandas", "pyarrow"} <= set(prereg.library_versions())
    assert prereg.library_versions()["numpy"] == np.__version__


def test_an_import_added_to_a_scorer_file_joins_the_closure(made_up):
    repo, _ = made_up
    before = prereg.scorer_closure(repo)
    for rel in ("src/volbt/engine/__init__.py", "src/volbt/engine/closures.py"):
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / rel, repo / rel)
    path = repo / "tools/forecast_test.py"
    path.write_text(path.read_text() + "\n\ndef later():\n    from volbt.engine import closures\n    return closures\n")
    assert prereg.scorer_closure(repo) == sorted(before + ["src/volbt/engine/__init__.py",
                                                           "src/volbt/engine/closures.py"])


def test_every_repository_module_the_scoring_path_loads_is_in_the_closure(engine_store):
    """At run time, in a fresh interpreter: the scorer's modules and the forecast series on the made-up store (its
    validation split: the store's sessions are in 2022-2023) load no repository file outside the closure."""
    code = f"""
import sys
from datetime import date
sys.path.insert(0, {str(REPO / 'tools')!r})
import numpy as np
import score_prereg, prereg, forecast_test as ft
from volbt.data.store import Store, session_calendar
store = Store({str(engine_store.root)!r})
days = ft.window(session_calendar(store), date(2023, 1, 3), date(2023, 4, 28))[:5]
ft.paired(ft.forecasts(store, days, "validation"), ft.realised(store, days, "validation"))
spec = {{"test": {{"q": 4, "block": 10, "draws": 99, "seed": 1, "level": 0.95}}, "threshold": 0.025,
        "effective_size": {{}},
        "size": {{"worst": {{"high": {{"rate": 0.25}}}}}}, "metric": {{"label": "proxy"}},
        "fragile_band": [0.02, 0.05]}}
score_prereg.forecast_result(spec, {{"d": np.random.default_rng(1).standard_normal(200)}})
for m in list(sys.modules.values()):
    f = getattr(m, "__file__", None)
    if f:
        print(f)
"""
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=REPO)
    assert out.returncode == 0, out.stderr
    loaded = {Path(f).resolve() for f in out.stdout.split()}
    mine = {p.relative_to(REPO).as_posix() for p in loaded if p.is_relative_to(REPO / "src")
            or p.is_relative_to(REPO / "tools")}
    assert {"src/volbt/signals/har.py", "src/volbt/data/store.py", "tools/forecast_test.py"} <= mine
    assert mine <= set(prereg.scorer_closure()), mine - set(prereg.scorer_closure())


def test_a_changed_scorer_is_refused(tmp_path, capsys):
    repo, store = throwaway(tmp_path, scorer_sha256="0" * 64)
    refused(repo, store, capsys, "scorer's SHA-256")


def test_a_committed_edit_to_a_module_the_scorer_imports_is_refused(made_up, capsys):
    """tN: the store's reader and the signals' base were outside the hand-listed SCORER_FILES."""
    repo, store = made_up
    for rel in ("src/volbt/data/store.py", "src/volbt/signals/base.py"):
        (repo / rel).write_text((repo / rel).read_text() + "\n# edited\n")
    commit(repo, "edit store.py and signals/base.py")
    refused(repo, store, capsys, "scorer's SHA-256")


def test_an_uncommitted_scorer_file_is_refused_even_when_its_hash_is_named(tmp_path, capsys):
    """tE (item 8): har.py edited and not committed, and a pre-registration written after the edit names its hash."""
    repo, store = throwaway(tmp_path)
    har = repo / "src/volbt/signals/har.py"
    har.write_text(har.read_text() + "\n# edited\n")
    other = "2026-11-10-after-edit"
    prereg.write(spec_for(store, repo, prereg_id=other, windows=[window_of(made_up_days(), "other")]), "# x\n",
                 prereg.prereg_dir(repo))
    g(repo, "add", prereg.PREREG_REL)
    g(repo, "commit", "-q", "-m", "the pre-registration only")
    assert prereg.load(other, repo)["scorer_sha256"] == prereg.scorer_sha256(repo)
    refused(repo, store, capsys, "src/volbt/signals/har.py is not committed", prereg_id=other)


@pytest.mark.parametrize("name", ["numpy", "python"])
def test_another_library_or_python_version_is_refused(tmp_path, name, capsys):
    """Fix pass 2 (review B N1): the pre-registration names the Python version too."""
    assert prereg.library_versions()["python"] == platform.python_version()
    repo, store = throwaway(tmp_path, libraries={**prereg.library_versions(), name: "0.0.0"})
    refused(repo, store, capsys, "the libraries are")


def test_other_data_is_refused(made_up, capsys):
    repo, store = made_up
    (store.root / "spy_bars.parquet").write_bytes(b"other bars")
    refused(repo, store, capsys, "tables")


def test_the_scorer_names_no_other_folder(made_up):
    repo, store = made_up
    with pytest.raises(SystemExit):
        score_prereg.main([ID, "--dir", str(repo)])


# --- one shot (item 2) -----------------------------------------------------------------------------------------------

def test_scoring_spends_the_window_and_writes_the_result_once(made_up, capsys):
    """The null control of plan section 7: d identically 0 (candidate = benchmark) gives p = 1 and naive. The spent
    line and the result line go to spent.jsonl and to its side ledger in the git common directory."""
    repo, store = made_up
    directory = prereg.prereg_dir(repo)
    assert score(repo, store, np.zeros(300)) == 0
    result = json.loads((directory / f"{ID}.result.json").read_text())
    assert (result["p"], result["ewc_t"], result["decision"]) == (1.0, 0.0, "naive")
    spent = prereg.read_lines(directory / prereg.SPENT)
    assert [line["event"] for line in spent] == ["spent", "result"] and {line["prereg_id"] for line in spent} == {ID}
    assert spent[0]["window"]["name"] == "made-up" and "window" not in spent[1]
    assert spent[1]["result_sha256"] == hashlib.sha256((directory / f"{ID}.result.json").read_bytes()).hexdigest()
    assert prereg.read_lines(repo / ".git" / prereg.SIDE_SPENT) == spent
    assert len((directory / f"{ID}.sessions.csv").read_text().splitlines()) == 301
    refused(repo, store, capsys, "exists")


def test_a_clear_difference_is_scored_har(made_up):
    repo, store = made_up
    d = np.random.default_rng(5).standard_normal(300) + 1.0
    assert score(repo, store, d) == 0
    result = json.loads((prereg.prereg_dir(repo) / f"{ID}.result.json").read_text())
    assert result["decision"] == "har" and result["p"] < 0.025 and result["ewc_t"] > 0 and result["ci"][0] > 0
    # Item 16: the result carries the registered threshold and the matched-null effective size
    assert result["threshold"] == result["alpha"] == 0.025
    assert result["effective_size"] == spec_for(store, repo)["effective_size"]


def test_the_decision_uses_the_registered_threshold(tmp_path):
    """Fix pass 2, item 16: the same clear difference (p about 0.001) is scored naive under a threshold of 0."""
    repo, store = throwaway(tmp_path, threshold=0.0)
    assert score(repo, store, np.random.default_rng(5).standard_normal(300) + 1.0) == 0
    result = json.loads((prereg.prereg_dir(repo) / f"{ID}.result.json").read_text())
    assert result["p"] < 0.025 and result["threshold"] == result["alpha"] == 0.0 and result["decision"] == "naive"


@pytest.mark.parametrize("name", ["result.json", "sessions.csv"])
def test_an_existing_result_file_is_refused(made_up, name, capsys):
    """tA, tA2, tB: the window put back in the working spent.jsonl (checkout, stash), the result still there."""
    repo, store = made_up
    (prereg.prereg_dir(repo) / f"{ID}.{name}").write_text("{}")
    refused(repo, store, capsys, "exists")


def test_an_uncommitted_spent_ledger_is_refused(made_up, capsys):
    """A scoring that was not committed: its line is in the working spent.jsonl only, the result files deleted."""
    repo, store = made_up
    assert score(repo, store) == 0
    for path in prereg.result_paths(ID, prereg.prereg_dir(repo)):
        path.unlink()
    refused(repo, store, capsys, "spent.jsonl is not committed")


def test_a_window_spent_in_history_stays_spent(made_up, capsys):
    """tA3: a scoring committed, then reverted (the line and the result files gone from HEAD)."""
    repo, store = made_up
    scored_and_committed(repo, store)
    (prereg.prereg_dir(repo) / prereg.SPENT).write_text("")
    for path in prereg.result_paths(ID, prereg.prereg_dir(repo)):
        path.unlink()
    commit(repo, 'Revert "scored"')
    assert prereg.read_lines(prereg.prereg_dir(repo) / prereg.SPENT) == []
    refused(repo, store, capsys, "shares dates with one spent")


def test_a_window_relabelled_with_another_split_is_still_spent(made_up, capsys):
    """tC: an amendment scores the same dates under the split label "development-2"."""
    repo, store = made_up
    scored_and_committed(repo, store)
    other = "2026-11-10-amend"
    prereg.write(spec_for(store, repo, prereg_id=other, windows=[window_of(made_up_days()[100:], "amend",
                                                                           "development-2")]),
                 "# amend\n", prereg.prereg_dir(repo))
    commit(repo, "amend")
    refused(repo, store, capsys, "shares dates with one spent", prereg_id=other, days=made_up_days()[100:])


@pytest.mark.parametrize("where", ["file", "folder"])
def test_a_symlink_on_a_checked_path_is_refused(tmp_path, where, capsys):
    """tK: the pre-registration's files point to copies committed at another path."""
    repo, store = throwaway(tmp_path)
    directory = prereg.prereg_dir(repo)
    elsewhere = repo / "elsewhere"
    shutil.copytree(directory, elsewhere)
    commit(repo, "files at another path")
    if where == "file":
        for ext in ("json", "md", "sha256"):
            (directory / f"{ID}.{ext}").unlink()
            (directory / f"{ID}.{ext}").symlink_to(elsewhere / f"{ID}.{ext}")
    else:
        shutil.rmtree(directory)
        directory.symlink_to(elsewhere, target_is_directory=True)
    assert prereg.paths(ID, directory)["json"].is_file()
    refused(repo, store, capsys, "is a symlink")


def test_a_git_environment_that_points_elsewhere_is_ignored(made_up, monkeypatch, capsys):
    """tL: GIT_DIR names a shadow repository in which the edited files are committed."""
    repo, store = made_up
    directory = prereg.prereg_dir(repo)
    (directory / f"{ID}.md").write_text("# edited\n")
    sums = {ext: prereg.file_sha256(directory / f"{ID}.{ext}") for ext in ("json", "md")}
    (directory / f"{ID}.sha256").write_text("".join(f"{sums[e]}  {ID}.{e}\n" for e in ("json", "md")))
    shadow = repo.parent / "shadow"
    shutil.copytree(repo, shadow, ignore=shutil.ignore_patterns(".git"))
    g(shadow, "init", "-q")
    commit(shadow, "shadow")
    monkeypatch.setenv("GIT_DIR", str(shadow / ".git"))
    plain = subprocess.run(["git", "-C", str(repo), "rev-parse", f"HEAD:{prereg.PREREG_REL}/{ID}.md"],
                           capture_output=True, text=True)
    assert plain.stdout.strip() == prereg.git_blob_sha1((directory / f"{ID}.md").read_bytes())    # the premise
    refused(repo, store, capsys, "not committed")


def test_a_replace_ref_is_ignored(made_up, capsys):
    """tM: `git replace` makes HEAD read as a commit of the edited files."""
    repo, store = made_up
    directory = prereg.prereg_dir(repo)
    original = g(repo, "rev-parse", "HEAD")
    (directory / f"{ID}.md").write_text("# edited\n")
    sums = {ext: prereg.file_sha256(directory / f"{ID}.{ext}") for ext in ("json", "md")}
    (directory / f"{ID}.sha256").write_text("".join(f"{sums[e]}  {ID}.{e}\n" for e in ("json", "md")))
    commit(repo, "fake")
    fake = g(repo, "rev-parse", "HEAD")
    g(repo, "reset", "-q", "--soft", original)
    g(repo, "replace", original, fake)
    assert g(repo, "rev-parse", f"HEAD:{prereg.PREREG_REL}/{ID}.md") == prereg.git_blob_sha1(
        (directory / f"{ID}.md").read_bytes())                                                # the premise
    refused(repo, store, capsys, "not committed")


def test_score_spends_the_window_before_it_computes_a_result(made_up, monkeypatch):
    """Item 8, fix pass 2 item 1: an append that fails leaves no result computed and no result file (the order:
    spend, then compute, then write)."""
    repo, store = made_up
    computed = []

    def broken(path, entry):
        raise OSError("disk full")

    def series_for(store, days):
        computed.append(len(days))
        return series_of(np.ones(300))(store, days)

    monkeypatch.setattr(prereg, "append_line", broken)
    monkeypatch.setattr(score_prereg, "check_tools_modules", lambda root, modules=None: None)
    with pytest.raises(OSError, match="disk full"):
        score_prereg.score(ID, store, repo, days_for=lambda s, w: made_up_days(), series_for=series_for,
                           modules_root=REPO)
    assert computed == []
    assert not any(os.path.lexists(p) for p in prereg.result_paths(ID, prereg.prereg_dir(repo)))


def test_a_window_whose_dates_changed_is_refused(made_up, capsys):
    repo, store = made_up
    refused(repo, store, capsys, "dates", days=made_up_days(301), d=np.ones(301))


# --- the run gate (item 3) -------------------------------------------------------------------------------------------

STRATEGY = RollingShortStraddle()
VALIDATION = dict(sample_start=date(2020, 1, 2), sample_end=date(2021, 12, 31), split="validation")
HOLDOUT = dict(sample_start=date(2024, 1, 2), sample_end=date(2025, 6, 30), split="holdout", data_source="dolthub",
               execution_mode="surface")            # ADR-0010 §1: the holdout runs on the DoltHub surface (item 4)


def trial(window, **extra):
    return RunConfig(**window, run_purpose="trial", prereg_id=ID, **extra)


def diag(**extra):
    """A validation diagnostic past 2019: it names its kind (fix pass 3, item D6)."""
    return RunConfig(**{**VALIDATION, "diagnostic_kind": "smoke", **extra})


LISTED = trial_hash(trial(VALIDATION), STRATEGY)
BENCHMARK = trial_hash(trial(VALIDATION), RollingShortStraddle(exit_dte=8))
# A configuration that no pre-registration lists: its smoke and budget diagnostics may run (fix pass 4, item F6d).
OTHER = RollingShortStraddle(exit_dte=5)
UNLISTED = trial_hash(trial(VALIDATION), OTHER)


@pytest.fixture
def gated(tmp_path):
    windows = [{"name": w["split"], "split": w["split"], "start": w["sample_start"].isoformat(),
                "end": w["sample_end"].isoformat()} for w in (VALIDATION, HOLDOUT)]
    assert trial_hash(trial(HOLDOUT), STRATEGY) == LISTED       # item 4: the split's source and mode are left out
    repo, _ = throwaway(tmp_path, windows=windows, candidates=[{"name": "x", "trial_hash": LISTED}],
                        benchmark={"name": "b", "trial_hash": BENCHMARK})
    return repo


def records(repo):
    """The runs the gate reserved: started lines merged with their completed lines (prereg.runs_of_record)."""
    return prereg.runs_of_record(repo)


def run_through(gate, cfg, strategy=STRATEGY, run_id="run"):
    """What run_backtest does with a gate: ask it, run, then call its recorder."""
    record = gate(cfg, strategy, trial_hash(cfg, strategy))
    if record is not None:
        record(run_id, "c" * 64)


def test_development_runs_pass_unrecorded_and_runs_past_2019_are_recorded_with_their_purpose(gated):
    gate = prereg.make_run_gate(gated)
    assert gate(RunConfig(date(2010, 1, 4), date(2019, 12, 31), "development", run_purpose="trial"), STRATEGY,
                LISTED) is None
    run_through(gate, diag(), OTHER, run_id="diag-1")
    assert [(r["run_id"], r["run_purpose"], r["split"], r["trial_hash"], r["completed"]) for r in records(gated)] == \
        [("diag-1", "diagnostic", "validation", UNLISTED, True)]
    lines = prereg.read_lines(prereg.prereg_dir(gated) / prereg.RECORDS)
    assert [line["event"] for line in lines] == ["started", "completed"]
    assert prereg.read_lines(gated / ".git" / prereg.SIDE_RECORDS) == lines


def test_a_spent_window_refuses_trials_and_diagnostics_whatever_its_label(gated):
    prereg.append_line(prereg.prereg_dir(gated) / prereg.SPENT,
                       {"window": {"name": "x", "split": "validation-2", "start": "2021-06-01", "end": "2022-06-30"},
                        "prereg_id": "older", "date": "x"})
    gate = prereg.make_run_gate(gated)
    for cfg in (trial(VALIDATION), diag()):
        with pytest.raises(PreregError, match="spent"):
            gate(cfg, STRATEGY, trial_hash(cfg, STRATEGY))
    assert records(gated) == []


def test_an_unlisted_trial_an_unknown_window_and_an_uncommitted_file_are_refused(gated):
    gate = prereg.make_run_gate(gated)
    run_through(gate, trial(VALIDATION))
    with pytest.raises(PreregError, match="unlisted"):
        gate(trial(VALIDATION), RollingShortStraddle(exit_dte=9), trial_hash(trial(VALIDATION),
                                                                             RollingShortStraddle(exit_dte=9)))
    with pytest.raises(PreregError, match="no window"):
        gate(trial({**VALIDATION, "sample_end": date(2021, 12, 30)}), STRATEGY, LISTED)
    (prereg.prereg_dir(gated) / f"{ID}.md").write_text("# edited\n")
    with pytest.raises(PreregError, match="does not match"):
        gate(trial(VALIDATION), STRATEGY, LISTED)


def test_a_holdout_trial_needs_its_validation_trial_of_record_and_runs_once(gated):
    """ADR-0010 test 4b on real RunConfigs: the holdout run finds its validation record by trial_hash, although the
    two configs' config_hash (split, dates, prereg) differ. A validation diagnostic is not a run of record (a surface
    run S: a smoke diagnostic of a listed configuration is refused, fix pass 4, item F6d)."""
    gate = prereg.make_run_gate(gated)
    with pytest.raises(PreregError, match="validation run of record"):
        gate(trial(HOLDOUT), STRATEGY, trial_hash(trial(HOLDOUT), STRATEGY))
    run_through(gate, diag(diagnostic_kind="surface_s", execution_mode="surface"), run_id="diagnostic")
    with pytest.raises(PreregError, match="validation run of record"):
        gate(trial(HOLDOUT), STRATEGY, trial_hash(trial(HOLDOUT), STRATEGY))
    run_through(gate, trial(VALIDATION), run_id="validation")
    run_through(gate, trial(HOLDOUT), run_id="holdout")
    assert [r["run_id"] for r in records(gated)] == ["diagnostic", "validation", "holdout"]
    with pytest.raises(PreregError, match="had its holdout run"):
        gate(trial(HOLDOUT), STRATEGY, trial_hash(trial(HOLDOUT), STRATEGY))
    with pytest.raises(PreregError, match="validation run of record"):         # the benchmark has none
        gate(trial(HOLDOUT), RollingShortStraddle(exit_dte=8), BENCHMARK)


def test_a_third_validation_re_run_is_refused_and_a_re_run_needs_a_reason(gated):
    """ADR-0010 test 8 on real RunConfigs: the run of record and two re-runs."""
    plain, reasoned = prereg.make_run_gate(gated), prereg.make_run_gate(gated, rerun_reason="defect #1")
    run_through(plain, trial(VALIDATION), run_id="run-1")
    with pytest.raises(PreregError, match="needs a reason"):
        plain(trial(VALIDATION), STRATEGY, LISTED)
    for n in (2, 3):
        run_through(reasoned, trial(VALIDATION), run_id=f"run-{n}")
    with pytest.raises(PreregError, match="third validation re-run"):
        reasoned(trial(VALIDATION), STRATEGY, LISTED)
    assert [(r["run_id"], r["rerun_reason"]) for r in records(gated)] == \
        [("run-1", None), ("run-2", "defect #1"), ("run-3", "defect #1")]


def test_run_backtest_records_a_validation_diagnostic_through_the_gate(gated, engine_store, tmp_path):
    """Item 3 ii end to end on the made-up store (2023 sessions): run_backtest asks the real gate, runs, and the
    gate's recorder logs the run with its purpose, its run id and both hashes."""
    import engine_helpers as eh

    strategy = eh.Scripted({})
    result = eh.run(engine_store, tmp_path / "runs", strategy, sample_end=date(2023, 1, 10), diagnostic_kind="smoke",
                    run_gate=prereg.make_run_gate(gated))
    assert [(r["run_id"], r["config_hash"], r["trial_hash"], r["run_purpose"], r["split"], r["diagnostic_kind"])
            for r in records(gated)] \
        == [(result.run_id, result.config_hash, trial_hash(eh.config(sample_end=date(2023, 1, 10)), strategy),
             "diagnostic", "validation", "smoke")]


# --- fix pass 2 (second review): the spend survives git, the gate reserves first, the boundary --------------------

def test_two_windows_that_share_exactly_one_date_overlap_in_both_orders(gated):
    """O14: a spent window that ends on the day the run's window starts (or starts on the day it ends) refuses the
    run; one day apart it passes."""
    first, last = VALIDATION["sample_start"].isoformat(), VALIDATION["sample_end"].isoformat()
    for spent in ({"start": "2019-06-03", "end": first}, {"start": last, "end": "2022-06-30"}):
        window = {"name": "x", "split": "other", **spent}
        assert prereg.overlaps(window, {"start": first, "end": last})
        assert prereg.overlaps({"start": first, "end": last}, window)
    path = prereg.prereg_dir(gated) / prereg.SPENT
    gate = prereg.make_run_gate(gated)
    for spent in ({"start": "2019-06-03", "end": first}, {"start": last, "end": "2022-06-30"}):
        path.write_text(json.dumps({"window": {"name": "x", "split": "other", **spent}, "prereg_id": "older",
                                    "date": "x"}) + "\n")
        with pytest.raises(PreregError, match="spent"):
            gate(diag(), OTHER, UNLISTED)
    path.write_text(json.dumps({"window": {"name": "x", "split": "other", "start": "2019-06-03",
                                           "end": "2020-01-01"}, "prereg_id": "older", "date": "x"}) + "\n")
    assert gate(diag(), OTHER, UNLISTED) is not None


def drop_side_ledger(repo) -> None:
    """Delete the spent side ledger: what is left is the history channel."""
    (prereg.common_dir(repo) / prereg.SIDE_SPENT).unlink()


def test_a1_a_scoring_stashed_with_its_result_files_stays_spent(made_up, capsys):
    """Review B A1: an uncommitted scoring, then `git stash -u` (spent.jsonl back to empty, the result files gone)."""
    repo, store = made_up
    assert score(repo, store) == 0
    g(repo, "stash", "-u")
    assert prereg.read_lines(prereg.prereg_dir(repo) / prereg.SPENT) == []
    refused(repo, store, capsys, "shares dates with one spent")
    drop_side_ledger(repo)
    refused(repo, store, capsys, "shares dates with one spent")             # the stash commit holds the line


def test_a1c_a_scoring_discarded_by_checkout_and_clean_stays_spent(made_up, capsys):
    """Review B A1c: an uncommitted scoring, then `git checkout -- .` and `git clean -fd`: no commit ever held the
    line, so only the side ledger in the git common directory remembers it."""
    repo, store = made_up
    assert score(repo, store) == 0
    g(repo, "checkout", "--", ".")
    g(repo, "clean", "-fdq")
    assert prereg.read_lines(prereg.prereg_dir(repo) / prereg.SPENT) == []
    refused(repo, store, capsys, "shares dates with one spent")


def test_a3_a_scoring_committed_on_another_branch_stays_spent(made_up, capsys):
    """Review B A3: scored and committed on branch "scoring", then the main branch checked out."""
    repo, store = made_up
    main = g(repo, "rev-parse", "--abbrev-ref", "HEAD")
    g(repo, "checkout", "-q", "-b", "scoring")
    scored_and_committed(repo, store)
    g(repo, "checkout", "-q", main)
    refused(repo, store, capsys, "shares dates with one spent")
    drop_side_ledger(repo)
    refused(repo, store, capsys, "shares dates with one spent")             # the branch holds the line


def test_a4_a_scoring_reset_away_stays_spent(made_up, capsys):
    """Review B A4: scored and committed, then `git reset --hard HEAD~1` (the commit is reachable from the reflog
    only)."""
    repo, store = made_up
    scored_and_committed(repo, store)
    g(repo, "reset", "-q", "--hard", "HEAD~1")
    refused(repo, store, capsys, "shares dates with one spent")
    drop_side_ledger(repo)
    refused(repo, store, capsys, "shares dates with one spent")             # the reflog holds the line


def test_a8_a_shallow_clone_is_refused(made_up, tmp_path, capsys):
    """Review B A8: scored, committed and reverted, then `git clone --depth 1`: the clone's one commit has an empty
    spent.jsonl and no side ledger, so a shallow repository is refused outright."""
    repo, store = made_up
    scored_and_committed(repo, store)
    g(repo, "revert", "--no-edit", "HEAD")
    clone = tmp_path / "clone"
    g(tmp_path, "clone", "-q", "--depth", "1", f"file://{repo}", str(clone))
    assert g(clone, "rev-parse", "--is-shallow-repository") == "true"
    refused(clone, store, capsys, "shallow")


def test_a9_a_cherry_pick_that_leaves_the_scoring_on_its_branch_stays_spent(made_up, capsys):
    """Review B A9: scored on branch "scoring" with a later doc fix there; main cherry-picks the doc fix only."""
    repo, store = made_up
    main = g(repo, "rev-parse", "--abbrev-ref", "HEAD")
    g(repo, "checkout", "-q", "-b", "scoring")
    scored_and_committed(repo, store)
    (repo / "NOTES.md").write_text("a doc fix\n")
    commit(repo, "doc fix")
    fix = g(repo, "rev-parse", "HEAD")
    g(repo, "checkout", "-q", main)
    g(repo, "cherry-pick", fix)
    refused(repo, store, capsys, "shares dates with one spent")
    drop_side_ledger(repo)
    refused(repo, store, capsys, "shares dates with one spent")


def test_scoring_spends_every_window_of_the_spec(tmp_path, capsys):
    """Fix pass 2, item 1: the review found only windows[0] spent. A spec with two windows spends both; a later
    pre-registration of the second window alone is refused."""
    days = made_up_days()
    second = [day + timedelta(days=700) for day in days]
    repo, store = throwaway(tmp_path, windows=[window_of(days, "first"), window_of(second, "second")])
    assert score(repo, store) == 0
    spent = [line for line in prereg.read_lines(prereg.prereg_dir(repo) / prereg.SPENT) if line["event"] == "spent"]
    assert [line["window"]["name"] for line in spent] == ["first", "second"]
    commit(repo, "scored")
    other = "2026-11-10-second"
    prereg.write(spec_for(store, repo, prereg_id=other, windows=[window_of(second, "again")]), "# again\n",
                 prereg.prereg_dir(repo))
    commit(repo, "the second window again")
    refused(repo, store, capsys, "shares dates with one spent", prereg_id=other, days=second)


def test_a_scorer_module_loaded_from_another_checkout_is_refused(made_up, tmp_path):
    """Fix pass 2, item 2 (review B claim 2): a PYTHONPATH that names another checkout's src/ puts its volbt ahead of
    the editable install. In a fresh interpreter, check() passes with PYTHONPATH at this checkout's src/ (what the
    editable install names) and refuses with it at another checkout's."""
    repo, store = made_up
    other = tmp_path / "other"
    shutil.copytree(REPO / "src", other / "src", ignore=shutil.ignore_patterns("__pycache__"))
    code = f"""
import sys
from pathlib import Path
sys.path.insert(0, {str(REPO / 'tools')!r})
import score_prereg, prereg
import volbt
store = type("S", (), {{"checked_table_file": lambda self, n: Path({str(store.root)!r}) / f"{{n}}.parquet"}})()
print("volbt", volbt.__file__)
try:
    score_prereg.check({ID!r}, store, Path({str(repo)!r}), modules_root=Path({str(REPO)!r}))
    print("passed")
except prereg.PreregError as error:
    print("refused:", error)
"""
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}

    def check(extra):
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=tmp_path,
                             env={**env, **extra})
        assert out.returncode == 0, out.stderr
        return out.stdout

    plain = check({"PYTHONPATH": str(REPO / "src")})
    assert f"volbt {REPO / 'src'}" in plain and plain.strip().endswith("passed"), plain
    shadowed = check({"PYTHONPATH": str(other / "src")})
    assert f"volbt {other / 'src'}" in shadowed, shadowed                         # the premise
    assert "refused: the module volbt" in shadowed and str(other / "src") in shadowed, shadowed


def test_two_gates_before_either_records_the_second_refuses(gated):
    """Fix pass 2, item 3 (review B B3): the gate reserves when it is asked, so a second holdout gate, asked before
    the first run recorded anything, is refused; so is a fourth validation trial whose earlier runs never recorded."""
    gate = prereg.make_run_gate(gated, rerun_reason="defect #1")
    run_through(gate, trial(VALIDATION), run_id="validation")
    assert gate(trial(HOLDOUT), STRATEGY, LISTED) is not None                  # started, not recorded
    with pytest.raises(PreregError, match="had its holdout run"):
        gate(trial(HOLDOUT), STRATEGY, LISTED)
    for _ in range(2):
        assert gate(trial(VALIDATION), STRATEGY, LISTED) is not None           # two re-runs, never recorded
    with pytest.raises(PreregError, match="third validation re-run"):
        gate(trial(VALIDATION), STRATEGY, LISTED)
    assert [(r["split"], r["completed"]) for r in records(gated)] == [
        ("validation", True), ("holdout", False), ("validation", False), ("validation", False)]


def test_a_recorder_that_fails_leaves_a_started_run_that_counts(gated, monkeypatch):
    """Fix pass 2, item 3 (review B B2): the completed line cannot be written; the started line still counts."""
    gate = prereg.make_run_gate(gated)
    record = gate(trial(VALIDATION), STRATEGY, LISTED)
    real = prereg.append_line

    def broken(path, entry):
        if entry.get("event") == "completed":
            raise OSError("disk full")
        real(path, entry)

    monkeypatch.setattr(prereg, "append_line", broken)
    with pytest.raises(OSError, match="disk full"):
        record("run-1", "c" * 64)
    monkeypatch.setattr(prereg, "append_line", real)
    assert [(r["split"], r["completed"]) for r in records(gated)] == [("validation", False)]
    with pytest.raises(PreregError, match="needs a reason"):
        gate(trial(VALIDATION), STRATEGY, LISTED)


def test_a_run_interrupted_in_on_session_end_keeps_its_started_record(engine_store, tmp_path):
    """Fix pass 2, item 3 (review B B1): run_backtest asks the real gate, then the run is interrupted in its first
    on_session_end. Its started line counts: a second run without a reason is a re-run, and refused."""
    import engine_helpers as eh

    strategy = eh.Scripted({})
    kw = dict(sample_end=date(2023, 1, 10), run_purpose="trial", prereg_id=ID)
    cfg = eh.config(**kw)
    window = {"name": "v", "split": "validation", "start": cfg.sample_start.isoformat(),
              "end": cfg.sample_end.isoformat()}
    repo, _ = throwaway(tmp_path, windows=[window], candidates=[{"name": "x", "trial_hash": trial_hash(cfg, strategy)}],
                        benchmark={"name": "b", "trial_hash": "b" * 64})

    def interrupt(t, book):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        eh.run(engine_store, tmp_path / "runs", strategy, run_gate=prereg.make_run_gate(repo),
               on_session_end=interrupt, **kw)
    assert [(r["run_purpose"], r["split"], r["completed"]) for r in records(repo)] == [("trial", "validation", False)]
    with pytest.raises(PreregError, match="needs a reason"):
        eh.run(engine_store, tmp_path / "again", strategy, run_gate=prereg.make_run_gate(repo), **kw)


def test_the_protocols_validation_trial_then_holdout_trial_passes(gated):
    """Fix pass 2, item 4 (review B claim 4a): ADR-0010 §1's validation run on OptionsDX quotes, then the same
    configuration's holdout run on the DoltHub surface: test 4b finds the validation record by trial_hash."""
    gate = prereg.make_run_gate(gated)
    validation, holdout = trial(VALIDATION), trial(HOLDOUT)
    assert (validation.data_source, validation.execution_mode) == ("optionsdx", "quote")
    assert (holdout.data_source, holdout.execution_mode) == ("dolthub", "surface")
    run_through(gate, validation, run_id="validation")
    run_through(gate, holdout, run_id="holdout")
    assert [(r["run_id"], r["split"], r["trial_hash"]) for r in records(gated)] == [
        ("validation", "validation", LISTED), ("holdout", "holdout", LISTED)]


# --- fix pass 3 (third review): diagnostics, the loaded modules, the side ledger's folder --------------------------

def test_a_diagnostic_past_2019_names_its_kind_and_the_gate_records_it(gated):
    """Item D6 (review D claim 6): a diagnostic past 2019 without a kind is refused before anything is recorded; a
    named one is recorded with its kind, data source and execution mode."""
    gate = prereg.make_run_gate(gated)
    with pytest.raises(PreregError, match="names its diagnostic_kind"):
        gate(RunConfig(**VALIDATION), STRATEGY, LISTED)
    assert records(gated) == []
    run_through(gate, diag(data_source="dolthub", execution_mode="surface"), OTHER, run_id="smoke-1")
    assert [(r["run_id"], r["diagnostic_kind"], r["data_source"], r["execution_mode"]) for r in records(gated)] == \
        [("smoke-1", "smoke", "dolthub", "surface")]


def test_the_volume_cap_runs_as_the_volume_cap_diagnostic_and_only_it(gated):
    """Item D6: ADR-0010 §1's volume cap is the diagnostic "volume_cap"; a volume-capped run under another kind is
    refused (RunConfig refuses the kind without the cap)."""
    gate = prereg.make_run_gate(gated)
    window = {**VALIDATION, "sample_start": date(2021, 1, 4)}
    with pytest.raises(PreregError, match="volume cap runs as"):
        gate(RunConfig(**window, cap_mode="volume", execution_mode="surface", diagnostic_kind="surface_s"), STRATEGY,
             LISTED)
    run_through(gate, RunConfig(**window, cap_mode="volume", diagnostic_kind="volume_cap"), run_id="cap")
    assert [(r["run_id"], r["diagnostic_kind"]) for r in records(gated)] == [("cap", "volume_cap")]


def test_a_diagnostic_re_run_needs_a_reason_and_the_third_re_run_is_refused(gated):
    """Item D6: a diagnostic with the trial_hash, kind, source and mode of an earlier one, started or completed, is a
    re-run and needs a reason, as for a validation trial. Fix pass 5, item G1 (review F claim 5; revised after the
    fifth review): a health run (smoke, budget) counts per trial_hash, kind, data source and execution mode, the run
    and two re-runs; the fourth is refused. Another source and mode, another health kind and an ADR diagnostic of the
    same trial_hash are first runs of their own: no reason, and no count toward this one."""
    plain, reasoned = prereg.make_run_gate(gated), prereg.make_run_gate(gated, rerun_reason="defect #2")
    run_through(plain, diag(), OTHER, run_id="smoke-1")
    with pytest.raises(PreregError, match="needs a reason"):
        plain(diag(), OTHER, UNLISTED)
    assert reasoned(diag(), OTHER, UNLISTED) is not None                         # started, never completed: counts
    run_through(reasoned, diag(), OTHER, run_id="smoke-3")
    with pytest.raises(PreregError, match="third re-run of the smoke run on optionsdx quote"):
        reasoned(diag(), OTHER, UNLISTED)
    run_through(plain, diag(data_source="dolthub", execution_mode="surface"), OTHER, run_id="smoke-dolthub")
    run_through(plain, diag(diagnostic_kind="budget"), OTHER, run_id="budget")
    run_through(plain, diag(diagnostic_kind="surface_s", execution_mode="surface"), OTHER, run_id="surface-s")
    assert [(r.get("run_id"), r["diagnostic_kind"], r["data_source"], r["rerun_reason"]) for r in records(gated)] == [
        ("smoke-1", "smoke", "optionsdx", None), (None, "smoke", "optionsdx", "defect #2"),
        ("smoke-3", "smoke", "optionsdx", "defect #2"), ("smoke-dolthub", "smoke", "dolthub", None),
        ("budget", "budget", "optionsdx", None), ("surface-s", "surface_s", "optionsdx", None)]


def test_a_structures_smoke_and_budget_runs_leave_its_adr_diagnostics_their_own_limits(gated):
    """Fix pass 5, item G1 (review F claim 5): a structure's smoke on both sources and its budget run share the
    trial_hash of the grid's "<structure>/always/dte" entry; its ADR-0009 §4 run S then passes. The ADR diagnostics
    count per trial_hash and kind: the fourth surface_s is refused, and the health runs still have their own re-runs.
    (A volume cap is another configuration: cap_mode enters the trial_hash.)"""
    import smoke_m4
    from volbt.strategies.grid import m4_grid

    structure = "short_straddle"
    smoke = {source: (smoke_m4.smoke_config(source, mode, *smoke_m4.VALIDATION),
                      smoke_m4.smoke_strategy(structure, source)) for source, mode in smoke_m4.MODES}
    budget = (smoke_m4.smoke_config("optionsdx", "quote", *smoke_m4.BUDGET, kind="budget"),
              smoke_m4.smoke_strategy(structure, "optionsdx"))
    entry = next(e for e in m4_grid("har") if e.label == f"{structure}/always/dte")
    surface_s = RunConfig(**{**entry.engine, "run_purpose": "diagnostic", "execution_mode": "surface",
                             "diagnostic_kind": "surface_s"}, **VALIDATION)
    shared = trial_hash(surface_s, entry.strategy)
    assert {trial_hash(cfg, strategy) for cfg, strategy in [*smoke.values(), budget]} == {shared}     # the premise
    plain, reasoned = prereg.make_run_gate(gated), prereg.make_run_gate(gated, rerun_reason="defect #3")
    for name, (cfg, strategy) in (("smoke-optionsdx", smoke["optionsdx"]), ("smoke-dolthub", smoke["dolthub"]),
                                  ("budget", budget)):
        run_through(plain, cfg, strategy, run_id=name)
    run_through(plain, surface_s, entry.strategy, run_id="surface-s-1")
    with pytest.raises(PreregError, match="re-run of the surface_s diagnostic needs a reason"):
        plain(surface_s, entry.strategy, shared)
    for n in (2, 3):
        run_through(reasoned, surface_s, entry.strategy, run_id=f"surface-s-{n}")
    with pytest.raises(PreregError, match="third re-run of the surface_s diagnostic"):
        reasoned(surface_s, entry.strategy, shared)
    run_through(reasoned, *smoke["optionsdx"], run_id="smoke-optionsdx-2")
    assert [(r["run_id"], r["diagnostic_kind"]) for r in records(gated)] == [
        ("smoke-optionsdx", "smoke"), ("smoke-dolthub", "smoke"), ("budget", "budget"), ("surface-s-1", "surface_s"),
        ("surface-s-2", "surface_s"), ("surface-s-3", "surface_s"), ("smoke-optionsdx-2", "smoke")]
    assert {r["trial_hash"] for r in records(gated)} == {shared}


def test_legacy_records_read_as_smoke_or_budget_by_the_stated_rule_without_a_rewrite(gated):
    """Item D6: a diagnostic line written before fix pass 3 has no diagnostic_kind; prereg.LEGACY_KIND_RULE reads it
    as "budget" when its window starts by 2019-12-31 and as "smoke" otherwise. A trial has none, and a line's own
    kind is kept. The file is read and appended to, never rewritten. Made-up lines, shaped like the nine real ones."""
    def line(run_id, start, purpose="diagnostic", prereg_id=None):
        return {"config_hash": "c" * 64, "date": "2026-11-09", "end": "2023-12-29", "prereg_id": prereg_id,
                "rerun_reason": None, "run_id": run_id, "run_purpose": purpose, "split": "validation",
                "start": start, "trial_hash": "t" * 64}

    legacy = [line("made-up-smoke", "2020-01-02"), line("made-up-budget", "2010-01-04"),
              line("made-up-trial", "2020-01-02", "trial", ID)]
    path = prereg.prereg_dir(gated) / prereg.RECORDS
    path.write_text("".join(json.dumps(x, sort_keys=True) + "\n" for x in legacy))
    before = path.read_bytes()
    assert [(r["run_id"], r["diagnostic_kind"]) for r in records(gated)] == [
        ("made-up-smoke", "smoke"), ("made-up-budget", "budget"), ("made-up-trial", None)]
    assert prereg.legacy_kind({**legacy[1], "diagnostic_kind": "volume_cap"}) == "volume_cap"
    assert path.read_bytes() == before
    run_through(prereg.make_run_gate(gated), diag(), OTHER, run_id="new")
    assert path.read_bytes().startswith(before) and len(prereg.read_lines(path)) == len(legacy) + 2


def test_a_module_whose_spec_origin_is_elsewhere_is_refused(monkeypatch, tmp_path):
    """Item D5 (review D claim 5): review D's forgery gave a module loaded from elsewhere the repository's __file__;
    its __spec__.origin still names where the import system found its code, and check_loaded compares both."""
    import importlib.machinery
    import types

    prereg.check_loaded(REPO)                                               # the premise: this process passes
    name = "volbt.analytics.inference"
    fake = types.ModuleType(name)
    fake.__file__ = sys.modules[name].__file__                               # the repository's path, forged
    fake.__spec__ = importlib.machinery.ModuleSpec(name, None, origin=str(tmp_path / "inference.py"))
    monkeypatch.setitem(sys.modules, name, fake)
    with pytest.raises(PreregError, match=r"inference is loaded from .*\(__spec__\.origin\)"):
        prereg.check_loaded(REPO)


def test_a_sitecustomize_or_usercustomize_from_outside_the_standard_library_is_refused(monkeypatch, tmp_path):
    """Item D5: such a module runs before the scorer and can put another module in place; one in the top folder of
    the interpreter's standard library is allowed, one in a subfolder of it (site-packages) is not."""
    import importlib.machinery
    import sysconfig
    import types

    for hook in ("sitecustomize", "usercustomize"):
        fake = types.ModuleType(hook)
        fake.__spec__ = importlib.machinery.ModuleSpec(hook, None, origin=str(tmp_path / f"{hook}.py"))
        monkeypatch.setitem(sys.modules, hook, fake)
        with pytest.raises(PreregError, match=f"a {hook} module is loaded from"):
            prereg.check_loaded(REPO)
        # fix pass 4, item O3: the base interpreter's site-packages is a subfolder of the standard library, and is
        # not its top folder
        inside = Path(sysconfig.get_path("stdlib")) / "site-packages" / f"{hook}.py"
        fake.__spec__ = importlib.machinery.ModuleSpec(hook, None, origin=str(inside))
        with pytest.raises(PreregError, match=f"a {hook} module is loaded from"):
            prereg.check_loaded(REPO)
        stdlib = Path(sysconfig.get_path("stdlib")) / f"{hook}.py"
        fake.__spec__ = importlib.machinery.ModuleSpec(hook, None, origin=str(stdlib))
        prereg.check_loaded(REPO)
        monkeypatch.delitem(sys.modules, hook)


def test_review_ds_sitecustomize_forgery_is_refused_before_the_spend(made_up, tmp_path):
    """Item D5: S/rev4/D/c5's attack in a fresh interpreter. A sitecustomize on PYTHONPATH loads inference.py from a
    copy outside the repository and gives it the repository's __file__; review D's made-up scoring then passed
    check_loaded. Now check() refuses, and spent.jsonl is as it was."""
    repo, store = made_up
    other, site = tmp_path / "other", tmp_path / "site"
    other.mkdir()
    site.mkdir()
    shutil.copyfile(REPO / "src/volbt/analytics/inference.py", other / "inference.py")
    (site / "sitecustomize.py").write_text(f"""
import importlib.util, sys
import volbt.analytics
spec = importlib.util.spec_from_file_location("volbt.analytics.inference", {str(other / 'inference.py')!r})
mod = importlib.util.module_from_spec(spec); sys.modules[spec.name] = mod; spec.loader.exec_module(mod)
mod.__file__ = {str(REPO / 'src/volbt/analytics/inference.py')!r}
volbt.analytics.inference = mod
""")
    code = f"""
import sys
from pathlib import Path
sys.path.insert(0, {str(REPO / 'tools')!r})
import score_prereg, prereg
from volbt.analytics import inference
store = type("S", (), {{"checked_table_file": lambda self, n: Path({str(store.root)!r}) / f"{{n}}.parquet"}})()
print("file", inference.__file__)
print("origin", inference.__spec__.origin)
try:
    score_prereg.check({ID!r}, store, Path({str(repo)!r}), modules_root=Path({str(REPO)!r}))
    print("passed")
except prereg.PreregError as error:
    print("refused:", error)
"""
    spent = (prereg.prereg_dir(repo) / prereg.SPENT).read_bytes()
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=tmp_path,
                         env={**env, "PYTHONPATH": f"{site}{os.pathsep}{REPO / 'src'}"})
    assert out.returncode == 0, out.stderr
    assert f"file {REPO / 'src/volbt/analytics/inference.py'}" in out.stdout, out.stdout     # the premise: forged
    assert f"origin {other / 'inference.py'}" in out.stdout, out.stdout
    assert "refused: a sitecustomize module is loaded from" in out.stdout, out.stdout
    assert (prereg.prereg_dir(repo) / prereg.SPENT).read_bytes() == spent


def test_a_new_ledger_file_has_its_folder_fsynced(tmp_path, monkeypatch):
    """Item D7 (review D claim 6): the append that creates a ledger fsyncs the file, then its folder, so the new name
    is as durable as the line; a later append fsyncs the file only."""
    import stat

    path = tmp_path / "common" / prereg.SIDE_SPENT
    path.parent.mkdir()
    synced, real = [], os.fsync

    def spy(fd):
        info = os.fstat(fd)
        synced.append("folder" if stat.S_ISDIR(info.st_mode) and info.st_ino == path.parent.stat().st_ino
                      else "file" if stat.S_ISREG(info.st_mode) else "other")
        real(fd)

    monkeypatch.setattr(prereg.os, "fsync", spy)
    prereg.append_line(path, {"line": 1})
    assert synced == ["file", "folder"]
    prereg.append_line(path, {"line": 2})
    assert synced == ["file", "folder", "file"]
    assert prereg.read_lines(path) == [{"line": 1}, {"line": 2}]


# --- fix pass 4 (fourth review): diagnostics by trial_hash, the scorer's process, grafts, the fragile band ---------

def test_a_smoke_or_budget_diagnostic_of_a_listed_configuration_is_refused(gated):
    """Item F6d (review E claim 4): a smoke or budget run of a candidate or benchmark that a pre-registration lists
    would run it on validation data outside its run of record: refused before anything is recorded. Another kind of
    diagnostic of it, and a smoke run of an unlisted configuration, pass. An unreadable pre-registration is refused."""
    gate = prereg.make_run_gate(gated)
    for kind in ("smoke", "budget"):
        for strategy, listed in ((STRATEGY, LISTED), (RollingShortStraddle(exit_dte=8), BENCHMARK)):
            with pytest.raises(PreregError, match="listed by a pre-registration"):
                gate(diag(diagnostic_kind=kind), strategy, listed)
    assert records(gated) == []
    run_through(gate, diag(diagnostic_kind="surface_s", execution_mode="surface"), run_id="surface-s")
    run_through(gate, diag(), OTHER, run_id="smoke-unlisted")
    assert [(r["run_id"], r["trial_hash"]) for r in records(gated)] == [("surface-s", LISTED),
                                                                         ("smoke-unlisted", UNLISTED)]
    (prereg.prereg_dir(gated) / "2026-11-10-unreadable.json").write_text("not json")
    with pytest.raises(PreregError, match="cannot be read as a pre-registration"):
        gate(diag(diagnostic_kind="budget"), RollingShortStraddle(exit_dte=6),
             trial_hash(diag(), RollingShortStraddle(exit_dte=6)))


def test_two_diagnostics_that_differ_only_in_their_trial_group_are_one_configuration(gated):
    """Item O1/F6a: the trial_group is a label (RunConfig.TRIAL_PLACEMENT), so a smoke config relabelled from
    "m4_smoke" to "anything_else" has the same trial_hash (its config_hash differs): it is a re-run, which needs a
    reason, and the relabelled runs count toward the same limit."""
    import dataclasses

    from volbt.engine.run_config import config_hash

    first, relabelled = diag(trial_group="m4_smoke"), diag(trial_group="anything_else")
    assert config_hash(first, OTHER) != config_hash(relabelled, OTHER)
    plain, reasoned = prereg.make_run_gate(gated), prereg.make_run_gate(gated, rerun_reason="relabelled")
    run_through(plain, first, OTHER, run_id="m4_smoke")
    with pytest.raises(PreregError, match="needs a reason"):
        plain(relabelled, OTHER, trial_hash(relabelled, OTHER))
    for n in (2, 3):
        run_through(reasoned, dataclasses.replace(first, trial_group=f"label-{n}"), OTHER, run_id=f"label-{n}")
    with pytest.raises(PreregError, match="third re-run"):
        run_through(reasoned, dataclasses.replace(first, trial_group="label-4"), OTHER)
    assert {r["trial_hash"] for r in records(gated)} == {UNLISTED} and len(records(gated)) == 3


def scorer_env() -> dict:
    """The environment for the scorer as a script: this one without the variables check_process refuses."""
    return {k: v for k, v in os.environ.items() if k not in score_prereg.HIDDEN_PATH_VARIABLES}


def run_scorer(script: Path, *args: str, env: dict | None = None, cwd: Path | None = None):
    return subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True,
                          env=env or scorer_env(), cwd=cwd)


def script_path(root: Path) -> list[str]:
    """sys.path as the scorer sees it when run as a script from <root>/tools: the folder first, then the standard
    library and the site-packages folders (where numpy, pandas and pytz are)."""
    site = [entry for entry in sys.path if entry.endswith("site-packages")]
    return [str(Path(root) / "tools"), *map(str, sorted(score_prereg.stdlib_entries())), *site]


@pytest.mark.parametrize("name", ["PYTHONPATH", "PYTHONHOME", "PYTHONUSERBASE"])
def test_the_process_check_refuses_a_hidden_path_variable(made_up, name):
    """Item F5 (review E claim 3): any of the three variables can put other code before the scorer's. (Fix pass 6:
    on a throwaway repository, whose tools/ is committed; the project's is not yet.)"""
    repo, _ = made_up
    path, source = script_path(repo), str(repo / prereg.SCORER)
    score_prereg.check_process(repo, environ={}, path=path, source=source, modules={})    # the premise: this passes
    with pytest.raises(PreregError, match=f"{name} is set"):
        score_prereg.check_process(repo, environ={name: ""}, path=path, source=source, modules={})


def test_the_process_check_refuses_a_path_entry_before_the_standard_library_and_a_main_from_elsewhere(made_up,
                                                                                                    tmp_path):
    """Item F5: an entry of sys.path before the standard library other than <root>/tools, and a main() defined in
    another file than <root>/tools/score_prereg.py, are refused; entries after the standard library are not."""
    repo, _ = made_up
    tools, stdlib = str(repo / "tools"), [str(p) for p in sorted(score_prereg.stdlib_entries())]
    source = str(repo / prereg.SCORER)
    score_prereg.check_process(repo, {}, [tools, *stdlib, str(tmp_path)], source, {})
    for path in ([tools, str(tmp_path), *stdlib], [str(tmp_path), tools, *stdlib], ["", *stdlib]):
        with pytest.raises(PreregError, match="comes before the standard library"):
            score_prereg.check_process(repo, {}, path, source, {})
    with pytest.raises(PreregError, match="no sys.path entry is the standard library"):
        score_prereg.check_process(repo, {}, [tools, str(tmp_path)], source, {})
    with pytest.raises(PreregError, match="main\\(\\) is defined in"):
        score_prereg.check_process(repo, {}, [tools, *stdlib], str(repo / "tools" / "score_copy.py"), {})


def test_review_es_json_shadow_on_pythonpath_is_refused_before_the_spend(made_up):
    """Item F5: S/rev5/E/c3's attack as a script. A json package on PYTHONPATH reads the spent lines as nothing, so a
    second scoring of a scored and committed made-up repository exited 0 and spent again. Now the scorer refuses
    because PYTHONPATH is set, and spent.jsonl keeps its two lines."""
    repo, store = made_up
    scored_and_committed(repo, store)
    shadow = repo.parent / "shadow" / "json"
    shadow.mkdir(parents=True)
    (shadow / "__init__.py").write_text(
        "import importlib.util, os, sys, sysconfig\n"
        "_path = os.path.join(sysconfig.get_path('stdlib'), 'json', '__init__.py')\n"
        "_spec = importlib.util.spec_from_file_location('json', _path, "
        "submodule_search_locations=[os.path.dirname(_path)])\n"
        "_real = importlib.util.module_from_spec(_spec)\n"
        "sys.modules['json'] = _real\n"
        "_spec.loader.exec_module(_real)\n"
        "_loads = _real.loads\n"
        "def _hide(s, *a, **k):\n"
        "    obj = _loads(s, *a, **k)\n"
        "    return {'event': 'ignored'} if isinstance(obj, dict) and obj.get('event') in ('spent', 'result') else obj\n"
        "_real.loads = _hide\n")
    spent = (prereg.prereg_dir(repo) / prereg.SPENT).read_bytes()
    assert len(spent.splitlines()) == 2                                          # the premise: scored once
    out = run_scorer(repo / prereg.SCORER, ID, "--store", str(store.root),
                     env={**scorer_env(), "PYTHONPATH": str(shadow.parent)})
    assert out.returncode == 2, out.stdout + out.stderr
    assert "refused: PYTHONPATH is set" in out.stderr, out.stderr
    assert (prereg.prereg_dir(repo) / prereg.SPENT).read_bytes() == spent


def test_an_edited_copy_of_the_scorer_under_another_name_is_refused(made_up):
    """Item F5: review E's score_copy.py passed every check because check_loaded knows the scorer by its file name.
    main() must be defined in <root>/tools/score_prereg.py."""
    repo, store = made_up
    copy = repo / "tools" / "score_copy.py"
    shutil.copyfile(repo / prereg.SCORER, copy)
    spent = (prereg.prereg_dir(repo) / prereg.SPENT).read_bytes()
    out = run_scorer(copy, ID, "--store", str(store.root))
    assert out.returncode == 2, out.stdout + out.stderr
    assert f"refused: main() is defined in {copy}" in out.stderr, out.stderr
    assert (prereg.prereg_dir(repo) / prereg.SPENT).read_bytes() == spent
    assert not any(os.path.lexists(p) for p in prereg.result_paths(ID, prereg.prereg_dir(repo)))


def git_would_commit(folder: str) -> list[str]:
    """The files under `folder` of the project that git would commit: tracked, or untracked and not ignored (git
    ls-files, read-only)."""
    out = subprocess.run(["git", "-C", str(REPO), "ls-files", "--cached", "--others", "--exclude-standard", "-z",
                          folder], capture_output=True, env=GIT_ENV)
    assert out.returncode == 0, out.stderr
    return sorted({name for name in out.stdout.decode().split("\0") if name and (REPO / name).is_file()})


def venv_for(repo: Path, where: Path) -> Path:
    """A virtual environment (python -m venv --without-pip) whose .pth names <repo>/src, then this interpreter's
    site-packages: `import volbt` loads the throwaway's closure, the libraries are this environment's, and no
    PYTHONPATH is set (the scorer refuses one). Its python, run on <repo>/tools/score_prereg.py, is the scorer as a
    script on the throwaway repository (the pattern of S/m4v7/venv)."""
    subprocess.run([sys._base_executable, "-m", "venv", "--without-pip", str(where)], check=True, capture_output=True)
    site = [entry for entry in sys.path if entry.endswith("site-packages")]
    (where / "lib" / f"python{sys.version_info[0]}.{sys.version_info[1]}" / "site-packages" / "throwaway.pth"
     ).write_text("".join(f"{line}\n" for line in [str(repo / "src"), *site]))
    return where / "bin" / "python"


def test_the_scorer_run_as_a_script_passes_the_process_and_loading_checks(tmp_path):
    """Item F5 (review E N1), revised in fix pass 6 (item H1). The setup path, `python tools/score_prereg.py <id>`, on
    a throwaway repository that holds every file of the project's tools/ that git would commit (and a
    tools/__pycache__ and an ignored node_modules folder, as the project's tree has), committed: it passes
    check_process and check_loaded and stops at the first file check, "no <id>.json". So no entry of the real tools/
    takes a name found elsewhere, and a committed tools/ passes the commit check; nor do two real entries share a
    module name or take a closure module's (name_clashes, which runs first; fix pass 7, item I1). On the project
    itself, which is not committed yet, the same command refuses at the first tools/ entry that `git status` lists,
    or, once everything is committed, at "no <id>.json". Nothing is written (the ledgers are compared byte for
    byte)."""
    made_up_id = "2026-11-10-no-such-pre-registration"
    repo = tmp_path / "repo"
    for rel in sorted(set(prereg.scorer_closure(REPO)) | set(git_would_commit("tools"))):
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / rel, repo / rel)
    shutil.copyfile(REPO / ".gitignore", repo / ".gitignore")
    g(repo, "init", "-q")
    commit(repo, "the project's tools/ and the scorer's closure")
    (repo / "tools" / "__pycache__").mkdir(exist_ok=True)
    (repo / "tools" / "__pycache__" / "prereg.cpython-312.pyc").write_bytes(b"")
    (repo / "tools" / "diagrams" / "node_modules" / "gyp").mkdir(parents=True)
    (repo / "tools" / "diagrams" / "node_modules" / "gyp" / "setup.py").write_text("")
    assert g(repo, "status", "--porcelain") == ""                                      # the premise: all ignored
    python = venv_for(repo, tmp_path / "venv")
    out = subprocess.run([str(python), str(repo / prereg.SCORER), made_up_id, "--store", str(tmp_path / "store")],
                         capture_output=True, text=True, env=scorer_env(), cwd=tmp_path)
    assert out.returncode == 2, out.stdout + out.stderr
    assert out.stderr.strip() == f"refused: {made_up_id}: no {made_up_id}.json", out.stderr
    # the project: the same command, with the project's interpreter
    ledgers = {name: (prereg.PREREG_DIR / name).read_bytes() for name in (prereg.SPENT, prereg.RECORDS)}
    out = run_scorer(REPO / prereg.SCORER, made_up_id, "--store", str(tmp_path / "store"), cwd=tmp_path)
    assert out.returncode == 2, out.stdout + out.stderr
    status = subprocess.run(["git", "--no-optional-locks", "-C", str(REPO), "status", "--porcelain",
                             "--untracked-files=all", "tools"],
                            capture_output=True, text=True, env=GIT_ENV).stdout.splitlines()
    listed = {line[3:] for line in status}
    if listed:
        first = out.stderr.removeprefix("refused: ").split(" is not committed as it is")[0]
        assert out.stderr.startswith("refused: ") and " is not committed as it is" in out.stderr, out.stderr
        assert Path(first).relative_to(REPO).as_posix() in listed, (first, listed)
    else:
        assert out.stderr.strip() == f"refused: {made_up_id}: no {made_up_id}.json", out.stderr
    assert {name: (prereg.PREREG_DIR / name).read_bytes() for name in ledgers} == ledgers
    assert not list(prereg.PREREG_DIR.glob(f"{made_up_id}*"))


def test_review_fs_gettext_shadow_in_tools_is_refused_before_the_spend(made_up):
    """Fix pass 5, item G5 (review F claim 4): a tools/gettext.py runs when argparse is imported, before main() and
    its checks, and the scorer's hash (the closure's files) does not change. This one prints a mark, then puts the
    real gettext in its place, so sys.modules shows the standard library's module: check_process refuses the file in
    tools/ by its name, before the spend."""
    repo, store = made_up
    (repo / "tools" / "gettext.py").write_text(
        "import importlib.util, os, sys, sysconfig\n"
        "print('the shadow ran', file=sys.stderr)\n"
        "_spec = importlib.util.spec_from_file_location('gettext', os.path.join(sysconfig.get_path('stdlib'), "
        "'gettext.py'))\n"
        "_real = importlib.util.module_from_spec(_spec)\n"
        "sys.modules['gettext'] = _real\n"
        "_spec.loader.exec_module(_real)\n")
    assert prereg.scorer_sha256(repo) == prereg.scorer_sha256(REPO)            # the premise: the hash is unchanged
    spent = (prereg.prereg_dir(repo) / prereg.SPENT).read_bytes()
    out = run_scorer(repo / prereg.SCORER, ID, "--store", str(store.root))
    assert out.returncode == 2, out.stdout + out.stderr
    assert out.stderr.startswith("the shadow ran\n"), out.stderr                  # it ran before any check
    assert (f"refused: {repo / 'tools' / 'gettext.py'} takes the name of the module 'gettext'" in out.stderr), \
        out.stderr
    assert (prereg.prereg_dir(repo) / prereg.SPENT).read_bytes() == spent
    assert not any(os.path.lexists(p) for p in prereg.result_paths(ID, prereg.prereg_dir(repo)))


def test_a_tools_entry_with_a_standard_library_name_or_a_name_found_elsewhere_is_refused(made_up):
    """Fix pass 5, item G5, revised in fix pass 6 (item H1, review G claim 2): every entry of tools/ that `import` can
    load (a folder, or a file with an import suffix) is refused when its name is a standard-library module's or when
    importlib.machinery.PathFinder finds it on another entry of sys.path: the libraries (numpy, pandas) and what they
    import after the process check (pytz, six, dateutil, _duckdb). Files with other suffixes, other names, and
    tools/__pycache__ (found as a namespace package in the standard library's folder) pass. (Fix pass 8, item J2:
    the bytecode file is tools/signal.pyc, which `import signal` can load; tools/signal.cpython-312.pyc, which no
    finder loads, is left out: test_a_tools_entry_whose_module_name_holds_a_dot_is_left_out_and_a_hyphen_is_read.)"""
    repo, _ = made_up
    tools = repo / "tools"
    args = ({}, script_path(repo), str(repo / prereg.SCORER), {})
    (tools / "fnmatch.txt").write_text("not importable")
    (tools / "notes.py").write_text("")
    (tools / "helpers").mkdir()
    (tools / "helpers" / "__init__.py").write_text("")
    commit(repo, "a note, a module and a folder of no other name")
    (tools / "__pycache__").mkdir(exist_ok=True)
    assert importlib.machinery.PathFinder.find_spec("__pycache__", args[1][1:]) is not None     # the premise
    score_prereg.check_process(repo, *args)                                    # the premise: these pass
    for name, make in (("fnmatch.py", lambda p: p.write_text("")), ("tokenize", lambda p: p.mkdir()),
                       ("signal.pyc", lambda p: p.write_bytes(b"")),
                       ("numpy", lambda p: p.mkdir()), ("pandas.py", lambda p: p.write_text("")),
                       ("pytz.py", lambda p: p.write_text("")), ("six.py", lambda p: p.write_text("")),
                       ("dateutil", lambda p: p.mkdir()), ("_duckdb.abi3.so", lambda p: p.write_bytes(b""))):
        make(tools / name)
        module = name.split(".")[0]
        with pytest.raises(PreregError, match=f"takes the name of the module '{module}'"):
            score_prereg.check_process(repo, *args)
        shutil.rmtree(tools / name) if (tools / name).is_dir() else (tools / name).unlink()
    score_prereg.check_process(repo, *args)


def test_review_gs_pytz_shadow_in_tools_is_refused_before_it_runs(made_up):
    """Fix pass 6, item H1 (review G claim 2): pandas imports pytz after check_process ran, so review G's untracked
    tools/pytz.py ran inside check() and patched the result. As a script now, the scorer refuses it by its name (pytz
    is found in site-packages) before any third-party import: it never runs, nothing is spent and no result file is
    written. Committed, it is refused the same way."""
    repo, store = made_up
    mark = repo.parent / "pytz_ran.txt"
    (repo / "tools" / "pytz.py").write_text(f"open({str(mark)!r}, 'w').write('ran')\n")
    spent = (prereg.prereg_dir(repo) / prereg.SPENT).read_bytes()
    for committed in (False, True):
        if committed:
            commit(repo, "the shadow, committed")
        out = run_scorer(repo / prereg.SCORER, ID, "--store", str(store.root))
        assert out.returncode == 2, out.stdout + out.stderr
        assert out.stderr.startswith(f"refused: {repo / 'tools' / 'pytz.py'} takes the name of the module 'pytz' ("), \
            out.stderr
        assert "site-packages" in out.stderr and not mark.exists(), out.stderr        # found there; it never ran
        assert (prereg.prereg_dir(repo) / prereg.SPENT).read_bytes() == spent
        assert not (repo / ".git" / prereg.SIDE_SPENT).exists()
        assert not any(os.path.lexists(p) for p in prereg.result_paths(ID, prereg.prereg_dir(repo)))


def test_an_entry_of_tools_that_takes_a_closure_modules_name_is_refused_before_it_runs(made_up):
    """Fix pass 7, item I1 (review H claims 1 and 2): Python's finder tries a package folder and an extension module
    before a .py file, so a tools/prereg/ package ran in place of tools/prereg.py at score_prereg's `import prereg`,
    before every check, and the name check passed it (prereg is found nowhere else). Run as a script, the scorer now
    refuses before `import prereg`: a committed package that writes a marker (it never runs), then a committed file
    named as an extension module beside tools/forecast_test.py. Nothing is spent and no result file is written."""
    repo, store = made_up
    tools = repo / "tools"
    mark = repo.parent / "prereg_package_ran.txt"
    package = tools / "prereg"
    package.mkdir()
    (package / "__init__.py").write_text(f"open({str(mark)!r}, 'w').write('ran')\n")
    extension = tools / f"forecast_test{importlib.machinery.EXTENSION_SUFFIXES[0]}"
    spent = (prereg.prereg_dir(repo) / prereg.SPENT).read_bytes()
    for shadow, name in ((package, "prereg"), (extension, "forecast_test")):
        if shadow == extension:
            shutil.rmtree(package)
            extension.write_bytes(b"not a shared object")
        commit(repo, f"{shadow.name}, committed")
        out = run_scorer(repo / prereg.SCORER, ID, "--store", str(store.root))
        assert out.returncode == 2, out.stdout + out.stderr
        expected = (f"refused: {shadow} takes the name of the scorer's module {name!r}: `import {name}` can load it "
                    f"in place of {tools / (name + '.py')}, the file the scorer's SHA-256 covers\n")
        assert out.stderr == expected, out.stderr
        assert not mark.exists()                                                     # the package never ran
        assert (prereg.prereg_dir(repo) / prereg.SPENT).read_bytes() == spent
        assert not (repo / ".git" / prereg.SIDE_SPENT).exists()
        assert not any(os.path.lexists(p) for p in prereg.result_paths(ID, prereg.prereg_dir(repo)))


def test_sysconfigs_data_module_in_tools_is_refused_by_its_name_before_it_runs(made_up):
    """Fix pass 8, item J2 (review I claim 3): check_process's stdlib_entries calls sysconfig.get_path, which imports
    sysconfig's data module (_sysconfigdata__linux_aarch64-linux-gnu here) with __import__, tools/ first on sys.path.
    Fix pass 7 left that name out of the checks (it is not an identifier), so a committed or uncommitted
    tools/<that name>.py ran, and one that put the standard library's module in its own sys.modules slot scored. Run
    as a script on a committed throwaway, the scorer now refuses it by its name, before sysconfig imports it: neither
    the plain file nor the one that swaps itself writes its marker. Nothing is spent and no result file is written."""
    import sysconfig

    repo, store = made_up
    sysconfig.get_config_vars()
    data = next(name for name in sys.modules if name.startswith("_sysconfigdata_"))
    real = os.path.join(sysconfig.get_path("stdlib"), f"{data}.py")
    assert not data.isidentifier() and os.path.isfile(real)                         # the premise: a hyphenated name
    mark = repo.parent / "sysconfigdata_ran.txt"
    shadow = repo / "tools" / f"{data}.py"
    spent = (prereg.prereg_dir(repo) / prereg.SPENT).read_bytes()
    plain = f"open({str(mark)!r}, 'a').write('ran')\nexec(compile(open({real!r}).read(), {real!r}, 'exec'))\n"
    swaps = (f"open({str(mark)!r}, 'a').write('ran')\nimport importlib.util, sys\n"
             f"_spec = importlib.util.spec_from_file_location({data!r}, {real!r})\n"
             "_real = importlib.util.module_from_spec(_spec)\n_spec.loader.exec_module(_real)\n"
             "build_time_vars = _real.build_time_vars\nsys.modules[__name__] = _real\n")
    for code in (plain, swaps):
        shadow.write_text(code)
        commit(repo, f"{shadow.name}, committed")
        out = run_scorer(repo / prereg.SCORER, ID, "--store", str(store.root))
        assert out.returncode == 2, out.stdout + out.stderr
        assert out.stderr == (f"refused: {shadow} takes the name of the module {data!r} ({real}): tools/ comes first "
                              "on sys.path, so it would run in its place\n"), out.stderr
        assert not mark.exists()                                                     # it never ran
        assert (prereg.prereg_dir(repo) / prereg.SPENT).read_bytes() == spent
        assert not (repo / ".git" / prereg.SIDE_SPENT).exists()
        assert not any(os.path.lexists(p) for p in prereg.result_paths(ID, prereg.prereg_dir(repo)))


def test_the_variable_that_names_sysconfigs_data_module_is_refused_before_a_tools_file_of_that_name_runs(made_up):
    """Fix pass 9, item K2 (review J N1): sysconfig imports the module that _PYTHON_SYSCONFIGDATA_NAME names. Set to
    zz_data, with a committed tools/zz_data.py, the name check passed the file (zz_data is found nowhere else) and
    check_process's sysconfig.get_path ran it; one that put the standard library's module in its own sys.modules slot
    and deleted its own file scored. Run as a script on a committed throwaway, the scorer now refuses the variable
    first, with its own reason: the file never runs. Nothing is spent and no result file is written."""
    import inspect
    import sysconfig

    repo, store = made_up
    assert "_PYTHON_SYSCONFIGDATA_NAME" in inspect.getsource(sysconfig._get_sysconfigdata_name)      # the premise
    sysconfig.get_config_vars()
    data = next(name for name in sys.modules if name.startswith("_sysconfigdata_"))
    real = os.path.join(sysconfig.get_path("stdlib"), f"{data}.py")
    mark = repo.parent / "zz_data_ran.txt"
    shadow = repo / "tools" / "zz_data.py"
    shadow.write_text(f"open({str(mark)!r}, 'a').write('ran')\n"
                      f"exec(compile(open({real!r}).read(), {real!r}, 'exec'))\n")
    commit(repo, f"{shadow.name}, committed")
    spent = (prereg.prereg_dir(repo) / prereg.SPENT).read_bytes()
    out = run_scorer(repo / prereg.SCORER, ID, "--store", str(store.root),
                     env={**scorer_env(), "_PYTHON_SYSCONFIGDATA_NAME": "zz_data"})
    assert out.returncode == 2, out.stdout + out.stderr
    assert out.stderr == ("refused: _PYTHON_SYSCONFIGDATA_NAME is set ('zz_data'): it names the module sysconfig "
                          "imports; unset it to score\n"), out.stderr
    assert not mark.exists()                                                         # it never ran
    assert (prereg.prereg_dir(repo) / prereg.SPENT).read_bytes() == spent
    assert not (repo / ".git" / prereg.SIDE_SPENT).exists()
    assert not any(os.path.lexists(p) for p in prereg.result_paths(ID, prereg.prereg_dir(repo)))


def test_name_clashes_refuses_a_closure_name_held_by_another_entry_and_two_entries_of_one_name(tmp_path):
    """Fix pass 7, item I1: CLOSURE_TOOLS are the tools/ modules of prereg.scorer_closure(). name_clashes passes the
    project's tools/ and a folder that holds the closure's .py files and a helper. It refuses, beside a closure .py,
    a package folder, an extension module or a .pyc; a closure module's name held by a .pyc alone; and a folder or
    an extension module beside a module of any other name. Fix pass 8, item J2 (review I N1): module names are
    tools_entries', so a tools/foo-bar.py and a tools/foo-bar/ share 'foo-bar' and are refused, and a
    tools/prereg.old.py, tools/report_m1.v2.py or tools/diagrams.bak/ beside the modules of those names is not."""
    assert score_prereg.CLOSURE_TOOLS == tuple(sorted(prereg.module_name(rel) for rel in prereg.scorer_closure()
                                                      if rel.startswith("tools/")))
    assert score_prereg.name_clashes(REPO / "tools") is None
    tools = tmp_path / "tools"
    tools.mkdir()
    for name in (*score_prereg.CLOSURE_TOOLS, "helper"):
        (tools / f"{name}.py").write_text("")
    assert score_prereg.name_clashes(tools) is None                                # the premise
    suffix = importlib.machinery.EXTENSION_SUFFIXES[0]
    closure, other = "takes the name of the scorer's module", "share the module name"
    for entry, made, expected in (("prereg", "folder", f"{closure} 'prereg'"),
                                  (f"score_prereg{suffix}", "file", f"{closure} 'score_prereg'"),
                                  ("forecast_test.abi3.so", "file", f"{closure} 'forecast_test'"),
                                  ("prereg.pyc", "file", f"{closure} 'prereg'"),
                                  ("helper", "folder", f"{other} 'helper'"),
                                  (f"helper{suffix}", "file", f"{other} 'helper'")):
        path = tools / entry
        path.mkdir() if made == "folder" else path.write_bytes(b"")
        assert expected in (score_prereg.name_clashes(tools) or ""), entry
        shutil.rmtree(path) if made == "folder" else path.unlink()
    for name in ("report_m1", "diagrams"):
        (tools / f"{name}.py").write_text("")
    (tools / "prereg.old.py").write_text("")
    (tools / "report_m1.v2.py").write_text("")
    (tools / "diagrams.bak").mkdir()
    assert score_prereg.name_clashes(tools) is None                                # no import loads them
    (tools / "foo-bar.py").write_text("")
    assert score_prereg.name_clashes(tools) is None                                # the premise: one entry
    (tools / "foo-bar").mkdir()
    assert f"{other} 'foo-bar'" in (score_prereg.name_clashes(tools) or "")
    (tools / "foo-bar").rmdir()
    (tools / "prereg.py").unlink()
    (tools / "prereg.pyc").write_bytes(b"")
    assert f"{closure} 'prereg'" in (score_prereg.name_clashes(tools) or "")


def test_a_tools_entry_git_does_not_hold_as_committed_is_refused(made_up):
    """Fix pass 6, item H1 (c): a module named after an optional dependency that is not installed (tools/numexpr.py:
    pandas imports numexpr when it exists) takes no name found elsewhere; check_process refuses it while git does not
    hold it as committed, and passes it once it is committed (the check under the lock then refuses it if sys.modules
    holds it then; a module whose import raised is not held: fix pass 7, item I2). Also refused: an edited committed
    file, an untracked folder, an untracked module directly in a committed folder, and an untracked bytecode file
    (git-ignored). Deeper files of a committed folder and tools/__pycache__ pass (default taken 2026-11-10, owner can
    override). (Fix pass 8, item J2: the bytecode file is tools/tables.pyc, which `import tables` can load;
    tools/tables.cpython-312.pyc, which no finder loads, is left out.) Fix pass 9, item K1 (review J claim 1): as the
    .md says, an edited committed deeper file and untracked files without an import suffix, in tools/ or directly in a
    committed folder, pass too: the commit check does not read them."""
    repo, _ = made_up
    tools = repo / "tools"
    args = ({}, script_path(repo), str(repo / prereg.SCORER), {})
    for name in ("numexpr", "bottleneck"):
        assert importlib.machinery.PathFinder.find_spec(name, args[1][1:]) is None             # the premise
    (repo / ".gitignore").write_text("__pycache__/\n*.pyc\nnode_modules/\n")
    (tools / "kit").mkdir()
    (tools / "kit" / "build.py").write_text("")
    (tools / "kit" / "sub").mkdir()
    (tools / "kit" / "sub" / "y.py").write_text("")
    commit(repo, "a folder of tools")
    (tools / "kit" / "node_modules" / "gyp").mkdir(parents=True)
    (tools / "kit" / "node_modules" / "gyp" / "setup.py").write_text("")
    (tools / "kit" / "deeper").mkdir()
    (tools / "kit" / "deeper" / "x.py").write_text("")
    (tools / "kit" / "sub" / "y.py").write_text("edited = True\n")           # item K1: files the check does not read
    (tools / "kit" / "notes.txt").write_text("")
    (tools / "NOTES").write_text("")
    (tools / "__pycache__").mkdir(exist_ok=True)
    (tools / "__pycache__" / "numexpr.cpython-312.pyc").write_bytes(b"")
    score_prereg.check_process(repo, *args)                                    # the premise: this passes
    stray = tools / "numexpr.py"
    stray.write_text("__version__ = '2.11.0'\n")
    with pytest.raises(PreregError, match=f"{stray} is not committed as it is"):
        score_prereg.check_process(repo, *args)
    commit(repo, "numexpr.py, committed")
    score_prereg.check_process(repo, *args)                                    # committed: it passes (c)
    package, pyc = tools / "bottleneck", tools / "tables.pyc"
    for make, entry in ((lambda: stray.write_text("__version__ = '9'\n"), stray),
                        (lambda: package.mkdir() or (package / "__init__.py").write_text(""), package),
                        (lambda: (tools / "kit" / "numba.py").write_text(""), tools / "kit" / "numba.py"),
                        (lambda: pyc.write_bytes(b""), pyc)):
        make()
        assert score_prereg.uncommitted_entries(repo) == [entry]
        with pytest.raises(PreregError, match=f"{entry} is not committed as it is"):
            score_prereg.check_process(repo, *args)
        g(repo, "checkout", "-q", "--", ".")
        g(repo, "clean", "-q", "-fd", "--", "tools/bottleneck", "tools/kit/numba.py")
        if entry.name.endswith(".pyc"):
            entry.unlink()
    score_prereg.check_process(repo, *args)


def test_a_tools_entry_whose_module_name_holds_a_dot_is_left_out_and_a_hyphen_is_read(made_up):
    """Fix pass 8, item J2 (review I claim 3 and N1; it replaces fix pass 7's item I3 test): a file's module name is its
    name less the longest import suffix, a folder's is its name. An entry whose module name holds a dot is left out,
    as no finder loads it under any name: tools/prereg.old.py, tools/report_m1.v2.py, tools/diagrams.bak/,
    tools/.ipynb_checkpoints/ (which the project's .gitignore lists), tools/.mypy_cache/ and a
    tools/signal.cpython-312.pyc (bytecode is found as <name>.pyc, so `import signal` cannot load it). Uncommitted,
    they pass check_process and name_clashes. A name with a hyphen is read (sysconfig imports one by such a name):
    an uncommitted tools/build-notes/ and tools/old-prereg.py are refused until committed. A new folder with an
    identifier name is refused too: git holds no empty folder, and `import` loads one as a namespace package."""
    repo, _ = made_up
    tools = repo / "tools"
    args = ({}, script_path(repo), str(repo / prereg.SCORER), {})
    names = {f"a{importlib.machinery.EXTENSION_SUFFIXES[0]}": "a", "b.abi3.so": "b", "c.so": "c", "d.pyc": "d",
             "e-f.py": "e-f", "g h.py": "g h"}
    for name in names:
        (tools / name).write_bytes(b"")
    (tools / "kit-2").mkdir()
    assert dict((entry.name, name) for name, entry in score_prereg.tools_entries(tools)
                if name not in score_prereg.CLOSURE_TOOLS) == {**names, "kit-2": "kit-2"}
    for name in (*names, "kit-2"):
        shutil.rmtree(tools / name) if (tools / name).is_dir() else (tools / name).unlink()
    for folder in (".ipynb_checkpoints", ".mypy_cache", "diagrams.bak"):
        (tools / folder).mkdir()
        (tools / folder / "notes.py").write_text("")
    for name in ("prereg.old.py", "report_m1.v2.py", "signal.cpython-312.pyc"):
        (tools / name).write_bytes(b"")
    assert [name for name, _ in score_prereg.tools_entries(tools)] == ["forecast_test", "prereg", "score_prereg"]
    assert score_prereg.name_clashes(tools) is None and score_prereg.uncommitted_entries(repo) == []
    score_prereg.check_process(repo, *args)
    for entry in (tools / "build-notes", tools / "old-prereg.py", tools / "scratch"):
        entry.mkdir() if entry.suffix == "" else entry.write_text("")
        if entry.name == "build-notes":
            (entry / "notes.py").write_text("")
        with pytest.raises(PreregError, match=f"{entry} is not committed as it is"):
            score_prereg.check_process(repo, *args)
        if entry.name != "scratch":
            commit(repo, f"{entry.name}, committed")
            score_prereg.check_process(repo, *args)                                # committed: it passes


def test_the_process_check_itself_refuses_a_module_loaded_from_tools_outside_the_closure(made_up):
    """Fix pass 7, item I5 (review H L4: with check_process's own call of check_tools_modules removed, every test still
    passed, as they pass modules={}). check_process, not check_tools_modules alone, refuses a module in `modules`
    loaded from a committed tools/ file outside the closure whose name is found nowhere else: the name check and the
    commit check pass that file. On the scorer's own imports no such module is loaded by then (the setup-path test),
    so this refusal needs other code to have run first."""
    import types

    repo, _ = made_up
    (repo / "tools" / "helper.py").write_text("")
    commit(repo, "a tools/ module of no other name, committed")
    args = ({}, script_path(repo), str(repo / prereg.SCORER))
    score_prereg.check_process(repo, *args, {})                                    # the premise: this passes
    stray = types.ModuleType("helper")
    stray.__file__ = str(repo / "tools" / "helper.py")
    with pytest.raises(PreregError, match="the module 'helper' is loaded from .*outside the scorer's closure"):
        score_prereg.check_process(repo, *args, {"helper": stray})


def test_main_passes_sys_modules_to_the_process_check_a_shadow_that_removed_its_file_is_refused(made_up):
    """Fix pass 8, item J3 (review I claim 5: with main() calling check_process(prereg.REPO, modules={}), every
    behavioural test passed). Run as a script: a tools/gettext.py runs when score_prereg.py imports argparse, runs the
    standard library's gettext in its own module (so argparse works), then deletes its own file. The name check and
    the commit check read the files of tools/, and none is left, so only check_process's scan of sys.modules, which
    still holds the module, refuses it, before any third-party import (with modules={}, the run goes on to
    check_loaded, which refuses the project's volbt instead). Fix pass 9, item K3 (review J N2): in a throwaway whose
    volbt is its own, that mutant gave the same stderr, from the scan under the ledgers' lock. So the shadow also
    records at exit whether numpy is in sys.modules: it is not, so the refusal came before any third-party import.
    Nothing is spent and no result file is written."""
    repo, store = made_up
    shadow, numpy_at_exit = repo / "tools" / "gettext.py", repo.parent / "numpy_at_exit.txt"
    shadow.write_text("import atexit, os, sys\n"
                      f"atexit.register(lambda: open({str(numpy_at_exit)!r}, 'w').write(str('numpy' in sys.modules)))\n"
                      "_real = os.path.join(os.path.dirname(os.__file__), 'gettext.py')\n"
                      "exec(compile(open(_real).read(), _real, 'exec'))\nos.remove(__file__)\n"
                      "print('the shadow ran and removed its file', file=sys.stderr)\n")
    spent = (prereg.prereg_dir(repo) / prereg.SPENT).read_bytes()
    out = run_scorer(repo / prereg.SCORER, ID, "--store", str(store.root))
    assert out.returncode == 2, out.stdout + out.stderr
    assert not shadow.exists()                                                       # the premise: it removed itself
    assert numpy_at_exit.read_text() == "False", out.stderr         # refused before any third-party import (item K3)
    assert out.stderr == ("the shadow ran and removed its file\n"
                          f"refused: the module 'gettext' is loaded from {shadow}, a file of tools/ outside the "
                          "scorer's closure: code that is not hashed ran in this process\n"), out.stderr
    assert (prereg.prereg_dir(repo) / prereg.SPENT).read_bytes() == spent
    assert not (repo / ".git" / prereg.SIDE_SPENT).exists()
    assert not any(os.path.lexists(p) for p in prereg.result_paths(ID, prereg.prereg_dir(repo)))


def made_up_store(root: Path, days: list[date], close=100.0):
    """A volbt Store with made-up spy_bars and dividends tables (what the scorer's checks and window read); `close`
    is a number or one price per day."""
    import pandas as pd

    from volbt.data.store import Store

    store = Store(root)
    store.write_table("spy_bars", pd.DataFrame({"date": days, "open": close, "high": close, "low": close,
                                                "close": close, "adj_close": close, "volume": 1}), sort_by=("date",))
    store.write_table("dividends", pd.DataFrame({"ex_date": [days[10]], "amount": [0.5]}), sort_by=("ex_date",))
    return store


def test_a_tools_module_imported_after_the_process_check_is_refused_before_the_spend(tmp_path):
    """Fix pass 6, item H1 (b): a committed tools/numexpr.py takes no name found elsewhere, so check_process passes it;
    pandas imports it after that check. Run as a script (in a virtual environment whose volbt is the throwaway's), the
    scorer passes every check on a made-up store and pre-registration, then, under the ledgers' lock just before the
    first spent line, refuses the module loaded from tools/: the module ran, nothing is spent and no result file is
    written."""
    import forecast_test as ft
    from volbt.data.store import session_calendar

    store = made_up_store(tmp_path / "real_store", made_up_days(320))
    calendar = session_calendar(store)
    window = {**window_of(ft.window(calendar, calendar[0], calendar[-1])), "last_target_end": calendar[-1].isoformat()}
    repo, _ = throwaway(tmp_path, windows=[window], data=prereg.store_tables(store))
    (repo / "tools" / "numexpr.py").write_text("import sys\n__version__ = '2.11.0'\n"
                                               "print('tools/numexpr.py ran', file=sys.stderr)\n")
    commit(repo, "a module named after an optional dependency, committed")
    python = venv_for(repo, tmp_path / "venv")
    out = subprocess.run([str(python), str(repo / prereg.SCORER), ID, "--store", str(store.root)],
                         capture_output=True, text=True, env=scorer_env(), cwd=tmp_path)
    assert out.returncode == 2, out.stdout + out.stderr
    assert out.stderr.startswith("tools/numexpr.py ran\n"), out.stderr                      # pandas imported it
    assert (f"refused: the module 'numexpr' is loaded from {repo / 'tools' / 'numexpr.py'}, a file of tools/ outside "
            "the scorer's closure") in out.stderr, out.stderr
    assert (prereg.prereg_dir(repo) / prereg.SPENT).read_bytes() == b""
    assert not (repo / ".git" / prereg.SIDE_SPENT).exists() and not (repo / ".git" / prereg.LOCK).exists()
    assert not any(os.path.lexists(p) for p in prereg.result_paths(ID, prereg.prereg_dir(repo)))


def test_a_committed_tools_module_whose_import_raises_is_not_refused(tmp_path):
    """Fix pass 7, item I2 (review H L1), a gap this test pins: a committed tools/numexpr.py runs when pandas imports
    it; when its import raises ImportError, Python removes it from sys.modules, so the scan under the ledgers' lock
    does not see it, and the scorer scores (review H's module replaced the result before it raised). The .md and the
    docstrings say so. A check that closes the gap changes them and this test. Made-up store (a random walk, long
    enough for the HAR fit) and pre-registration, in a throwaway repository."""
    import forecast_test as ft
    from volbt.data.store import session_calendar

    days = made_up_days(1200)
    close = 100 * np.exp(np.cumsum(0.01 * np.random.default_rng(11).standard_normal(len(days))))
    store = made_up_store(tmp_path / "real_store", days, close)
    calendar = session_calendar(store)
    window = {**window_of(ft.window(calendar, calendar[700], calendar[-1])),
              "last_target_end": calendar[-1].isoformat()}
    repo, _ = throwaway(tmp_path, windows=[window], data=prereg.store_tables(store))
    (repo / "tools" / "numexpr.py").write_text("import sys\nprint('tools/numexpr.py ran', file=sys.stderr)\n"
                                               "raise ImportError('made up: the module removes itself')\n")
    commit(repo, "a module named after an optional dependency, whose import raises, committed")
    python = venv_for(repo, tmp_path / "venv")
    out = subprocess.run([str(python), str(repo / prereg.SCORER), ID, "--store", str(store.root)],
                         capture_output=True, text=True, env=scorer_env(), cwd=tmp_path)
    assert out.returncode == 0, out.stdout + out.stderr
    assert out.stderr.startswith("tools/numexpr.py ran\n") and "refused" not in out.stderr, out.stderr
    assert [line["event"] for line in prereg.read_lines(prereg.prereg_dir(repo) / prereg.SPENT)] == ["spent", "result"]
    assert all(os.path.lexists(p) for p in prereg.result_paths(ID, prereg.prereg_dir(repo)))


def test_score_scans_the_modules_of_tools_under_the_lock_just_before_the_spend(made_up, capsys):
    """Fix pass 6, item H1 (b): score() calls check_tools_modules while it holds the ledgers' lock, after every other
    check and before the first spent line; a module of tools/ outside the closure (made up here) is refused and the
    ledgers are as they were."""
    import types

    repo, store = made_up
    real, seen = score_prereg.check_tools_modules, []
    stray = types.ModuleType("numexpr")
    stray.__file__ = str(REPO / "tools" / "numexpr.py")

    def scan(root, modules=None):
        seen.append((Path(root), (prereg.common_dir(repo) / prereg.LOCK).exists()))
        real(root, {"prereg": sys.modules["prereg"], "numexpr": stray})

    spent = (prereg.prereg_dir(repo) / prereg.SPENT).read_bytes()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(score_prereg, "check_tools_modules", scan)
        with pytest.raises(PreregError, match="the module 'numexpr' is loaded from .*outside the scorer's closure"):
            score_prereg.score(ID, store, repo, days_for=lambda s, w: made_up_days(),
                               series_for=series_of(np.ones(300)), modules_root=REPO)
    assert seen == [(REPO, True)]                                               # once, under the lock
    assert (prereg.prereg_dir(repo) / prereg.SPENT).read_bytes() == spent
    assert not (repo / ".git" / prereg.SIDE_SPENT).exists() and not (repo / ".git" / prereg.LOCK).exists()


def test_a_module_loaded_from_tools_outside_the_closure_is_refused(tmp_path):
    """Fix pass 5, item G5: a module in sys.modules whose __file__, __spec__.origin or package folder lies in
    <root>/tools, and that is not one of the closure's tools files (tools/prereg.py, tools/score_prereg.py,
    tools/forecast_test.py), is refused: its code is not hashed. The closure's own modules pass, and so do modules
    loaded from elsewhere. (Fix pass 6: check_tools_modules, which check_process and score() call.)"""
    import types

    tools = REPO / "tools"
    closure = {name: sys.modules[name] for name in ("prereg", "score_prereg")}
    score_prereg.check_tools_modules(REPO, {**closure, "json": sys.modules["json"]})      # the premise: passes
    by_file = types.ModuleType("stray")
    by_file.__file__ = str(tools / "smoke_m4.py")
    by_origin = types.ModuleType("stray")
    by_origin.__spec__ = importlib.machinery.ModuleSpec("stray", None, origin=str(tools / "stray.py"))
    by_folder = types.ModuleType("stray")
    by_folder.__spec__ = importlib.machinery.ModuleSpec("stray", None, is_package=True)
    by_folder.__spec__.submodule_search_locations = [str(tools / "stray")]
    for fake in (by_file, by_origin, by_folder):
        with pytest.raises(PreregError, match="the module 'stray' is loaded from .*outside the scorer's closure"):
            score_prereg.check_tools_modules(REPO, {**closure, "stray": fake})


def test_main_takes_the_command_line_only(made_up):
    """Fix pass 6, item H2 (review G claim 2): main(..., repo=, modules_root=) from `python -c` scored another
    repository with an edited copy of the scorer, and series_for= (or store=, an object that passes the store check
    and serves other data) scored made-up data. main() takes argv and nothing else."""
    repo, store = made_up
    for name, value in (("repo", repo), ("modules_root", REPO), ("store", store), ("days_for", made_up_days),
                        ("series_for", series_of(np.ones(300)))):
        with pytest.raises(TypeError, match="unexpected keyword argument"):
            score_prereg.main([ID], **{name: value})


def test_a_module_root_that_is_not_the_repositorys_closure_byte_for_byte_is_refused(made_up, capsys):
    """Fix pass 6, item H2 (review G claim 2): score() keeps modules_root for the tests. Review G scored a repository
    whose committed closure the pre-registration names, with an edited copy as the module root: every check passed.
    Here the repository's committed forecast_test.py differs from the module root's (the project's) and the
    pre-registration names the repository's hash: refused before the spend."""
    repo, store = made_up
    path = repo / "tools" / "forecast_test.py"
    path.write_text(path.read_text() + "\n# edited, committed, and named by the pre-registration\n")
    for p in prereg.paths(ID, prereg.prereg_dir(repo)).values():
        p.unlink()
    prereg.write(spec_for(store, repo), "# made up\n", prereg.prereg_dir(repo))
    commit(repo, "an edited closure file, and a pre-registration that names it")
    assert prereg.load(ID, repo)["scorer_sha256"] == prereg.scorer_sha256(repo) != prereg.scorer_sha256(REPO)
    refused(repo, store, capsys, f"{REPO / 'tools/forecast_test.py'} is not {path} byte for byte")


def emptied_clone(repo: Path, store, tmp_path: Path) -> Path:
    """S/rev5/E/c5: scored and committed, then an ordinary commit empties spent.jsonl; a fresh clone has no side
    ledger, so only git's history holds the spent line."""
    scored_and_committed(repo, store)
    for path in prereg.result_paths(ID, prereg.prereg_dir(repo)):
        g(repo, "rm", "-q", str(path))
    (prereg.prereg_dir(repo) / prereg.SPENT).write_text("")
    commit(repo, "ledger emptied")
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", str(repo), str(clone)], check=True, env=GIT_ENV, capture_output=True)
    assert prereg.read_lines(prereg.prereg_dir(clone) / prereg.SPENT) == []
    assert not (prereg.common_dir(clone) / prereg.SIDE_SPENT).exists()
    return clone


def test_a_graft_does_not_hide_a_spent_line(made_up, tmp_path, capsys):
    """Item F7 (review E claim 5): .git/info/grafts makes HEAD parentless, so plain git reaches one commit of three;
    prereg.git reads no graft file (GIT_GRAFT_FILE is the null device), sees the spent line and the scorer refuses."""
    repo, store = made_up
    clone = emptied_clone(repo, store, tmp_path)
    head = g(clone, "rev-parse", "HEAD")
    (clone / ".git" / "info").mkdir(exist_ok=True)
    (clone / ".git" / "info" / "grafts").write_text(head + "\n")
    assert len(g(clone, "rev-list", "--all", "--reflog").split()) == 1            # the premise: plain git, 1 commit
    assert len(prereg.git(clone, "rev-list", "--all", "--reflog").stdout.split()) == 3
    assert [line["prereg_id"] for line in prereg.spent_lines(clone)] == [ID]
    refused(clone, store, capsys, "shares dates with one spent")


def test_a_replace_ref_of_the_spent_commit_does_not_hide_a_spent_line(made_up, tmp_path, capsys):
    """Item F7: `git replace` puts a parentless commit with HEAD's tree in place of HEAD; plain git then reaches no
    commit that holds the spent line. prereg.git runs with replace objects off and still sees it."""
    repo, store = made_up
    clone = emptied_clone(repo, store, tmp_path)
    fake = g(clone, "commit-tree", "HEAD^{tree}", "-m", "parentless")
    g(clone, "replace", g(clone, "rev-parse", "HEAD"), fake)
    plain = g(clone, "log", "--format=%H", "HEAD").split()
    assert len(plain) == 1                                                         # the premise: history hidden
    assert len(prereg.git(clone, "log", "--format=%H", "HEAD").stdout.split()) == 3
    assert [line["prereg_id"] for line in prereg.spent_lines(clone)] == [ID]
    refused(clone, store, capsys, "shares dates with one spent")


def test_a_forged_commit_graph_does_not_hide_a_spent_line(made_up, tmp_path, capsys):
    """Fix pass 5, item G6 (review F claim 6, S/rev6/F/c6/cgraph.py): with no reflog, only HEAD's parent reaches the
    commit that holds the spent line. A commit-graph file whose entry for HEAD names no parent hides it from plain git;
    prereg.git runs with core.commitGraph=false, reads the parents from the commit objects, sees the spent line, and
    the scorer refuses."""
    import struct

    repo, store = made_up
    clone = emptied_clone(repo, store, tmp_path)
    head = g(clone, "rev-parse", "HEAD")
    shutil.rmtree(clone / ".git" / "logs")
    g(clone, "commit-graph", "write", "--reachable")
    path = clone / ".git" / "objects" / "info" / "commit-graph"
    data = bytearray(path.read_bytes())
    chunks = dict(struct.unpack(">4sQ", data[8 + 12 * i:20 + 12 * i]) for i in range(data[6] + 1))
    count = (chunks[b"CDAT"] - chunks[b"OIDL"]) // 20
    oids = [bytes(data[chunks[b"OIDL"] + 20 * i:chunks[b"OIDL"] + 20 * i + 20]).hex() for i in range(count)]
    struct.pack_into(">I", data, chunks[b"CDAT"] + 36 * oids.index(head) + 20, 0x70000000)    # first parent: none
    path.chmod(0o644)
    path.write_bytes(bytes(data))
    assert len(g(clone, "rev-list", "--all", "--reflog").split()) == 1             # the premise: plain git, 1 commit
    assert len(prereg.git(clone, "rev-list", "--all", "--reflog").stdout.split()) == 3
    assert [line["prereg_id"] for line in prereg.spent_lines(clone)] == [ID]
    refused(clone, store, capsys, "shares dates with one spent")


def test_a_symlinked_ledger_has_the_folder_of_its_target_fsynced(tmp_path, monkeypatch):
    """Item F7 (review E's D7 case): the side ledger is a symlink to a file not yet created elsewhere; the append
    creates the file in the target's folder, so that folder is fsynced, not the link's."""
    import stat

    common, elsewhere = tmp_path / "common", tmp_path / "elsewhere"
    common.mkdir()
    elsewhere.mkdir()
    path = common / prereg.SIDE_SPENT
    path.symlink_to(elsewhere / "ledger.jsonl")
    synced, real = [], os.fsync

    def spy(fd):
        info = os.fstat(fd)
        synced.append("file" if stat.S_ISREG(info.st_mode)
                      else "target folder" if info.st_ino == elsewhere.stat().st_ino
                      else "link folder" if info.st_ino == common.stat().st_ino else "other")
        real(fd)

    monkeypatch.setattr(prereg.os, "fsync", spy)
    prereg.append_line(path, {"line": 1})
    assert synced == ["file", "target folder"]
    assert prereg.read_lines(elsewhere / "ledger.jsonl") == [{"line": 1}]


def test_the_result_carries_the_fragile_band_and_whether_p_lies_in_it(tmp_path, capsys):
    """Item F1: the result carries the spec's "fragile_band" and "fragile": true when lo <= p < hi. The made-up d
    (score()'s default) is scored once to learn its p; then bands are set around p, above it, and with p on either
    edge (lo = p is inside, hi = p is not)."""
    repo, store = throwaway(tmp_path / "first")
    assert score(repo, store) == 0
    result = json.loads(capsys.readouterr().out)
    p = result["p"]
    assert 0 < p < 1 and result["fragile_band"] == [0.02, 0.05] and result["fragile"] is (0.02 <= p < 0.05)
    for n, (band, inside) in enumerate((([p / 2, (p + 1) / 2], True), ([(p + 1) / 2, (p + 3) / 4], False),
                                        ([p, (p + 1) / 2], True), ([p / 2, p], False))):
        repo, store = throwaway(tmp_path / f"band{n}", fragile_band=band)
        assert score(repo, store) == 0
        result = json.loads(capsys.readouterr().out)
        assert (result["p"], result["fragile_band"], result["fragile"]) == (p, band, inside), (p, band)


@pytest.mark.parametrize("band", [None, [0.05, 0.02], [0, 0.05], [0.02, 1], [True, 0.05], [0.02]])
def test_a_spec_without_a_valid_fragile_band_is_refused_before_the_spend(tmp_path, band, capsys):
    """Item F1: the band is checked with the other refusals, before the spend, so a bad band never costs a window."""
    repo, store = throwaway(tmp_path, fragile_band=band)
    refused(repo, store, capsys, "the fragile band")


# --- fix pass 6 (sixth review): the health runs' pairs, the most runs of one configuration, development dates -------

PAIRS = (("optionsdx", "quote"), ("optionsdx", "surface"), ("dolthub", "quote"), ("dolthub", "surface"))


def test_the_gates_health_pairs_are_the_pairs_the_tools_run():
    """Fix pass 6, item H4 (review G claim 1): the gate's pairs are smoke_m4's, MODES for the smoke and BUDGET_MODE for
    the budget run. (tests/test_smoke_m4.py checks the configs the tools build carry these pairs and no other.)"""
    import smoke_m4

    assert prereg.HEALTH_PAIRS == {"smoke": smoke_m4.MODES, "budget": (smoke_m4.BUDGET_MODE,)}
    assert set(prereg.HEALTH_PAIRS) == set(prereg.HEALTH_KINDS)


@pytest.mark.parametrize("kind", ["smoke", "budget"])
def test_a_health_run_on_a_pair_no_tool_runs_is_refused(gated, kind):
    """Item H4: review G ran smoke and budget runs on (optionsdx, surface) and (dolthub, quote), and the gate counted
    each pair apart. Now a health run passes only on a pair of prereg.HEALTH_PAIRS; on any other pair it is refused
    before anything is recorded."""
    gate = prereg.make_run_gate(gated)
    passed = []
    for source, mode in PAIRS:
        cfg = diag(diagnostic_kind=kind, data_source=source, execution_mode=mode)
        if (source, mode) in prereg.HEALTH_PAIRS[kind]:
            run_through(gate, cfg, OTHER, run_id=f"{kind}-{source}-{mode}")
            passed.append((source, mode))
        else:
            with pytest.raises(PreregError, match=f"a {kind} run on {source} {mode} is refused: no tool runs one"):
                gate(cfg, OTHER, trial_hash(cfg, OTHER))
    assert passed == list(prereg.HEALTH_PAIRS[kind])
    assert [(r["data_source"], r["execution_mode"]) for r in records(gated)] == passed


def test_one_configuration_runs_at_most_15_times_on_validation_dates(tmp_path):
    """Item H4: the most runs the gate accepts of one trial_hash on validation dates, measured on a made-up repository
    (as review G's S/rev7/G/probe/gate_count.py, which counted 30 with health runs on all four pairs). The grid's
    "short_straddle/always/dte": each kind tried four times on each pair (the first plain, the rest with a reason),
    the health runs first (once listed, they are refused), then the configuration listed by a second pre-registration
    and run as a validation trial four times. Accepted: 3 trials + 3 runs S + 6 smoke (2 pairs) + 3 budget = 15. The
    volume cap is another configuration (cap_mode enters the trial_hash): 3 more, under its own trial_hash. RunConfig
    refuses runs M and M' (no masked pricing build); chain_mask enters the trial_hash, so once built each is 3 more
    under its own trial_hash. Fix pass 7, item I6 (review H claim 4, S/rev9/H/probe/h4_count.py: 16): the listing
    pre-registration also has a "holdout" window of validation dates, and a holdout trial on it, after the validation
    trials, is refused because its dates lie outside the holdout split; the count stays 15."""
    import smoke_m4
    from volbt.engine.run_config import TRIAL_PLACEMENT
    from volbt.strategies.grid import m4_grid

    window = {"name": "validation", "split": "validation", "start": "2020-01-02", "end": "2023-12-29"}
    holdout_on_validation = {**window, "name": "holdout on validation dates", "split": "holdout"}
    dates = dict(sample_start=date(2020, 1, 2), sample_end=date(2023, 12, 29), split="validation")
    repo, store = throwaway(tmp_path, windows=[window])
    entry = next(e for e in m4_grid("har") if e.label == "short_straddle/always/dte")
    th = trial_hash(RunConfig(**{**entry.engine, **dates, "prereg_id": "any"}), entry.strategy)   # prereg_id: left out
    plain, reasoned = prereg.make_run_gate(repo), prereg.make_run_gate(repo, rerun_reason="made up")
    accepted, refusals = {}, {}

    def attempt(label, cfg, strategy=entry.strategy):
        assert trial_hash(cfg, strategy) == th or label == "volume_cap"              # the premise
        for n in range(4):
            try:
                run_through(plain if n == 0 else reasoned, cfg, strategy, run_id=f"{label}-{n}")
                accepted[label] = accepted.get(label, 0) + 1
            except PreregError as error:
                refusals.setdefault(label, set()).add(str(error))

    for kind in prereg.HEALTH_KINDS:
        for source, mode in PAIRS:
            span = smoke_m4.BUDGET if kind == "budget" else smoke_m4.VALIDATION
            attempt(f"{kind} {source} {mode}", smoke_m4.smoke_config(source, mode, *span, kind=kind),
                    smoke_m4.smoke_strategy("short_straddle", source))
    diagnostic = {**entry.engine, **dates, "run_purpose": "diagnostic"}
    attempt("surface_s", RunConfig(**{**diagnostic, "execution_mode": "surface", "diagnostic_kind": "surface_s"}))
    cap = RunConfig(**{**diagnostic, "sample_start": date(2021, 1, 4), "cap_mode": "volume",
                       "diagnostic_kind": "volume_cap"})
    attempt("volume_cap", cap)
    for kind, mask in (("masked_m", "dolthub"), ("masked_m_prime", "dolthub_daily")):
        with pytest.raises(ValueError, match="chain_mask"):
            RunConfig(**{**diagnostic, "execution_mode": "surface", "chain_mask": mask, "diagnostic_kind": kind})
    assert not {"cap_mode", "chain_mask"} & set(TRIAL_PLACEMENT)          # both enter the trial_hash
    listing = "2026-11-10-made-up-listing"
    prereg.write(spec_for(store, repo, prereg_id=listing, windows=[window, holdout_on_validation],
                          candidates=[{"name": "x", "trial_hash": th}]), "# made up\n", prereg.prereg_dir(repo))
    commit(repo, "lists the configuration")
    attempt("smoke after listing", smoke_m4.smoke_config("dolthub", "surface", *smoke_m4.VALIDATION),
            smoke_m4.smoke_strategy("short_straddle", "dolthub"))
    attempt("trial", RunConfig(**{**entry.engine, **dates, "prereg_id": listing}))
    attempt("holdout trial on validation dates", RunConfig(**{**entry.engine, **dates, "split": "holdout",
                                                             "data_source": "dolthub", "execution_mode": "surface",
                                                             "prereg_id": listing}),
            smoke_m4.smoke_strategy("short_straddle", "dolthub"))
    assert refusals["holdout trial on validation dates"] == {
        "a holdout trial runs on holdout dates (2024-01-02 to 2026-10-26), not on 2020-01-02 to 2023-12-29"}
    assert accepted == {"smoke optionsdx quote": 3, "smoke dolthub surface": 3, "budget optionsdx quote": 3,
                        "surface_s": 3, "volume_cap": 3, "trial": 3}
    on_th = [r for r in records(repo) if r["trial_hash"] == th]
    assert len(on_th) == 15 and all(r["completed"] and r["start"] <= "2023-12-29" and r["end"] >= "2020-01-02"
                                    for r in on_th)
    cap_hash = trial_hash(cap, entry.strategy)
    assert cap_hash != th and sum(r["trial_hash"] == cap_hash for r in records(repo)) == 3
    assert len(records(repo)) == 18
    no_tool = {label for label, why in refusals.items() if any("no tool runs one" in w for w in why)}
    assert no_tool == {"smoke optionsdx surface", "smoke dolthub quote", "budget optionsdx surface",
                       "budget dolthub quote", "budget dolthub surface"}
    assert any("listed by a pre-registration" in w for w in refusals["smoke after listing"])


def test_a_trial_that_ends_after_its_split_is_refused_before_the_gate_writes_a_line(gated):
    """Fix pass 7, item I6, its end-date branch (the orchestrator's mutant Q7 survived the tests above, which only
    start a trial before its split). A validation trial that runs on into holdout dates is refused by the gate
    itself, before it reserves: view() would refuse the run later, but only after a "started" line, which counts
    toward the run of record and its two re-runs."""
    cfg = RunConfig(date(2020, 1, 2), date(2024, 1, 5), "validation", run_purpose="trial", prereg_id="any")
    with pytest.raises(PreregError) as refused:
        run_through(prereg.make_run_gate(gated), cfg)
    assert str(refused.value) == ("a validation trial runs on validation dates (2020-01-02 to 2023-12-29), not on "
                                  "2020-01-02 to 2024-01-05")
    assert records(gated) == []


def spend(repo: Path, start: str, end: str, prereg_id: str) -> None:
    prereg.append_line(prereg.prereg_dir(repo) / prereg.SPENT,
                       {"window": {"name": prereg_id, "split": "development", "start": start, "end": end},
                        "prereg_id": prereg_id, "date": "2026-11-11"})


def test_a_scored_forecast_window_leaves_the_budget_run_and_its_re_runs(gated):
    """Fix pass 6, item H5 (S/rev7/G/probe/budget_spent.py): the gate meets only a run's dates after 2019-12-31 with
    the spent windows; development dates are free (ADR-0010). With a window spent as the forecast test's would be
    (2010-01-04 to 2019-11-29), the budget run (2010-01-04 to 2023-12-29) and its two re-runs pass, and the third
    re-run is refused by the count, not by the spend."""
    import smoke_m4

    spend(gated, "2010-01-04", "2019-11-29", "forecast-like")
    cfg = smoke_m4.smoke_config(*smoke_m4.BUDGET_MODE, *smoke_m4.BUDGET, kind="budget")
    strategy = smoke_m4.smoke_strategy("short_strangle", "optionsdx")
    plain, reasoned = prereg.make_run_gate(gated), prereg.make_run_gate(gated, rerun_reason="made up")
    for n, gate in enumerate((plain, reasoned, reasoned)):
        run_through(gate, cfg, strategy, run_id=f"budget-{n}")
    with pytest.raises(PreregError, match="third re-run of the budget run"):
        reasoned(cfg, strategy, trial_hash(cfg, strategy))
    assert [(r["start"], r["end"], r["completed"]) for r in records(gated)] == [("2010-01-04", "2023-12-29", True)] * 3


def test_a_run_that_shares_a_date_after_2019_with_a_spent_window_is_still_refused(gated):
    """Item H5: a window spent across 2019-12-31, or after it, still refuses the budget run; one that ends on
    2019-12-31 does not."""
    import smoke_m4

    cfg = smoke_m4.smoke_config(*smoke_m4.BUDGET_MODE, *smoke_m4.BUDGET, kind="budget")
    path = prereg.prereg_dir(gated) / prereg.SPENT
    for n, (start, end, refused_) in enumerate((("2019-12-02", "2020-01-02", True), ("2021-06-01", "2021-06-30", True),
                                                ("2019-12-02", "2019-12-31", False))):
        path.write_text("")
        spend(gated, start, end, f"spent-{n}")
        strategy = smoke_m4.smoke_strategy(smoke_m4.STRUCTURES[n], "optionsdx")
        gate = prereg.make_run_gate(gated)
        if refused_:
            with pytest.raises(PreregError, match=f"shares dates after 2019-12-31 with one spent by spent-{n}"):
                gate(cfg, strategy, trial_hash(cfg, strategy))
        else:
            run_through(gate, cfg, strategy, run_id=f"budget-{n}")
    assert [r["run_id"] for r in records(gated)] == ["budget-2"]

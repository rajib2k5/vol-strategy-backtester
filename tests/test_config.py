"""Tests for volbt.config. HOME is redirected to tmp_path so results never depend on the real machine."""

from pathlib import Path

import pytest

from volbt import config


def test_default_is_data_vol_projects_under_home(monkeypatch, tmp_path):
    monkeypatch.delenv("VOL_DATA_DIR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    # "~/data/vol-projects" with ~ = tmp_path.
    assert config.data_dir() == tmp_path / "data" / "vol-projects"


def test_env_var_overrides_default(monkeypatch, tmp_path):
    custom = tmp_path / "custom-place"
    monkeypatch.setenv("VOL_DATA_DIR", str(custom))
    assert config.data_dir() == custom


def test_tilde_in_env_var_is_expanded(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("VOL_DATA_DIR", "~/elsewhere")
    # Without expanduser() this would be the relative path "~/elsewhere".
    assert config.data_dir() == tmp_path / "elsewhere"
    assert not str(config.data_dir()).startswith("~")


def test_empty_env_var_falls_back_to_default(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("VOL_DATA_DIR", "")
    # An empty string must not become Path("") (= the current directory).
    assert config.data_dir() == tmp_path / "data" / "vol-projects"


def test_paths_need_not_exist_and_are_not_created(monkeypatch, tmp_path):
    monkeypatch.setenv("VOL_DATA_DIR", str(tmp_path / "missing"))
    config.data_dir()
    config.kaggle_dir()
    config.dolthub_options_dir()
    assert not (tmp_path / "missing").exists()


def test_subdirectories_hang_off_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("VOL_DATA_DIR", str(tmp_path / "root"))
    assert config.kaggle_dir() == tmp_path / "root" / "kaggle"
    assert config.dolthub_options_dir() == tmp_path / "root" / "dolthub" / "options"
    assert isinstance(config.kaggle_dir(), Path)


def test_the_dolt_mirror_is_this_project_s_private_copy_outside_the_shared_clone(monkeypatch, tmp_path):
    # The project-wide rule of 2026-10-29: query a private `cp -a` copy, never the shared clone.
    monkeypatch.setenv("VOL_DATA_DIR", str(tmp_path / "root"))
    assert config.dolthub_mirror_dir() == tmp_path / "root" / "vol-strategy-backtester" / "cache" / "dolt_mirror" / "options"
    assert not config.inside_shared_clone(config.dolthub_mirror_dir())
    assert config.inside_shared_clone(tmp_path / "root" / "dolthub" / "options" / ".dolt")
    assert not (tmp_path / "root").exists()


# --- work_dir: where this project writes (default taken 2026-10-29) ---------------------------

REPO = Path(__file__).resolve().parent.parent


def test_work_dir_defaults_to_the_repo_data_folder(monkeypatch):
    monkeypatch.delenv("VOLBT_WORK_DIR", raising=False)
    assert config.work_dir() == REPO / "data"


def test_work_dir_env_var_overrides_the_default(monkeypatch, tmp_path):
    monkeypatch.setenv("VOLBT_WORK_DIR", str(tmp_path / "elsewhere"))
    assert config.work_dir() == tmp_path / "elsewhere"


def test_empty_work_dir_falls_back_and_tilde_is_expanded(monkeypatch, tmp_path):
    monkeypatch.setenv("VOLBT_WORK_DIR", "")
    assert config.work_dir() == REPO / "data"
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("VOLBT_WORK_DIR", "~/w")
    assert config.work_dir() == tmp_path / "w"


def test_raw_and_store_hang_off_work_dir_and_are_not_created(monkeypatch, tmp_path):
    monkeypatch.setenv("VOLBT_WORK_DIR", str(tmp_path / "w"))
    assert config.raw_dir() == tmp_path / "w" / "raw"
    assert config.store_dir() == tmp_path / "w" / "store"
    assert not (tmp_path / "w").exists()


@pytest.mark.parametrize("inside", ["", "store", "../options/.dolt"])
def test_a_work_dir_inside_the_shared_dolt_clone_is_refused(monkeypatch, tmp_path, inside):
    # Everything below work_dir() is written to; the shared clone must never be.
    monkeypatch.setenv("VOL_DATA_DIR", str(tmp_path / "root"))
    monkeypatch.setenv("VOLBT_WORK_DIR", str(tmp_path / "root" / "dolthub" / "options" / inside))
    with pytest.raises(config.SharedCloneError):
        config.work_dir()
    with pytest.raises(config.SharedCloneError):
        config.store_dir()


def test_a_symlinked_work_dir_that_resolves_into_the_clone_is_refused(monkeypatch, tmp_path):
    clone = tmp_path / "root" / "dolthub" / "options"
    clone.mkdir(parents=True)
    (tmp_path / "innocent").symlink_to(clone)
    monkeypatch.setenv("VOL_DATA_DIR", str(tmp_path / "root"))
    monkeypatch.setenv("VOLBT_WORK_DIR", str(tmp_path / "innocent" / "w"))
    with pytest.raises(config.SharedCloneError):
        config.work_dir()


def test_a_work_dir_next_to_the_clone_is_fine(monkeypatch, tmp_path):
    monkeypatch.setenv("VOL_DATA_DIR", str(tmp_path / "root"))
    monkeypatch.setenv("VOLBT_WORK_DIR", str(tmp_path / "root" / "dolthub" / "options-work"))
    assert config.work_dir() == tmp_path / "root" / "dolthub" / "options-work"


def test_work_dir_is_independent_of_the_vendor_data_dir(monkeypatch, tmp_path):
    # Reading vendor data from one place must never move where we write.
    monkeypatch.delenv("VOLBT_WORK_DIR", raising=False)
    monkeypatch.setenv("VOL_DATA_DIR", str(tmp_path / "vendors"))
    assert config.work_dir() == REPO / "data"


def test_git_ignores_everything_under_the_default_work_dir():
    import shutil
    import subprocess

    import pytest

    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    paths = ["data/raw/yfinance/SPY_daily.csv", "data/store/option_quotes/source=optionsdx/year=2010/part-0.parquet",
             "data/dolt_root/.dolt/config_global.json", "data/cache/yfinance/cookies.db"]
    result = subprocess.run(["git", "check-ignore", "--no-index", *paths], cwd=REPO, capture_output=True, text=True)
    assert result.stdout.split() == paths

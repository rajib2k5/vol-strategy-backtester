"""Tests for volbt.config. HOME is redirected to tmp_path so results never depend on the real machine."""

from pathlib import Path

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

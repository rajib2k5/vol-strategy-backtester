"""Tests for tools/export_app_data.py: the JSON contract the React app reads."""

import json
import math
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import export_app_data  # noqa: E402

SHA = "0123456789abcdef0123456789abcdef01234567"
FIXED_NOW = datetime(2026, 10, 27, 12, 0, 0, tzinfo=timezone.utc)
ENVELOPE = {"schema_version": "0.1.0", "generated_at": "2026-10-27T12:00:00Z", "source_commit": SHA}


def reject_non_finite(token):
    # json.load calls this for the bare tokens NaN, Infinity, -Infinity. Browsers' JSON.parse
    # rejects them, so a valid file must never contain them.
    raise ValueError(f"non-standard JSON constant {token}")


def parse_finite_float(text):
    # json.load does NOT call parse_constant for "1e999": that is a legal JSON number, and
    # Python's float() turns it into inf (JavaScript's JSON.parse does the same). Catch it here.
    value = float(text)
    if not math.isfinite(value):
        raise ValueError(f"number {text} is not finite")
    return value


def read_json(path):
    return json.loads(
        path.read_text(encoding="utf-8"),
        parse_constant=reject_non_finite,
        parse_float=parse_finite_float,
    )


@pytest.fixture
def exported(tmp_path):
    export_app_data.build_payloads(tmp_path, lambda: (SHA, False), FIXED_NOW)
    return tmp_path


def test_writes_exactly_the_two_files(exported):
    assert sorted(p.name for p in exported.iterdir()) == ["illustrative_surface.json", "manifest.json"]


def test_manifest_content(exported):
    assert read_json(exported / "manifest.json") == {
        **ENVELOPE,
        "datasets": [{
            "name": "illustrative_surface",
            "path": "illustrative_surface.json",
            "schema_version": "0.1.0",
            "description": (
                "Illustrative SSVI implied-vol surface for the milestone-0 3D hero. "
                "Not market data."
            ),
        }],
    }


def test_every_manifest_path_exists_next_to_the_manifest(exported):
    for dataset in read_json(exported / "manifest.json")["datasets"]:
        assert (exported / dataset["path"]).is_file()


def test_surface_keys_and_envelope(exported):
    surface = read_json(exported / "illustrative_surface.json")
    assert set(surface) == {
        "schema_version", "generated_at", "source_commit",
        "illustrative", "label", "moneyness", "dte", "iv", "params",
    }
    assert {key: surface[key] for key in ENVELOPE} == ENVELOPE


def test_surface_is_labelled_illustrative(exported):
    surface = read_json(exported / "illustrative_surface.json")
    assert surface["illustrative"] is True
    assert surface["label"] == "Illustrative SSVI surface — not market data"


def test_surface_grid_shapes(exported):
    surface = read_json(exported / "illustrative_surface.json")
    assert len(surface["moneyness"]) == 26
    assert len(surface["dte"]) == 20
    # iv[i_dte][j_k]: 20 rows (expiries) of 26 columns (strikes).
    assert len(surface["iv"]) == 20
    assert all(len(row) == 26 for row in surface["iv"])
    assert surface["moneyness"][0] == -0.3 and surface["moneyness"][-1] == 0.2
    assert surface["dte"][0] == 7 and surface["dte"][-1] == 365
    # Whole days, written as 7 not 7.0 (json.loads gives float for "7.0").
    assert all(isinstance(d, int) for d in surface["dte"])


def test_surface_iv_is_finite_positive_and_rounded_to_6_dp(exported):
    surface = read_json(exported / "illustrative_surface.json")
    values = [v for row in surface["iv"] for v in row]
    assert all(math.isfinite(v) and v > 0 for v in values)
    assert all(v == round(v, 6) for v in values)


def test_surface_iv_hand_value_pins_orientation_and_rounding(exported):
    surface = read_json(exported / "illustrative_surface.json")
    # Last row is dte = 365 (T = 1), column 10 is k = -0.10. Worked by hand in
    # tests/test_illustrative.py: iv = 0.23436825742309448 -> 0.234368 at 6 dp.
    assert surface["dte"][-1] == 365 and surface["moneyness"][10] == -0.1
    assert surface["iv"][-1][10] == 0.234368


def test_surface_params_record_what_was_used(exported):
    assert read_json(exported / "illustrative_surface.json")["params"] == {
        "model": "SSVI", "rho": -0.7, "eta": 1.0,
        "sigma_atm_short": 0.16, "sigma_atm_long": 0.2,
    }


def test_refuses_to_export_a_surface_that_fails_no_arbitrage():
    # eta = 2.0 breaks butterfly_2 (2^2 * 1.7 = 6.8 > 4).
    with pytest.raises(ValueError, match="no-arbitrage"):
        export_app_data.surface_payload(ENVELOPE, eta=2.0)


def test_writer_refuses_nan(tmp_path):
    # NaN is not valid JSON; the app's JSON.parse would choke on it.
    with pytest.raises(ValueError):
        export_app_data.write_json(tmp_path / "bad.json", {"iv": [[float("nan")]]})


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity", "1e999", "-1e999", "[1e999]"])
def test_the_test_reader_rejects_non_finite_numbers(tmp_path, token):
    # Guards the guard: if read_json let one of these through, "every IV is finite" proves nothing.
    path = tmp_path / "x.json"
    path.write_text(f'{{"iv": {token if token.startswith("[") else "[" + token + "]"}}}', encoding="utf-8")
    with pytest.raises(ValueError):
        read_json(path)


def test_the_test_reader_accepts_ordinary_numbers(tmp_path):
    path = tmp_path / "x.json"
    path.write_text('{"a": [1, 2.5, -3e-2, 1e300]}', encoding="utf-8")
    assert read_json(path) == {"a": [1, 2.5, -0.03, 1e300]}


def test_refuses_to_export_an_inverted_term_structure():
    # 7-day vol 100% and one-year vol 5%: theta falls with expiry, a calendar arbitrage.
    # Before the check looked at the real term structure, the exporter could not see this.
    with pytest.raises(ValueError, match="calendar': False"):
        export_app_data.surface_payload(ENVELOPE, sigma_short=1.0, sigma_long=0.05)


def test_a_valid_custom_term_structure_is_exported_and_recorded():
    payload = export_app_data.surface_payload(ENVELOPE, sigma_short=0.30, sigma_long=0.25)
    assert payload["params"]["sigma_atm_short"] == 0.30
    assert payload["params"]["sigma_atm_long"] == 0.25
    # k = 0 is column 15; there iv = sigma_atm, so the grid really was built from these numbers.
    assert payload["iv"][0][15] == 0.30
    assert payload["iv"][-1][15] == 0.25


def test_every_file_ends_with_exactly_one_newline_and_has_no_carriage_returns(exported):
    for path in exported.iterdir():
        data = path.read_bytes()
        assert data.endswith(b"}\n") and not data.endswith(b"\n\n"), path.name
        assert b"\r" not in data, path.name


def test_files_are_written_with_lf_even_where_text_mode_would_write_crlf(tmp_path, windows_text_mode):
    # On Windows the default text mode would turn each "\n" into "\r\n": same export, different
    # bytes, a spurious git diff. The fixture applies that rule on any OS.
    export_app_data.build_payloads(tmp_path, lambda: (SHA, False), FIXED_NOW)
    for path in tmp_path.iterdir():
        assert b"\r" not in path.read_bytes(), path.name


def test_output_directory_is_created(tmp_path):
    target = tmp_path / "a" / "b"
    export_app_data.build_payloads(target, lambda: (SHA, False), FIXED_NOW)
    assert (target / "manifest.json").is_file()


def test_no_head_gives_uncommitted(tmp_path):
    export_app_data.build_payloads(tmp_path, lambda: (None, False), FIXED_NOW)
    assert read_json(tmp_path / "manifest.json")["source_commit"] == "uncommitted"


def test_volbt_is_importable_from_an_install_not_from_a_path_hack(tmp_path):
    # `-I` (isolated mode) ignores PYTHONPATH, the current directory and user site, so this
    # only works if volbt is really installed (uv sync does an editable install of src/volbt).
    result = subprocess.run(
        [sys.executable, "-I", "-c", "import volbt; print(volbt.__file__)"],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert Path(result.stdout.strip()) == REPO / "src" / "volbt" / "__init__.py"


def test_script_runs_as_a_plain_script_from_another_directory(tmp_path):
    out = tmp_path / "out"
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    script = REPO / "tools" / "export_app_data.py"
    result = subprocess.run(
        [sys.executable, str(script), "--out-dir", str(out)],
        cwd=elsewhere, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert (out / "manifest.json").is_file() and (out / "illustrative_surface.json").is_file()
    # --out-dir was absolute, so nothing may land next to the (different) working directory.
    assert list(elsewhere.iterdir()) == []


def test_default_out_dir_comes_from_the_script_location_not_the_working_directory(tmp_path):
    # Run from a foreign directory and ask the script where it would write by default. We do not
    # let it write: that folder holds the committed data.
    script = REPO / "tools" / "export_app_data.py"
    result = subprocess.run(
        [sys.executable, "-I", "-c",
         f"import runpy; print(runpy.run_path({str(script)!r}, run_name='probe')['DEFAULT_OUT_DIR'])"],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert Path(result.stdout.strip()) == REPO / "app" / "public" / "data"


def lookup_for(source_commit):
    """A git lookup that reproduces a given `source_commit` string (the inverse of source_commit())."""
    if source_commit == "uncommitted":
        return lambda: (None, False)
    if source_commit.endswith("-dirty"):
        return lambda: (source_commit.removesuffix("-dirty"), True)
    return lambda: (source_commit, False)


COMMITTED_DIR = REPO / "app" / "public" / "data"


def assert_matches_a_fresh_export(committed_dir, fresh_dir, name):
    """Export again into fresh_dir, stamped with the committed envelope, and compare BYTES.

    generated_at and source_commit change on every run, so the fresh export reuses the committed
    manifest's values; after that, any difference at all (a value, the key order, the
    indentation, a CRLF line ending) is drift.
    """
    stamp = read_json(committed_dir / "manifest.json")
    now = datetime.strptime(stamp["generated_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    export_app_data.build_payloads(fresh_dir, lookup_for(stamp["source_commit"]), now)
    assert (fresh_dir / name).read_bytes() == (committed_dir / name).read_bytes(), (
        f"app/public/data/{name} is stale; run: uv run python tools/export_app_data.py")


@pytest.mark.parametrize("name", ["manifest.json", "illustrative_surface.json"])
def test_committed_app_data_matches_a_fresh_export_byte_for_byte(tmp_path, name):
    # Catches "changed the model, forgot to re-run the exporter".
    if not (COMMITTED_DIR / name).exists():
        pytest.skip("run tools/export_app_data.py first")
    assert_matches_a_fresh_export(COMMITTED_DIR, tmp_path, name)


@pytest.fixture
def committed_copy(tmp_path):
    """A scratch copy of the committed data that a test may damage."""
    if not (COMMITTED_DIR / "manifest.json").exists():
        pytest.skip("run tools/export_app_data.py first")
    copy = tmp_path / "committed"
    copy.mkdir()
    for path in COMMITTED_DIR.glob("*.json"):
        (copy / path.name).write_bytes(path.read_bytes())
    return copy


def test_the_drift_check_passes_on_an_untouched_copy(committed_copy, tmp_path):
    assert_matches_a_fresh_export(committed_copy, tmp_path / "fresh", "illustrative_surface.json")


def test_the_drift_check_fails_on_a_one_digit_change(committed_copy, tmp_path):
    path = committed_copy / "illustrative_surface.json"
    data = path.read_bytes()
    path.write_bytes(data.replace(b"0.234368", b"0.234369", 1))
    assert path.read_bytes() != data
    with pytest.raises(AssertionError, match="is stale"):
        assert_matches_a_fresh_export(committed_copy, tmp_path / "fresh", "illustrative_surface.json")


def test_the_drift_check_fails_on_crlf_line_endings(committed_copy, tmp_path):
    # Parsed as JSON these two files are identical; only a byte comparison tells them apart.
    path = committed_copy / "illustrative_surface.json"
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    with pytest.raises(AssertionError, match="is stale"):
        assert_matches_a_fresh_export(committed_copy, tmp_path / "fresh", "illustrative_surface.json")

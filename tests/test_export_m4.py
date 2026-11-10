"""The milestone-4 exporter bodies (plan section 8, task 13): signals_timeline_body and strategy_positions_body.

Runs of VolStrategy on the made-up signal store (dated 2023, so its runs are 'validation': the positive path widens
the guard with splits/last_date, as engine_bodies' tests do). The bodies carry the run's own values; the HAR fits
reproduce the run's forecasts; the ex-post RV is the window's realised variance and null where the window ends after
the last date; the forecast-test block is checked; a non-development run and any date after 2019-12-31 are refused;
the layout is the app fixtures' (app/src/test/fixtures). Made-up values only.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

import engine_helpers as eh
import engine_store as es
import signal_store as ss
from volbt.data import store as store_module
from volbt.signals import har
from volbt.signals.base import RV_FALLBACK
from volbt.signals.realised import total_log_returns
from volbt.strategies.rules import EntryRule, ExitRules
from volbt.strategies.vol import VolStrategy

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
import export_app_data as ex  # noqa: E402

WIDE = dict(splits=("validation",), last_date=es.LAST_BAR)
FIXTURES = REPO / "app" / "src" / "test" / "fixtures"
RESULT = {"prereg_id": "2026-11-09-made-up", "prereg_sha256": "a" * 64, "window": "development", "n": 2495, "q": 8,
          "block": 42, "draws": 10000, "mean_d": 0.01, "ewc_t": 2.5, "se": 0.004, "p": 0.01, "p_holm": 0.01,
          "ci": (0.002, 0.018), "alpha": 0.025, "threshold": 0.025, "worst_simulated_size": 0.09,
          "effective_size": {"threshold": 0.025, "abc_size_battery_seed": 0.0507525, "abc_size_second_seed": 0.0501617,
                             "worst_matched_battery_seed": {"rate": 0.0815, "null_side": "S4 f=0.15 right +d"},
                             "worst_matched_second_seed": {"rate": 0.083, "null_side": "S4 f=0.1 left -d"},
                             "lowest_matched_battery_seed": {"rate": 0.011, "null_side": "orch long +d"},
                             "worst_battery": {"rate": 0.189, "null": "orch long", "side": "-d"}, "note": "made up"},
          "fragile_band": [0.02, 0.05], "fragile": False, "decision": "har", "label": "proxy: QLIKE on squared returns"}


def write_prereg(folder: Path, result: dict = RESULT, sha_bytes: bytes | None = None, **json_edits) -> dict:
    """Write a MADE-UP pre-registration for `result` into `folder` (<id>.json that agrees with the result, its test
    call included, and a <id>.sha256 holding `sha_bytes`, by default the `sha256sum` lines of the .json and of a
    made-up .md); `json_edits` replace top-level keys of the .json (a value of None removes one). Returns a copy of
    `result` whose prereg_sha256 is the SHA-256 of the .sha256 file's bytes."""
    prereg = {"id": result["prereg_id"], "threshold": result["threshold"], "fragile_band": list(result["fragile_band"]),
              "effective_size": result["effective_size"], "size": {"worst": {"high": {"rate": result["worst_simulated_size"]}}},
              "test": {"q": result["q"], "block": result["block"], "draws": result["draws"], "seed": 1}}
    prereg.update(json_edits)
    prereg = {k: v for k, v in prereg.items() if v is not None}
    folder.mkdir(parents=True, exist_ok=True)
    text = json.dumps(prereg).encode("utf-8")
    (folder / f"{result['prereg_id']}.json").write_bytes(text)
    if sha_bytes is None:
        sha_bytes = (f"{hashlib.sha256(text).hexdigest()}  {result['prereg_id']}.json\n"
                     f"{'0' * 64}  {result['prereg_id']}.md\n").encode("utf-8")
    (folder / f"{result['prereg_id']}.sha256").write_bytes(sha_bytes)
    return {**result, "prereg_sha256": hashlib.sha256(sha_bytes).hexdigest()}


def checked(tmp_path, **changes):
    """checked_forecast_test on RESULT with `changes`, against a made-up pre-registration written from the UNCHANGED
    RESULT (so a change that the pre-registration does not carry is a disagreement)."""
    result = write_prereg(tmp_path)
    return ex.checked_forecast_test({**result, **changes}, "har", tmp_path)


@pytest.fixture(scope="module")
def store(tmp_path_factory):
    return ss.signal_store(tmp_path_factory.mktemp("export_m4_store"))


@pytest.fixture(scope="module")
def runs(store, tmp_path_factory):
    out = {}
    for structure, side, entry, exits in (
            ("short_straddle", "short", EntryRule("above", 0.0), ExitRules(14, 1.0, 0.5, -0.4)),
            ("straddle_calendar", "short", EntryRule(), ExitRules(14))):
        out[structure] = eh.run(store, tmp_path_factory.mktemp(f"export_{structure}"),
                                VolStrategy(structure, side, entry, exits)).run_dir
    return out


def test_the_timeline_is_the_runs_signals_and_its_fits_give_the_runs_forecasts(store, runs):
    run_dir = runs["short_straddle"]
    body = ex.signals_timeline_body(run_dir, store, **WIDE)
    table = eh.table(run_dir, "signals").sort_values("session_date").reset_index(drop=True)
    assert body["dates"] == [d.isoformat() for d in table["session_date"]]
    assert body["signal"] == {"name": "vrp_har", "rv_model": "har", "window_days": 30, "horizon": 21, "min_pairs": 504}
    for key, column in (("iv30", "iv30"), ("rv_forecast", "rv_forecast"), ("log_var_ratio", "log_var_ratio")):
        assert [None if x is None else x for x in body[key]] == [
            None if v != v else round(float(v), 6) for v in table[column]], key
    assert body["n_window"] == table["n_window"].tolist() and body["flags"] == table["flags"].tolist()
    assert [f["fit_date"] for f in body["fits"]] == sorted({d.isoformat() for d in table["model_fit_date"].dropna()})
    assert len(body["fits"]) == 4 and all(f["n_pairs"] >= 504 for f in body["fits"])
    # Each fit, applied to the returns up to t, gives the run's own RV^ at t (where HAR did not fall back).
    view = store_module.view(es.LAST_BAR, "validation", store)
    days, r = total_log_returns(view.spy_bars(), view.dividends())
    coef = {f["fit_date"]: np.asarray(f["coef"]) for f in body["fits"]}
    checked = 0
    for _, row in table.iterrows():
        if row["model_fit_date"] is None or row["flags"] & RV_FALLBACK:
            continue
        upto = int(np.searchsorted(days, np.datetime64(row["session_date"], "D"), "right"))
        y_hat = float(har.regressors(r[:upto] ** 2)[-1] @ coef[row["model_fit_date"].isoformat()])
        assert math.sqrt(row["n_window"] * y_hat * 365 / 30) == pytest.approx(row["rv_forecast"], rel=1e-9)
        checked += 1
    assert checked >= 60


def test_the_ex_post_rv_is_the_windows_realised_variance_and_null_past_the_last_date(store, runs):
    last = date(2023, 5, 15)
    body = ex.signals_timeline_body(runs["short_straddle"], store, splits=("validation",), last_date=last)
    view = store_module.view(last, "validation", store)
    days, r = total_log_returns(view.spy_bars(), view.dividends())
    days = [d.astype(object) for d in days.astype("datetime64[D]")]
    for text, value in zip(body["dates"], body["rv_realised"]):
        t = date.fromisoformat(text)
        if t + timedelta(days=30) > last:
            assert value is None, text
            continue
        window = [x for d, x in zip(days, r) if t < d <= t + timedelta(days=30)]
        assert value == pytest.approx(math.sqrt(sum(x * x for x in window) * 365 / 30), abs=1e-6), text
    assert body["rv_realised"][0] is not None and body["rv_realised"][-1] is None


def test_a_run_off_the_development_split_or_past_2019_is_refused(store, runs):
    run_dir = runs["short_straddle"]
    with pytest.raises(ValueError, match="development-split"):
        ex.signals_timeline_body(run_dir, store, last_date=es.LAST_BAR)
    with pytest.raises(ValueError, match="after 2019-12-31"):
        ex.signals_timeline_body(run_dir, store, splits=("validation",))
    with pytest.raises(ValueError, match="development-split"):
        ex.strategy_positions_body([(run_dir, 36)], "36 development trials", last_date=es.LAST_BAR)
    with pytest.raises(ValueError, match="after 2019-12-31"):
        ex.strategy_positions_body([(run_dir, 36)], "36 development trials", splits=("validation",))
    with pytest.raises(ValueError, match="after 2023-03-01"):
        ex.check_dates([date(2023, 3, 1), date(2023, 3, 2)], date(2023, 3, 1), "made up")


def test_rows_dated_after_2019_are_refused_whatever_the_runs_row_says(store, runs, monkeypatch):
    """Fix pass 2, item 18 (review C claim 7): a runs row forged to say development, 2010-01-04 to 2019-12-31, over
    rows dated 2023: the row-level date checks refuse both bodies (the run-level check alone would pass them)."""
    real = ex.engine_report.run_block

    def forged(run_dir):
        block = real(run_dir)
        block.update(split="development", sample_start="2010-01-04", sample_end="2019-12-31")
        return block

    monkeypatch.setattr(ex.engine_report, "run_block", forged)
    run_dir = runs["short_straddle"]
    assert ex.m4_run(run_dir, ("development",), date(2019, 12, 31))["sample_end"] == "2019-12-31"   # the premise
    with pytest.raises(ValueError, match=r"signals: \d+ date\(s\) after 2019-12-31"):
        ex.signals_timeline_body(run_dir, store)
    with pytest.raises(ValueError, match=r"position \d+: \d+ date\(s\) after 2019-12-31"):
        ex.strategy_positions_body([(run_dir, 36)], "36 development trials")


def test_the_forecast_test_block_is_checked(store, runs, tmp_path):
    run_dir = runs["short_straddle"]
    result = write_prereg(tmp_path)
    assert ex.signals_timeline_body(run_dir, store, **WIDE)["forecast_test"] is None
    block = ex.signals_timeline_body(run_dir, store, forecast_test=result, prereg_dir=tmp_path, **WIDE)["forecast_test"]
    assert block["k"] == 1 and block["decision"] == "har" and block["ci"] == [0.002, 0.018]
    assert list(block) == list(json.loads((FIXTURES / "signals_timeline.json").read_text())["forecast_test"])
    for bad, match in (({"p": 0.06}, "p < threshold"), ({"p": 0.06, "decision": "naive"}, "chose 'naive'"),
                       ({"label": "QLIKE"}, "proxy")):
        with pytest.raises(ValueError, match=match):
            ex.signals_timeline_body(run_dir, store, forecast_test={**result, **bad}, prereg_dir=tmp_path, **WIDE)
    with pytest.raises(ValueError, match="lacks"):
        ex.checked_forecast_test({k: v for k, v in result.items() if k != "se"}, "har", tmp_path)


def test_signals_timeline_body_checks_the_result_against_the_preregistration_folder(store, runs, tmp_path):
    result = write_prereg(tmp_path / "made_up")
    with pytest.raises(ValueError, match="does not exist"):
        ex.signals_timeline_body(runs["short_straddle"], store, forecast_test=result, prereg_dir=tmp_path / "empty",
                                 **WIDE)
    assert ex.signals_timeline_body(runs["short_straddle"], store, forecast_test=result, prereg_dir=tmp_path / "made_up",
                                    **WIDE)["forecast_test"]["prereg_id"] == RESULT["prereg_id"]


def test_a_consistent_result_passes_and_carries_the_band_the_fragile_flag_and_the_effective_size_threshold(tmp_path):
    block = checked(tmp_path)
    assert block["fragile_band"] == [0.02, 0.05] and block["fragile"] is False
    assert block["effective_size"]["threshold"] == 0.025
    assert list(block["effective_size"])[0] == "threshold"
    fragile = write_prereg(tmp_path / "f", {**RESULT, "p": 0.03, "p_holm": 0.03, "fragile": True, "decision": "naive"})
    assert ex.checked_forecast_test(fragile, "naive", tmp_path / "f")["fragile"] is True


def test_the_forecast_test_block_carries_the_threshold_and_the_effective_size(tmp_path):
    block = checked(tmp_path)
    assert block["threshold"] == 0.025 and block["alpha"] == 0.025
    assert block["effective_size"] == {
        "threshold": 0.025, "abc_size_battery_seed": 0.0507525, "abc_size_second_seed": 0.0501617,
        "worst_matched_battery_seed": {"rate": 0.0815, "null_side": "S4 f=0.15 right +d"},
        "worst_matched_second_seed": {"rate": 0.083, "null_side": "S4 f=0.1 left -d"}}
    assert list(block["effective_size"]) == ["threshold", "abc_size_battery_seed", "abc_size_second_seed",
                                             "worst_matched_battery_seed", "worst_matched_second_seed"]


def test_a_threshold_that_differs_from_alpha_is_refused(tmp_path):
    result = write_prereg(tmp_path)
    with pytest.raises(ValueError, match="threshold 0.05 differs from its alpha 0.025"):
        ex.checked_forecast_test({**result, "threshold": 0.05}, "har", tmp_path)


def test_the_decision_follows_the_threshold(tmp_path):
    both = {"threshold": 0.005, "alpha": 0.005}
    result = write_prereg(tmp_path, RESULT, **{"threshold": 0.005, "effective_size": {**RESULT["effective_size"], "threshold": 0.005}})
    with pytest.raises(ValueError, match="p < threshold"):
        ex.checked_forecast_test({**result, **both}, "har", tmp_path)


def test_a_naive_decision_with_p_above_the_threshold_passes(tmp_path):
    made = {**RESULT, "p": 0.3, "p_holm": 0.3, "decision": "naive"}
    result = write_prereg(tmp_path, made)
    assert ex.checked_forecast_test(result, "naive", tmp_path)["decision"] == "naive"


def test_a_threshold_equal_to_alpha_but_not_to_the_registered_one_is_refused(tmp_path):
    """Review E: threshold = alpha = 0.05 (and effective_size.threshold = 0.05) agrees with itself, not with the .json."""
    changes = {"threshold": 0.05, "alpha": 0.05, "p": 0.04, "p_holm": 0.04, "fragile": True,
               "effective_size": {**RESULT["effective_size"], "threshold": 0.05}}
    with pytest.raises(ValueError, match=r"threshold 0\.05 differs from the pre-registration's 0\.025"):
        checked(tmp_path, **changes)


@pytest.mark.parametrize("bad", [True, 1.5, 0, "0.025", 1, -0.1])
def test_a_threshold_or_alpha_that_is_not_a_number_inside_0_1_is_refused(tmp_path, bad):
    for key in ("threshold", "alpha"):
        with pytest.raises(ValueError, match=rf"the forecast test's {key} is {bad!r}, not a number in \(0, 1\)"):
            checked(tmp_path, **{key: bad})


def test_an_effective_size_that_is_missing_a_key_or_outside_0_1_is_refused(tmp_path):
    es_ = RESULT["effective_size"]
    def check(effective_size):
        return ex.checked_forecast_test({**write_prereg(tmp_path), "effective_size": effective_size}, "har", tmp_path)
    for key in ("threshold", "abc_size_battery_seed", "abc_size_second_seed"):
        with pytest.raises(ValueError, match=f"effective_size lacks '{key}'"):
            check({k: v for k, v in es_.items() if k != key})
    for key in ("worst_matched_battery_seed", "worst_matched_second_seed"):
        with pytest.raises(ValueError, match=f"effective_size.{key} must hold"):
            check({k: v for k, v in es_.items() if k != key})
        with pytest.raises(ValueError, match="must hold"):
            check({**es_, key: {"rate": 0.1}})
        with pytest.raises(ValueError, match="null_side must be a non-empty string"):
            check({**es_, key: {"rate": 0.1, "null_side": ""}})
        with pytest.raises(ValueError, match=r"\.rate is 1\.5, not a number in \[0, 1\]"):
            check({**es_, key: {"rate": 1.5, "null_side": "x"}})
    with pytest.raises(ValueError, match=r"abc_size_battery_seed is -0.1, not a number in \[0, 1\]"):
        check({**es_, "abc_size_battery_seed": -0.1})
    with pytest.raises(ValueError, match="effective_size must be a dict"):
        check(0.05)
    with pytest.raises(ValueError, match="lacks"):
        ex.checked_forecast_test({k: v for k, v in write_prereg(tmp_path).items() if k != "effective_size"}, "har",
                                 tmp_path)


def test_an_effective_size_threshold_that_is_not_in_0_1_or_differs_from_the_threshold_is_refused(tmp_path):
    es_ = RESULT["effective_size"]
    for bad in (True, 0, 1, 1.5, "0.025"):
        with pytest.raises(ValueError, match=r"effective_size.threshold is .*, not a number in \(0, 1\)"):
            checked(tmp_path, effective_size={**es_, "threshold": bad})
    with pytest.raises(ValueError, match=r"effective_size.threshold 0.05 differs from its threshold 0.025"):
        checked(tmp_path, effective_size={**es_, "threshold": 0.05})


def test_an_abc_size_above_the_worst_matched_size_of_its_seed_is_refused(tmp_path):
    es_ = RESULT["effective_size"]
    with pytest.raises(ValueError, match="abc_size_battery_seed 0.0816 is above its worst_matched_battery_seed rate 0.0815"):
        checked(tmp_path, effective_size={**es_, "abc_size_battery_seed": 0.0816})
    with pytest.raises(ValueError, match="abc_size_second_seed 0.084 is above its worst_matched_second_seed rate 0.083"):
        checked(tmp_path, effective_size={**es_, "abc_size_second_seed": 0.084})
    # the battery seed's worst matched size does not excuse the second seed, nor the reverse
    with pytest.raises(ValueError, match="abc_size_second_seed 0.0816 is above its worst_matched_second_seed rate 0.0815"):
        checked(tmp_path, effective_size={**es_, "abc_size_second_seed": 0.0816,
                                          "worst_matched_second_seed": {"rate": 0.0815, "null_side": "x"}})
    equal = {**es_, "abc_size_battery_seed": 0.0815, "abc_size_second_seed": 0.083}
    assert ex.checked_forecast_test(write_prereg(tmp_path / "eq", {**RESULT, "effective_size": equal}), "har",
                                    tmp_path / "eq")["effective_size"]["abc_size_battery_seed"] == 0.0815


def test_p_holm_must_equal_p_for_k_1(tmp_path):
    with pytest.raises(ValueError, match="p_holm 0.02 differs from its p 0.01"):
        checked(tmp_path, p_holm=0.02)
    with pytest.raises(ValueError, match="p_holm 0.005 differs from its p 0.01"):
        checked(tmp_path, p_holm=0.005)


def test_the_worst_simulated_size_must_be_at_least_the_worst_matched_battery_seed_size(tmp_path):
    with pytest.raises(ValueError, match="worst_simulated_size 0.08 is below the worst matched battery-seed size 0.0815"):
        checked(tmp_path, worst_simulated_size=0.08)
    result = write_prereg(tmp_path / "eq", {**RESULT, "worst_simulated_size": 0.0815})
    assert ex.checked_forecast_test(result, "har", tmp_path / "eq")["worst_simulated_size"] == 0.0815


@pytest.mark.parametrize("band, message", [
    ([0.02], r"fragile_band is \[0.02\], not \[lo, hi\]"), ([0.02, 0.03, 0.05], "not .lo, hi."), (0.05, "not .lo, hi."),
    ([0.05, 0.02], "lo 0.05 is not below hi 0.02"), ([0.03, 0.03], "lo 0.03 is not below hi 0.03"),
    ([True, 0.05], r"fragile_band\[0\] is True, not a number in \(0, 1\)"),
    ([0.02, True], r"fragile_band\[1\] is True, not a number in \(0, 1\)"),
    ([0, 0.05], r"fragile_band\[0\] is 0, not a number in \(0, 1\)"),
    ([0.02, 1], r"fragile_band\[1\] is 1, not a number in \(0, 1\)"),
    ([-0.1, 0.05], r"fragile_band\[0\] is -0.1, not a number"), ([0.02, 1.5], r"fragile_band\[1\] is 1.5, not a number"),
    (["0.02", 0.05], r"fragile_band\[0\] is '0.02', not a number")])
def test_a_malformed_fragile_band_is_refused(tmp_path, band, message):
    with pytest.raises(ValueError, match=message):
        checked(tmp_path, fragile_band=band)


def test_a_boolean_size_is_refused(tmp_path):
    es_ = RESULT["effective_size"]
    for changes in ({"abc_size_battery_seed": True}, {"worst_matched_battery_seed": {"rate": True, "null_side": "x"}}):
        with pytest.raises(ValueError, match="is True, not a number in .0, 1."):
            checked(tmp_path, effective_size={**es_, **changes})
    with pytest.raises(ValueError, match="worst_simulated_size is True, not a number in .0, 1."):
        checked(tmp_path, worst_simulated_size=True)


def test_the_fragile_flag_must_be_a_bool_equal_to_the_band_test(tmp_path):
    with pytest.raises(ValueError, match="fragile is True but p 0.01 against the band .* makes it False"):
        checked(tmp_path, fragile=True)
    with pytest.raises(ValueError, match="fragile is 0, not a bool"):
        checked(tmp_path, fragile=0)
    inside = {**RESULT, "p": 0.022, "p_holm": 0.022, "fragile": False}
    with pytest.raises(ValueError, match="fragile is False but p 0.022 against the band .* makes it True"):
        ex.checked_forecast_test(write_prereg(tmp_path, inside), "har", tmp_path)
    one = {**inside, "fragile": 1}
    with pytest.raises(ValueError, match="fragile is 1, not a bool"):
        ex.checked_forecast_test(write_prereg(tmp_path, one), "har", tmp_path)
    for p, flag in ((0.02, True), (0.0199, False), (0.05, False), (0.0499, True)):
        edge = write_prereg(tmp_path / str(p), {**RESULT, "p": p, "p_holm": p, "fragile": flag,
                                                "decision": "har" if p < 0.025 else "naive"})
        assert ex.checked_forecast_test(edge, "har" if p < 0.025 else "naive", tmp_path / str(p))["fragile"] is flag


@pytest.mark.parametrize("bad", ["", "../x", "a/b", "..", ".hidden", "a b", "a\\b", None, 5])
def test_a_prereg_id_that_is_not_a_plain_file_name_is_refused(tmp_path, bad):
    result = write_prereg(tmp_path)
    with pytest.raises(ValueError, match="not a plain file name"):
        ex.checked_forecast_test({**result, "prereg_id": bad}, "har", tmp_path)


def test_a_prereg_id_with_a_file_in_the_parent_folder_is_not_followed(tmp_path):
    folder = tmp_path / "prereg"
    result = write_prereg(tmp_path / "elsewhere")          # the pre-registration exists, one folder up from `folder`
    folder.mkdir()
    with pytest.raises(ValueError, match="not a plain file name"):
        ex.checked_forecast_test({**result, "prereg_id": "../elsewhere/" + RESULT["prereg_id"]}, "har", folder)


def test_an_unknown_prereg_id_is_refused(tmp_path):
    result = write_prereg(tmp_path)
    with pytest.raises(ValueError, match="names the pre-registration 'no-such-id', but .* does not exist"):
        ex.checked_forecast_test({**result, "prereg_id": "no-such-id"}, "har", tmp_path)
    with pytest.raises(ValueError, match="does not exist"):
        ex.checked_forecast_test(result, "har", tmp_path / "no-such-folder")


def test_a_json_whose_id_differs_is_refused(tmp_path):
    result = write_prereg(tmp_path, id="some-other-id")
    with pytest.raises(ValueError, match="its id 'some-other-id' differs from the forecast test's prereg_id"):
        ex.checked_forecast_test(result, "har", tmp_path)


def test_a_missing_sha256_file_is_refused(tmp_path):
    result = write_prereg(tmp_path)
    (tmp_path / f"{RESULT['prereg_id']}.sha256").unlink()
    with pytest.raises(ValueError, match=r"has no 2026-11-09-made-up.sha256"):
        ex.checked_forecast_test(result, "har", tmp_path)


def test_a_prereg_sha256_that_is_not_the_hash_of_the_sha256_file_is_refused(tmp_path):
    result = write_prereg(tmp_path)
    with pytest.raises(ValueError, match="prereg_sha256 .* differs from the SHA-256 "):
        ex.checked_forecast_test({**result, "prereg_sha256": "a" * 64}, "har", tmp_path)
    (tmp_path / f"{RESULT['prereg_id']}.sha256").write_bytes(b"changed after scoring\n")
    with pytest.raises(ValueError, match="prereg_sha256 .* differs from the SHA-256 "):
        ex.checked_forecast_test(result, "har", tmp_path)


def test_a_json_that_does_not_match_its_sha256_line_is_refused_before_it_is_used(tmp_path):
    """Fix pass 5, item G6 (review F claim 6, S/rev6/F/c7/exporter.py): the working .json was edited (threshold 0.05)
    while its .sha256 was left as it was, and a result with threshold 0.05 agreed with it. The exporter checks the
    .json's bytes against its line in the .sha256 before it reads a value from it; a .sha256 with no line for the
    .json, or two, is refused too."""
    name = RESULT["prereg_id"]
    result = write_prereg(tmp_path)
    assert ex.checked_forecast_test(result, "har", tmp_path)["threshold"] == 0.025          # the premise: it passes
    frozen = json.loads((tmp_path / f"{name}.json").read_text())
    edited = {**frozen, "threshold": 0.05, "effective_size": {**frozen["effective_size"], "threshold": 0.05}}
    (tmp_path / f"{name}.json").write_text(json.dumps(edited))
    changed = {**result, "threshold": 0.05, "alpha": 0.05, "p": 0.04, "p_holm": 0.04, "fragile": True,
               "effective_size": {**result["effective_size"], "threshold": 0.05}}
    with pytest.raises(ValueError, match=f"{name}.json does not match its line in {name}.sha256"):
        ex.checked_forecast_test(changed, "har", tmp_path)
    line = f"{hashlib.sha256((tmp_path / f'{name}.json').read_bytes()).hexdigest()}  {name}.json\n"
    for sha_bytes in (f"{'0' * 64}  {name}.md\n".encode(), (line + line).encode()):
        folder = tmp_path / str(len(sha_bytes))
        result = write_prereg(folder, sha_bytes=sha_bytes)
        with pytest.raises(ValueError, match="does not match its line"):
            ex.checked_forecast_test(result, "har", folder)


def test_a_result_whose_q_block_or_draws_differ_from_the_registered_test_is_refused(tmp_path):
    """Fix pass 5, item G6 (review F claim 6): q 2 and draws 99 were accepted. The result's q, block and draws must
    be the .json's test call, as integers."""
    for key, value in (("q", 2), ("block", 21), ("draws", 99), ("q", 8.0), ("draws", True)):
        with pytest.raises(ValueError, match=f"the forecast test's {key} {value!r} differs from the "
                                             f"pre-registration's test {key} {RESULT[key]!r}"):
            checked(tmp_path, **{key: value})
    folder = tmp_path / "no-test"
    result = write_prereg(folder, test=None)
    with pytest.raises(ValueError, match="test q None"):
        ex.checked_forecast_test(result, "har", folder)


def test_a_result_that_differs_from_the_registered_values_is_refused(tmp_path):
    es_ = RESULT["effective_size"]
    with pytest.raises(ValueError, match=r"fragile_band \[0.03, 0.05\] differs from the pre-registration's \[0.02, 0.05\]"):
        checked(tmp_path, fragile_band=[0.03, 0.05])
    with pytest.raises(ValueError, match=r"worst_simulated_size 0.095 differs from the pre-registration's 0.09"):
        checked(tmp_path, worst_simulated_size=0.095)
    with pytest.raises(ValueError, match=r"threshold 0.03 differs from the pre-registration's 0.025"):
        checked(tmp_path, threshold=0.03, alpha=0.03, effective_size={**es_, "threshold": 0.03})
    for key, value in (("abc_size_battery_seed", 0.05), ("abc_size_second_seed", 0.0501),
                       ("worst_matched_battery_seed", {"rate": 0.0816, "null_side": "S4 f=0.15 right +d"}),
                       ("worst_matched_second_seed", {"rate": 0.083, "null_side": "another"}),
                       ("lowest_matched_battery_seed", {"rate": 0.012, "null_side": "orch long +d"}),
                       ("worst_battery", {"rate": 0.19, "null": "orch long", "side": "-d"}), ("note", "edited")):
        with pytest.raises(ValueError, match=rf"effective_size.{key} .* differs from the pre-registration's"):
            checked(tmp_path, effective_size={**es_, key: value})
    with pytest.raises(ValueError, match="effective_size.extra_key 1 differs from the pre-registration's None"):
        checked(tmp_path, effective_size={**es_, "extra_key": 1})


def test_a_json_without_the_registered_values_is_refused(tmp_path):
    for missing, match in (("threshold", "threshold 0.025 differs"), ("fragile_band", "fragile_band .* differs"),
                           ("size", "worst_simulated_size 0.09 differs"), ("effective_size", "has no effective_size")):
        folder = tmp_path / missing
        result = write_prereg(folder, **{missing: None})
        with pytest.raises(ValueError, match=match):
            ex.checked_forecast_test(result, "har", folder)


def test_the_positions_carry_their_legs_entry_signal_and_exit_reason(runs):
    body = ex.strategy_positions_body([(runs["short_straddle"], 36), (runs["straddle_calendar"], 36)],
                                      "36 development trials; no performance before M6", **WIDE)
    assert body["banner"] == "36 development trials; no performance before M6"
    for run, structure, n_legs in zip(body["runs"], ("short_straddle", "straddle_calendar"), (2, 4)):
        assert run["strategy"] == run["run"]["strategy"] == "VolStrategy" and run["params"]["structure"] == structure
        table = eh.table(runs[structure], "positions")
        opened = table[table["opened_date"].notna()]
        assert [p["position_id"] for p in run["positions"]] == opened["position_id"].tolist() and len(opened) >= 2
        for p, (_, row) in zip(run["positions"], opened.iterrows()):
            assert p["structure"] == structure and len(p["legs"]) == n_legs
            assert {abs(leg["ratio"]) for leg in p["legs"]} == {1}
            assert p["entry_signal"] == (None if row["entry_signal"] != row["entry_signal"]
                                         else round(row["entry_signal"], 6))
            assert p["exit_reason"] == row["exit_reason"] and (p["closed"] is None) == (p["exit_reason"] is None)
    with pytest.raises(ValueError, match="n_trials_group"):
        ex.strategy_positions_body([(runs["short_straddle"], 0)], "banner", **WIDE)


def test_the_layout_is_the_app_fixtures(store, runs, tmp_path):
    signals = ex.signals_timeline_body(runs["short_straddle"], store, **WIDE)
    positions = ex.strategy_positions_body([(runs["short_straddle"], 36)], "banner", **WIDE)
    app_signals = json.loads((FIXTURES / "signals_timeline.json").read_text())
    app_positions = json.loads((FIXTURES / "strategy_positions.json").read_text())
    envelope = ["schema_version", "generated_at", "source_commit"]
    assert envelope + list(signals) == list(app_signals)
    assert envelope + list(positions) == list(app_positions)
    for key in ("units", "thresholds", "flag_names"):
        assert signals[key] == app_signals[key], key
    assert list(signals["signal"]) == list(app_signals["signal"]) and list(signals["run"]) == list(app_signals["run"])
    assert positions["units"] == app_positions["units"]
    assert list(positions["runs"][0]) == list(app_positions["runs"][0])
    assert list(positions["runs"][0]["positions"][0]) == list(app_positions["runs"][0]["positions"][0])
    # Written by build_payloads, both are listed in the manifest at the current schema version.
    payloads = ex.build_payloads(tmp_path, lambda: ("0" * 40, False), quality_body={}, frames_body={},
                                 signals_body=signals, strategy_body=positions)
    listed = {d["name"]: d for d in payloads["manifest.json"]["datasets"]}
    assert listed["signals_timeline"]["path"] == "signals_timeline.json"
    assert listed["strategy_positions"]["schema_version"] == "0.5.0"
    assert json.loads((tmp_path / "signals_timeline.json").read_text())["dates"] == signals["dates"]
    plain = ex.build_payloads(tmp_path / "plain", lambda: ("0" * 40, False), quality_body={}, frames_body={})
    assert {d["name"] for d in plain["manifest.json"]["datasets"]}.isdisjoint({"signals_timeline", "strategy_positions"})

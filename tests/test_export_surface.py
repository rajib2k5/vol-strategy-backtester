"""surface_frames.json (ADR-0001 §5, milestone 2): what the exporter writes, from a made-up pricing store."""

import hashlib
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import export_app_data  # noqa: E402
import pricing_store  # noqa: E402
from volbt import build, contract  # noqa: E402
from volbt.pricing import smile  # noqa: E402
from volbt.data.store import Store  # noqa: E402

SHA = "0123456789abcdef0123456789abcdef01234567"
FIXED_NOW = datetime(2026, 10, 29, 12, 0, 0, tzinfo=timezone.utc)
FRAMES = ((date(2023, 6, 15), "made-up date"),)
COMMITTED = REPO / "app" / "public" / "data" / "surface_frames.json"


@pytest.fixture(scope="module")
def store(tmp_path_factory):
    built = pricing_store.make_store(tmp_path_factory.mktemp("frames"))
    build.build_pricing(built)
    return built


def test_the_results_blocks_come_first_after_the_envelope(store, tmp_path, quality_body_for_frames):
    body = export_app_data.surface_frames_body(store, FRAMES)
    export_app_data.build_payloads(tmp_path, lambda: (SHA, False), FIXED_NOW, quality_body=quality_body_for_frames,
                                   frames_body=body)
    written = json.loads((tmp_path / "surface_frames.json").read_text(encoding="utf-8"))
    assert list(written)[:6] == ["schema_version", "generated_at", "source_commit", "run", "units", "illustrative"]
    assert written["illustrative"] is False and written["schema_version"] == contract.SCHEMA_VERSION == "0.3.0"


def test_the_run_block_names_the_pricing_build(store):
    run = export_app_data.surface_frames_body(store, FRAMES)["run"]
    summary = json.loads((store.root / build.SUMMARY_FILE).read_text())
    assert run["config_hash"] == summary["code_fingerprint"] == build.code_fingerprint()
    assert run["run_id"] == "pricing-" + summary["code_fingerprint"][:12]
    assert len(run["data_fingerprint"]) == 64 and run["data_source"] == "optionsdx" and run["chain_mask"] == "none"
    # ADR-0001 §5's run block, every key, with the backtest-only ones null, and the data's last date.
    assert set(run) == {"run_id", "config_hash", "data_fingerprint", "data_source", "data_last_date", "execution_mode",
                        "fill_timing", "cap_mode", "chain_mask", "sample_start", "sample_end"}
    assert run["execution_mode"] is run["fill_timing"] is run["cap_mode"] is None
    assert run["sample_start"] == run["sample_end"] == "2023-06-15" and run["data_last_date"] == "2023-06-15"


def test_the_data_fingerprint_is_adr_0001_s_list_of_input_files(store):
    # ADR-0001 §7: SHA-256 over the sorted "path, size, SHA-256" lines of the input files, here the
    # frame year's option_quotes partition and the four tables beside it. Recomputed by hand.
    run = export_app_data.surface_frames_body(store, FRAMES)["run"]
    files = [store.root / "option_quotes" / "source=optionsdx" / "year=2023" / "part-0.parquet"] + [
        store.root / name / "part-0.parquet" for name in ("rates", "dividends", "spy_bars", "vix")]
    lines = sorted(f"{p.relative_to(store.root).as_posix()}\t{p.stat().st_size}\t{hashlib.sha256(p.read_bytes()).hexdigest()}"
                   for p in files)
    assert run["data_fingerprint"] == hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()
    # Separate from the code: config_hash does not move when only the data does.
    assert run["data_fingerprint"] != run["config_hash"]


def test_every_number_field_has_a_unit(store):
    body = export_app_data.surface_frames_body(store, FRAMES)
    frame_numbers = {k for k, v in body["frames"][0].items() if k not in ("date", "label")}
    assert frame_numbers | {"grid_moneyness", "grid_dte"} <= set(body["units"])


def test_a_changed_input_partition_changes_the_data_fingerprint(store, tmp_path):
    first = export_app_data.surface_frames_body(store, FRAMES)["run"]
    for year, changes in (("2022", False), ("2023", True)):
        other = pricing_store.make_store(tmp_path / f"other{year}")
        quotes = other.read_table("option_quotes", order_by="source, quote_date, osi_symbol")
        part = quotes[(quotes["year"] == year) & (quotes["source"] == "optionsdx")].drop(columns=["source", "year"]).copy()
        part.loc[part.index[0], "bid"] = 0.0
        other.write_partition("option_quotes", part, {"source": "optionsdx", "year": year}, ("quote_date", "osi_symbol"))
        build.build_pricing(other)
        run = export_app_data.surface_frames_body(other, FRAMES)["run"]
        # Only the frame's own year is an input of a 2023 frame; the code is the same either way.
        assert (run["data_fingerprint"] != first["data_fingerprint"]) is changes
        assert run["config_hash"] == first["config_hash"]


def test_total_variance_never_falls_with_tenor_in_a_frame(store):
    # D5: on every k column, w = iv^2 dte / 365 rises (or stays) from each grid tenor to the next.
    body = export_app_data.surface_frames_body(store, FRAMES)
    for frame in body["frames"]:
        iv = np.array(frame["iv"])
        w = iv * iv * np.array(body["grid_dte"], dtype=float)[:, None] / 365       # as the app computes it
        assert np.all(np.diff(w, axis=0) >= 0), np.min(np.diff(w, axis=0))
        assert frame["atm_iv_30d"] == frame["iv"][body["grid_dte"].index(30)][body["grid_moneyness"].index(0.0)]


def test_two_exports_of_one_store_give_identical_bytes(store, tmp_path, quality_body_for_frames):
    for name in ("a", "b"):
        export_app_data.build_payloads(tmp_path / name, lambda: (SHA, False), FIXED_NOW,
                                       quality_body=quality_body_for_frames,
                                       frames_body=export_app_data.surface_frames_body(store, FRAMES))
    assert (tmp_path / "a" / "surface_frames.json").read_bytes() == (tmp_path / "b" / "surface_frames.json").read_bytes()


def test_without_the_pricing_build_the_exporter_says_what_to_run(tmp_path):
    with pytest.raises(FileNotFoundError, match="tools/build_pricing.py"):
        export_app_data.surface_frames_body(Store(tmp_path), FRAMES)


def test_the_exporter_refuses_partitions_priced_by_older_code(tmp_path, monkeypatch):
    # M2 round 2, design claim 3 (decision E5): after a code change a filtered build re-priced one
    # year, and the export still named the new code as config_hash for every partition.
    built = pricing_store.make_store(tmp_path / "older")
    build.build_pricing(built)
    export_app_data.surface_frames_body(built, FRAMES)                       # current: it exports
    monkeypatch.setattr(build.FINGERPRINT_LIBRARIES["scipy"], "__version__", "99.0.0")
    with pytest.raises(build.PricingNotCurrent, match="partitions priced by older code: run a full build"):
        export_app_data.surface_frames_body(built, FRAMES)
    with pytest.raises(build.PricingNotCurrent):
        build.build_pricing(built, years=["2023"])                            # re-prices two of three
    with pytest.raises(build.PricingNotCurrent, match="source=optionsdx/year=2022"):
        export_app_data.surface_frames_body(built, FRAMES)


def test_the_exporter_refuses_a_summary_of_other_code(tmp_path):
    built = pricing_store.make_store(tmp_path / "summary")
    build.build_pricing(built)
    path = built.root / build.SUMMARY_FILE
    summary = json.loads(path.read_text())
    summary["code_fingerprint"] = "0" * 64
    path.write_text(json.dumps(summary))
    with pytest.raises(build.PricingNotCurrent, match="names code"):
        export_app_data.surface_frames_body(built, FRAMES)


def test_the_default_dates_are_one_calm_two_stressed_and_the_reference_date():
    days = [day for day, _ in export_app_data.SURFACE_FRAME_DATES]
    assert days == sorted(days) and date(2023, 6, 15) in days and len(days) == 4


@pytest.fixture(scope="module")
def quality_body_for_frames(tmp_path_factory):
    from data_quality_store import make_store

    return export_app_data.data_quality_body(make_store(tmp_path_factory.mktemp("dq")))


# --- the committed file ----------------------------------------------------------------------

def committed():
    if not COMMITTED.exists():
        pytest.skip("run tools/export_app_data.py first")
    return json.loads(COMMITTED.read_text(encoding="utf-8"))


def test_the_committed_file_holds_the_four_labelled_dates_on_the_fixed_grid():
    written = committed()
    assert [f["date"] for f in written["frames"]] == [d.isoformat() for d, _ in export_app_data.SURFACE_FRAME_DATES]
    assert written["grid_moneyness"] == list(build.GRID_MONEYNESS) and written["grid_dte"] == list(build.GRID_DTE)
    for frame in written["frames"]:
        assert len(frame["iv"]) == len(build.GRID_DTE) and {len(row) for row in frame["iv"]} == {len(build.GRID_MONEYNESS)}
        assert all(0 < v < 5 for row in frame["iv"] for v in row)


def test_the_committed_file_never_has_total_variance_falling_with_tenor():
    # The first export had 17, 18, 2 and 10 adjacent-tenor cells where w fell (M2 review, code
    # claim 7). With the calendar floor there are none, to the last bit of iv^2 dte / 365.
    written = committed()
    dte = np.array(written["grid_dte"], dtype=float)[:, None]
    for frame in written["frames"]:
        iv = np.array(frame["iv"])
        step = np.diff(iv * iv * dte / 365, axis=0)
        assert int((step < 0).sum()) == 0, (frame["date"], np.min(step))


def test_the_committed_file_is_small():
    committed()
    assert COMMITTED.stat().st_size < 200_000           # ADR-0001: under 10 MB; this one is far under


def test_the_committed_stress_frame_sits_above_the_calm_one_at_the_money():
    frames = {f["label"].split(":")[0]: f for f in committed()["frames"]}
    assert frames["stress"]["atm_iv_30d"] > 3 * frames["calm"]["atm_iv_30d"]
    assert frames["stress"]["vix_close"] > 80 > 10 > frames["calm"]["vix_close"]


# --- what the exporter refuses, and what it writes for the app (M2 round 3, F9) ----------------------------------

def _smile(days: int, k, iv) -> tuple:
    """(tau, k_nodes, w_nodes) of a crafted smile, as build.usable_smiles returns one."""
    tau = days / 365
    return (tau, *smile.smile_nodes(np.asarray(k, dtype=float), np.asarray(iv, dtype=float), tau))


WIDE = np.linspace(-0.5, 0.3, 9)
FAR_RIGHT = [0.3, 0.35, 0.4, 0.45, 0.5]

# (name, data source, what the case shows, smiles). Each is read by the real exporter code (build.surface_frame) into
# app/src/test/fixtures/surface_frames_exporter.json, where the app's tests read them (surfaceFrames.exporter.test.ts).
CASES = (
    ("t1_moved_past_the_back_above_5", "optionsdx",
     "T1: a 7-day expiry with its nodes right of the grid and a 10-day back expiry whose nodes hold x = k sqrt(10 / 14) "
     "but not k = -0.3: the calendar rule's running maximum carries the 7-day wing into the back's w at k, so the 14-day "
     "cell at k = -0.3 reads 6.58 with flags 12 (tenor and calendar, no strike bit)",
     [_smile(7, FAR_RIGHT, [4.9, 0.5, 0.4, 0.35, 0.3]), _smile(10, [-0.27, -0.2, -0.1, 0.0, 0.1], [0.3, 0.27, 0.24, 0.2, 0.19])]),
    ("x2_atm_cell_extrapolated_above_5", "optionsdx",
     "X2: the round-3 reviewer's smiles, a 40-day front with calls only at k in [0.02, 0.2] and a 90-day expiry: the "
     "30-day k = 0 cell is before the front and beyond its strikes (flags 5), 5.036, and atm_iv_30d with it",
     [_smile(40, [0.02, 0.06, 0.1, 0.15, 0.2], [5.0, 4.6, 4.0, 3.5, 3.0]),
      _smile(90, [0.02, 0.06, 0.1, 0.15, 0.2], [4.5, 4.14, 3.6, 3.15, 2.7])]),
    ("x1_wing_above_10", "optionsdx",
     "X1: the round-3 reviewer's 7-day put-only smile at k in [-1, -0.8] with a steep right edge: its wing reads above 10",
     [_smile(7, [-1.0, -0.95, -0.9, -0.85, -0.8], [1.2, 1.1, 1.05, 1.0, 2.5])]),
    ("rounding_raise_above_5", "optionsdx",
     "a 14-day expiry quoted flat at 4.9999998 and a 7-day one whose wing is held to it: rounding the 7-day IV up "
     "raises the 14-day quoted cells to 5.000001 (flags 0), above a solved IV",
     [_smile(7, FAR_RIGHT, [4.9, 1.0, 0.9, 0.8, 0.7]), _smile(14, WIDE, np.full(9, 4.9999998))]),
    ("p1_first_inside_row_on_a_later_expiry", "optionsdx",
     "P1: a 10-day front, a 14-day and a 60-day expiry, the front's at-the-money vol above the 14-day one's: the 7-day "
     "row is before the front and the 14-day row, on the second expiry, is raised to the front (bit 8, no strike bit)",
     [_smile(10, WIDE, 0.5 - 0.3 * WIDE), _smile(14, WIDE, 0.3 - 0.3 * WIDE), _smile(60, WIDE, 0.3 - 0.2 * WIDE)]),
    ("p1_front_row_proven", "optionsdx",
     "P1: expiries at 7, 14 and 30 days, each on a row: expiries_used is exactly what the rows need, so the 7-day row is "
     "the front, and it carries no bit 8; the 30-day row is the back",
     [_smile(7, WIDE, 0.5 - 0.3 * WIDE), _smile(14, WIDE, 0.3 - 0.3 * WIDE), _smile(30, WIDE, 0.3 - 0.2 * WIDE)]),
    ("p6_first_inside_row_on_a_later_expiry", "optionsdx",
     "P6: a wide 10-day front and a narrower 14-day expiry: the 14-day row is beyond its strikes at k = -0.3, the 7-day "
     "row before the front reads the front at x = -0.3 sqrt(10 / 7), inside",
     [_smile(10, WIDE, 0.25 - 0.3 * WIDE), _smile(14, np.linspace(-0.25, 0.15, 9), 0.24 - 0.3 * np.linspace(-0.25, 0.15, 9)),
      _smile(60, WIDE, 0.22 - 0.2 * WIDE)]),
    ("p6_front_row_right_run_below_0", "optionsdx",
     "P6: a 14-day front with nodes at k in [-0.6, -0.29] and a 30-day back, both proven: the front row is beyond its "
     "RIGHT strike from k = -0.28, while the 7-day row reads x = k sqrt(2), inside for k down to -0.22",
     [_smile(14, np.linspace(-0.6, -0.29, 6), 0.5 - 0.5 * np.linspace(-0.6, -0.29, 6)), _smile(30, WIDE, 0.3 - 0.2 * WIDE)]),
    ("p6_front_row_beyond_everywhere", "optionsdx",
     "P6: a 14-day front with nodes at k in [-0.6, -0.32], left of the whole grid, and a 30-day back: the front row is "
     "beyond its strikes on every cell, so which side each cell is on does not show, while the 7-day row reads x = "
     "k sqrt(2) and is inside for k up to -0.24",
     [_smile(14, np.linspace(-0.6, -0.32, 6), 0.5 - 0.5 * np.linspace(-0.6, -0.32, 6)), _smile(30, WIDE, 0.3 - 0.2 * WIDE)]),
    ("p6_front_row_left_run_above_0", "optionsdx",
     "P6: a 14-day front with calls only, nodes at k in [0.05, 0.4], and a 30-day back: the front row is beyond its "
     "LEFT strike at k = 0.04, while the 7-day row reads x = 0.04 sqrt(2) = 0.057, inside",
     [_smile(14, np.linspace(0.05, 0.4, 8), 0.25 + 0.2 * np.linspace(0.05, 0.4, 8)), _smile(30, WIDE, 0.3 - 0.2 * WIDE)]),
    ("p6_last_inside_row_on_an_earlier_expiry", "optionsdx",
     "P6: a wide 30-day expiry and a narrow 40-day back between the 30- and 45-day rows: the rows past the back read "
     "its narrow smile and are beyond it at k = -0.3, while the 30-day row, on the other expiry, is inside",
     [_smile(30, WIDE, 0.3 - 0.2 * WIDE), _smile(40, np.linspace(-0.2, 0.1, 7), 0.28 - 0.2 * np.linspace(-0.2, 0.1, 7))]),
    ("n4_dolthub", "dolthub",
     "N4: a DoltHub surface, labelled by the exporter's own surface_frames_label",
     [_smile(10, WIDE, 0.25 - 0.3 * WIDE), _smile(30, WIDE, 0.22 - 0.25 * WIDE), _smile(90, WIDE, 0.2 - 0.2 * WIDE)]),
)
EXPORTER_CASES = REPO / "app" / "src" / "test" / "fixtures" / "surface_frames_exporter.json"
CASE_DATE = "2020-03-16"


def case_frame(smiles: list) -> dict:
    """One frame as build.surface_frames_body writes it, from crafted smiles (the spot and VIX are made up)."""
    return {"date": CASE_DATE, "label": "crafted smiles", "spot": 240.0, "vix_close": 80.0,
            "expiries_used": len(smiles), **build.surface_frame(smiles)}


def exporter_cases() -> dict:
    """The crafted cases, each a whole surface_frames.json of one frame, and the exporter's own verdict on it."""
    config_hash = hashlib.sha256(b"crafted smiles").hexdigest()
    cases = []
    for name, source, why, smiles in CASES:
        frame = case_frame(smiles)
        try:
            export_app_data.check_frame_ivs(frame, list(build.GRID_MONEYNESS), list(build.GRID_DTE))
            verdict = "writes"
        except ValueError as error:
            verdict = f"refuses: {error}"
        run = {"run_id": f"pricing-{config_hash[:12]}", "config_hash": config_hash,
               "data_fingerprint": hashlib.sha256(name.encode()).hexdigest(), "data_source": source,
               "data_last_date": CASE_DATE, "execution_mode": None, "fill_timing": None, "cap_mode": None,
               "chain_mask": "none", "sample_start": CASE_DATE, "sample_end": CASE_DATE}
        file = {"schema_version": contract.SCHEMA_VERSION, "generated_at": "2026-10-29T12:00:00Z",
                "source_commit": SHA, "run": run, "units": export_app_data.SURFACE_UNITS, "illustrative": False,
                "label": export_app_data.surface_frames_label(source), "grid_moneyness": list(build.GRID_MONEYNESS),
                "grid_dte": list(build.GRID_DTE), "cell_flag_names": list(smile.SURFACE_FLAG_NAMES), "frames": [frame]}
        cases.append({"name": name, "why": why, "exporter": verdict, "file": file})
    return {"note": "Written by tests/test_export_surface.py from crafted smiles through build.surface_frame; "
                    "regenerate with: uv run python tests/test_export_surface.py --write-exporter-cases",
            "cases": cases}


def write_exporter_cases() -> None:
    payload = exporter_cases()
    lines = ",\n".join(json.dumps(case, allow_nan=False) for case in payload["cases"])
    EXPORTER_CASES.write_text(f'{{"note": {json.dumps(payload["note"])},\n"cases": [\n{lines}\n]}}\n', encoding="utf-8")


def case(name: str) -> dict:
    return next(c for c in exporter_cases()["cases"] if c["name"] == name)


def test_the_app_s_exporter_cases_are_what_the_exporter_writes_today():
    # The app's tests read these files as the exporter's output; a change to the exporter or to smile.py that moves
    # them fails here until the fixture is written again (and the app's tests then read the new files).
    assert json.loads(EXPORTER_CASES.read_text(encoding="utf-8")) == json.loads(json.dumps(exporter_cases()))


def test_a_wing_above_10_is_refused_with_its_cell():
    # X1: the method does not bound a wing, so the exporter refuses a frame the app's ceiling would refuse.
    frame = case("x1_wing_above_10")["file"]["frames"][0]
    assert max(map(max, frame["iv"])) > export_app_data.MAX_EXTRAPOLATED_IV
    with pytest.raises(ValueError, match=r"the 2020-03-16 frame reads IV 10\.\d+ at 7 days, k = -?0\.\d+ \(cell flags 1\), "
                                         r"outside \(0, 10\], the app's ceiling for that cell"):
        export_app_data.check_frame_ivs(frame, build.GRID_MONEYNESS, build.GRID_DTE)


def test_a_quoted_cell_raised_by_rounding_above_5_is_refused():
    frame = case("rounding_raise_above_5")["file"]["frames"][0]
    assert frame["iv"][1][0] == 5.000001 and frame["cell_flags"][1][0] == 0
    with pytest.raises(ValueError, match=r"IV 5\.000001 at 14 days, k = -0\.3 \(cell flags 0\), outside \(0, 5\]"):
        export_app_data.check_frame_ivs(frame, build.GRID_MONEYNESS, build.GRID_DTE)


def test_a_moved_cell_past_the_back_may_read_above_5_without_a_strike_bit():
    # T1: the exporter writes it, so the app's ceiling there is 10, not 5.
    c = case("t1_moved_past_the_back_above_5")
    frame = c["file"]["frames"][0]
    assert (frame["iv"][1][0], frame["cell_flags"][1][0]) == (6.579568, 12) and c["exporter"] == "writes"


def test_the_ceiling_of_each_cell_follows_its_flags_and_row():
    # Rows: 7 days on an expiry (inside), then two rows outside, past the back. 13 = 1 | 4 | 8, 12 = 4 | 8.
    flags = [[0, 8, 1], [4, 12, 13], [4, 12, 5]]
    assert export_app_data.iv_ceilings(flags).tolist() == [[5, 5, 10], [5, 10, 10], [5, 10, 10]]
    # The same outside rows before the front (the 30-day row inside): bit 8 there does not lift the ceiling.
    assert export_app_data.iv_ceilings([[4, 12, 13], [2, 10, 3]]).tolist() == [[5, 5, 10], [5, 5, 10]]
    # Every row outside: which ones are past the back is unknown, so bit 8 lifts it on each.
    assert export_app_data.iv_ceilings([[4, 12], [12, 4]]).tolist() == [[5, 10], [10, 5]]


def test_atm_iv_30d_reads_above_5_when_its_cell_is_extrapolated():
    # X2: atm_iv_30d is the 30-day k = 0 cell, so its ceiling is that cell's.
    c = case("x2_atm_cell_extrapolated_above_5")
    frame = c["file"]["frames"][0]
    assert frame["atm_iv_30d"] == frame["iv"][3][15] == 5.036368 and frame["cell_flags"][3][15] == 5
    assert c["exporter"] == "writes"


def test_an_iv_of_0_is_refused_too():
    frame = case("p1_front_row_proven")["file"]["frames"][0]
    frame["iv"][0][0] = 0.0
    with pytest.raises(ValueError, match=r"reads IV 0\.0 at 7 days, k = -0\.3 \(cell flags 0\), outside \(0, 5\]"):
        export_app_data.check_frame_ivs(frame, build.GRID_MONEYNESS, build.GRID_DTE)


def test_surface_frames_body_refuses_a_frame_the_app_would_refuse(store, monkeypatch):
    frame = case_frame(next(s for name, _, _, s in CASES if name == "x1_wing_above_10"))
    frame["date"] = "2023-06-15"
    body = {"grid_moneyness": list(build.GRID_MONEYNESS), "grid_dte": list(build.GRID_DTE),
            "cell_flag_names": list(smile.SURFACE_FLAG_NAMES), "frames": [frame]}
    monkeypatch.setattr(build, "surface_frames_body", lambda *args, **kwargs: body)
    with pytest.raises(ValueError, match="the app would refuse the file, so it is not written"):
        export_app_data.surface_frames_body(store, FRAMES)


def test_a_dolthub_export_names_dolthub_in_its_label(store):
    # N4: the label once said "(OptionsDX)" whatever the source, and the app refuses a label without the run's vendor.
    body = export_app_data.surface_frames_body(store, FRAMES, source="dolthub")
    assert body["run"]["data_source"] == "dolthub"
    assert "(DoltHub)" in body["label"] and "OptionsDX" not in body["label"]
    assert export_app_data.surface_frames_body(store, FRAMES)["label"] == export_app_data.surface_frames_label("optionsdx")
    assert "(OptionsDX)" in export_app_data.surface_frames_label("optionsdx")
    with pytest.raises(ValueError, match="'yahoo' is not a data source the app knows"):
        export_app_data.surface_frames_label("yahoo")


def test_the_committed_label_is_the_exporter_s_for_its_source():
    written = committed()
    assert written["label"] == export_app_data.surface_frames_label(written["run"]["data_source"])


def _main_frames(monkeypatch, tmp_path, *frame_args) -> tuple:
    """The frames main() hands surface_frames_body, with the store reads and the writes stubbed out."""
    seen = []
    monkeypatch.setattr(export_app_data, "data_quality_body", lambda store: {})
    monkeypatch.setattr(export_app_data, "surface_frames_body", lambda store, frames: seen.append(frames) or {})
    monkeypatch.setattr(export_app_data, "build_payloads", lambda *args, **kwargs: {})
    args = ["--store", str(tmp_path), "--out-dir", str(tmp_path / "out")]
    for text in frame_args:
        args += ["--frame", text]
    assert export_app_data.main(args) == 0
    return seen[0]


def test_main_writes_the_frame_dates_in_date_order(monkeypatch, tmp_path):
    # N1: the frames were written in the order given, and the app refuses frames out of date order.
    frames = _main_frames(monkeypatch, tmp_path, "2023-06-15=high rates", "2017-11-03=calm", "2020-03-16=stress")
    assert frames == ((date(2017, 11, 3), "calm"), (date(2020, 3, 16), "stress"), (date(2023, 6, 15), "high rates"))
    assert _main_frames(monkeypatch, tmp_path) == export_app_data.SURFACE_FRAME_DATES


@pytest.mark.parametrize("frame_args, message", [
    (("2020-03-16=stress", "2017-11-03=calm", "2020-03-16=crash"),
     "--frame 2020-03-16 is given twice ('stress' and 'crash'): give each date once"),
    (("2020-03-16=",), "expected YYYY-MM-DD=LABEL with a non-empty label"),
    (("2020-03-16",), "expected YYYY-MM-DD=LABEL with a non-empty label"),
    (("2020-02-30=x",), "'2020-02-30' is not a date YYYY-MM-DD"),
])
def test_main_refuses_a_date_given_twice_and_an_empty_label(monkeypatch, tmp_path, capsys, frame_args, message):
    with pytest.raises(SystemExit) as stop:
        _main_frames(monkeypatch, tmp_path, *frame_args)
    assert stop.value.code == 2 and message in capsys.readouterr().err


def test_surface_frames_body_refuses_frames_out_of_date_order(store):
    later_first = ((date(2023, 6, 15), "b"), (date(2023, 6, 14), "a"))
    with pytest.raises(ValueError, match="frames must be in strictly increasing date order"):
        export_app_data.surface_frames_body(store, later_first)
    with pytest.raises(ValueError, match="strictly increasing"):
        export_app_data.surface_frames_body(store, ((date(2023, 6, 15), "a"), (date(2023, 6, 15), "b")))


if __name__ == "__main__":
    if sys.argv[1:] != ["--write-exporter-cases"]:
        sys.exit("usage: uv run python tests/test_export_surface.py --write-exporter-cases")
    write_exporter_cases()
    print("wrote", EXPORTER_CASES)

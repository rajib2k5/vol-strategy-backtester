"""The forecast test's frozen files in docs/validation/prereg/ (milestone 4, plan section 6, task 8): a tripwire.

The pre-registration names the scorer's SHA-256 (tools/prereg.py scorer_closure: the repository files the scorer
imports, found from the source; fix pass 5, item G5) and the versions of the libraries those files import. An edit
to any of those files, or another library version, before scoring makes the scorer refuse, so this test fails at once, not at scoring time: the remedy is an
amendment, a new dated file that names the old hash. The size and matched sections must name the inference module and
the battery script as they are (tools/forecast_size.py ran them), the matched section the battery it read, and the
registered threshold must be the one the matched rule chose (fix pass 2). The .md is rationale_for(the .json) byte
for byte, and the variants and the conditional check name the code, battery and match they ran (fix pass 3). Fix pass
4: the fragile band is the full grid's range of picks, and the .md states it before scoring. Fix pass 5 (item G3,
review F claim 2): six simulations the .json carries ran the current tools/forecast_size.py, by its file SHA-256 (no
AST hash any more): the battery, the match, the variants, the combinations, the main conditional draw and the third
fix pass's draw; review D's draw was not run again (its figures are typed in tools/prereg.py; fix pass 6, item H3,
revised after the sixth review); the combinations are counted by combination and by distinct rule (item G2). Fix
pass 6 (item H1): the .md states when the scorer checks tools/ and what the checks do not stop. Fix pass 7 (items
I1, I2 and I4): it says the checks catch mistakes and the routes they name, not code written to defeat them, names
the refusal before `import prereg` and a module that removes itself, and says to commit tools/ in full. Fix pass 8
(items J1 and J2): it states which entries of tools/ the checks read, by module name, that an entry whose module name
holds a dot and tools/__pycache__ are left out, and that the name check runs before sysconfig imports its data module.
The real-data test
re-measures the 2002-2009 dependence summary and the scored window's dates, and checks they are the
ones the file names; it computes no loss on the scored window and nothing that shows the mean or sign of the
2002-2009 d-series.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))

import prereg  # noqa: E402
import score_prereg  # noqa: E402

ID = prereg.FORECAST_ID


def spec() -> dict:
    return prereg.load(ID, prereg.REPO, lambda path: True)      # hashes only: the files are not committed yet


def test_the_forecast_pre_registration_is_intact_and_names_the_current_scorer():
    frozen = spec()
    assert frozen["scorer_sha256"] == prereg.scorer_sha256(), \
        "a scorer file changed after the pre-registration: amend it in a new dated file"
    assert frozen["scorer_files"] == prereg.scorer_closure()
    assert frozen["libraries"] == prereg.library_versions()
    window = frozen["windows"][0]
    assert (window["n"], window["start"], window["last_target_end"]) == (2495, "2010-01-04", "2019-12-31")
    assert frozen["k"] == 1 and frozen["metric"]["proxy"] is True and "alpha" not in frozen
    test = frozen["test"]
    assert (test["function"], test["q"], test["block"], test["draws"]) == \
        ("volbt.analytics.inference.ewc_bootstrap", 4, 21, 9999)
    threshold, matched = frozen["threshold"], frozen["matched"]
    assert frozen["decision_rule"].startswith(f"use HAR if p < threshold ({threshold}); otherwise use naive")
    size = frozen["size"]
    assert size["runs"] >= 2000 and len(size["nulls"]) == 30 and size["met"] is False and size["threshold"] == threshold
    assert size["worst"]["high"]["rate"] == max(max(n["plus_d"], n["minus_d"]) for n in size["nulls"])
    assert size["worst_at_0.05"]["high"]["rate"] == max(max(n["plus_d_at_0.05"], n["minus_d_at_0.05"])
                                                       for n in size["nulls"])
    # the six simulations ran the inference module and the tools/forecast_size.py that are here, byte for byte (fix
    # pass 5, item G3: those earlier outputs were run again with the current script; no AST hash links them any more;
    # review D's draw was not run again: fix pass 6, item H3)
    script = prereg.file_sha256(REPO / "tools/forecast_size.py")
    runs = (size, matched, frozen["variants"], frozen["combinations"], frozen["conditional"],
            frozen["conditional"]["earlier"]["fix_pass_3"])
    for section in runs:
        assert section["inference_sha256"] == prereg.file_sha256(REPO / "src/volbt/analytics/inference.py")
        assert section["script_sha256"] == script
    scripts = frozen["size_scripts"]
    assert scripts["current"] == script and script not in scripts["earlier"].values()
    assert scripts["earlier"] == prereg.SIZE_SCRIPTS_EARLIER
    assert not hasattr(prereg, "size_code_sha256") and "battery_match_variants_code_sha256" not in scripts
    # the matched rule (fix pass 2, item 9): the largest threshold that passes is the registered one
    assert matched["battery_sha256"] == size["battery_sha256"] and matched["runs"] >= 2000
    assert matched["real"] == frozen["calibration"]["summaries"]
    passing = [row["threshold"] for row in matched["table"] if row["passes"]]
    assert passing and threshold == max(passing) == matched["threshold"] == 0.025
    for row in matched["table"]:
        assert row["passes"] == (max(row["abc_size_battery_seed"], row["abc_size_second_seed"]) <= matched["size_cap"]
                                 and row["abc_power"] >= matched["power_floor"])
    assert abs(sum(side["weight"] for side in matched["matched"]) - 1) < 1e-9
    assert frozen["effective_size"]["abc_size_battery_seed"] == next(
        row["abc_size_battery_seed"] for row in matched["table"] if row["threshold"] == threshold)
    assert frozen["calibration"]["window"]["label"] == "pre-development (2002-2009)"
    for name in (prereg.SPENT, prereg.RECORDS):
        for entry in prereg.read_lines(prereg.PREREG_DIR / name):
            if name == prereg.RECORDS and entry["prereg_id"] is None:
                # make_run_gate records a diagnostic run past 2019 without a pre-registration (the M4 smoke and
                # budget runs); a trial past 2019 always names one (default taken 2026-11-09, owner can override),
                # and no diagnostic runs on the holdout (ADR-0010 §1; fix pass 2, item 20)
                assert entry["run_purpose"] == "diagnostic" and entry["split"] != "holdout", entry
                continue
            assert prereg.paths(entry["prereg_id"])["json"].is_file()


def test_the_md_is_rationale_for_the_json_byte_for_byte():
    """Fix pass 3, item D3a (review D claim 3): every figure of the .md is a value of the .json, so the .md is
    rebuilt from the .json alone, in a fixed order."""
    frozen = spec()
    md = prereg.paths(ID)["md"].read_text(encoding="utf-8")
    assert prereg.rationale_for(frozen) == md


def test_the_variants_and_the_conditional_check_are_saved_runs_of_this_code():
    """Fix pass 3, items D1 and D2 (review D claims 1 and 2): the .json carries tools/forecast_size.py variants' and
    conditional's output, run on the battery and the match it names; the registered variant is the matched rule;
    each variant's pick follows from its own sizes and power. Fix pass 4: the variants and the earlier conditional
    draw ran the fix-pass-3 script, the main conditional draw (10,000 paths, declared before it ran) the current one;
    the .md states the fragile band before scoring (items F1, F3)."""
    frozen = spec()
    size, matched, variants, conditional = (frozen[k] for k in ("size", "matched", "variants", "conditional"))
    earlier = conditional["earlier"]["fix_pass_3"]
    for section in (variants, earlier, conditional):
        assert section["inference_sha256"] == prereg.file_sha256(REPO / "src/volbt/analytics/inference.py")
        assert section["script_sha256"] == prereg.file_sha256(REPO / "tools/forecast_size.py")
        assert section["real"] == frozen["calibration"]["summaries"]
    assert (variants["battery_sha256"], variants["match_sha256"]) == (size["battery_sha256"], matched["sha256"])
    assert all(variants["reproduction"][k] == 0 for k in ("weights", "second_seed_size", "power"))
    threshold = frozen["threshold"]
    t = prereg.key(threshold)
    row = next(r for r in matched["table"] if r["threshold"] == threshold)
    registered = next(v for v in variants["variants"] if v["name"] == "registered")
    assert registered["threshold"] == threshold and registered["sides"] == len(matched["matched"])
    assert abs(registered["size"]["battery"][t] - row["abc_size_battery_seed"]) < 1e-12
    assert abs(registered["size"]["second"][t] - row["abc_size_second_seed"]) < 1e-12
    order = [r["threshold"] for r in matched["table"]]
    for v in variants["variants"]:
        passing = [a for a in order if max(tab[prereg.key(a)] for tab in v["size"].values()) <= v["cap"]
                   and v["power"][prereg.key(a)] >= matched["power_floor"]]
        assert v["threshold"] == (max(passing) if passing else None), v["name"]
    picks = [v["threshold"] for v in variants["variants"]] + [r["threshold"] for r in variants["summary_seeds"]["rows"]]
    assert picks == prereg.picks(frozen)
    lo, hi = min(p for p in picks if p is not None), max(p for p in picks if p is not None)
    assert lo < threshold < hi
    band = frozen["fragile_band"]
    assert band == frozen["combinations"]["band"] and band[0] <= lo and hi <= band[1]
    md = " ".join(prereg.paths(ID)["md"].read_text(encoding="utf-8").split())
    assert f"A p in [{band[0]:g}, {band[1]:g}) is decided by these modelling choices, not by the data." in md
    assert f'"fragile": true when {band[0]:g} <= p < {band[1]:g}' in md
    assert "No null reproduces" not in md and "resembl" not in md
    assert "Chosen: p <" not in md and "How the threshold was chosen" not in md
    assert "The threshold was set from them through the matched nulls" not in md
    assert "never read as 5% evidence" not in md
    assert (conditional["n_calibration"], conditional["T"]) == (frozen["calibration"]["window"]["n"], size["T"])
    assert conditional["paths_per_null"] >= 10000 and conditional["by_accept"]
    assert conditional["seed_value"] == 20261115 and earlier["paths_per_null"] == 3000
    assert earlier["seed_value"] == 20261114
    assert conditional["earlier"]["review_d"] == prereg.CONDITIONAL_THIRD_REVIEW
    lowest = min(side["size_battery_seed"][t] for side in matched["matched"])
    assert frozen["effective_size"]["lowest_matched_battery_seed"]["rate"] == lowest
    screen = frozen["screen"]
    assert sorted(screen["order"]) == sorted(screen["candidates"])
    assert screen["first_revision_rule"]["power_floor"] == 0.9 and frozen["threshold_history"]["threshold"] == 0.025


def test_every_combination_of_the_choices_gives_the_fragile_band_and_the_power_rows_pick_none():
    """Fix pass 4, item F1 (review E claim 1): tools/forecast_size.py combinations ran on the saved battery, match and
    variants; its one-at-a-time picks are the variant rows; the two-at-a-time and full-grid counts add up to their
    number of combinations; the fragile band is the lowest and the highest threshold the full grid picks; both
    power-requirement rows pick none, and each row's pick follows from its own sizes and power."""
    frozen = spec()
    comb, variants, matched = frozen["combinations"], frozen["variants"], frozen["matched"]
    assert comb["script_sha256"] == prereg.file_sha256(REPO / "tools/forecast_size.py")
    assert (comb["battery_sha256"], comb["match_sha256"], comb["variants_sha256"]) == (
        frozen["size"]["battery_sha256"], matched["sha256"], variants["sha256"])
    assert comb["reproduction"]["weights"] == 0 and comb["reproduction"]["one_at_a_time_mismatch"] == []
    sizes = {name: len(values) for name, values in comb["choices"].items()}
    full = 1
    for n in sizes.values():
        full *= n
    assert comb["full_grid"]["n"] == full == 2160
    assert comb["one_at_a_time"]["n"] == sum(n - 1 for n in sizes.values()) == len(variants["variants"]) - 1
    names = list(sizes)
    assert comb["two_at_a_time"]["n"] == sum((sizes[a] - 1) * (sizes[b] - 1)
                                             for i, a in enumerate(names) for b in names[i + 1:])
    for part in ("one_at_a_time", "two_at_a_time", "full_grid"):
        assert sum(comb[part]["picks"].values()) == comb[part]["n"], part
    picked = [float(a) for a, n in comb["full_grid"]["picks"].items() if a != "none" and n]
    assert comb["band"] == [min(picked), max(picked)] == frozen["fragile_band"]
    order = [prereg.key(r["threshold"]) for r in matched["table"]]
    assert len(comb["power_rows"]) == 2
    assert [row["requirement"] for row in comb["power_rows"]] == ["abc_power", "falsifier_c_power"]
    for row in comb["power_rows"]:
        power = row["power"] if row["requirement"] == "abc_power" else row["falsifier_c_power"]
        passes = {a: max(tab[a] for tab in row["size"].values()) <= row["cap"] and power[a] >= row["floor"]
                  for a in order}
        assert row["passes"] == passes and not any(passes.values()) and row["threshold"] is None, row["name"]


def test_the_combinations_are_counted_by_distinct_rule_and_the_md_states_the_menu_and_the_power_failures():
    """Fix pass 5, item G2 (review F claim 1 and N1): logging the kurtosis is no choice when the kurtosis is dropped,
    so the 2,160 combinations are 1,620 distinct rules, and the two-at-a-time combinations 91 rules of their own; one
    rule never picks two thresholds; the picks come from the table's menu, whose top bounds what the band can say;
    the combinations that pick none fail at the lowest threshold on power, not on size; the .md states all of it, the
    three conditional draws two at a time (item G4) and what the scorer's hash covers (item G5)."""
    frozen = spec()
    comb, matched = frozen["combinations"], frozen["matched"]
    grid, distinct, two = comb["full_grid"], comb["full_grid"]["distinct_rules"], comb["two_at_a_time"]["distinct"]
    assert (grid["n"], distinct["n"], comb["two_at_a_time"]["n"], two["n"]) == (2160, 1620, 93, 91)
    for part in (distinct, two):
        assert sum(part["picks"].values()) == part["n"]
    # dropping the kurtosis makes "kurtosis logged" no choice: the grid without it, with the kurtosis' own count
    sizes = {name: len(values) for name, values in comb["choices"].items()}
    drops_kurt = sum("kurt" in d for d in comb["choices"]["drop"])
    rest = grid["n"] // (sizes["drop"] * sizes["logkurt"])
    assert distinct["n"] == rest * ((sizes["drop"] - drops_kurt) * sizes["logkurt"] + drops_kurt)
    best = lambda picks: max((n, a) for a, n in picks.items() if a != "none")[1]
    assert (best(grid["picks"]), best(distinct["picks"])) == ("0.025", "0.03")
    assert comb["thresholds"] == [r["threshold"] for r in matched["table"]] == [0.05, 0.04, 0.03, 0.025, 0.02]
    lowest = prereg.key(min(comb["thresholds"]))
    rows = grid["none_at_lowest"]
    assert len(rows) == grid["picks"]["none"] == 9
    for r in rows:
        assert r["threshold"] == 0.02 and r["fails"] == ["power"] and r["power"] < r["floor"] == 0.9
        assert max(r["size"]) <= r["cap"]
    for r in comb["power_rows"]:
        power = r["power"] if r["requirement"] == "abc_power" else r["falsifier_c_power"]
        assert power[lowest] < r["floor"] and max(tab[lowest] for tab in r["size"].values()) <= r["cap"]
    md = " ".join(prereg.paths(ID)["md"].read_text(encoding="utf-8").split())
    assert "the 2,160 combinations are 1,620 distinct rules (540 combinations repeat a rule)" in md
    assert "The most common pick is p < 0.025 by combination and p < 0.03 by distinct rule." in md
    assert "Of the 93 combinations two at a time, 91 are rules of their own" in md
    assert "The picks come from the table's menu: p < 0.05, 0.04, 0.03, 0.025 and 0.02." in md
    assert f"{grid['picks']['0.05']} combinations ({distinct['picks']['0.05']} distinct rules) pick its top" in md
    assert "the saved tables cannot say what a threshold above 0.05 would do" in md
    assert "The 9 combinations that pick none, and both power-requirement rows, fail at p < 0.02 on power, not on " \
           "size." in md
    assert "So a p below 0.02 is a rejection at a size within the cap" in md
    assert "review A named p < 0.025 first (below), and the rule, coded after it, picks it" in md
    assert "the threshold the rule picks" not in md
    assert frozen["revised"][1].startswith("2026-11-09, before any commit or scoring, after the second review: "
                                           "review A named p < 0.025 first, and the rule, coded after it, picks it")
    assert "after the fifth review" in frozen["revised"][4] and len(frozen["revised"]) == 9
    sixth = frozen["revised"][5]
    assert "after the sixth review" in sixth and "review D's draw was not run again" in sixth
    assert "after the seventh review" in frozen["revised"][6] and "removes itself" in frozen["revised"][6]
    eighth = frozen["revised"][7]
    assert "after the eighth review" in eighth and "holds a dot" in eighth and "tools/__pycache__" in eighth
    ninth = frozen["revised"][8]
    assert "after the ninth review" in ninth and "_PYTHON_SYSCONFIGDATA_NAME" in ninth
    assert ("an entry of tools/ (a file with an import suffix, or a folder) is refused when HEAD does not hold it as "
            "committed; for a folder, HEAD must hold it as a folder and every file with an import suffix directly in "
            "it must be committed as it is; files deeper down, and files without an import suffix, are not "
            "checked") in ninth
    # fix pass 6, item H3 (review G claim 3): the fifth revision names the six runs; review D's draw was not run again
    assert "every simulation was run again with the final" not in md
    assert ("six simulations were run again with the final `tools/forecast_size.py` and gave the same values: the "
            "battery, the match, the variants, the combinations, the main conditional draw and the third fix pass's "
            "draw. Review D's draw was not run again: its seed was not recorded.") in md
    assert "Sixth, after the sixth review:" in md
    # item G4: the three conditional draws two at a time, the SE's caveat and the sizes above the cap
    assert "The main draw minus the third fix pass's:" in md and "+2.08 SE" in md
    assert "The main draw minus review D's:" in md and "The third fix pass's minus review D's:" in md
    assert "so it understates the spread between draws" in md
    assert ("Above the cap: the main draw's 0.0560 at 0.25%, the third fix pass's 0.0600 at 0.25%, review D's 0.0556 "
            "at 1.00%.") in md
    # item G5: what the scorer's hash covers
    assert "covers every repository file it can import" not in md
    assert f"The scorer's SHA-256 covers the {len(frozen['scorer_files'])} files of its closure" in md
    assert "Other code outside the closure is not hashed." in md
    # fix pass 6, item H1 (review G claim 2): when the checks of tools/ run, and what they do not stop; revised in fix
    # pass 7 (items I1, I2, I4; review H claims 1 and 2, L1, L3): the routes are examples, not a complete list
    assert "takes the name of a standard-library module or of a library the closure imports" not in md
    assert "These checks do not stop code that runs when it is imported and patches them in memory" not in md
    assert ("The scorer's checks catch mistakes and the routes they name. They do not stop code written to defeat "
            "them. Any code that runs in the scorer's process before or between the checks can defeat them: a file "
            "put on the import path, a .pth file, an edited library or standard library, a forged .pyc, or a module "
            "that removes itself. The routes named here are examples, not a complete list.") in md
    # fix pass 8, items J1 and J2 (review I claims 2 and 3, N1 and N2): which entries the checks read
    assert ("The checks of tools/ read every folder in tools/ and every file there whose name ends with an import "
            "suffix (.py, .pyc or an extension module's suffix). A file's module name is its name less the longest "
            "import suffix; a folder's module name is its name. The checks leave out an entry whose module name holds "
            "a dot, such as tools/prereg.old.py: no import loads it under any name. They also leave out "
            "tools/__pycache__, Python's bytecode cache.") in md
    assert ("so the commit check and the name check would refuse every run. `import __pycache__` can load it, and no "
            "check reads what it holds. The checks read a name with a hyphen: the standard library's sysconfig imports "
            "its data module by such a name") in md
    assert ("Run as a script, before it imports tools/prereg.py, the scorer refuses to run when an entry of tools/ "
            "that the checks read takes the name of one of the scorer's modules there and is not that module's .py "
            "file (a tools/prereg/ package would run in place of tools/prereg.py), or when two entries of tools/ that "
            "the checks read share a module name.") in md
    # fix pass 9, items K1 and K2 (review J claim 1 and N1): what the commit check reads; the refused variables
    variables = score_prereg.HIDDEN_PATH_VARIABLES
    assert ("Before it imports any third-party module, it refuses when "
            f"{', '.join(variables[:-1])} or {variables[-1]} is set, when an entry of tools/ that the checks read has "
            "the name of a standard-library module or of a module found on another entry of sys.path, when HEAD does "
            "not hold such an entry as committed, or when sys.modules holds a module loaded from tools/ that is not a "
            "closure file. Under the ledgers' lock, just before it writes the first spent line, the scorer refuses "
            "again when sys.modules holds such a module. The first three variables can put other code before the "
            "scorer's. _PYTHON_SYSCONFIGDATA_NAME names the module sysconfig imports, and the scorer refuses it before "
            "that import. The name check also runs before that import, so a tools/ file named after sysconfig's data "
            "module is refused before it runs. The commit check reads the same entries as the name check: a file with "
            "an import suffix, or a folder. A file must be in HEAD with the same bytes.") in md
    folder = ("For a folder, HEAD must hold it as a folder, and every file with an import suffix directly in it must "
              "be committed as it is. The commit check does not read files deeper down, or files without an import "
              "suffix")
    assert md.count(folder) == 3                                   # the refusal bullet, step 1, the ninth revision
    assert "that the checks read is not committed as it is" not in md
    assert "that its checks read is not committed as it is" not in md
    assert ("Under the ledgers' lock, just before it writes the first spent line, the scorer refuses again when "
            "sys.modules holds such a module.") in md
    assert "(a module file, a package folder or an extension module)" not in md
    assert "that an import statement can name" not in md and "that an import statement cannot name" not in md
    assert ("If its import raises ImportError, Python removes it from sys.modules and pandas carries on: no check "
            "refuses it, and the scorer scores.") in md
    assert "A committed tools/ file that is first imported after the spend is not refused." in md
    assert "1. Commit the three files and an empty spent.jsonl" not in md
    assert ("1. Commit the whole tree first, tools/ in full, with the three files and an empty spent.jsonl (after the "
            "history rewrite). The scorer's checks read each file with an import suffix and each folder in tools/, "
            "other than tools/__pycache__ and an entry whose module name holds a dot. The scorer refuses to run while "
            "HEAD does not hold such an entry as committed. A file must be in HEAD with the same bytes. " + folder +
            " (tools/score_prereg.py uncommitted_entries says which).") in md
    assert "Eighth, after the eighth review:" in md and "Ninth, after the ninth review:" in md
    assert "lists what still defeats the tripwire" not in md


def test_rule_key_counts_a_combination_that_drops_the_kurtosis_once_whatever_logkurt_says():
    """Fix pass 5, item G2 (review F claim 1): tools/forecast_size.py rule_key reads the kurtosis logged or not as no
    choice when the kurtosis is dropped; over the CHOICES grid that gives the frozen counts, 2,160 combinations and
    1,620 distinct rules (computed from the code, no simulation)."""
    import itertools

    import forecast_size as fs

    grid = [dict(zip(fs.CHOICES, values)) for values in itertools.product(*fs.CHOICES.values())]
    comb = spec()["combinations"]
    assert (len(grid), len({fs.rule_key(c) for c in grid})) == \
        (comb["full_grid"]["n"], comb["full_grid"]["distinct_rules"]["n"]) == (2160, 1620)
    dropped = {**fs.REGISTERED_CHOICE, "drop": ("kurt",)}
    assert fs.rule_key({**dropped, "logkurt": True}) == fs.rule_key({**dropped, "logkurt": False})
    assert fs.rule_key(fs.REGISTERED_CHOICE) != fs.rule_key({**fs.REGISTERED_CHOICE, "logkurt": False})


def test_the_nine_records_written_before_fix_pass_3_read_as_eight_smoke_runs_and_one_budget_run():
    """Fix pass 3, item D6: the records without an "event" (written before fix pass 2) are the M4 smoke and budget
    runs; prereg.LEGACY_KIND_RULE reads them, the file is never rewritten, and each keeps its run_id."""
    legacy = [line for line in prereg.read_lines(prereg.PREREG_DIR / prereg.RECORDS) if "event" not in line]
    kinds = [prereg.legacy_kind(line) for line in legacy]
    assert sorted(kinds) == ["budget"] + ["smoke"] * 8
    assert all(line["run_id"] and "diagnostic_kind" not in line for line in legacy)
    assert len({line["run_id"] for line in legacy}) == 9
    # Fix pass 4, item F6e (review E claim 4): they count toward no current limit, because their trial_hash has the
    # formula before fix pass 2, which no current smoke, budget or grid configuration gives (computed, nothing runs).
    assert not {line["trial_hash"] for line in legacy} & current_trial_hashes()


def current_trial_hashes() -> set[str]:
    """The trial_hash of every smoke and budget configuration of tools/smoke_m4.py and of every grid entry."""
    from datetime import date

    import smoke_m4
    from volbt.engine.run_config import RunConfig, trial_hash
    from volbt.strategies.grid import m4_grid

    out = {trial_hash(smoke_m4.smoke_config(source, mode, *smoke_m4.VALIDATION),
                      smoke_m4.smoke_strategy(structure, source)) for structure, source, mode in smoke_m4.SMOKE_RUNS}
    out |= {trial_hash(smoke_m4.smoke_config("optionsdx", "quote", *smoke_m4.BUDGET, kind="budget"),
                       smoke_m4.smoke_strategy(structure, "optionsdx")) for structure in smoke_m4.STRUCTURES}
    out |= {trial_hash(RunConfig(date(2010, 1, 4), date(2019, 12, 31), "development", **entry.engine), entry.strategy)
            for rv in ("har", "naive") for entry in m4_grid(rv)}
    assert len(out) == 72                         # the smoke and budget configs are 4 of the grid's (fix pass 4, F6a)
    return out


@pytest.mark.real_data
def test_the_dependence_summary_and_the_windows_re_measure_to_the_frozen_ones():
    from volbt import config
    from volbt.data.store import Store

    frozen = spec()
    store = Store(config.store_dir())
    if not store.has("smile_fits"):
        pytest.skip("no built store: run tools/build_data.py and tools/build_pricing.py")
    dependence = prereg.measure_dependence(store)
    assert dependence == {k: v for k, v in frozen["calibration"].items() if k != "use"}
    windows = [{"start": "2010-01-04", "split": "development"}]
    assert [{k: w[k] for k in ("start", "split")} for w in frozen["windows"]] == windows
    import forecast_test as ft
    from volbt.data.store import session_calendar

    days = ft.window(session_calendar(store), prereg.WINDOW_START, prereg.WINDOW_LAST_TARGET)
    assert prereg.dates_sha256(days) == frozen["windows"][0]["dates_sha256"] and len(days) == 2495
    assert prereg.store_tables(store) == frozen["data"]

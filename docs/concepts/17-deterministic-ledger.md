# A deterministic ledger

## First principles

A backtest is only worth reading if you can run it again and get the same answer. "The same answer" has to mean the same *bytes*, because a number that moves in the last digit hides a bug that moves in the first. ADR-0001 §7 sets the rule: the same input files, config and code give byte-identical ledger files.

Terms:
- **Ledger**: the tables one run writes, one parquet file each, in a folder `runs/run_id=<id>/`.
- **`config_hash`**: the SHA-256 of the canonical JSON of the engine config and the strategy's name and parameters. It defines a trial (ADR-0010 §2).
- **`data_fingerprint`**: the SHA-256 over the sorted (path, size, SHA-256) lines of every input file the run reads.
- **`run_id`**: the SHA-256 of `config_hash`, `data_fingerprint`, the commit and the code fingerprint (every volbt source file and the library versions: a "-dirty" commit names no code, the M3 review found). It is the folder name and never a column (decision D13 as amended).

Three things break byte equality, and the engine closes each:
- **Order.** A set of strings iterates in a different order in each Python process (`PYTHONHASHSEED`). Lot ids are allocated in creation order, from a list, never from a set. Rows are sorted by the ERD key before writing.
- **Floats.** Addition of floats is not associative. In Python `(0.1 + 0.2) + 0.3` is 0.6000000000000001 and `0.1 + (0.2 + 0.3)` is 0.6. So cash is an integer number of cents, and the NAV sums are taken by NumPy in `lot_id` order, never by a DuckDB aggregate whose order depends on its threads.
- **Clocks and ids.** Nothing in a ledger file holds a clock, a uuid or a timing. Those live in `run_meta.json`, which is not hashed.

## The maths

There is no model. There is a hash chain.

```
run_id = SHA-256( "config_hash=" + H_cfg + "\n" + "data_fingerprint=" + H_data + "\n" + "commit=" + C + "\n"
                  + "code_fingerprint=" + H_code )
```

A change of seed changes `config_hash`, so it changes the folder, and leaves every other ledger file byte for byte the same (ADR-0001 test 3, second part). M3 draws nothing at random, so the seed is in the hash only to make a seed change a new run.

**Reading is checked as well as writing.** `run_backtest` checks that the store is current and fingerprints the inputs before it reads, writes the ledger into a `.tmp` folder, checks both again, and renames the folder into place only if nothing changed (`StoreChanged` otherwise). `volbt.engine.report.check_ledger` re-hashes every ledger file against `run_meta.json` and re-derives the `run_id`, before and after it builds the app's JSON.

**Worked example**, ADR-0001 test 3 (`tests/test_engine_determinism.py:64`; `uv run pytest -q tests/test_engine_determinism.py`). The reference strategy runs on the made-up store twice in the test process and once in each of three fresh interpreters with `PYTHONHASHSEED` 0, 1 and 12345. All five runs write the same folder name, the same 12 ledger files (same SHA-256 each) and the same two app bodies. A run with `seed=7` writes a different folder, and the only ledger file that differs is `runs/part-0.parquet`, in two columns: `config_hash` and `config_json` (`:88`).

**On real data.** The 2010-2023 run was made twice inside `tests/test_real_engine.py` and the two ledgers had equal file hashes and an equal `Book.digest` (`uv run pytest -q -s -m real_data tests/test_real_engine.py`, 2026-10-30). The development run `4eede29cb2ae...` (2026-11-09, after the round-3 fixes) has a ledger of 12 parquet files, 781,620 bytes in all (`cat .../*/part-0.parquet | wc -c`); its largest file, `position_marks` (301,351 bytes), has 4,789 rows, and `cash_flows` has the most rows, 11,740 (`pyarrow` metadata). Only `risk_events` (empty) has the same SHA-256 as in the run it replaced, `7f5d4f011508...`: round 3 changed the expiry picker, which now takes the Saturday-dated December 2015 monthly, so the tables differ from the session 2015-11-16 on. `7f5d4f011508...` itself had 11 of 12 files equal to the run before it, `ca1ff654a3c3...` (only `runs` differed, because the code fingerprint changed).

## Assumptions

- **The inputs are pinned.** `uv.lock` pins the libraries; `data_fingerprint` pins the data; `code_fingerprint`, the SHA-256 of every `.py` file under `src/volbt/` and the library versions, pins the code. The commit names the tree, but a dirty tree's commit string (`...-dirty`) names no code, which is why the run id hashes the code fingerprint too (decision B17).
- **One machine class.** The tests compare processes on one machine. Whether a different CPU gives the same float bits is not measured here.
- **One writer at a time.** The store has no lock (ADR-0001 amendment). The before-and-after check turns a race into an error, not a mixed ledger.

## Where it breaks

- **The same id replaces the folder.** A second run with the same `run_id` removes the first folder and renames its own into place. That is safe only because the same id means the same bytes.
- **The committed JSON names a dirty commit.** `blotter.json` and `positions_timeline.json` say `engine_commit 9fb7403...-dirty` until the milestone is committed and the files are exported again.
- **A mutant shows each guard.** A uuid in place of the hash (mutant 31) is caught by `check_ledger` inside the determinism test. Lot ids taken from iterating a set (mutant 29) fail the same test under a different `PYTHONHASHSEED`. Both are killed.

## In this project

- `src/volbt/engine/run_config.py:121` `config_hash`, `:126` `make_run_id`, `:115` `config_json`.
- `src/volbt/engine/ledger.py:29` `SCHEMAS`, `:84` `SORT_KEYS`, `:90` `_clean` (NaN as null), `:113` `Ledger.write`.
- `src/volbt/engine/loop.py:765` `run_backtest`: the check, the fingerprint, the `.tmp` folder, the second check, the rename (`:776-830`).
- `src/volbt/engine/report.py:44` `check_ledger`.
- `src/volbt/engine/book.py:132` `Book.digest`: a SHA-256 of the whole book, so a test can show that a strategy's `decide()` changed nothing.
- `tests/test_engine_determinism.py:64` and `:88`; `tests/test_engine_provenance.py:30`, `:39` and `:59`.

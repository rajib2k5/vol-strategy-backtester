# Querying a shared database without touching it: the private mirror

> **Data notice.** The DoltHub figures in this document (counts, dates, quantiles and summaries, in its text and in its tables) are derived from the DoltHub database `post-no-preference/options` (<https://www.dolthub.com/repositories/post-no-preference/options>), licensed [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/), and are shared under the same licence. Changes: we aggregated it into counts, shares and quantiles, compared it with OptionsDX and ran our pricing build on it; no quote row is reproduced. The rest of this repository is MIT. See [DATA.md](../../DATA.md).

## First principles

The DoltHub clone at `$VOL_DATA_DIR/dolthub/options` is shared with other projects, so we must never change it. "Run only SELECT" sounds like enough. It is not: a database engine can write while it answers a read. It may take a lock file, update its statistics, or tidy its journal. Those writes change files that another program relies on.

This was measured on dolt 2.6.1 on 2026-10-29. Even `dolt status` opens `.dolt/noms/manifest`, `.dolt/noms/journal.idx`, the journal, the lock files and the `stats/` files for writing, and creates a new empty folder, `.dolt/tmp/`. The bytes it writes back are the same, but the files' modification times change and a new folder appears. A read-only mount does not help either: dolt then refuses to start (`fslock ... read-only file system`). When two projects query one clone at the same time, both rewrite the same lock, manifest and journal files, so they contend for them.

A **private mirror** solves this by giving each reader its own database. Copy the clone once with `cp -a`, which keeps permissions and timestamps, and run every dolt command in the copy. dolt's housekeeping writes then land in the copy, which nobody else reads. The shared clone is read exactly once, by `cp`.

## The maths

There is no formula. There are three checks:

- **Where dolt runs.** Before any process starts, the target path is resolved (symlinks and `..` included) and refused if it is the shared clone or lies inside it. The same check applies to the work folder, because dolt's home (`DOLT_ROOT_PATH`) is created there.
- **Our SQL only reads.** Every statement must be one SELECT, SHOW or DESCRIBE and name none of the write words (concept: the guard in `assert_read_only_sql`).
- **The mirror's data did not change.** `dolt status` on the mirror says `nothing to commit, working tree clean` before and after the export. Housekeeping files may change; table data may not.

Measured on 2026-10-29 (`uv run python tools/build_data.py --export-dolthub --no-build`, evidence in `data/raw/dolthub/option_chain_spy.export.json`): the export of DoltHub's 185,910 SPY rows from the mirror took 166.8 s (the overlay export took 107.6 s), `dolt status` was clean before and after, and the parquet it wrote has the same SHA-256 as the one exported through the old overlay. A listing of the shared clone (63 entries: path, size, mtime, ctime), taken before and after, was identical.

## Assumptions

- **The copy is consistent.** It was made while nobody was writing to the clone. A `cp -a` of a database during a write could copy a torn state.
- **The disk has room.** Each copy of `dolthub/options` is 8.3 GiB (`du -sh`).
- **The copy is as new as we need.** The mirror does not follow the shared clone. If the hub updates the clone, the mirror must be copied again.

## Where it breaks

- **A stale mirror.** Nothing checks that the mirror matches the current shared clone. The export's row count (185,910) and the build's input fingerprint show a change only after the fact.
- **A path that only looks private.** A symlink or a `..` path into the clone would pass a plain string comparison. That is why the check resolves the path first; `tests/test_dolthub_readonly.py` tries both.
- **A protected path that moves with a setting.** The clone's path came from `VOL_DATA_DIR`, so with `VOL_DATA_DIR` pointed elsewhere the real clone looked like any other folder: it passed as a mirror, and `VOLBT_WORK_DIR=<real clone>/work` was accepted (M1 review, round 2). Now the default clone, `~/data/vol-projects/dolthub/options`, is refused whatever the environment says (resolved with `$HOME` and with the account's home from the password database), and dolt runs only in a folder under this project's cache. An allow-list ("only here") is safer than a deny-list ("never there"): a path the deny-list forgot is still refused.
- **Writes outside both.** dolt also keeps settings and telemetry in `~/.dolt`. We point that at `data/dolt_root/` in the repo with `DOLT_ROOT_PATH`, and switch telemetry off.

## In this project

Until 2026-10-29, M1 ran dolt on an unprivileged `unshare` overlay mount of the clone, whose writes went to a throwaway upper layer. The overlay was replaced on 2026-10-29 because two projects querying one clone contend for its files: the project-wide rule from that day is that every project queries its own copy.

- `src/volbt/config.py:78-115`: `project_cache_dir()`, `dolthub_mirror_dir()` (`$VOL_DATA_DIR/vol-strategy-backtester/cache/dolt_mirror/options`), `shared_clones()` (the clone `VOL_DATA_DIR` names and the default one, whatever the environment says) and `inside_shared_clone()`.
- `src/volbt/config.py:118-130`: `work_dir()` refuses a `VOLBT_WORK_DIR` inside any shared clone.
- `src/volbt/data/dolthub.py:104-119`: `mirror_dir`, which refuses a target inside a shared clone, or outside the project's cache folder (`MirrorPathError`).
- `src/volbt/data/dolthub.py:135-156`: `run_dolt`, a plain `dolt` process with the mirror as its working folder.
- `src/volbt/data/dolthub.py:216-241`: `export_spy_rows`, with the `dolt status` checks before and after.
- `src/volbt/data/dolthub.py:90-101`: `assert_read_only_sql`, the guard on our own SQL.
- `tests/test_dolthub_readonly.py`: a real dolt on a throwaway clone and its `cp -a` copy. The clone's listing is unchanged; the mirror's is not, as allowed.

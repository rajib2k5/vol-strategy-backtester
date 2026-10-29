# ADR-0009: Data sources, trading calendar, quality flags and the out-of-sample execution mode

**Status:** Accepted at milestone 0. To be implemented in M1, with the IV-related flags in M2. To be revisited in M1 after the full quality report.

## Revised after M0 review (2026-10-28)

The adversarial review (`docs/validation/00-design-research-ledger.md`, claims 3, 9 and 13, and "Findings nobody asked about") refuted the following. Each was re-measured: DoltHub with SELECT-only `dolt sql` (`dolt status` clean before and after), OptionsDX with DuckDB.

1. **"The surface-mode gap bounds the DoltHub distortion" was false.** Running surface mode on the dense OptionsDX chain measures only the small in-grid interpolation error. On a DoltHub-like grid, the reviewer measured:
   - median 0.03 vol points inside the grid;
   - 7.0 vol points (p90 34.6) beyond it, with flat extrapolation;
   - 1.02 vol points at every 7-DTE exit, because DoltHub lists nothing under 10 DTE.

   I reproduced all three figures exactly. I also found a larger effect the reviewer's probe did not test: DoltHub lists a given expiry on only about half the sessions, so most held contracts are marked across expiries. That costs a median 0.24 vol points, against 0.04 in-grid.

   **Changed:** the distortion is now *estimated*, not bounded. Each frozen configuration is run on OptionsDX masked by DoltHub's **own** SPY sampling on the same 2020–23 dates (§4).
2. **"12 rows on market closures"** is 12 snapshot **dates** holding **44,926** rows. The two Sandy dates share a stale underlying, but they are not copies: 6.6% of their quotes are identical.
3. **DoltHub facts.**
   - It has almost every weekday only from **Oct**-2024 (11 sessions to 2026-10-26 have no SPY rows); Sep-2024 has some Tue/Thu sessions.
   - Rows per date were 76–266 in 2024, not 88–212.
   - The 520 put is quoted on 2 of **14** sessions.
   - The Aug-2024 hole is **2024-07-30 → 2024-08-09**: 2024-07-29 (110 rows) and 2024-08-12 (116 rows) both exist.
4. **The cross-vendor window.** DoltHub's 2019 SPY rows fall on Saturdays (46 of 48 dates), so there is no same-date overlap with OptionsDX in 2019. **Changed:** the window is 2020-01-06 → 2023-12-29 (§5).

Round 2 (`docs/validation/00-round2-ledger.md`, claim 11): the error numbers above reproduce, but the row saying DoltHub's 2020–23 structure "matches 2024–26" was false on expiry churn (listing share 0.286 in 2020–22 against 0.50–0.54 from 2023; about 111 expiries a year against 36–44). The row is replaced by the per-regime figures, M and M′ are reported separately for 2020–22 and 2023, and 2023 is the closest holdout analogue.

## Context

All the facts below were measured read-only on 2026-10-28 unless marked otherwise. The OptionsDX files were left unmodified. **Corrected in M1 (2026-10-29): the DoltHub clone was not.** Its data is unchanged, but the M0 measurements ran `dolt` directly in the clone, and on dolt 2.6.1 that rewrites files even to answer a SELECT. `.dolt/`, `.dolt/noms/manifest`, `journal.idx`, the journal and the matching `stats/` files have a modification time of 2026-10-28 14:11 CDT from those runs; their bytes did not change (the data hub's own reproduction, 2026-10-29). From M1 on, dolt runs only in this project's private copy of the clone ("Out-of-sample source" below).

### Primary in-sample source: OptionsDX via Kaggle

The source is Kaggle `dudesurfin/spy-options-eod-volatility-surface-2010-2023`, MIT licence, files at `$VOL_DATA_DIR/kaggle/spy-eod-2010-2023/`.

**Size and coverage**
- 14 files, about 569 MiB, 9,468,584 rows.
- 3,508 snapshot dates, 2010-01-04 to 2023-12-29.
- Average expiries per date grew from 14.6 (2010) to 35.7 (2020). Average strikes per date grew from 133 to 327 (2022).

**Columns.** There are 33 columns, one wide row per (date, expiry, strike). The names really do contain the square brackets. In file order:

```
[QUOTE_UNIXTIME] int64, [QUOTE_READTIME] string, [QUOTE_DATE] string, [QUOTE_TIME_HOURS] double,
[UNDERLYING_LAST] double, [EXPIRE_DATE] string, [EXPIRE_UNIX] int64, [DTE] double,
[C_DELTA] [C_GAMMA] [C_VEGA] [C_THETA] [C_RHO] [C_IV] [C_VOLUME] [C_LAST] double, [C_SIZE] string,
[C_BID] [C_ASK] [STRIKE] [P_BID] [P_ASK] double, [P_SIZE] string, [P_LAST] [P_DELTA] [P_GAMMA]
[P_VEGA] [P_THETA] [P_RHO] [P_IV] [P_VOLUME] [STRIKE_DISTANCE] [STRIKE_DISTANCE_PCT] double
```

**Snapshot time**
- `[QUOTE_TIME_HOURS]` is 16.0 on every row.
- `[QUOTE_UNIXTIME]` and `[EXPIRE_UNIX]` are 16:00 America/New_York on every row.
- There is exactly one `[UNDERLYING_LAST]` per date.
- Expiration-day (0-DTE) contracts are present: on 38 dates in 2010, 166 in 2022, and all 250 dates in 2023.

**Keys and parsing**
- The natural key (`[QUOTE_DATE]`, `[EXPIRE_DATE]`, `[STRIKE]`) is unique on all rows.
- `[C_SIZE]` parses as `"<bid size> x <ask size>"` on 100% of rows.

**Volume** is unreliable before 2021 (details in ADR-0002):
- The median daily total jumps from 366,024 contracts (Dec-2020) to 2,981,034 (Jan-2021).
- Volume is null on 37.6% of call rows overall, including heavily traded contracts.
- There is no open interest.

**Units**
- IV is a decimal (0.12 = 12%).
- Vega is per vol point; gamma is per $1.
- Vendor theta does not reconcile with Black-Scholes-Merton (ADR-0004).
- Vendor `[DTE]` carries a DST artefact (ADR-0008).

**Calendar anomalies**

| Anomaly | Dates |
|---|---|
| Snapshot dates on market closures (12 dates; 44,926 rows) | 2012-10-29, 2012-10-30 (Hurricane Sandy; 1,416 rows each; both show the same `[UNDERLYING_LAST]`, a stale underlying, but only 6.6% of their quotes are identical); 2018-12-05; 2022-01-17, 02-21, 04-15, 05-30, 06-20, 07-04, 09-05, 11-24, 12-26 |
| Weekday sessions missing a snapshot (26) | Count is against our approximate NYSE holiday list. Examples: 2011-01-19 → 2011-01-25 (5 sessions), 2022-06-17, 2022-06-24, 2022-12-16 |

The 2022-06-20 row (Juneteenth closure) shows an `[UNDERLYING_LAST]` that we believe is SPY's 2022-06-17 close, and 06-17 itself is missing. That points to a mislabelled snapshot. This was **unverified** at M0, until we had yfinance closes.

**Updated in M1 (2026-10-29): verified.** OptionsDX has no 06-17 snapshot, and its 06-20 `[UNDERLYING_LAST]` equals yfinance's unadjusted 2022-06-17 close to the cent. All 12 closure-dated snapshots carry the previous session's SPY close exactly: 0 cents off on every one. Measured with `uv run python tools/report_m1.py`, block "calendar: OptionsDX" (`docs/milestones/01-data-layer.md`, "Rows, flags and the calendar").

**Updated in M1, round 2 (2026-10-29): the 06-20 snapshot is not a mislabelled 06-17 one, and it is dropped.** Its prices are 06-17's, but its contract list is 06-20's. Filed under 06-17 by the relabel rule (as the first M1 build did), the chain had 9,742 long rows whose first expiry was 2022-06-21: none of the 516 contracts expiring 2022-06-17 that 06-16 listed, and 1,142 (symbol, expiry) pairs that 06-16 did not list, including two expiries first seen on 06-21's chain, 2022-07-25 and 2022-07-27 (DuckDB on the first M1 store, 2026-10-29). So a relabel would show a strategy on 06-17 contracts first listed on 06-20 (look-ahead) and hide that day's own expiries. A matching underlying cannot tell a late snapshot from one that mixes two days. **Default taken 2026-10-29, the owner can override it:** all 12 closure-dated dates are dropped, 2022-06-17 is served as a session without a snapshot, and the underlying-equals-previous-close check is kept as a diagnostic in the quality report (`quality_non_session_dates`), not as a rule.

### Out-of-sample source: DoltHub `post-no-preference/options`

> **Data notice.** Tables in this ADR that report DoltHub counts, dates or summaries are derived from this database, licensed [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/), and shared under the same licence; the rest of the repository is MIT. See [DATA.md](../../DATA.md).

The clone is at `$VOL_DATA_DIR/dolthub/options`, licensed CC BY-SA 4.0, and is **read-only**: it is shared with other projects.

**Updated in M1 (2026-10-29):** nothing of ours runs dolt in it. Every dolt call runs in a private mirror, a `cp -a` copy at `$VOL_DATA_DIR/vol-strategy-backtester/cache/dolt_mirror/options` (`config.dolthub_mirror_dir()`), under the project-wide rule of that day: two projects querying one clone contend for its files. The loader refuses a target, or a work folder, that resolves inside the shared clone (`docs/concepts/06-private-dolt-mirror.md`). Round 2 of the review found that "the shared clone" followed `VOL_DATA_DIR`: pointed elsewhere, the real clone passed as a mirror and as a work folder. Now the default clone, `~/data/vol-projects/dolthub/options` resolved (with `$HOME`, and with the account's home), is refused whatever the environment says, and dolt runs only in a folder under `$VOL_DATA_DIR/vol-strategy-backtester/cache/` (`config.shared_clones`, `dolthub.mirror_dir`).

**Table `option_chain`.** It has 13 columns, with primary key (`date`, `act_symbol`, `expiration`, `strike`, `call_put`):

```
date date, act_symbol varchar(64), expiration date, strike decimal(7,2), call_put varchar(64) ('Call'|'Put'),
bid decimal(7,2), ask decimal(7,2), vol decimal(5,4), delta decimal(5,4), gamma decimal(5,4),
theta decimal(5,4), vega decimal(5,4), rho decimal(5,4)
```

**Missing from it:** volume, sizes, last price, underlying price and snapshot time.

**SPY coverage, measured over every SPY row** (SELECT-only `dolt sql`, grouped by date and expiry)

| Property | Measured |
|---|---|
| Date range | 1,299 SPY dates, 2019-02-09 → 2026-10-26 |
| 2019 | 48 dates: 46 Saturdays, 1 Friday, 1 Sunday. Weekly Saturday snapshots run to 2020-01-04 |
| Sessions, 2020-01-06 → Aug-2024 | Mon/Wed/Fri, about 151 dates a year, with a handful of Tue/Thu dates |
| Sessions from Sep-2024 | Sep-2024 adds some Tue/Thu (Tue 2, Thu 3). **Almost every weekday from Oct-2024** (11 sessions missing to 2026-10-26) |
| Gap | No SPY dates from **2024-07-30 to 2024-08-09**. 2024-07-29 and 2024-08-12 exist; the M/W/F sessions 07-31, 08-02, 08-05, 08-07 and 08-09 are missing. So the Aug-2024 shock itself is missing |
| Rows per date | 76–266 (2024), 86–210 (2025), 162–216 (2026) |
| Expiries per date | 3 (2020–24), 3–4 (2025), 4 (2026), at median DTEs of about 13–14, 29 and 51–56 |
| Front expiry | 10–18 DTE (median 13–14). **No expiry under 10 DTE is ever listed** |
| Strikes | median 17–27 per expiry, about 2.2–2.3% of the mid strike apart, spanning ±17–30%. **Re-centred every day** |
| Expiry persistence | An expiry first listed at ≥ 25 DTE appears on a median 50% of the DoltHub sessions between its first and last listing (by year range in the last row of this table). 95% of those expiries are listed again at 14–21 DTE, 67% at 10–13 DTE, and none below 10 |
| Expiry types | 429 expiries listed in 2024–26: Fridays 147, Mondays 107, Tuesdays 100, Wednesdays 62, Thursdays 13. Only 8% are third Fridays |
| Contract persistence | The 2025-04-30 520 put was quoted on 2 of the 14 sessions between 2025-03-31 and 2025-04-17 (04-02 and 04-14) |
| Market closures | Rows exist for 2020-01-20 (MLK Day), 2024-01-01 (New Year's Day) and 2024-09-02 (Labor Day). **Updated in M1 (2026-10-29):** this list was too short. There are **55** closure dates in 2020-26, not 3. Add the 48 weekend dates (47 Saturdays and 1 Sunday, 2019-02-09 → 2020-01-04) and DoltHub has **103** non-session dates holding 11,218 rows (`uv run python tools/report_m1.py`, block "calendar: DoltHub") |
| Expiry persistence by regime | **Not the same across 2020–26.** An expiry is listed on a median 0.286 of the sessions between its first and last listing in 2020–22, against 0.50–0.54 in each year from 2023. DoltHub lists about 111 distinct expiries a year in 2020–22 against 36–44 a year later, and the 2020 strike spacing is about 2.97% of spot, against about 2.2–2.3% later. So the masked runs of §4 describe the holdout's expiry churn only from 2023: **2023 is their closest analogue, and 2020–22 is a different regime** |

**Table `volatility_history`** has date, act_symbol, `hv_*` and `iv_*` fields (current, week-ago, month-ago, year high/low). It is not used in M0.

### Other inputs, fetched in M1 to the repo's git-ignored `data/raw/`

Where M1 writes (default taken 2026-10-29, owner can override): every download goes to `data/raw/` and every built table to `data/store/`, inside the repo's git-ignored `data/` folder (`config.work_dir()`, overridable with `VOLBT_WORK_DIR`). Vendor sources (the Kaggle files, the DoltHub clone) are still only read, from `$VOL_DATA_DIR`. **Corrected in round 2 of the M1 review:** one thing M1 writes does live under `$VOL_DATA_DIR`: the private dolt mirror at `$VOL_DATA_DIR/vol-strategy-backtester/cache/dolt_mirror/options`, made once with `cp -a`, which dolt's housekeeping writes into on every call. Nothing else M1 writes goes there.

| Source | What we take | Notes |
|---|---|---|
| yfinance | SPY daily OHLC (unadjusted, `auto_adjust=False`) and dividends | |
| FRED `DGS3MO` | Daily yield, percent, investment basis | https://fred.stlouisfed.org/series/DGS3MO |
| Cboe VIX history | `DATE,OPEN,HIGH,LOW,CLOSE` (MM/DD/YYYY), 1990 to date | `cdn.cboe.com/.../VIX_History.csv` now redirects to `https://cdn-api.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv`, verified 2026-10-28. VIX3M from the same family was **unverified** at M0. **Updated in M1 (2026-10-29): available.** `cdn-api.cboe.com/.../VIX3M_History.csv`, 4,304 rows, 2009-09-18 → 2026-10-28 (`uv run python tools/report_m1.py`, block "VIX3M"). |

## Decision

1. **The trading calendar comes from SPY's daily bars, not from the chain.**
   - A session is a date with a SPY bar.
   - Chain rows dated on non-sessions are flagged `NON_SESSION_DATE`.
   - **Relabel rule.** Relabel such a row to the nearest earlier session that has no snapshot of its own, but only if its `[UNDERLYING_LAST]` is within $0.02 of that session's SPY close. Flag it `RELABELLED`. Otherwise drop it from the clean table.
   - **Updated in M1, round 2 (2026-10-29): the relabel rule is removed.** Every non-session row is dropped, in every source. The one date it moved, OptionsDX 2022-06-20, held 06-20's contract list under 06-17's prices (Context, "Calendar anomalies"). `RELABELLED` keeps bit 8 and is never set, so no other bit moves. The underlying-against-previous-close test is reported per dropped date (`quality.non_session_check`), and moves nothing.
   - Sessions with no snapshot run in the engine with `STALE_SURFACE` marks (ADR-0004), and option orders wait (ADR-0002).
   - The same rule applies to DoltHub, which also has rows on closures (2020-01-20, 2024-01-01, 2024-09-02).
   - **Updated in M1 (2026-10-29):** DoltHub has 55 closure dates, not 3, and 48 weekend dates. DoltHub gives no underlying, so the $0.02 test cannot pass. M1 drops all 103 of its non-session dates (11,218 rows). Whether to relabel them by a parity test instead is the owner's call (`docs/milestones/01-data-layer.md`, "Decisions taken in M1", item 2).
2. **The clean table is long and flagged.** `option_quotes` has one row per (`source`, `quote_date`, `osi_symbol`).
   - The OSI symbol has the form `SPY   240315C00450000`: root padded to 6 characters, yymmdd, C or P, then strike × 1000 as 8 digits.
   - **We flag rows rather than delete them.** The only deletions are the non-session rows in point 1.
   - Each consumer applies its own rule to the flags: marks in ADR-0004, fills in ADR-0002, the smile and forward in ADR-0008.
3. **Quality flags.** `quality_flags` is an int bitmask:

   | Bit | Flag | Rule |
   |---|---|---|
   | 0 | `BID_NULL` | bid is null |
   | 1 | `ASK_NULL` | ask is null |
   | 2 | `ZERO_BID` | bid = 0 |
   | 3 | `CROSSED` | bid > ask |
   | 4 | `LOCKED` | bid = ask > 0 |
   | 5 | `WIDE` | ask − bid > mid, i.e. relative spread > 100% |
   | 6 | `STALE` | bid and ask both unchanged from the contract's previous snapshot while \|ΔS/S\| ≥ 0.5% |
   | 7 | `NON_SESSION_DATE` | the date is not a SPY session |
   | 8 | `RELABELLED` | the date was moved by the point-1 rule. **Reserved and never set from M1, round 2:** the rule was removed |
   | 9 | `VOLUME_UNRELIABLE` | volume is null, or the row is OptionsDX before 2021-01-04, or the row is DoltHub |
   | 10 | `UNDERLYING_MISMATCH` | \|`[UNDERLYING_LAST]`/S_close − 1\| > 0.10% |
   | 11 | `VENDOR_IV_INVALID` | the vendor's IV is null or ≤ 0 |
   | 12 | `EXPIRY_DAY` | τ = 0 |

   **Updated in M1 (2026-10-29):** bit 11 was `VENDOR_IV_NULL`, "the vendor gives no IV". The M1 review found vendor IVs that are present but unusable: OptionsDX has 216,700 rows with IV from −0.0005 to −0.00001 and 5,984 with IV = 0, and DoltHub has 70 rows with `vol` = 0, all on bid = ask = 0 quotes (216,665 and 5,983 OptionsDX rows in the store rebuilt after round 2, which dropped the 2022-06-20 rows). The bit keeps its number and now covers null or ≤ 0. It does not flag a tiny positive IV: 321,212 OptionsDX rows have 0 < IV ≤ 0.0005 and 482,104 have 0 < IV < 0.01, all unflagged; M2 recomputes IV from quotes, so the vendor's value is not used for pricing. An IV above 5 is not flagged; its count is reported as a measurement (`tools/report_m1.py`, block "vendor IV").

   The pricing build (M2) writes `quote_iv.iv_flags` separately: `IV_FAIL`, `PARITY_OUTLIER` and `FORWARD_FALLBACK`.
4. **Execution mode per source, and how the holdout distortion is estimated.**
   - OptionsDX runs `execution_mode = quote`: fills and marks come from quotes.
   - DoltHub runs `execution_mode = surface`: fills and marks come from the day's surface plus a modelled half-spread (ADR-0002 §7, ADR-0004 rule 3).
   - **Estimating the surface-mode distortion.** Each frozen configuration is run on the validation window, 2020-01-06 → 2023-12-29, in four ways:

     | Run | Chain (`chain_mask`) | Mode | What it isolates |
     |---|---|---|---|
     | Q | full OptionsDX (`none`) | quote | the validation result of record |
     | S | full OptionsDX (`none`) | surface | model-marking error on a dense chain |
     | M | OptionsDX masked by DoltHub's SPY sampling (`dolthub`) | surface | holdout conditions before Oct-2024: the M/W/F calendar, 3 expiries, about 24 strikes, expiries that come and go (at the 2020–22 or the 2023 rate of churn, by year), nothing under 10 DTE |
     | M′ | as M, with Tue/Thu sessions added (`dolthub_daily`) | surface | holdout conditions from Oct-2024. A Tue/Thu session keeps the (expiry, strike) pairs DoltHub listed on the previous session |

   - **The mask.** On each date, keep only the OptionsDX rows whose (expiry, strike) pair DoltHub lists for SPY that date, applying the calendar rule of point 1 to DoltHub's dates. A session DoltHub lacks becomes a session with no snapshot: `STALE_SURFACE` marks, and orders wait.
   - **Reported:** M − Q and M′ − Q, for Sharpe, mean daily P&L and max drawdown, together with the share of marks carrying each ADR-0004 surface flag. They are reported **separately for 2020–22 and for 2023, and not pooled**, because DoltHub's expiry persistence differs between them (context table, last row). **2023 is the closest analogue of the holdout** and its M − Q and M′ − Q are the **estimate** of the holdout distortion; 2020–22 shows how far that estimate moves under a different regime. S − Q splits the distortion into a model part and a sampling part.
   - **Mark-level errors, measured on M's mask for 2022–23** (ADR-0004 table): median 0.04 vol points in-grid, 0.24 across expiries, 0.19 beyond the grid and 1.21 below the front expiry. That sample pools 2022 with 2023, so the table is re-reported for each year.
   - **It is an estimate, not a bound.** It is measured under 2020–23 conditions, of which only 2023 resembles the holdout's expiry churn. It cannot include the Aug-2024 hole, DoltHub's unknown snapshot time (§5), or surface error that differs at 2024–26 rate levels.
   - S, M and M′ are diagnostics, with `run_purpose = diagnostic`. They select nothing and are not trials (ADR-0010 §2).
5. **Cross-vendor check, 2020-01-06 → 2023-12-29.** The same-date overlap is DoltHub's Mon/Wed/Fri dates in that window, about 151 a year.
   - **2019 does not overlap:** 46 of DoltHub's 48 SPY dates in 2019 are Saturdays. We compare them with the preceding Friday's OptionsDX snapshot only as a labelled test of the hypothesis that they are Friday closes, never as same-date overlap.
   - On the overlap dates, compare the 30-day ATM IV computed from each source.
   - Compare DoltHub's parity-implied spot with the SPY close.
   - Together these tell us DoltHub's effective snapshot time and how it differs from OptionsDX. Tolerances are set in M1, after we have looked at the distribution.
   - **Updated in M1 (2026-10-29):** because the thresholds (1 vol point, 25 bp) were chosen on the same 573 overlap dates they would judge (572 after round 2 dropped the relabelled 2022-06-17 chain), a pass/fail on them could not fail. They are published as measurements: the share of dates inside each, pooled and by year, with no verdict (`docs/milestones/01-data-layer.md`, "The cross-vendor check").

## Alternatives considered

- **Build the calendar from the chain's own dates.** Rejected. It would include 12 closure-dated snapshots (44,926 rows), two of them with a stale underlying, and it would miss 26 sessions.
- **Relabel a closure-dated snapshot to an empty previous session when its underlying matches that session's close** (this ADR's first rule, used by the first M1 build). Rejected in M1, round 2: the one snapshot it moved had the right prices and the wrong day's contract list (Context). It would win if the vendor's file for the closure were a pure re-stamp of the previous session's file, which the contract list rules out here.
- **Drop flagged quotes during cleaning.** Rejected. A held contract with a zero bid still needs a mark. Deleting the row would turn "worth almost nothing" into "missing" and send it to a different marking rule.
- **Run DoltHub through the same quote-level engine.** Rejected. With strikes re-centred daily, almost every exit would be `NO_QUOTE`, and the backtest would measure the vendor's sampling rather than the strategy.
- **Interpolate volume for DoltHub from OptionsDX patterns.** Rejected: that would be fabricated data. DoltHub uses the hard cap only.
- **Buy a fuller 2024–2026 chain** (OptionsDX, CBOE DataShop, ORATS). Not rejected, only out of scope for M0. It would replace surface mode for out-of-sample data and restore the Aug-2024 episode.
- **Estimate the distortion by imitating DoltHub's grid** (19 strikes about 2.3% apart, re-centred) on the contract's own expiry. That was the reviewer's probe, and it is better than the dense-chain run. Rejected as the method of record: DoltHub's 2020–23 chain exists, so its real sampling can be replayed. Imitation also misses the expiries that come and go, which turned out to be the bigger error source.

## Consequences and biases

- **Out-of-sample results test the signal plus the surface model, not execution.** The masked runs of §4 *estimate* that distortion under 2020–23 conditions, with 2023 the closest analogue of the holdout. They neither bound it nor remove it.
- **Every holdout exit at 7 DTE is a tenor extrapolation,** because nothing under 10 DTE is listed. Measured median error 1.21 vol points (ADR-0004). This is why ADR-0003 has M4 choose `exit_dte` with the masked runs in view.
- **Aug-2024 cannot be replayed historically.** The shock (2024-07-30 → 08-09) is missing. DoltHub has the run-up to 07-29 and the recovery from 08-12, so a run passes through the hole on `STALE_SURFACE` marks, and the stress window is reported as `NO_DATA`. It is covered by the spot × vol stress grid (ADR-0010). Apr-2025 is covered, because every weekday is present from Oct-2024.
- **Calendar spreads are limited out of sample.** DoltHub has only 3–4 expiries, at about 13, 29 and 51–56 DTE, so front/back pairs are coarse. Calendar results from 2024–26 carry less weight.
- **Early-close sessions (13:00 ET) still carry a 16:00 snapshot.** Their quotes are post-close, but we treat them as that session's close.
- **The closure-dated snapshots look like late re-snapshots, not copies.** Their `[UNDERLYING_LAST]` differs from the previous session's by cents: about 4 cents on 2022-07-04 against 07-01, and about 6 cents on 2022-01-17 against 01-14. At most 2.6% of their quotes match a neighbour's.
  - So the vendor's normal-day `[UNDERLYING_LAST]` may not be exactly the official close either.
  - The 0.10% `UNDERLYING_MISMATCH` tolerance, about $0.45, would hide a cents-level asynchronicity.
  - This was **unverified** at M0. **Updated in M1 (2026-10-29): measured.** The closure-dated snapshots carry the previous session's SPY close exactly (0 cents on all 12). On normal dates `[UNDERLYING_LAST]` is not exactly the close: the median gap is 3 cents, p95 is 12, p99 is 24, and the worst is 162 cents (2020-03-13). The gap is exactly 0 on 476 of 3,496 dates (477 of 3,497 before round 2 dropped the relabelled 2022-06-17 chain), and 37 dates fall beyond the 0.10% tolerance (`uv run python tools/report_m1.py`, block "UNDERLYING_LAST minus the SPY close").

## How we will test it

1. **Schema pin.** The loader asserts the exact 33 OptionsDX names and types listed above, and the 13 DoltHub columns. The test is run against a 20-row fixture copied from each source's schema, not against the real files.
2. **Calendar.** A fixture has a chain row on 2022-07-04 and a SPY calendar without 07-04. The row gets `NON_SESSION_DATE` and is dropped. A row on 2022-06-20 whose `UNDERLYING_LAST` equals the 06-17 SPY close (made-up values in the fixture), where 06-17 has no snapshot, was relabelled to 2022-06-17 with `RELABELLED`. **Updated in M1, round 2:** it is dropped too, 2022-06-17 stays without a snapshot, and the quality report's non-session check gives it 0 cents against the 06-17 close.
3. **Flags, one row each.** Each of these fixture rows must set exactly the stated bits:

   | Bid / ask | Bits |
   |---|---|
   | 0.00 / 0.05 | 2 |
   | 1.10 / 1.00 | 3 |
   | 2.00 / 2.00 | 4 |
   | 0.10 / 0.40 (relative spread 120%) | 5 |

4. **Stale.** A contract with an identical bid/ask on two consecutive sessions while S moves from 400 to 404 (+1%) gets `STALE`. The same contract when S moves to 401 (+0.25%) does not.
5. **OSI.** (SPY, 2024-03-15, C, 450.00) → `SPY   240315C00450000`. The inverse function parses it back.
6. **Read-only.** The DoltHub loader opens the clone with a read-only SQL session. A test asserts that the loader's SQL contains no `INSERT`, `UPDATE`, `DELETE`, `CALL DOLT_` or `COMMIT`. This is a guard on our own code, not on behaviour. The behavioural guard is that the M1 job runs `dolt status` before and after and asserts it is clean.
   - **Updated in M1 (2026-10-29):** the session runs in the private mirror, not the clone. Tests also check that a target or work folder resolving inside the shared clone (directly, through `..` or through a symlink) is refused before any process starts, and run a real dolt on a throwaway clone and its copy: the clone's listing (size, mtime, ctime) stays identical.
7. **DoltHub mask.** On Wed 2022-06-15 the masked OptionsDX chain holds exactly the (expiry, strike) pairs DoltHub lists that day that OptionsDX also has. On Tue 2022-06-14, which DoltHub lacks, the masked chain is empty: the engine marks with `STALE_SURFACE`, and option orders wait. Under `dolthub_daily`, 2022-06-14 keeps 06-13's pairs instead.

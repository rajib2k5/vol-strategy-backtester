# ADR-0002: Fill model and fill timing

> **Data notice.** The DoltHub figures in this document (counts, dates, quantiles and summaries, in its text and in its tables) are derived from the DoltHub database `post-no-preference/options` (<https://www.dolthub.com/repositories/post-no-preference/options>), licensed [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/), and are shared under the same licence. Changes: we aggregated it into counts, shares and quantiles, compared it with OptionsDX and ran our pricing build on it; no quote row is reproduced. The rest of this repository is MIT. See [DATA.md](../../DATA.md).

**Status:** Accepted at milestone 0. To be implemented in M3. To be revisited in M6, once the sweep over the fill price parameter *k* has been run.

## Revised after M0 review (2026-10-28)

The adversarial review (`docs/validation/00-design-research-ledger.md`, claims 1, 2, 5 and 11 and "Findings nobody asked about") refuted these points. Each was re-measured before this revision.

1. **The volume cap used the fill day's volume: look-ahead.** An order committed at *t* cannot know day *t+1*'s volume. Re-measured in round 2 on OptionsDX 2021–23, near-ATM 20–40 DTE contract-days, with contracts selected on the **order** date:
   - the 10-lot clip decision flips on 25.4% of contract-days when the fill-day volume replaces the order-day volume;
   - the fill-day rule clips 50.9% of 10-lots, against 51.9% with the order-day volume: the two are about equally strict, so the case against the fill-day volume is the look-ahead and the flip rate, not a bias in either direction;
   - the fill-day volume change correlates −0.062 with the fill day's |SPY return|.

   The round-1 figures (25.9% flips, 49.7% against 57.8%, correlation 0.183 with n = 62,098) came from selecting contracts on the **fill** day. They were a selection artefact; only the flip rate survives (25.4%, against 25.9%).

   **Changed:** the cap uses `V_t`, the contract's volume on the order date (§5), and the fill records that information date.
2. **"The hard cap should rarely bind" misled.** The *volume* cap binds, and how often depends on the expiry type: in 2021–23 the median near-ATM volume was 68 contracts a day for weeklies and 1,525 for monthlies. **Changed:** strategies trade standard monthly expiries by default (§5).
3. **Fill-price rounding failed in floating point.** For quote 2.00/2.10, `floor_to_tick(mid − h)` gives 1.99 for a k = 1 sell, and the k = 0 sell gives 2.04. Over 100,000 random penny quotes, the k = 1 buy missed the ask on 11.8% (the reviewer measured 12.2% on a different random draw). **Changed:** prices are computed in integer cents (§2).
4. **Test 6 rounded 6.175 to 6.18 without saying how.** Python's `round(1235*0.005, 2)` gives 6.17. **Changed:** costs use `Decimal` with `ROUND_HALF_UP` (§4).
5. **Data and citation errors.**
   - The 370 put's January range starts at 9,775, not 11,123.
   - The Section 31 fee on a $500 sale is $0.0139 (FY2024) and $0.0103 (FY2026), not "under $0.01".
   - Muravyev & Pearson compare effective spreads with "conventional measures" (Crossref abstract), not with the quoted spread.
   - SEC Rel. 34-105569 never names SPY. The trading-hours fact now cites Rel. 34-105153.
   - The OCC fee was $0.02 before 2025, and the TAF and ORF figures were wrong (§3).

Round 2 (`docs/validation/00-round2-ledger.md`, claim 7): the look-ahead argument stands, because `V_t` is reported in snapshot *t* and so is known when the order is created (the volume change correlates 0.292 with the same day's |return| and −0.017 with the next day's). The round-1 bias figures were a fill-day selection artefact and are replaced above and in the table, §5 and the consequences. "`V_t` is a little conservative (57.8% vs 49.7%)" is withdrawn, and so is "the hard cap can bind too" for wings (§5): at the defaults per-position vega allows 62 strangles and the stress budget 65–94.

## Context

Short-vol results depend on fills more than on almost anything else.
- **Bid/ask fills.** Paying bid/ask instead of mid cut monthly short-put returns by 4–6.9% in Santa-Clara & Saretto's data.
- **Effective spreads.** Muravyev & Pearson (2020) find that the effective spreads of traders who time their executions are under 40% of the size of conventional measures. The overall average effective spread is a quarter smaller than conventional estimates. So a mid fill is optimistic and a far-side fill is pessimistic.
- **Spreads widen in stress.** Both points are covered in `docs/concepts/00-background.md` §4.

**What we measured in the OptionsDX data (2026-10-28):**
- **ATM spreads.** For near-ATM calls (|K/S−1| < 1%) with 20–40 DTE, the median quoted spread is $0.02–0.08 depending on the year. That is 0.4–2.5% of mid.
- **Stress spreads.** In Mar-2020 the same median widened from $0.245 (9 Mar) to $0.61 (16 Mar). A fixed basis-point cost would miss that.

**Volume is unreliable before 2021 (measured):**
- **Under-counted.** The median daily total volume summed over the chain jumps from 366,024 contracts in Dec-2020 to 2,981,034 in Jan-2021, with no market event to explain it.
- **Missing.** `[C_VOLUME]` is null on 37.6% of all rows. It is null on 84–97% of near-ATM 20–40 DTE rows in 2010–2012.
- **Null on traded contracts.** The 2021-01-15 370 put shows null volume on every day from 15 to 31 Dec 2020. It then shows 9,775–58,087 contracts a day from 4 to 8 January.
- **The break is one step at the yearly-file boundary:** 371,587 contracts on 2020-12-31, then 3,417,626 on 2021-01-04.
- **Conclusion.** A null volume is "unknown", not "zero". Open interest is absent from both datasets.

**Volume depends on the expiry type (measured, OptionsDX 2021–23, near-ATM |K/S−1| < 1%, 20–40 DTE):**

| Expiry type | Median daily volume (IQR) | 10-lots clipped by a 10% cap on `V_t` |
|---|---|---|
| Standard monthly (third Friday) | 1,525 (712–2,967) | 3.8% |
| Weekly and other | 68 (17–209) | 58.4% |

The clip shares are round-2 figures (contracts selected on the order date; on the fill-day volume the weekly share is 57.2%). The medians, the IQRs and the wing figure below are round-1 numbers and were not re-measured.

For 5–10% OTM wings with the same DTE, a 10-lot on a monthly expiry is clipped on 31.5% of contract-days.

**The DoltHub `option_chain` table** has no volume, no sizes and no last price (schema in ADR-0009).

**Timing facts:**
- **OptionsDX snapshot time.** Every one of the 9,468,584 rows has `[QUOTE_TIME_HOURS]` = 16.0. `[QUOTE_UNIXTIME]` converts to 16:00 America/New_York on 3,507 of 3,508 dates; 2010-07-09 reads 16:00:01. Option quotes and `[UNDERLYING_LAST]` therefore share the 4:00 pm stamp, the SPY close.
- **Trading hours.** SPY options trade until 4:15 pm ET, including on their expiration day (SEC Rel. 34-105153, p. 10; Cboe Equity Options ETH FAQ, Q5). A trader could therefore compute a signal from the 4:00 snapshot and still trade, but not *at* the 4:00 quotes.
- **Tick size.** SPY options trade in $0.01 increments at every premium level (SEC Rel. 34-89075, Cboe Rule 5.4).

## Decision

### 1. Timing: a signal from day *t* fills at the day-*t+1* close

- **Same-snapshot rule.** Any order the strategy or risk layer creates after seeing snapshot *t* is executed against snapshot *t+1*. Snapshot *t+1* is the next session that has an option snapshot. On sessions without a snapshot the order waits.
- **Calendar-driven orders follow the same rule.** For example, a DTE-threshold exit is created at *t* when DTE at *t+1* ≤ `exit_dte`.
- **Hedges are the one exception.** They trade at the same close that produced the delta (ADR-0005).
- **Diagnostic mode.** `fill_timing = same_close` exists only as a diagnostic. It is stamped in `run.fill_timing`. The gap between the two modes is reported as the "same-snapshot premium".

### 2. Fill price as a fraction *k* of the day's own half-spread

The mid and half-spread come from the fill day's quote. The formula is defined, and must be implemented, in **integer cents**. With `b` and `a` the bid and ask in cents, and *k* an exact rational (0, 1/4, 1/2, 3/4 or 1):

```
buy_cents  = ceil ( (b + a + k·(a − b)) / 2 )
sell_cents = floor( (b + a − k·(a − b)) / 2 )
price      = cents / 100            (stored as fills.price_cents, an integer)
```

This is `mid ± k·h` rounded outward to the $0.01 tick. Do not compute it in floating-point dollars: `(2.00 + 2.10)/2 − (2.10 − 2.00)/2` is `1.9999999999999998`, so a floor gives 1.99.

- **Default `k = 1.0`:** fill at the far side.
- **Required sweep:** `k ∈ {0, 0.5, 1.0}`. The values 0.25 and 0.75 are optional.
- **`k = 0` is a known-optimistic bound,** labelled as such in every output.
- **Rounding:** buys round up and sells round down.

### 3. Fees per option contract, per side (open, close and liquidation)

- **All-in fee: `fee_per_contract = $0.70`.** This is a $0.65 broker commission plus about $0.04–0.06 of pass-through fees:
  - OCC clearing fee: $0.025 since 2025-01-01; $0.02 before.
  - FINRA TAF, on sales only: $0.00279 per contract in 2024–25 and $0.00329 in 2026, paused at $0 for Q4-2026.
  - Cboe ORF: $0.0023 per side on all customer-range trades until June 2026; from July 2026, $0.01248 per side on executions at Cboe only. Other exchanges charge their own.
  - Section 31 fee on a $500 option sale: $0.0040 (FY2023), $0.0139 (FY2024), $0 (FY2025), $0.0103 (FY2026).
- **Sweep:** {0.35, 0.70, 1.00}.
- **Exercise and assignment:** `assignment_fee_per_contract = $0` by default. Brokers differ, so this is a parameter.

### 4. SPY hedge shares

- **Commission:** `stock_commission_per_share = $0.005`, with a minimum of $1.00 per order.
- **Slippage:** `stock_half_spread = $0.005` per share (a $0.01 quoted spread). yfinance gives no SPY bid/ask, so this is a parameter rather than a measurement.
- **Rounding of costs.** Commission and slippage are computed exactly with `Decimal` and rounded to the cent with `ROUND_HALF_UP`. Binary floats and Python's `round()` are not used for money: `round(1235*0.005, 2)` gives 6.17.

### 5. Liquidity cap for each option line per day, and the expiry universe

**The cap uses only volume known when the order was created.** For an order created at *t* (after snapshot *t*) and filled at *t+1*:

```
V_t      = that contract's reported volume in snapshot t     (the order date; never the fill day's)
reliable = (source == optionsdx) and (t ≥ volume_reliable_from = 2021-01-04) and V_t not null
cap      = min(max_contracts_per_line, floor(participation_rate · V_t))   if cap_mode = volume and reliable
cap      = max_contracts_per_line                                       otherwise
```

- **The information date is stamped.** `V_t` and its date are recorded on the order leg (`order_legs.cap_volume`, `cap_volume_date`) and copied to the fill. `cap_volume_date < fill_date` always holds.
- **Why `V_t` rather than a trailing median.** A median of `V_{t−4..t}` lags a contract whose volume is rising as it nears the money. In round 1 it clipped more 10-lots than `V_t` (67.7% against 57.8%) and differed from the fill-day decision about as often (28.3% against 25.9%), so the lag bought nothing. Those figures used fill-day selection and were not re-measured in round 2, so the choice rests on the lag argument and not on them.
- **`cap_mode`.** `hard_only` is the rule of record in every split. `volume` is a capacity diagnostic, run on OptionsDX from 2021-01-04 only. ADR-0010 §1 explains why the rule of record must be the same in development, validation and holdout. The run records `cap_mode`.
- **Defaults:** `participation_rate = 0.10` (sweep {0.05, 0.10, 0.25}); `max_contracts_per_line = 100`.
- **Which cap binds.** At the default $1M capital and greek budgets (ADR-0006), a near-ATM position is about 7–12 straddles. That is far below the 100-contract hard cap, but not below the volume cap: on `V_t`, a 10% cap clips 51.9% of near-ATM 10-lots across all 2021–23 expiries, 58.4% on weeklies and 3.8% on monthlies. For OTM wings the budgets also stop short of the hard cap at the defaults: per-position vega allows 62 strangles and the stress budget 65–94 (ADR-0006, ADR-0007), so the 100-contract cap does not bind for them either. The analytics report the share of orders clipped by each cap.
- **Reduce-only orders** (closes, risk reductions, margin liquidations, sales of delivered shares) are never volume-capped. They use only `max_contracts_per_line`, so a proxy can never trap a position.
- **Era flag.** Every fill records `cap_type` (`volume` / `hard`) and `volume_reliable`.

**Expiry universe: standard monthly expiries by default.** Strategies open positions only in the standard monthly expiry: the third Friday of the month, or the session before it when that Friday is not a session (for example Thursday 2022-04-14, the day before Good Friday). Weeklies are allowed only in variants that are labelled as such.
- **Liquidity.** Near-ATM monthly volume is about 22× the weekly median, so the monthly cap clips 3.8% of 10-lots against 58.4% on weeklies.
- **One instrument set for the whole sample.** Monthlies exist from 2010 to 2026. The short-dated schedule kept changing: OptionsDX has a 0-DTE expiry on 38 dates in 2010, 166 in 2022 and all 250 in 2023 (ADR-0009). A weekly-based rule would therefore change its instruments partway through the sample.
- **Comparability.** The Cboe PUT index and the studies in the background doc use monthly options.
- **Cost.** Entry tenors are coarse: a 30-DTE target picks the monthly expiry nearest to 30 DTE, which lies anywhere from 14 to 46 DTE (computed over 2010–2026 weekdays). Out of sample, DoltHub rarely lists the monthly itself (8% of the expiries it lists are third Fridays), so those marks come from the surface (ADR-0004, ADR-0009).

### 6. Partial fills and multi-leg orders

- **No carry-over.** Unfilled quantity is cancelled at the end of the fill day and never carried forward. If the signal still holds, the strategy may re-issue the order the next day, which makes the information date of every order explicit.
- **Packages fill whole.** A package (straddle, strangle, calendar) fills in whole packages:
  - `package_fill = min over legs(floor(cap_leg / |ratio_leg|))`;
  - each leg fills at its own price from section 2.
- **No legging.** We never leave half a package open.

### 7. Quote states at fill time

The flags are defined in ADR-0009.

| Quote on the fill day | Opening order | Reduce-only order |
|---|---|---|
| Valid two-sided: `0 < bid ≤ ask` | Fill per section 2 if `bid ≥ open_min_bid = $0.05` and `(ask−bid)/mid ≤ open_max_rel_spread = 0.25`; otherwise reject (`ILLIQUID`) | Fill per section 2 |
| Locked: `bid = ask > 0` | Fill at that price (*h* = 0) | Fill at that price |
| Zero bid: `bid = 0 < ask` | Reject. We do not sell into a zero bid or open where there is no buyer. | **Buy:** fill at the ask whatever *k* is, because the mid is meaningless. **Sell:** no fill; the long is held and marked per ADR-0004. |
| Crossed (`bid > ask`), one-sided, missing or stale | No fill (`NO_QUOTE`) | **Surface fill:** `model_mid ± m·h_model`, where `h_model` is the median half-spread of valid quotes in the same expiry within ±0.05 log-moneyness. `m = surface_half_spread_mult = 1.0` (sweep 1.5). Recorded with `fill_source = surface`. |

**Surface execution mode.** In `execution_mode = surface`, the default for the DoltHub out-of-sample data (ADR-0009), opening orders also use surface fills. The reason: DoltHub re-centres about 17–27 strikes per expiry on a roughly 2.2% grid every day, and lists each expiry on only about half the sessions, so the contract chosen at *t* is usually absent at *t+1* (measured in ADR-0009).
- `model_mid` uses the surface steps of ADR-0004, including its extrapolation flags.
- If the contract's own expiry has no valid quotes within ±0.05 log-moneyness, `h_model` comes from the nearest listed expiry, and the fill carries the mark's surface flags.

## Alternatives considered

- **Fill at mid.** Rejected as the default. It overstates short-option returns by several percent a month. It survives only as the `k = 0` bound.
- **A fixed slippage in bp or ticks.** Rejected. It understates costs exactly when a short-vol book is losing (Mar-2020: the spread went from $0.245 to $0.61). It would win only if we had no quoted spreads at all.
- **Fill at the same close as the signal.** Rejected as the default. The signal and the fill would share the same quote noise: an ask that is spuriously high makes "IV is rich", and we would then sell at that same quote. That flatters returns. It would win if signals came from data observed *before* the fill time, for example a 15:45 snapshot with fills at 16:00. We do not have that data.
- **Fill at the *t+1* open.** Rejected: we have no option quotes at the open. Opening quotes are also the least reliable of the day (Aug-2024 pre-open VIX above 65 was mostly quote widening, §6 of the background doc).
- **Use reported volume in every era, treating null as 0.** Rejected. It blocks 84–97% of ATM trades in 2010–2012 because of a data artefact, not because liquidity was missing.
- **Rescale pre-2021 volume by the 2021 jump (~8×).** Rejected: that fabricates data.
- **Cap at displayed size (`[C_SIZE]`, for example "10 x 10").** Rejected as the main cap. Displayed size is a snapshot of the top of book, not daily liquidity, and DoltHub lacks it. We keep it in the clean table for diagnostics.
- **Carry unfilled quantity forward.** Rejected: it hides the date of the information behind an order.

## Consequences and biases

- **`k = 1` is conservative.** It understates net returns for every strategy that trades. The size of the gap is reported by the sweep.
- **The *t+1* rule is conservative.** It costs one day of signal decay. Stops gap through: a stop seen at *t* fills at *t+1*, which is realistic for EOD data and harsh in fast markets.
- **The rule of record is the hard cap in every split.** Capacity is therefore **optimistic** for illiquid lines throughout. The `cap_mode = volume` diagnostic over 2021–23 measures how much, and it is reported next to the validation result as a capacity haircut.
- **The volume cap is not shown to be conservative or optimistic.** `V_t` is known before the fill, so the cap carries no look-ahead. On near-ATM lines it clips 51.9% of 10-lots against 50.9% for the fill-day volume (order-date selection, round 2), too small a gap to call a direction. The round-1 claim that it was a little conservative (57.8% vs 49.7%) was a selection artefact.
- **No selling into a zero bid, and a minimum opening bid of $0.05.** This rules out "picking up nickels" in far wings. It is conservative for deep-OTM short strategies.
- **Surface fills are model-based.** Out-of-sample results are therefore a test of the signal plus the surface model, not of quote-level execution (ADR-0009 quantifies the gap on in-sample data).

## How we will test it

1. **Price for a quote of bid 2.00 / ask 2.10:**

   | *k* | Buy | Sell |
   |---|---|---|
   | 1 | 2.10 | 2.00 |
   | 0.5 | 2.08 (from 2.075) | 2.02 (from 2.025) |
   | 0 | 2.05 | 2.05 |
2. **Zero bid, quote 0.00 / 0.05.** A buy-to-close fills at 0.05 for every *k*. A sell-to-open is rejected with `ZERO_BID`.
3. **Crossed quote, 1.10 / 1.00.** An opening order is not filled (`NO_QUOTE`). A reduce-only order fills off the surface, with `fill_source = surface`.
4. **Volume cap uses the order date's volume** (`cap_mode = volume`, `p = 0.10`).
   - An order created on 2022-03-14, when the contract's volume is 850, fills on 2022-03-15. The cap is 85, so an order for 120 fills 85 and cancels 35. The fill records `cap_volume = 850` and `cap_volume_date = 2022-03-14`.
   - **Mutant check.** Changing the contract's 2022-03-15 volume to 50 or to 50,000 must not change the fill.
   - With an order-date volume of 5,000 the cap is min(500, 100) = 100.
   - On a 2015 date with null volume, the cap is 100 and `cap_type = hard`.
   - With `cap_mode = hard_only`, the 2022 order fills 100 whatever the volume.
5. **Package.** A straddle with a call-leg cap of 85 and a put-leg cap of 60 fills 60 calls and 60 puts. Fees are 120 × $0.70 = $84.00.
6. **Hedge cost.** Selling 1,235 SPY shares costs $6.18 commission plus $6.18 slippage. Each is 1,235 × 0.005 = 6.175 exactly in `Decimal`, rounded `ROUND_HALF_UP`; the commission is above the $1 minimum. An implementation that uses `round()` on floats gives 6.17 and must fail this test.
7. **Timing.** An order created from the 2023-03-14 snapshot fills against the 2023-03-15 quotes even when the 03-14 ask was lower. If the contract is absent on 03-15, the order is cancelled with `NO_QUOTE`. Switching to `same_close` changes `run.fill_timing`, and the ledger must show fills dated 03-14.
8. **Rounding at exact tick boundaries.**
   - For quote 2.00/2.10, the k = 1 sell is 2.00 (not 1.99), the k = 0 sell is 2.05 (not 2.04), and the k = 1 buy is 2.10.
   - Property test over random penny bids and asks, for each *k*: `price_cents` is an integer, a k = 1 buy equals the ask and a k = 1 sell equals the bid, and buy ≥ sell.
   - "At most 2 decimals" alone cannot detect the float bug, because 1.99 has 2 decimals.
9. **Expiry universe.** On 2022-04-01 a 14-DTE monthly target selects 2022-04-14, the Thursday before Good Friday, and never a weekly.

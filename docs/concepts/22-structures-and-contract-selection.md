# Structures and contract selection

> **Data notice.** The DoltHub figures in this document (counts, dates, quantiles and summaries, in its text and in its tables) are derived from the DoltHub database `post-no-preference/options` (<https://www.dolthub.com/repositories/post-no-preference/options>), licensed [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/), and are shared under the same licence. Changes: we aggregated it into counts, shares and quantiles, compared it with OptionsDX and ran our pricing build on it; no quote row is reproduced. The rest of this repository is MIT. See [DATA.md](../../DATA.md).

## First principles

A strategy that says "sell volatility" has not yet said what to sell. A **structure** is a fixed shape of option legs. A **pick** is the rule that turns a structure into listed contracts on one day: which expiry, which strikes. Two runs of one structure that pick differently are different strategies, and a pick that looks at data it should not have is a leak.

Terms:
- **Straddle**: a call and a put of one expiry and one strike. **Strangle**: a call above and a put below the spot, of one expiry. **Calendar**: legs of two expiries.
- **Package**: one set of legs, traded together. Ten packages of a straddle are 10 calls and 10 puts.
- **Standard monthly**: the expiry on the third Friday of a month (ADR-0002 §5). Weekly and end-of-month expiries are not used.
- **DTE**: calendar days from the session to the day the contract settles.
- **Listed**: a contract (or an expiry) that appears in the vendor's snapshot for that day.

## The maths

**The four structures** (plan section 5, `strategies/structures.py`):

| Structure | Legs per package | Entry window |
|---|---|---|
| `short_straddle`, `long_straddle` | call and put at the ATM strike, both short or both long | the standard monthly at 50-60 DTE |
| `short_strangle` | call and put nearest a spot delta of +0.25 and −0.25, both short | the same |
| `straddle_calendar` | short call and put of the front expiry, long call and put of the back expiry, at one strike | front monthly at 22-35 DTE; the back is the next calendar month's standard monthly |

**The picks.**
- **ATM strike**: of the strikes listed with both a call and a put, the one nearest the expiry's parity forward ([concept 03](03-put-call-parity-forward-and-spot.md)). A tie goes to the lower strike.
- **The strangle's strikes**: the call whose spot delta is nearest +0.25 and the put nearest −0.25. The delta is ADR-0005's, DF·(F/S)·N(d1), at the engine's own inputs (S the session's close, r the last DGS3MO dated before the session, F the parity forward, σ by the mark rule of ADR-0004). So the strangle is picked at the deltas it will be hedged at. A pick whose call strike is not above its put strike is no strangle.
- **The calendar's strike**: of the strikes both expiries list with a call and a put, the one nearest the front's forward.
- **The expiry**: the standard monthly found from the *listed* expiries and the session calendar: the third Friday if listed, else the Saturday after it (December 2015), else, only when the third Friday is not a session, the last session before it (Good Friday 2014-04-18, 2019-04-19, 2022-04-15). A weekly never stands in for a missing monthly.
- **One position per expiry, at most two open.** An expiry a run has already held is not opened again. Two open positions double the exposure until M5's risk rules.
- **Never beyond 180 days.** The engine's `check_intent` refuses an opening leg more than 180 days out (ADR-0008 amendment 8: the pricing build has one rate for every expiry, and past 180 days it carries a gap).

**Why 50-60 DTE.** The entry has to be a contract that every split can trade at the same DTE. On the DoltHub surface runs of 2020-22 and 2023, a standard monthly at 50-60 DTE is listed on every measured session (162 of 162 session-expiry pairs in 2020-22, 54 of 54 in 2023). At 36-49 DTE it is listed on 32.2% and 30.3%; at 29-35 DTE on 1.0% and 33.3% (`tools/measure_listing.py`, 2026-11-17). So a 45-DTE entry would trade different contracts in the holdout than in development. On OptionsDX development snapshots, 1,010 of 2,497 have a standard monthly at 50-60 DTE.

**Why the calendar is different.** At 29-35 DTE a standard monthly is listed on only 1.0% and 33.3% of the DoltHub sessions (same source as above), so the calendar's holdout trades are sparse. The calendar is in the grid by an owner default (plan section 12, decision 4, default taken 2026-11-09); the sparse holdout is stated, not hidden.

**Worked example on real data**, 2010-04-26, short straddle (development run `10d433dd…`, position 4). The listed expiries that day give three standard monthlies: 2010-05-21 at 25 DTE, 2010-06-18 at 53 and 2010-07-16 at 81. Only 06-18 is in the 50-60 window. Its parity forward is 120.84. The listed strikes near it are 119, 120, 121, 122 and 123, at distances 1.84, 0.84, 0.16, 1.16 and 2.16. The nearest is **121**. The legs are the 121 call `SPY   100618C00121000` and the 121 put `SPY   100618P00121000`, each with ratio −1, in 10 packages ([concept 04](04-osi-symbol.md) decodes the symbol).

## Assumptions

- **The parity forward is the ATM reference.** It comes from the pricing build ([concept 03](03-put-call-parity-forward-and-spot.md)).
- **The strangle's σ**: in quote mode a contract in the smile with a solved IV uses it; any other contract takes the surface IV at its log-moneyness. A contract with no finite σ is not a candidate.
- **Ten packages** (`FixedPackages(10)`, inside ADR-0002's 7 to 12 straddles) until M5's vega sizing. It is fixed, not tuned.
- **The exchange calendar is known.** The standard-monthly rule uses the session list ([concept 21](21-iv30-log-variance-ratio-and-calendar-time.md)).

## Where it breaks

- **A missing monthly.** If the monthly is not listed, there is no entry that month. The strategy never picks a later one in its place (the calendar's back leg is the next month's monthly or nothing).
- **Two expiries that settle on one day.** A listed non-session expiry settles on the session before (decision D16's map). The DTE counts to the settlement date.
- **A thin wing.** The strangle's 0.25-delta strikes can be far apart in a quiet market and close in a wild one, so the same rule trades different widths.
- **A long-dated position is mostly vega.** In theory its gamma and theta are small until the last weeks, so for weeks its value moves with implied vol. The exit rules ([concept 23](23-exits-on-a-hedged-book.md)) act on that path.

## In this project

- `src/volbt/strategies/structures.py:58` `atm_strike`, `:72` `atm_straddle`, `:82` `delta_strangle`, `:100` `straddle_calendar`, `:110` `Chain` (`:150` `deltas`, `:167` `sigmas`).
- `src/volbt/strategies/expiry.py:46` `standard_monthly`, `:93` `settle_date`, `:106` `dte`, `:112` `monthly_in_window`, `:130` `next_monthly`, `:38` `MAX_EXPIRY_DAYS`.
- `src/volbt/strategies/vol.py:130` `entry_order` (the windows are `ENTRY_DTE` and `FRONT_DTE` at `:38-39`), `:90` `decide`.
- `src/volbt/engine/loop.py:662` `check_intent` (the 180-day refusal).
- `tools/measure_listing.py` prints every listing figure above.
- `tests/test_strategy_picks.py`, `tests/test_strategy_expiry.py`, `tests/test_strategy_causal.py:118` (each structure opens its legs in its window and closes at 14 DTE).

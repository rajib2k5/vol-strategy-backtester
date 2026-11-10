# NAV_mid, NAV_liq and model marks

> **Data notice.** The DoltHub figures in this document (counts, dates, quantiles and summaries, in its text and in its tables) are derived from the DoltHub database `post-no-preference/options` (<https://www.dolthub.com/repositories/post-no-preference/options>), licensed [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/), and are shared under the same licence. Changes: we aggregated it into counts, shares and quantiles, compared it with OptionsDX and ran our pricing build on it; no quote row is reproduced. The rest of this repository is MIT. See [DATA.md](../../DATA.md).

## First principles

A **mark** is the value the book gives an open lot today. A day's quotes give a mark for most lots, but not all: a quote can be crossed, one-sided, stale or missing, and some sessions have no snapshot at all. The rule table says which price to use in each case and records which one it used, so a reader can tell a market price from a model price.

Two NAV series come out of the marks (ADR-0004):
- **NAV_mid** = cash + shares × S + Σ qty × 100 × mark. It drives returns and margin.
- **NAV_liq** values a long at the bid and a short at the ask. If a lot has no valid side, it uses the model price minus (long) or plus (short) `h_model`, the median half-spread nearby. NAV_mid − NAV_liq is the spread haircut.

Terms:
- **Model mark**: the CRR American price at the surface IV, N = 500 ([concept 10](10-crr-lattice-and-de-americanisation.md), [concept 11](11-smile-in-total-variance.md)).
- **`mark_source`**: `INTRINSIC`, `QUOTE_MID`, `ZERO_BID_MID`, `SURFACE_MODEL` or `STALE_SURFACE`.
- **DEGRADED**: a day on which more than 20% of the gross option value is model-marked.

The rule table (ADR-0004; `src/volbt/engine/marks.py:1-28`), the first rule that applies:

| # | Case | Mark | Source |
|---|---|---|---|
| 0 | the contract settled today | intrinsic value at S_set, kept out of NAV | `INTRINSIC` |
| 1 | 0 < bid ≤ ask, not stale, not crossed | (bid + ask)/2 | `QUOTE_MID` |
| 2 | bid = 0 < ask | ask/2 | `ZERO_BID_MID` |
| 3 | crossed, one-sided, stale or missing, on a session with a surface; **and every lot in surface mode** (decision D4) | the model price | `SURFACE_MODEL` |
| 4 | no snapshot today | the previous surface's IV at the same log-moneyness, priced at today's spot and forward | `STALE_SURFACE` |

## The maths

**Why American, and at every |k|.** The surface is European-equivalent: M2 took the early-exercise premium off every out-of-the-money quote. A Black-76 price at a surface IV would leave the premium out. ADR-0008 test 9: a put at S = K = 450, r = 5%, σ = 0.15, 30 days has the CRR price **6.9574** on N = 500, and Black-76 gives 6.8162. The engine uses the lattice at every |k| (decision D5), as M2 de-Americanised every quote with no |k| band (`tests/test_engine_marks.py:135`).

**Worked example**, ADR-0004 tests 1 and 2 (`tests/test_engine_marks.py:79` and `:88`):
- A quote 1.00 / 1.20 is marked at the mid 1.10. One long contract is worth +$110 in NAV_mid and +$100 in NAV_liq (at the bid). One short is worth −$110 and −$120 (at the ask).
- A put quoted 0.00 / 0.04 has a zero bid. It is marked at ask/2 = 0.02. A long is +$2.00 in NAV_mid and **$0** in NAV_liq, because nobody bids. A short is −$2.00 and **−$4.00**.

**Worked example**, rules 3 and 4, ADR-0004 tests 3 and 4 (`:105` and `:115`). A crossed put quote 1.10 / 1.00 at S = F = K = 400, surface IV 0.20, 30 days, r = 0, is marked at the lattice price **9.1440** (computed with `uv run python -c`, 2026-10-30; ADR-0004 gives the Black-76 value 9.1486, and the test accepts both within a cent). It is not marked at the crossed mid 1.05. The next day the quote is missing and S has fallen to 380. The mark rises to the lattice price at 380, 22.1667 (Black-76 gives 22.1672). It never keeps yesterday's mark.

**DEGRADED, in integers.** The share is of *gross* option value: the sum of |value| over the lots in NAV, so a long and a short of the same size do not net out. With $100,000 gross and $25,000 model-marked the share is 25% and the day is DEGRADED (ADR-0004 test 6, `:203`). The test is "above 20%", so exactly 20% is OK. In floats that fails: 0.2 as a float is 3602879701896397/18014398509481984, which is slightly above 1/5, so `0.2 > Fraction(1, 5)` is True and exactly 20% would read as DEGRADED (checked with `uv run python -c`, 2026-10-30). The engine compares model × 5 > gross, in the same units, with no division (`src/volbt/engine/marks.py:196`).

**Greeks.** They are our own Black-76 at the mark IV, never the vendor's. A quote in the smile uses its own IV. An in-the-money quote, or one not in the smile, uses the surface IV at its strike and carries the `GREEKS_OTM_IV` bit. A model mark uses the IV it was priced at.

## Assumptions

- **The surface is right.** A model mark is as good as the smile it reads. M2's calendar constraint moves some nodes, and stub quotes that are not WIDE still move a few (ADR-0004 amendment 5, an open owner question that the engine inherits).
- **A lot has one mark a day.** No mark is carried over from the day before (a mutant that did is killed by `test_a_missing_quote_moves_with_spot_and_is_never_the_previous_mark`).
- **`h_model` can be missing.** If no expiry has a valid quote within ±0.05 log-moneyness, NAV_liq of a model-marked lot uses h = 0 (decision B13). A surface fill with no `h_model` is cancelled `NO_QUOTE`.

## Where it breaks

- **In surface mode DEGRADED stops meaning "bad".** Decision D4 model-marks every lot, quoted or not, so that ADR-0009 §4's S run measures model-marking error alone. The 20% rule then flags nearly every day. The DoltHub surface run (2020-01-02 to 2023-12-29, 1,006 sessions; run `33dab70903f1...`) has **888 DEGRADED days**, and its marks are 0.5716 `SURFACE_MODEL` and 0.4284 `STALE_SURFACE`, with no quote mark at all (`tools/report_m3.py`, 2026-11-09; 855 days, 0.5757 and 0.4243 in the run before the round-2 fix to the expiry picker).
- **On OptionsDX the flag is rare.** The development run (2010-2019) has 61 DEGRADED days of 2,516, and its marks are 0.9762 `QUOTE_MID`, 0.0163 `SURFACE_MODEL` and 0.0075 `STALE_SURFACE`.
- **MARK_JUMP is a warning, not a filter.** A mark that moves more than 50% in a day while spot and ATM vol barely move is flagged and still used: 73 marks of the development run.

## In this project

- `src/volbt/engine/marks.py:73` `mark_lots` (rules 1 to 4 and the greeks), `:165` `intrinsic_row` (rule 0), `:177` `nav`, `:183` `model_share`, `:192` `mark_quality`.
- `src/volbt/engine/surface.py:98` `forward`, `:110` `iv`: the surface the marks read, with the `FORWARD_CARRY` bit when the forward is a carry forward. The mark-flag bits are at `:33-37`.
- `src/volbt/engine/loop.py:478` `step_05_mark`, `:530` `step_07_snapshot` (the NAVs and the `daily_pnl` row).
- `tests/test_engine_marks.py`: ADR-0004 tests 1 to 4, 6 to 8 and 11, and ADR-0008 test 9.

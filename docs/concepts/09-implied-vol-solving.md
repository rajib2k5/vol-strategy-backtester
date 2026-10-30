# Solving for implied volatility

> **Data notice.** The DoltHub figures in this document (counts, dates, quantiles and summaries, in its text and in its tables) are derived from the DoltHub database `post-no-preference/options` (<https://www.dolthub.com/repositories/post-no-preference/options>), licensed [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/), and are shared under the same licence. Changes: we aggregated it into counts, shares and quantiles, compared it with OptionsDX and ran our pricing build on it; no quote row is reproduced. The rest of this repository is MIT. See [DATA.md](../../DATA.md).

## First principles

The **implied volatility** (IV) of a quote is the σ at which Black-76 returns the quote's price. It turns a dollar price into a number that can be compared across strikes, expiries and days: a 0.40 put and a 12.00 call are hard to compare, 0.21 and 0.18 vol are not.

Terms:
- **Mid**: (bid + ask)/2, the price we solve from. The build solves only out-of-the-money (OTM) quotes, puts with K < F and calls with K ≥ F, after taking their early-exercise premium off (ADR-0008 §7; [concept 10](10-crr-lattice-and-de-americanisation.md)).
- **Root**: the σ where model price minus market price is zero.
- **Vega**: ∂price/∂σ, the slope of the price in σ ([concept 08](08-greeks-and-their-usd-units.md)).

**Why a root always exists, and only one.** The Black-76 price rises strictly with σ: from the discounted intrinsic value as σ → 0 to the upper bound as σ → ∞ ([concept 07](07-black-76-on-the-forward.md)). So a price strictly between the bounds has exactly one σ, and a price on or outside them has none. That is the whole design: check the bounds, then search a monotone function.

## The maths

Four stages, for a whole chain at once (ADR-0008 §7, with the M2 review's amendment 5):

1. **Bounds.** A call needs DF·max(F−K, 0) < C < DF·F, a put DF·max(K−F, 0) < P < DF·K. Outside: no IV, flagged `IV_FAIL`, with reason `below_lower_bound` or `above_upper_bound`. Inside the bounds but outside what σ ∈ [1e-4, 5] can produce: reason `no_root`. Never an exception, never a clipped 5.0 (ADR-0008 test 4).
2. **The OTM side.** By parity an in-the-money price is its lower bound plus the out-of-the-money price at the same strike (a call C = DF·(F − K) + P). So the solver always searches on that OTM price, the **time value** (price − lower bound). Black-76 computes a small OTM price to many significant digits; an ITM price minus its bound keeps only the digits the two share, so the time value carries the rounding of the ITM price (a few epsilons of its Black-76 terms) and of its bound, and the check of step 4 counts it. ~~A time value at or below 1e-9 of the price cannot be resolved in float64.~~ (M2 round 2, code claim 4: that fixed cut called ITM prices `unresolved` whose σ float64 pins, and let others through solved only to 2e-7.)
3. **Newton-Raphson**: σ ← σ − (B(σ) − target)/vega(σ), from the **Brenner-Subrahmanyam** guess σ₀ = √(2π/τ)·V/(DF·F), clipped to [0.01, 3]. That guess comes from expanding the at-the-money price, C ≈ DF·F·σ√τ/√(2π), and inverting it. It stops when the price matches to 1e-10 **of itself** and the next step, |B − target|/vega, is below 1e-10 **of σ**, or after 50 steps.
4. **Bisection** on [1e-4, 5] wherever Newton cannot be trusted: a step that leaves the bracket, a vega below 1e-8, or no convergence in 50 steps. Halve the bracket on the side where the model price is too high until it is narrower than 1e-10 of σ; because B is increasing, this always converges. Then one check, for every answer from either solver: float64's rounding of the price (a few epsilons of Black-76's two terms, plus a few of the smallest normal float, plus for an ITM price the rounding its time value inherits), divided by vega, must pin σ to 1e-6 of itself. An answer that fails it is `unresolved`, never a number: an underflowed price, one on a flat stretch near the upper bound, or an ITM time value that rounding can hide.

**Where 1e-10 holds.** Newton's step and bisection's bracket stop at 1e-10 of σ, so σ is within 1e-10 of itself of the true σ wherever float64's rounding of the price, over vega, is below 1e-10 of σ: every one of 200,000 random OTM prices (σ 0.01-4, τ 1 day to 3 years) came back within 9.99e-11. Elsewhere the price itself pins σ only to its rounding over vega, which the check keeps below 1e-6: near the upper bound (20,000 OTM calls of 1-30 years at σ 0.5-2.4: up to 4.6e-8) and for every ITM price (200,000 random ITM prices: up to 4.6e-8) (`uv run python tools/report_m2.py`, block "IV solver accuracy"). The build solves OTM prices only.

**Why the tolerances are relative.** The first version stopped when |B − price| < 1e-8 dollars. For any price below 1e-8 that is true at every σ, so the solver returned its clipped starting guess, 0.01, after 0 steps: K = 500, F = 442, σ 0.12, 7 days (a price of 6e-14) came back as 0.01 (M2 review, code claim 2). Measured now (`tests/test_iv.py`): that case returns 0.12 to 1e-6, at 7, 10 and 14 days; an ITM call one float step above its lower bound (root 0.0233) is `unresolved` instead of 0.0319; and a 30-year call at σ 3, within 1e-14 of its upper bound, is `unresolved` instead of 2.43, because there the price barely moves with σ and a price match says nothing about σ.

**Worked examples** (computed with `uv run python -c` against `src/volbt/pricing/iv.py`, 2026-10-29):

- ADR-0008 test 3: the ATM call at 9.148603 (F = K = 400, τ = 30/365, r = 0). The guess is √(2π/0.082192) × 9.148603/400 = 0.199973, already within 3e-5 of the answer; one Newton step gives **0.20000001**, solver `newton`.
- ADR-0008 test 4: a call priced at DF·F + 0.01 = 398.3595 + 0.01 (F = 400, K = 380, r = 5%). It is above the upper bound: IV NaN, reason `above_upper_bound`, no solver run.
- A far OTM put (F = 400, K = 200, σ = 1.8, 30 days, price 5.9187): the guess is 0.129, where the put is worth almost nothing and vega is about zero, so the first Newton step jumps outside [1e-4, 5]. Bisection finds **1.8** (`tests/test_iv.py::test_bisection_takes_over_when_newton_leaves_the_bracket`).

**Measured on real quotes.** Over the full build, Newton finished 2,658,161 of OptionsDX's 9,111,523 OTM solves and bisection 6,453,362 (70.8%); on DoltHub 19,388 and 67,890 (77.8%) (`uv run python tools/report_m2.py` on the forced pricing build of 2026-10-29, `uv run python tools/build_pricing.py --workers 10 --force`, block "IV solve"). Most OTM quotes go to bisection because the Brenner-Subrahmanyam guess is an at-the-money approximation: for an OTM option it is far too low, where vega is tiny, so the Newton step leaves the bracket. The answers are the same either way; bisection only costs more iterations. No real quote was `unresolved` and none failed the Black-76 bounds: all 2,172 OptionsDX and 7 DoltHub `IV_FAIL`s have no American IV on the de-Americanisation lattice (same block; [concept 10](10-crr-lattice-and-de-americanisation.md)).

## Assumptions

- **The price is European.** The mid has had its early-exercise premium removed first; solving an American mid on a European model would bias the IV up.
- **The forward is right.** Every IV is relative to *F*. An *F* that is too low makes OTM calls look expensive and OTM puts cheap.
- **Relative tolerances are tight enough.** A converged Newton answer reprices to 1e-10 of the price and stops within 1e-10 of σ by its own step; where the price pins σ that well, that is the accuracy (above). The property test recovers σ to 1e-8 on every one of 5,000 random cases whose price float64 can hold, however small, and to 1e-6 on 20,000 near the upper bound (`tests/test_iv.py`).

## Where it breaks

- **Prices float64 cannot hold.** A deep OTM, short-dated, low-vol price can be exactly 0.0 in floating point, which is on the lower bound, or a few float steps above it: no IV (`below_lower_bound` or `unresolved`).
- **Flat prices.** Where vega is tiny, a cent of price error is many vol points. Deep OTM quotes at $0.005 (a zero bid, ask $0.01) have IVs that mean little; they are not in the smile (`in_smile`, [concept 11](11-smile-in-total-variance.md)).
- **σ above 5.** A quote whose IV would exceed 500% has no IV. Over the full build, 2,146 OptionsDX quotes had a mid above the lattice's American price at σ = 5 (`american_above_cap`, block "IV solve"); the ones inspected were one-day puts at log-moneyness near −1 with a $0.005 mid.

## In this project

- `src/volbt/pricing/iv.py:99` `brenner_subrahmanyam`; `:106` `implied_vol`, with the bounds and the OTM side first, then Newton and bisection; `:85` `price_rounding`, the float64 resolution check (for an ITM price also the rounding its time value inherits).
- `src/volbt/pricing/iv.py:64-83`: the tolerances, and the solver and fail codes stored in `quote_iv.solver` and `quote_iv.iv_fail_reason` (the seven `american_*` codes are the American IV solve's, in `deam.py`).
- `src/volbt/pricing/chain.py:210`: every OTM quote's IV is solved from its European-equivalent mid (`iv`), and, to measure the correction only, from the raw mid (`iv_raw`).
- `tests/test_iv.py`: ADR-0008 tests 3 and 4, the review's cases, and the property tests.

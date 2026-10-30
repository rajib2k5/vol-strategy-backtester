# Greeks, and the USD units they are budgeted in

## First principles

A **greek** is the sensitivity of an option's value to one input, all the others held fixed. A book of options is risky through these sensitivities, so risk limits are set on them (ADR-0006).

Terms (*V* is the option's value per share, *S* the SPY spot, *F* the forward, σ the implied vol, τ the time to expiry in years):
- **Delta**, ∂V/∂S: how much the value moves per $1 of spot.
- **Gamma**, ∂²V/∂S²: how fast delta itself moves. A short-gamma book loses on big moves either way.
- **Vega**, ∂V/∂σ: the value per unit of vol (1.00 = 100 vol points).
- **Theta**, ∂V/∂t: the value per year of calendar time passing, with everything else fixed. Time passing shortens τ, so ∂V/∂t = −∂V/∂τ.

**What "everything else fixed" means here.** Black-76 prices on *F*, not on *S* ([concept 07](07-black-76-on-the-forward.md)). Two choices follow, both from ADR-0008 §1:
- the **spot** greeks hold *F/S* fixed: when *S* moves 1%, *F* moves 1%. That gives the spot delta DF·(F/S)·N(d₁);
- **theta** holds *F*, *K*, σ and *r* fixed and lets τ shrink. That is not the same as holding the spot fixed: with *S* fixed, *F* = *S*·e^(r·τ) falls as τ shrinks, which adds −DF·N(d₁)·r·*F* per year to a call's theta. For one long ATM call (S = K = 400, σ 0.20, 30 days, r 5%) `theta_1d_usd` is −$15.04 with *F* fixed and −$18.00 with *S* fixed; a one-day step with *S* fixed gives −$18.12 (`uv run python tools/report_m2.py`, block "theta: F held fixed against S held fixed"). The $2.96 a day is real P&L that a theta-plus-delta attribution with *F* fixed leaves in ADR-0005's residual, so M6 must attribute it (the carry of the forward), not report it as unexplained.

**Why USD units.** "Vega 2,500" means nothing until its unit is fixed. Vendors disagree: OptionsDX's vega is per vol point and its theta does not reconcile at all (ADR-0004, Context). ADR-0006 therefore budgets portfolio-level dollar amounts that include the 100-share multiplier and the signed quantity *q* (positive = long).

## The maths

Per share, with *DF* = e^(−rτ) and *n* the normal density (`src/volbt/pricing/black76.py`, module docstring):

- delta: DF·(F/S)·N(d₁) for a call, −DF·(F/S)·N(−d₁) for a put
- gamma: DF·F·n(d₁) / (S²·σ·√τ), the same for calls and puts
- vega: DF·F·n(d₁)·√τ, the same for calls and puts
- theta: r·V − DF·F·n(d₁)·σ / (2√τ), per year

ADR-0006's units, for *q* contracts:

| Name | Formula | Meaning |
|---|---|---|
| `delta_usd` | q·100·delta·S | P&L for a +100% move in S, to first order |
| `gamma_1pct_usd` | q·100·gamma·S²·0.01 | change in `delta_usd` for a +1% move |
| `vega_1vol_usd` | q·100·vega·0.01 | P&L when every IV rises by 1 vol point |
| `theta_1d_usd` | q·100·theta/365 | P&L from one calendar day passing |

A move of *m* (as a fraction) earns or loses about 50·`gamma_1pct_usd`·m².

**Worked example**, ADR-0006 test 1 (computed with `uv run python -c` against `src/volbt/pricing/black76.py`, 2026-10-29): one long call, S = F = K = 400, σ = 0.20, τ = 30/365, r = 0. Then d₁ = 0.0286691 and n(d₁) = 0.398778.

- delta = N(0.0286691) = 0.5114358, so `delta_usd` = 100 × 0.5114358 × 400 = **$20,457.43**
- gamma = 0.398778 / (400 × 0.0573382) = 0.0173871, so `gamma_1pct_usd` = 100 × 0.0173871 × 400² × 0.01 = **$2,781.94**
- vega = 400 × 0.398778 × 0.286691 = 45.7305, so `vega_1vol_usd` = **$45.73**
- theta = −400 × 0.398778 × 0.20 / (2 × 0.286691) = −55.6388 per year, so `theta_1d_usd` = **−$15.24**

ADR-0006 prints $20,457.44 for the first one. The exact value is 20,457.4301, so the ADR's last digit is a rounding slip; `tests/test_black76.py` pins 20,457.43 and says why. The other three agree with the ADR to the cent, and a straddle doubles gamma, vega and theta to $5,563.88, $91.46 and −$30.49.

The same test file checks every analytic greek against a central finite difference of the price on 2,000 random cases (delta and gamma bumping *S* with *F/S* fixed, vega bumping σ, theta bumping τ).

## Assumptions

- **Black-76 at the mark's IV.** The greeks come from our own model at the IV the mark uses (ADR-0004), never from the vendor.
- **F moves with S in proportion.** True for a continuous yield. With discrete dividends ∂F/∂S is 1/DF rather than F/S; the two differ by the dividend's share of the price, a fraction of a percent of delta.
- **Parallel vol moves.** `vega_1vol_usd` raises every expiry by the same 1 point. Calendars, which are long one expiry and short another, hide their real risk in that assumption (ADR-0006, Consequences).

## Where it breaks

- **Near-ATM American puts at high rates.** The greeks stay Black-76 even where the mark is the American lattice price (ADR-0008 §8), so they are an approximation exactly where the early-exercise premium is largest.
- **Close to expiry.** Gamma grows like 1/√τ at the money; a one-day-old gamma is a poor guide to tomorrow's.
- **Big moves.** Delta and gamma are a second-order Taylor expansion. A −20% shock needs full revaluation, which is why ADR-0006 adds a stress-loss budget beside the greek budgets.

## In this project

- `src/volbt/pricing/black76.py:97` `greeks`: the per-share greeks.
- `src/volbt/pricing/black76.py:118` `greeks_usd`: ADR-0006's units, `CONTRACT_MULTIPLIER`, `ONE_PERCENT`, `ONE_VOL_POINT` and `DAYS_PER_YEAR` at `:41-44`.
- `tests/test_black76.py`: ADR-0006 test 1, the straddle, the finite differences.
- Budgets and sizing on these units are milestone 5 (ADR-0006).

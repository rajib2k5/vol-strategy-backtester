# The smile in total variance, and the surface built from it

> **Data notice.** The DoltHub figures in this document (counts, dates, quantiles and summaries, in its text and in its tables) are derived from the DoltHub database `post-no-preference/options` (<https://www.dolthub.com/repositories/post-no-preference/options>), licensed [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/), and are shared under the same licence. Changes: we aggregated it into counts, shares and quantiles, compared it with OptionsDX and ran our pricing build on it; no quote row is reproduced. The rest of this repository is MIT. See [DATA.md](../../DATA.md).

## First principles

For one expiry, the implied vols of different strikes are not equal: SPY puts below the money trade at higher IVs than calls above it. Plotted against the strike, the IVs form the **smile** (for SPY, a skew). Put the smiles of all expiries side by side and you have the **surface**. The engine needs an IV for any contract on any day, including strikes and expiries nobody quoted (ADR-0004, rules 3 and 4), so it reads them off the surface.

Terms:
- **Log-moneyness** k = ln(K/F): where a strike sits against the forward. k < 0 is below the forward (OTM puts), k > 0 above (OTM calls).
- **Total variance** w = σ²·τ: the variance of ln(S_T/F) to expiry, the quantity Black-76 actually uses ([concept 07](07-black-76-on-the-forward.md)).
- **Node**: one valid out-of-the-money quote's (k, w), after its early-exercise premium is removed ([concept 10](10-crr-lattice-and-de-americanisation.md)). `quote_iv.in_smile` is true exactly for the quotes that are nodes; a zero-bid, `STALE` or (since round 3) `WIDE` quote may have a descriptive IV but is not one.

**Why w and not σ.** The no-arbitrage rules are simple in w. At a fixed k, w must not fall as τ grows (a longer option cannot be worth less than a shorter one with the same moneyness): no calendar arbitrage. In the far wings, w can grow at most like 2|k| (Roger Lee's 2004 moment formula). And linear interpolation in w across expiries is interpolation of variance, which adds up over time; linear interpolation in σ is not.

**The smile model** is the one ADR-0004 names: piecewise-linear total variance through the nodes. It is exact at every quoted strike and needs no optimiser, so it cannot fail to converge on a thin DoltHub smile of about 20 nodes; an SVI or SSVI fit is deferred (ADR-0004, Alternatives).

## The maths

Reading an IV at (k, τ); each step that is not a plain interpolation sets a flag (`position_marks.mark_flags`, ADR-0004):

2. **Own expiry, inside its nodes**: w linear in k between the two neighbouring nodes.
3. **Beyond the last node** (`SURFACE_EXTRAP_STRIKE`): w extended linearly with the slope of the two outermost nodes on that side, clipped to [0, 2] per unit of |k|. Never falling away from the money, never steeper than Lee's bound, never held flat.
4. **Own expiry absent or thin, an expiry on each side** (`SURFACE_CROSS_EXPIRY`): w linear in τ at fixed k between the two nearest, each read by steps 2-3. An expiry needs at least 5 nodes to count.
5. **No expiry on one side** (`SURFACE_EXTRAP_TENOR`): the IV held constant along k/√τ from the nearest expiry, σ(τ, k) = σ_near(k·√(τ_near/τ)). The smile steepens like 1/√τ, so reading the near smile at the same k would understate short-dated wings.
6. **The calendar constraint** (`SURFACE_CALENDAR_ADJUSTED`, ADR-0004 amendment 2 as revised in round 2). The market's own smiles cross: at some k a longer expiry's w is below a shorter one's, and steps 4 and 5 carried that into the surface (the first export had 17, 18, 2 and 10 grid cells where w fell from one tenor to the next; M2 review, code claim 7, round-1 measurement). So, at each k, an expiry's w(k) is **anchored** where k lies inside that expiry's own nodes and **extrapolated** where it lies beyond them; anchored values take the running maximum of the anchored values before them in τ order (a quote below a shorter expiry's quote is raised to it); each extrapolated value is held between the anchored values before and after it (so a short expiry's wing can be lowered, and can never lift a longer expiry's quote); a final running maximum orders what is left, which cannot move an anchor. Step 4 interpolates between those values; step 5's w along k/√τ is replaced by its running maximum from the back expiry onward (never below the back expiry's value) or its running minimum up to the front expiry (never above the front's). Step 5's w is piecewise-rational in τ, so those extrema are found exactly, at the segment ends and stationary points. A cell whose value this moves, up or down, carries the bit. The first version took the running maximum over every expiry's w, extrapolated wings included: it moved 5.82% of OptionsDX's nodes on 250 random dates, 78.2% of them off a shorter expiry's extrapolated wing, up to 72.76 vol points (2020-02-28; the round-2 reviewer's measurement). Now it moves 1.27%, every one by a shorter expiry's quote, at most 7.51 vol points (`uv run python tools/report_m2.py`, block "the calendar constraint at the smiles' own nodes"; 1.56% and up to 41.98 points while WIDE stub quotes were nodes, before round 3). On the four exported dates it moves 67, 80, 28 and 24 of 286 cells (the round-1 floor moved 66, 97, 28 and 24), and no cell's w falls with tenor (block "the surface frames"; `tests/test_smile.py` checks 40 random surfaces at 220 tenors for the fall, and 150 more for where the bit is set).

**Worked examples** (ADR-0004's tests, as `tests/test_smile.py` pins them, 2026-10-29):

- **Test 5, interpolation.** Nodes 0.22 at k = −0.05 and 0.18 at k = 0, τ = 0.1. At k = −0.025, w = ½(0.22² + 0.18²) × 0.1 = 0.004040, so σ = √(0.004040/0.1) = **0.2010**. Linear in σ would give 0.2000.
- **Test 9, the wing.** Nodes 0.22 at −0.10 and 0.20 at −0.05, τ = 0.1: w = 0.00484 and 0.00400. The slope in |k| is (0.00484 − 0.00400)/0.05 = 0.0168, inside [0, 2]. At −0.15, w = 0.00484 + 0.0168 × 0.05 = 0.00568 and σ = **0.2383**. A flat rule would give 0.22, which under-marks the wing.
- **Test 10, below the front expiry.** One expiry at 14 days with the nodes of test 5. A 7-day contract at k = −0.025 reads the smile at k′ = −0.025 × √2 = −0.03536: σ = **0.2091**. At the same k it would read 0.2010.

**How good is an exact interpolant?** It is exact at its nodes, so its error there says nothing. The honest measure is **leave-one-out**: drop each interior node, read it back from its two neighbours, and compare with the quoted IV. Measured in vol points (`uv run python tools/report_m2.py` on the round-3 forced pricing build of 2026-10-29, `uv run python tools/build_pricing.py --workers 10 --force`, block "smiles and leave-one-out interpolation error"):

| Source, tenor | Nodes per smile (median) | Median | p90 |
|---|---|---|---|
| OptionsDX, 0-60 days | 69 | 0.052 | 0.43 |
| OptionsDX, all | 69 to 100 by tenor | 0.031 | 0.28 |
| DoltHub, 0-60 days | 22 | 0.152 | 0.48 |
| DoltHub, all | 22 to 25 | 0.147 | 0.47 |

DoltHub's strikes are about 2.2% of spot apart against OptionsDX's dollar strikes, and its leave-one-out error is about three times larger within 60 days and five times over all tenors. Leave-one-out overstates the error a DoltHub model mark carries, though: it reads a node from neighbours twice as far apart as the grid itself. Read at the strikes OptionsDX quoted and DoltHub did not, inside DoltHub's nodes, on the same dates and expiries (2020-2023, 0-60 days), DoltHub's smile misses OptionsDX's IV by a median **0.098** and a p90 of **0.392** vol points (block "DoltHub's smile read at OptionsDX-only strikes"): that is the in-grid error of a DoltHub mark, before any cross-expiry or tenor step. (The DoltHub figures are derived from DoltHub's CC BY-SA 4.0 data; see [DATA.md](../../DATA.md).)

## Assumptions

- **The nodes are the valid quotes, not clean ones.** Valid OTM quotes only: a two-sided mid with a bid above zero, not stale, not crossed (ADR-0004 rule 1), not `WIDE` (ask − bid ≤ mid; round 3, decision F2: stub quotes with a $0.03 bid and a $4.84 ask were nodes at IV 0.80-0.87 between neighbours at 0.33-0.38), with an IV that solved. Valid is not clean (M2 round 2, design claim 9, which refuted "the nodes are clean"): a node can sit below a shorter expiry's quote at its k (the calendar constraint raises it, step 6), carry its quote's noise into a kink, and carry butterfly arbitrage.
- **The forward is right.** Each node's k uses its expiry's de-Americanised parity forward; a wrong F shifts every k of that smile.
- **Linear is good enough between nodes.** True for dense chains; on DoltHub the nodes are far enough apart that curvature between them shows up as the error above.
- **Only calendar arbitrage is removed.** The nodes are taken as quoted. The calendar constraint (step 6) stops w falling with τ at a fixed k. Butterfly arbitrage is not removed, and ~~linear interpolation adds none of its own inside the nodes~~ is wrong (M2 round 2, design claim 9): linear interpolation in w can CREATE it between quotes that have none. Four quotes at 7 days, F = 100, IVs 1.00, 0.45, 0.15 and 0.14 at k = −0.30, −0.10, 0, 0.05, have convex call prices at the quoted strikes (slope increments +0.068 and +0.766), yet the interpolated calls have a negative density at 1,092 of 3,499 grid points between k = −0.209 and −0.100 (the round-2 reviewer's `q7_butterfly.py`, re-run on 2026-10-29). M2 does not test the built smiles for it.

## Where it breaks

- **Thin smiles.** Fewer than 5 nodes: the expiry is flagged `SMILE_THIN` and the surface steps over it to its neighbours.
- **Far wings.** The clipped linear extension is a rule, not data. ADR-0004 measured it at a median 1.2 vol points on DoltHub-like grids; better than flat (7.0), still far worse than in-grid.
- **Below DoltHub's front expiry.** Nothing under 10 days is listed, so every 7-day mark is a tenor extrapolation, with a median error of 1.21 vol points (ADR-0004, table). No rule can recover a term structure nobody quoted.
- **Noisy nodes.** One bad quote becomes a kink: piecewise-linear has no smoothing.

## In this project

- `src/volbt/pricing/smile.py:73` `smile_nodes`, `:81` `wing_slope` (the [0, 2] clip), `:86` `smile_variance` (steps 2-3), `:101` `smile_iv`, `:152` `calendar_variance` (step 6 at and between expiries), `:196` `surface_iv` (steps 2-6), `:129` `_envelope` (step 5's running extremum).
- `src/volbt/pricing/chain.py:275`: each expiry's smile from its `in_smile` quotes (valid, not WIDE, OTM, with an IV); stored in `smile_fits` (`k_nodes`, `total_var_nodes`, `atm_iv`, `fit_flags`).
- `src/volbt/build.py:619-620` the fixed grid of `surface_frames.json`, `:634` `surface_frame` (every cell read with `surface_iv`, rounded so that w still never falls, refused if rounding cannot mend it, `atm_iv_30d` copied from its cell), and the leave-one-out query in `SUMMARY_SQL`.

# PR/FAQ: Vol Strategy Backtester

> **Status: working-backwards draft, milestone 0 (written 2026-10-27/28).** No strategy has been run
> yet. The press release describes what the finished project must be able to show. Every *result*
> in it is a placeholder in `[brackets]` until the final milestone replaces it with a measured,
> re-checked value.
>
> Three kinds of number appear below, labelled where they occur:
> - **measured** data facts, taken from the local data copy on 2026-10-28;
> - **design** parameters chosen in the ADRs, which may be recalibrated at the milestone named there;
> - **placeholders** in brackets.
>
> Educational project — not financial advice.
>
> *How this was written:* drafted from the approved project plan and ADRs 0001–0010, then
> reader-tested by a fresh model with no other context, and revised. The author's curation questions
> are at the end.

---

## Press release

### Vol Strategy Backtester shows how much of the volatility risk premium survives real trading costs

*An open-source backtester for SPY straddles, strangles and calendar spreads. On 2010–2023 quotes
it fills every trade at bid/ask, at most 100 contracts per option a day. It enforces gamma, vega,
theta and stress-loss budgets, and reports every strategy through the 2018–2025 volatility shocks.*

**[Launch date, after milestone 6]** — Today we are releasing Vol Strategy Backtester, a public
Python engine and React app. It answers one question: after realistic costs, did selling (or buying)
SPY option volatility earn more than Treasury bills? "Earn more" means a positive return in excess
of T-bills after all fills, fees and hedging, with a deflated Sharpe ratio reported alongside it. A
"no" is a result worth publishing too.

The engine replays fourteen years of end-of-day SPY option quotes (2010–2023). It tunes on
2010–2019 and checks on 2020–2023. It then runs the frozen strategies once over 2024–2026, using a
thinner free dataset where trades are priced from a fitted volatility surface instead of quotes.

**The problem.** Implied volatility on index options is usually higher than the volatility that
follows: the *volatility risk premium* (see `docs/concepts/00-background.md`). Selling options to
collect it can look excellent in a backtest that:
- fills at the mid-price;
- ignores how many contracts actually traded;
- divides P&L by whatever capital base flatters it;
- leaves out the weeks when short volatility loses years of gains.

A student or small researcher cannot tell which part of such a result is the premium and which part
the assumptions made.

**The solution.** An event-driven engine steps through each trading day at the 4 pm close. Each day
it:
1. fills the orders created at the previous snapshot, at today's closing quotes. The default fill is
   the far side of the quote (buy at the ask, sell at the bid), at most 100 contracts per option a
   day. A signal never trades at the close that produced it;
2. settles expiring options, and models early assignment when exercising early is optimal for the
   holder: short calls before an ex-dividend date by a closed-form test, short puts by a binomial
   tree;
3. marks every position, at the mid-price when the quote is usable and at a model price otherwise.
   It uses its own implied vols, never the vendor's;
4. delta-hedges with SPY shares;
5. checks gamma, vega and theta budgets, a stress-loss budget (at most 15% of NAV lost if SPY falls
   10% and implied vol rises 20 points), and the margin requirement. A margin call forces
   liquidation at the next snapshot;
6. lets each strategy decide the next trades on standard monthly expiries, for example when 30-day
   implied vol is far above a forecast of realised vol. Every forecast is fitted only on data up to
   that day.

It reports:
- returns in excess of T-bills, drawdowns, and Sharpe, Sortino and Calmar ratios;
- the probabilistic and deflated Sharpe ratios, which correct for the configurations logged. ADR-0010
  admits what the trial count still misses: exploration outside the log, and choices made while
  reading the literature;
- P&L split into gamma, vega, theta and costs;
- results by VIX level and by volatility shock;
- a spot-and-vol shock grid;
- the five named episodes: Feb-2018, Mar-2020, 2022, Aug-2024 and Apr-2025. Four are replayed day
  by day. The free 2024 data has no SPY snapshots from 2024-07-30 to 2024-08-09, so Aug-2024 is
  reported as `NO_DATA`, alongside the shock-grid cells closest to what happened then.

> **Design statement.** Papers show that the volatility risk premium exists. This project measures how
> much of it a real account keeps after the spread, the margin call and the crash.

**How it works.** Option chains come from a local Parquet/DuckDB store built from the OptionsDX SPY
end-of-day dataset (via Kaggle, 2010–2023). Every quote is quality-flagged before any strategy sees
it: zero bids, crossed or stale quotes, and put-call parity violations. DoltHub's free `options`
database supplies 2024–2026. It is too sparse to trade quote by quote, so the holdout tests the
signal and a fitted surface, not execution. The error that surface introduces is estimated by
running 2020–2023 through it after thinning OptionsDX to DoltHub's own strikes, expiries and
sessions. Each design choice is recorded with its rejected
alternatives in an ADR (index below). The app only visualises what the Python engine exported: a 3D
implied-vol surface with open positions, a 3D stress terrain, greek timelines, an attribution
waterfall and a trade blotter.

> "Every options-selling backtest I'd seen filled at mid. This one shows the same strategy at mid,
> at half the spread and at the full spread, side by side, and the Sharpe falls from [x] to [y]."
> — *hypothetical user: a graduate student preparing for quant interviews*

**Get started.** Clone `github.com/rajib2k5/vol-strategy-backtester`, run `uv sync`, then
`cd app && npm ci && npm run dev`. The milestone walkthroughs in `docs/milestones/` explain each
module line by line.

---

## External FAQ

**1. Is this a trading system or advice?**
No. It places no orders and connects to no broker. It reports what strategies *would have* earned,
net of costs, on past data, and makes no claim that any strategy will be profitable.

**2. What data does it use?**
- **2010–2023:** OptionsDX SPY end-of-day quotes, re-hosted on Kaggle
  (`dudesurfin/spy-options-eod-volatility-surface-2010-2023`).
- **2024–2026:** DoltHub `post-no-preference/options` (CC BY-SA 4.0).
- **Inputs:** SPY prices and dividends from yfinance (an unofficial Yahoo client), the 3-month
  Treasury yield from FRED (`DGS3MO`), and VIX history from Cboe.

All are free to download. None of the raw files is committed: loaders read them from `VOL_DATA_DIR`
(default `~/data/vol-projects`). Small derived DoltHub tables may be committed later. If so, they
carry the attribution and the same CC BY-SA licence.

**3. Why SPY and not SPX?**
SPX options are European and cash-settled, which makes them cleaner to model. But the free dataset
with bid/ask and volume covers SPY. SPY options are American and physically settled, and the ETF
pays quarterly dividends, so the engine handles early assignment and share delivery explicitly
(ADR-0003).

**4. When does a trade fill, and at what price?**
- **When:** at the next session that has an option snapshot. A signal from Tuesday's close fills at
  Wednesday's close. In the 2024–2026 data, which before ~Oct 2024 has only Mon/Wed/Fri snapshots,
  it fills at the next available one.
- **Price** (design): mid ± k × half-spread, from that day's own quote, rounded a cent against the
  strategy. The default is k = 1 (the far side). Results are also shown at k = 0.5, and at k = 0
  (mid, labelled optimistic). Studies of real option trades find effective costs well below
  conventional spread measures (Muravyev & Pearson 2020; see the background doc), so k = 1 is
  deliberately conservative.
- **Fees** (design): $0.70 per contract all-in: a typical $0.65 retail commission plus regulatory
  fees, itemised in ADR-0002. Hedge shares pay a per-share commission and slippage.
- **Liquidity** (design): at most 100 contracts per option a day, in every period, on standard
  monthly expiries. A cap at 10% of each option's volume would be the more natural rule, but
  OptionsDX volume is null or unreliable before 2021 (often null on contracts that clearly traded,
  measured), and DoltHub has no volume at all, so one rule cannot span the splits. The volume cap
  is therefore reported only as a 2021–2023 diagnostic. It uses the volume known on the day the
  order was made, never the fill day's, which the order could not have known.
- **Partial fills:** a structure (straddle, strangle, calendar) fills only in whole units, so its
  legs never drift out of ratio. If one leg can fill 85 contracts and the other 60, a straddle fills
  60 of each. Unfilled quantity is cancelled, not carried over. The full rules,
  including zero-bid and crossed quotes, are in ADR-0002.

**5. Why might your Sharpe ratio differ from a paper's?**
A Sharpe ratio on returns in excess of T-bills does not change if you scale every position up or down
by a constant: the mean and the standard deviation scale together. Two things do change it.
- **A capital base that moves with the strategy.** Return on margin is the common case: margin
  shrinks in calm markets and balloons in a crash, so leverage is highest just before the losses.
- **Survival.** A real account is forced out by a margin call at the bottom, and never earns the
  recovery a frictionless backtest books.

Many short-volatility backtests report return on margin or on premium, and assume the account
survives every drawdown.

Here (ADR-0007) the account starts with $1M (design) earning the T-bill rate. Position size is set
by whichever binds first: greek and stress-loss budgets that are fractions of current NAV
(ADR-0006), or a margin cap. Greeks bind for at-the-money straddles; margin and the stress budget
bind for out-of-the-money strangles. Margin is the Cboe strategy-based requirement, net of the
short options' market value, recomputed daily. A margin call forces liquidation at the next
snapshot. Sharpe is
computed on daily returns in excess of T-bills, and is always shown next to the margin utilisation
behind it.

**6. What will it not tell you?**
- Whether a strategy will work in the future.
- Anything about intraday execution or hedging.
- Anything about underlyings other than SPY.

---

## Internal FAQ

**Data (measured on the local copy, 2026-10-28; ADR-0001/0002/0009)**
- *2010–2023 (OptionsDX):* 569 MiB of Parquet, 9,468,584 rows, 3,508 snapshot dates. Every row is
  stamped 4:00 pm New York time to the minute, the same instant as the SPY close. Gaps:
  - no open interest;
  - volume under-counted and often null before 2021;
  - the vendor's own IVs and thetas are not internally consistent, so they are recomputed;
  - 12 snapshot dates that fall on market closures (44,926 rows), and 26 trading days with no
    snapshot.
- *2024–2026 (DoltHub):* good enough only to test a signal through a fitted surface:
  - no volume, sizes or underlying price;
  - strikes re-centred daily, so a held contract is rarely quoted again;
  - Mon/Wed/Fri only before ~Oct 2024;
  - no SPY snapshots from 2024-07-30 to 2024-08-09. Positions are carried through that gap. They are
    marked from the last surface, re-priced at each day's SPY close and flagged `STALE_SURFACE`.
    Option orders wait for the next snapshot (ADR-0004, ADR-0009).
- *Reproducibility:* the raw files cannot be committed, so each run records a fingerprint of the
  data it read (ADR-0001). A third party with the same downloads can check they match.

**Feasibility**
- DuckDB ran nine full-scan queries over all 14 Kaggle files in about 0.2 s wall-clock on this
  machine, warm cache (measured, ADR-0001). The engine's daily loop over ~3,500 sessions has not been timed yet.
  ADR-0001 sets a 60 s budget for one 14-year run, and the design is revisited at M3 if a run
  exceeds it.

**Risks and how we handle them**

| Risk | Mitigation |
|---|---|
| Look-ahead bias | Orders from snapshot *t* fill at the next snapshot (ADR-0002). Strategies and signals read data only through a `MarketView` that raises on any read after *t*; an import test will enforce each module's allow-list from M1; forecasts are refitted on data up to *t* only, checked by a test that changes the future and expects nothing at or before *t* to move (ADR-0001). Split guards stop a tuning run from touching later dates (ADR-0010). |
| Optimistic fills | Far-side fills and a hard per-option cap by default. Mid fills are reported only as a labelled comparison. |
| Bad quotes | 13 quality flags per quote, with counts per flag (ADR-0009). A day where more than 20% of option value is model-marked is flagged (ADR-0004). |
| Overfitting | A declared parameter grid. Every configuration, re-run and logged design choice counts as a trial, and the headline deflated Sharpe uses the more conservative of the raw and the effective (clustered) trial count. At most two re-runs per frozen configuration. The holdout runs only frozen configurations. It is semi-blind: its stress episodes were discussed while designing (ADR-0010). |
| Holdout realism | The holdout uses surface marks and fills. Their error is estimated, not bounded, by running 2020–2023 through the same surface after thinning OptionsDX to DoltHub's own strikes, expiries and sessions. Marks beyond the quoted strikes or expiries are flagged (ADR-0004, ADR-0009). |
| American-option approximations | Black-76 on a forward from quotes with their early-exercise premium removed (ADR-0008). Early assignment when exercise is optimal: calls by a closed-form test before ex-dividend dates, puts by a binomial tree (ADR-0003). |
| Leverage hidden in a smooth Sharpe | Greek and stress-loss budgets as fractions of NAV, entries capped at 50% of NAV in net margin, forced liquidation on a margin call, and a ruin stop at NAV ≤ 0 (ADR-0006, ADR-0007). |
| Wrong maths that looks right | Hand-worked tests, mutation checks, and an adversarial review with evidence-gated validation at every milestone, ledgers in `docs/validation/`. |

**Success metrics for launch** (each checkable from the repo)
1. A scripted set of trades, including an expiry, an early assignment and a hedge, reproduces a
   hand-worked P&L to the cent, as a committed test.
2. Every strategy is reported under k = 0, 0.5 and 1 fills.
3. Every named episode with data has its own P&L, drawdown and greek table. Aug-2024 appears as
   `NO_DATA` plus its shock-grid cells.
4. The holdout result is produced only from configurations frozen and committed before the holdout
   run, and is reported next to the estimated surface-mode error.
5. Every number in the README is regenerated from `reports/` by the pipeline, and a check fails if
   any committed number differs.

**What we will not do**
- No live or paper trading, and no broker integration.
- No intraday simulation.
- No underlyings other than SPY.
- No parameter search beyond the declared grid.
- No raw vendor data in the repository.

---

## Glossary

| Term | Meaning here |
|---|---|
| ADR | Architecture decision record: one file per design decision, with the alternatives rejected. |
| Black-76 | The Black-Scholes formula written on a forward price instead of spot. It needs no dividend yield when the forward comes from put-call parity. |
| HAR / GARCH | Two standard models that forecast realised volatility from past returns. |
| PSR / DSR | Probabilistic and deflated Sharpe ratios. They give the probability that the true Sharpe exceeds a benchmark, after allowing for skew, fat tails and, for DSR, the number of strategies tried. |
| Calmar | Annual growth rate divided by the worst drawdown. |
| NAV | Net asset value: cash plus the marked value of all positions. |
| Greek budget | A cap on portfolio gamma, vega or theta, as a fraction of NAV (ADR-0006). |
| Stress budget | A cap on the loss from fully repricing the book under spot and vol shocks, as a fraction of NAV (ADR-0006). |
| Surface mode | Marking and filling from a fitted implied-vol surface instead of individual quotes. Used where the chain is too thin. |
| Model mark | A price from the pricing model at the day's surface vol, used when the quote is unusable. |
| Vol shock | A session where VIX rises at least 25% or 5 points close to close (ADR-0010). |
| `NO_DATA` | A reported row that says the data for that window does not exist, instead of omitting it. |

## ADR index

| ADR | Decides |
|---|---|
| 0001 | Daily event-driven engine, Parquet + DuckDB store, module boundaries, JSON contract |
| 0002 | Fill timing (next snapshot), fill price, fees, volume caps |
| 0003 | Expiry, physical settlement, early assignment |
| 0004 | Mark-to-market rules and bad-quote handling |
| 0005 | Delta-hedge frequency and instrument |
| 0006 | Greek units, budgets and limit enforcement |
| 0007 | Capital base, cash interest, margin, return definition |
| 0008 | Pricing inputs: Black-76, parity forward, rates, day count |
| 0009 | Data sources, trading calendar, quality flags, surface mode |
| 0010 | Sample splits, trial counting, regimes, stress windows and grid |

## Open questions for the author (defaults taken 2026-10-29; the owner can override)

1. Is the primary audience you (an interview-ready explanation) or other learners cloning the repo?
   This changes how much the README teaches versus reports.
2. Should the headline strategy be the short straddle (the classic premium harvest) or the
   signal-gated strangle?
3. Do you want the author quote kept in first person, or replaced with a plain design statement?
4. Is "positive excess return over T-bills after costs, with DSR reported" the right bar for
   "pays", or do you want a stricter one (e.g. DSR above 0.95)?

Defaults taken on 2026-10-29, recorded in `LEARNING_LOG.md` ("Defaults taken"):
1. The author is the primary audience. The README reports, and the docs teach.
2. The short straddle is the headline baseline. The signal-gated strangle is the challenger beside it.
3. The quote is replaced with a plain design statement.
4. Two tiers: "pays" is a positive after-cost excess return over T-bills; "pays beyond luck" also
   needs a headline DSR of at least 0.95.


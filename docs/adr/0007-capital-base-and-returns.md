# ADR-0007: Capital base, margin, forced liquidation and the return definition

**Status:** Accepted, milestone 0. The margin model is implemented in M5 and returns and metrics in M6. The portfolio-margin variant will be revisited in M5.

## Revised after M0 review (2026-10-28)

The adversarial review (`docs/validation/00-design-research-ledger.md`, claims 6, 7, 11 and 13) refuted five points. The 15%/10% rates survived.

1. **Wrong citation.** FINRA 4210(f)(2)(E)(i) has a "broad index stock group" row but never mentions ETFs. The ETF row is in **Interpretation 4210(f)(2)(E)/02**, "Options on Leveraged Exchange Traded Products". Its chart row "Listed Non-Leveraged ETP Option on a Broad-Based Index or Benchmark" reads "100% of the option premium plus 15% of the market value, minus any out-of-the-money amount". I checked this on finra.org on 2026-10-28.
2. **The margin call counted option value twice.** The requirement includes 100% of each short option's value, and NAV has already subtracted that value as a liability. The Cboe Margin Manual applies the sale proceeds instead (p. 30: requirement $4,110, "SMA Debit or Margin Call: $4,110.00 − $10.00 = $4,100.00"). **Changed:** the call trigger, the liquidation target and the pre-trade cap all use the **net requirement**, the rule's requirement minus the short options' market value. On the reviewer's probe, a book of 24 short straddles hit a margin call at a −50% move under the old rule ($645,771 > $506,637). On the net basis it does not.
3. **Hedge shares at a flat 30% sat below Reg T's 50% initial margin.** 30% was also called "conservative", which is true only for long maintenance (25%). **Changed:** shares use 50% (Reg T initial) in the pre-trade projection, and FINRA 4210(c) maintenance in the margin-call test: 25% long, 30% short.
4. **"Leverage is set by the greek budgets" was false for OTM wings.** Margin bound them first: 109 10%-OTM strangles at the 50% cap, against 155 allowed by vega. **Changed:** the statement now names the binding limit by structure. ADR-0006's new stress budget is tighter than margin for wings.
5. **"Sharpe can be scaled up by leverage" was false.** Constant leverage multiplies the mean and the standard deviation of excess returns by the same factor, so it leaves the Sharpe ratio unchanged. **Changed:** the text now says what leverage does change: a time-varying capital base, and forced liquidation and ruin.

Also corrected: Santa-Clara & Saretto's −1.0% a month is for the portfolio containing the short near-maturity 5% strangle, not for "the best strangle" (WP, Nov 2004, checked in the text).

## Context

A short option needs no cash up front, so a "return" needs a stated denominator. The background doc (§4, "The capital base") lists three:
- the premium received, which is meaningless;
- the notional, which is the cash-secured PUT index view;
- the margin posted, which is levered and depends on the path.

Margin also decides whether a strategy can survive at all. In Santa-Clara & Saretto's working paper, adding margin calls that are met by liquidating positions turned the optimal portfolio containing a short near-maturity 5% strangle from +2.7% a month (Sharpe 0.474) into −1.0% a month.

For SPY, the Cboe Margin Manual (p. 7) treats an ETF on a broad-based index like a broad-based index option, at a 15% rate rather than the 20% for equity options. FINRA's rule is Interpretation 4210(f)(2)(E)/02, chart row "Listed Non-Leveraged ETP Option on a Broad-Based Index or Benchmark". FINRA Notice 09-53 describes the same 15% requirement under the predecessor rules NASD 2520 and NYSE 431. The rules:
- **Short call:** 100% of the option's value + 15% of the underlying value − the out-of-the-money amount. The minimum is the option value + 10% of the underlying.
- **Short put:** the same, but the minimum is 10% of the **strike**.
- **Short straddle:** the greater of the two sides' requirements + the market value of the other side.
- **How the requirement is met.** FINRA 4210(a)(5) equity already subtracts the market value of short positions. The Cboe Manual applies the sale proceeds to the requirement: in its p. 30 example, a short put at 0.10 carries a $4,110 requirement and a $4,100 margin call. So the cash the account must hold beyond the option's value, the **net requirement**, is the requirement minus the short options' market value.
- **Stock.** Reg T initial margin is 50% of market value for long and for short stock (12 CFR 220.12; for a short sale, 150% including the proceeds). FINRA 4210(c) maintenance is 25% long, and for short the greater of 30% and $5 a share.

Sources:
- Cboe Margin Manual: https://cdn.cboe.com/resources/membership/Margin_Manual.pdf
- FINRA Rule 4210: https://www.finra.org/rules-guidance/rulebooks/finra-rules/4210
- FINRA Interpretations of Rule 4210, including 4210(f)(2)(E)/02: https://www.finra.org/rules-guidance/guidance/interps-4210
- Regulation T, 12 CFR 220.12: https://www.ecfr.gov/current/title-12/chapter-II/subchapter-A/part-220/section-220.12
- FINRA Notice 09-53: https://www.finra.org/rules-guidance/notices/09-53

## Decision

1. **The capital base is fixed allocated capital: `initial_nav = $1,000,000`**, held as cash.
   - No external flows after inception.
   - NAV compounds.
   - Leverage is set by the tightest of three limits, never by "use all available margin": the greek budgets and the stress-loss budget of ADR-0006, and the margin cap in §4. Which one binds depends on the structure, measured at S = 450, σ = 0.18, 30 DTE, NAV $1M:
     - **Near-ATM straddles: the greek budgets.** 24 straddles at the vega budget use 16% of NAV in net margin.
     - **OTM wings: the stress budget, then margin.** For 10%-OTM strangles, vega would allow 155, net margin 111 and the stress budget 65.
2. **Cash accrues at the 3-month T-bill rate.**
   - Take FRED **DGS3MO**: the 3-month constant-maturity yield, in percent, on an investment (bond-equivalent) basis.
   - Convert it once to a continuous rate: `r_cc = (365/91)·ln(1 + y/100·91/365)`.
   - Accrue interest for the `d` calendar days from the previous session to this one: `cash·(e^{r_cc·d/365} − 1)`, using the previous session's rate. A Friday→Monday step therefore earns three days.
   - Negative cash, from buying hedge shares or long premium, pays `r_cc + 0.50%`.
   - Short-stock proceeds earn `r_cc − 0.25%`. That 0.25% is the borrow fee in ADR-0005. Both spreads are assumptions, not measured values.
   - Missing FRED days, shown as `.`, carry the last value forward and are flagged.
3. **The margin model is Cboe/Reg-T strategy-based margin, recomputed every session at the day-*t* marks.**
   - **Pairing.** Short straddles and strangles are paired by expiry. A calendar whose long leg has the same strike and a later expiry pays the debit only. Defined-risk spreads are charged their maximum loss. Anything left over is margined as a naked option, using the formulas in Context.
   - **Hedge shares.** No offset against the options.
     - In the pre-trade projection (§4) they are charged Reg T initial margin, 50% of absolute market value.
     - In the margin-call test (§5) they are charged FINRA 4210(c) maintenance: 25% of market value for long shares, and max(30%, $5/share) for short shares, which is 30% at SPY prices.
     - The rates are parameters: `share_initial_rate = 0.50`, `share_maint_rate_long = 0.25`, `share_maint_rate_short = 0.30`.
   - Long options are paid in full and add nothing to the requirement.
   - **Gross and net requirement.** `margin_req_gross` is the rule's requirement as written, including 100% of each short option's market value. The engine compares only the net figure with NAV:

     ```
     margin_req_net = margin_req_gross − Σ market value of short options
     ```

     NAV_mid already counts the short options as a liability, so comparing NAV with the gross figure would count their value twice. `daily_pnl` stores both figures and the short-option value.
4. **Pre-trade margin cap.** Each new entry is scaled so that the projected **net** requirement stays ≤ **50% of NAV**. Hedge shares count at the initial rate. This runs after the greek and stress checks in ADR-0006.
   - The cushion is meant to survive a 2–3× vol spike without forced liquidation.
5. **Margin call and forced liquidation.**
   - **Trigger.** If `margin_req_net,t > NAV_mid,t`, step 8 of the daily loop issues reduce-only liquidation orders. Hedge shares count at the maintenance rates. `excess_liquidity = NAV_mid − margin_req_net` is stored.
   - **Which positions.** The largest contributors to the net requirement go first, until the projected net requirement is ≤ **80% of NAV**.
   - **When they fill.** At *t+1*, at the far side (ADR-0002, k = 1). There is no waiting for the signal and no exemption for "it will come back".
   - **Ruin.** If NAV ≤ 0 the run stops with `status = ruin`. Metrics are computed up to that point and the ruin is shown prominently.
6. **The return definition.**
   - Daily return on sessions: `r_t = NAV_mid,t / NAV_mid,t−1 − 1`.
   - Risk-free return: `rf_t = e^{r_cc,t−1·d/365} − 1`.
   - Sharpe: `√252 · mean(r − rf) / std(r − rf)`, with the sample std (ddof = 1).
   - Sortino: the same mean divided by the downside deviation of `r − rf` below 0.
   - Calmar: CAGR / |max drawdown of NAV_mid|.
   - Drawdowns are reported on both NAV_mid and NAV_liq.
   - PSR and DSR use the daily excess returns, including their skew and kurtosis (ADR-0010).
   - Every metric sits next to the average and peak margin utilisation, so the reader can see the leverage behind the Sharpe.
7. **A secondary view for comparison only.**
   - For short-put and strangle variants we also report a **cash-secured** return: notional = 100·K·|q| for each short put, fully collateralised.
   - This makes the strategy comparable with the Cboe PUT index.
   - It is never the headline figure.

## Alternatives considered

- **Return on margin posted.** Rejected as the headline. The denominator changes with vol and with the path, so the return series becomes a time-varying-leverage version of the NAV return. Its Sharpe then reflects the margin formula as much as the strategy: margin shrinks in calm markets, which inflates calm-period returns. Constant leverage alone would not change the Sharpe of excess returns. Peak margin use is reported as a utilisation figure instead.
- **Return on premium.** Rejected as meaningless.
- **Fully cash-secured notional for everything.** Rejected as the headline. For delta-hedged straddles it is roughly 30× more capital than any broker requires, and it makes every strategy look like a T-bill. It is kept as the secondary view for put-writing.
- **Portfolio margin**, an OCC TIMS-style stress over spot and vol shocks. Deferred to M5 as a variant.
  - Its scan ranges for broad-based ETFs are *unverified* here.
  - It would win if we model a professional account. Requirements would then be roughly 2–4× lower for hedged books, which makes the 50% cap bind less.
  - We will reuse our own stress grid (ADR-0010).
- **No margin model**, sized by greeks only. Rejected. This is exactly the omission that Santa-Clara & Saretto show reverses conclusions.
- **Time-weighted vs money-weighted returns.** The question does not arise, because there are no external flows.

## Consequences and biases

- **Charging stock with no offset overstates the requirement.** Real strategy-based accounts recognise some covered combinations. This is conservative: it makes forced liquidation more likely.
- **Hedge trades are never blocked for initial margin.** A real broker would want Reg T initial margin on a hedge that adds shares. We charge it only in the pre-trade projection for new entries, and the end-of-day maintenance test catches the rest. That is mildly optimistic in a fast market.
- **Leverage and Sharpe.** Holding leverage constant leaves the Sharpe of excess returns unchanged. What leverage changes is the path: a margin call forces sales at the worst prices, ruin truncates the series, and compounding turns the same arithmetic Sharpe into a different CAGR. Those effects are why the margin model exists.
- **Liquidating at t+1, at the far side, is a coin toss in a crash.** In a falling market a real broker would sell intraday on day t, which may be better or worse than our t+1 price. The direction of the bias is not known. The analytics flag every liquidation.
- **Fixed capital with compounding.** After drawdowns the budgets shrink, because they are a fraction of NAV, so recovery is slower than for a desk with fresh capital.
- **Earning the T-bill rate on all cash flatters absolute returns compared with a retail account.** It does not affect the excess return, and therefore not Sharpe either, because the same rate is the risk-free rate.

## How we will test it

1. **Interest.**
   - DGS3MO = 5.25 gives r_cc = 5.2159%.
   - Cash of $1,000,000 from Friday to Monday (d = 3) earns **$428.80**.
   - A negative cash balance of −$100,000 over the same three days pays 100,000·(e^{0.057159·3/365} − 1) = **$46.99**.
2. **A short put.** Strike 400, marked at 5.00, with S = 420 (so 20 points out of the money).
   - Requirement per share: 5 + max(0.15·420 − 20, 0.10·400) = 5 + 43 = 48.
   - Per contract: **$4,800** gross; net of the $500 market value, **$4,300**.
3. **A short call.** Strike 440, marked at 3.00, with S = 420.
   - Requirement per share: 3 + max(63 − 20, 42) = 46.
   - Per contract: **$4,600**.
4. **A short straddle.** Strike 420, call marked at 9, put at 8, with S = 420.
   - Call side: 9 + 63 = 72. Put side: 8 + 63 = 71.
   - Requirement: the larger side, 72, plus the other side's value, 8, so 80 per share.
   - Per straddle: **$8,000** gross; net of the $1,700 market value, **$6,300**.
5. **The same straddle after a crash** to S = 300, with the put marked at 121 and the call at 0.05.
   - Put side: 121 + max(45 − 0, 42) = 166.
   - Requirement: 166 per share plus the call's 0.05 = **$16,605** per straddle gross. Net of the $12,105 market value it is **$4,500**, which is 15% of the $30,000 underlying.
6. **Forced liquidation.**
   - NAV is $100k. The gross requirement is $150k and the short options are worth $30k, so the net requirement is $120k > $100k, which triggers a margin call.
   - Liquidation orders are created for *t+1* until the projected net requirement is ≤ $80k.
   - The same book with a gross requirement of $125k has a net requirement of $95k: no call. The M0 rule, which compared the gross figure with NAV, would have called it.
   - If NAV is at most 0 instead, the run stops with `status = ruin`.
7. **Daily return.** NAV goes from 1,000,000 to 1,004,287, so `r_t` = 0.4287%.
8. **Sharpe, by hand.** Excess returns are [0.01, −0.01, 0.02, 0.00].
   - The mean is 0.005 and the sample std is 0.012910.
   - Sharpe = √252·0.005/0.012910 = **6.148**.
   - Scaling every excess return by 2 leaves it at 6.148.
9. **Cboe's own example (Margin Manual p. 30).** Short 1 Oct 410 put at 0.10, with the underlying at 445.35.
   - The basic calculation is 10.00 + 6,680.25 − 3,535.00 = $3,155.25. The minimum, 10.00 + 4,100.00 = $4,110.00, applies, so the gross requirement is $4,110.
   - The net requirement is **$4,100**, which matches Cboe's "SMA Debit or Margin Call".
   - An account with NAV $4,100.00 is not called. One with $4,099.99 is.
10. **Hedge-share rates.** +1,000 SPY shares at $450:
    - in the pre-trade projection they count $225,000 (50%);
    - in the margin-call test they count $112,500 (25%);
    - −1,000 shares count $135,000 (30%) in the margin-call test.

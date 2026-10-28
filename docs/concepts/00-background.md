# Background: volatility mispricing in SPY options

The theory and evidence the backtester is built on. Numbers are cited to sources checked on 2026-10-28 (§8), computed by us from Cboe daily index files (**[measured]**, method at the end of §8), or taken from a working paper (**[WP]**; the published version may differ). Anything we could not check is marked **[unverified]**.

---

## 1. Implied vs realised volatility, and the VRP

### Realised variance

With daily log returns $r_i=\ln(S_i/S_{i-1})$, annualised realised variance over the next $n$ trading days is

$$RV_{t,n}=\frac{252}{n}\sum_{i=1}^{n}r_{t+i}^2 .$$

The mean is set to zero, which is negligible at daily frequency. Two choices decide what this measures:

- **Close-to-close or intraday.** Close-to-close returns include the overnight gap; intraday RV (as in Corsi 2009) leaves it out. An option holder bears the gap.
- **Units.** Compare variance with variance. Because $\mathbb{E}\sqrt{RV}<\sqrt{\mathbb{E}\,RV}$, a premium in vol points is a different quantity from one in variance.

### Model-free implied variance

If the price path is continuous, the risk-neutral expectation of integrated variance to expiry ($\tau=T-t$) can be built from a strip of OTM options (Britten-Jones & Neuberger 2000; Demeterfi et al. 1999):

$$\mathbb{E}^{\mathbb{Q}}_t\!\left[\int_t^T\sigma_u^2\,du\right]=2e^{r\tau}\left[\int_0^{F}\frac{P(K)}{K^2}dK+\int_F^{\infty}\frac{C(K)}{K^2}dK\right].$$

Divided by $\tau$, this is the annualised fair strike of a variance swap, $SW_{t,T}$. Carr & Wu show that the replication is exact for continuous paths, and that with jumps the error is third order in the jump size **[WP]**.

The VIX discretises this formula (Cboe VIX Methodology v6.0):

$$\sigma^2=\frac{2}{T}\sum_i\frac{\Delta K_i}{K_i^2}e^{RT}Q(K_i)-\frac1T\left(\frac{F}{K_0}-1\right)^2 .$$

- $Q(K_i)$ is the bid/ask **midpoint** of the OTM option at strike $K_i$; only options with a non-zero bid are used.
- $K_0$ is the first strike at or below the forward price $F$.
- The near-term and next-term variances are interpolated to 30 days, and $\text{VIX}=100\sqrt{\sigma^2_{30}}$.

Cboe redefined VIX this way on 22 September 2003, so that it approximates the 30-day variance-swap rate (Carr & Wu). Two consequences:

1. VIX measures **variance**, and the $1/K^2$ weights favour low strikes, so it is not at-the-money vol.
2. VIX is built from **quotes**, so it can jump when quotes widen even if nothing trades (§6, Aug-2024).

Our SPY IV30 will be close to VIX but not equal to it, because SPY options are American and SPY pays dividends.

### The VRP

$$\text{VRP}_t\equiv\mathbb{E}^{\mathbb{Q}}_t[RV_{t,T}]-\mathbb{E}^{\mathbb{P}}_t[RV_{t,T}]\approx SW_{t,T}-\mathbb{E}^{\mathbb{P}}_t[RV_{t,T}] .$$

After the fact, $SW_{t,T}-RV_{t,T}$ is the payoff of a short variance swap per unit of variance notional.

**Sign convention.** Carr & Wu define the premium as $RV-SW$, so their "negative" premium is our positive VRP.

### Why the VRP is positive for index options

- **Variance spikes when the market falls.** The daily correlation between SPX log returns and VIX changes is $-0.79$ **[measured, 1990–2026]**. Long variance therefore hedges the market, and buyers accept a negative expected return for it.
  - Carr & Wu find a strongly negative market beta, but it explains only a small part of the premium, and the Fama-French factors explain little more.
  - They conclude that either the variance market is inefficient or most of the premium comes from a separate, heavily priced variance factor **[WP]**.
- **Crash insurance.** Bakshi & Kapadia (2003) find that delta-hedged S&P 500 options lose money on average, and lose more when volatility is high; the premium survives allowing for jump fears.
  - Dew-Becker et al. (2017) find that only unexpected, transitory realised variance is priced, and the WP ties this to its *downside* component.

### How big the VRP is

| Source | Window | Implied (mean) | Realised (mean) |
|---|---|---|---|
| Carr & Wu, Tables 4–5 **[WP]**, 30-day SPX | Jan 1996 – Feb 2003 | $\sqrt{SW}$ 24.41 | $\sqrt{RV}$ 18.82 |
| Bondarenko for Cboe (2019) | 1990–2018 | VIX 19.3 | 15.1 |
| **[measured]** VIX vs the next 21 days' close-to-close RV | windows starting 1990-01-02 to 2026-09-28 | VIX 19.43 | 15.33 |

- **Carr & Wu.** The mean log premium is $\ln(RV/SW)=-0.594$ ($t=-9.48$): a long variance swap lost over 50% a month in log terms.
- **Our measurement.** VIX beat the realised vol that followed on 85.9% of days; the mean of $\ln(RV/\text{VIX}^2)$ was $-0.60$.
- **Sanity check.** Over the Carr–Wu window our method gives 23.73 vs 18.97, close to their numbers.

### Time variation and skew

The premium is a small gain on most days and an occasional very large loss. Means of $\text{VIX}^2-RV$ in variance points (vol%²), by window start year **[measured]**:

| Year | Mean $\text{VIX}^2-RV$ |
|---|---|
| 2018 | −6 |
| 2020 | −198 |
| 2022 | +89 |
| 2024 | +89 |
| 2025 | +45 |

- **2020 averaged negative even though VIX beat realised vol on 76.7% of its days.**
- On 2020-02-21 VIX closed at 17.08; SPX then realised 88.0% over 21 trading days.

### Term structure

- **Dew-Becker, Giglio, Le & Rodriguez (2017)** use variance swaps from 1 month to 14 years, 1996–2014.
  - Hedging news about *future* variance cost roughly nothing at horizons from a quarter to 14 years. Only unexpected, transitory realised variance was priced.
  - The WP gives annualised Sharpe ratios on zero-coupon variance claims of −1.4 at one month and −0.5 at two months; longer maturities are insignificant. **The premium sits at the front of the curve.**
- **Johnson (2017)** finds that the shape of the VIX term structure reflects variance risk premia, not expected VIX changes.
  - Its second principal component, SLOPE, predicts excess returns on variance swaps, VIX futures and S&P 500 straddles.
  - On direction, a secondary summary (CXO Advisory) says a low slope predicts higher returns on long-variance positions **[unverified against the paper]**.
- **Backwardation is rare.** VIX closed above VIX3M on only 7.5% of days since 2009-09-18 **[measured]**.

---

## 2. Delta-hedged option P&L: the gamma-rent formula

**Setup.** Hold one option $V(t,S;\sigma_i)$, marked with Black–Scholes–Merton (BSM) at implied vol $\sigma_i$. Short $\Delta=\partial V/\partial S$ shares, and finance $V-\Delta S$ at rate $r$.

**Step 1: hedged P&L over $\delta t$.**

$$\delta\Pi=\delta V-\Delta\,\delta S-r(V-\Delta S)\,\delta t .$$

**Step 2: Taylor-expand $V$ in $t$, $S$ and $\sigma_i$.** Vanna and volga are the cross and second-order terms in $\sigma_i$.

$$\delta V=\Theta\,\delta t+\Delta\,\delta S+\tfrac12\Gamma(\delta S)^2+\mathcal{V}\,\delta\sigma_i+\underbrace{\partial_{S\sigma}V\,\delta S\,\delta\sigma_i+\tfrac12\partial_{\sigma\sigma}V(\delta\sigma_i)^2}_{\text{vanna, volga}}+\dots$$

**Step 3: the $\Delta\,\delta S$ terms cancel.**

$$\delta\Pi=\big[\Theta-r(V-\Delta S)\big]\delta t+\tfrac12\Gamma(\delta S)^2+\mathcal{V}\,\delta\sigma_i+\dots$$

**Step 4: use the BSM PDE at $\sigma_i$.** $\Theta+\tfrac12\sigma_i^2S^2\Gamma+rS\Delta-rV=0$ implies $\Theta-r(V-\Delta S)=-\tfrac12\sigma_i^2S^2\Gamma$, so

$$\boxed{\;\delta\Pi\approx\tfrac12\Gamma S^2\left[\left(\frac{\delta S}{S}\right)^2-\sigma_i^2\,\delta t\right]+\mathcal{V}\,\delta\sigma_i\;}$$

**Step 5: write it in terms of realised vol** $\sigma_r$, using $(\delta S/S)^2\approx\sigma_r^2\,\delta t$:

$$\delta\Pi\approx\tfrac12\Gamma S^2(\sigma_r^2-\sigma_i^2)\,\delta t+\mathcal{V}\,\delta\sigma_i .$$

### How to read the formula

- **Dollar gamma** $\tfrac12\Gamma S^2$ is the P&L per unit of squared return. Theta, net of financing, is the rent for that exposure, charged at the implied rate.
- **Break-even move.** The gamma term is zero when $|\delta S/S|=\sigma_i\sqrt{\delta t}$. At $\sigma_i=16\%$ and daily steps that is about 1.0% a day.
- **Short straddle** ($\Gamma<0$, $\mathcal{V}<0$):
  - Each day it earns $\tfrac12|\Gamma|S^2(\sigma_i^2\delta t-r_t^2)$, which is positive when the move is below break-even and negative, growing with the square of the move, when it is above.
  - It loses $|\mathcal{V}|\,\delta\sigma_i$ when implied vol rises. This mark-to-market loss arrives before any realised vol.
  - Near expiry gamma dominates; for longer tenors vega dominates.

### Over the option's life

Hedging at $\sigma_i$ until expiry (El Karoui, Jeanblanc-Picqué & Shreve 1998) gives

$$\Pi_T=\tfrac12\int_0^Te^{r(T-t)}\,\Gamma_tS_t^2\,(\sigma_{r,t}^2-\sigma_i^2)\,dt .$$

**The P&L depends on *where* realised variance arrives**, not just how much.

- The weight $\Gamma S^2$ is concentrated near the strike and near expiry. A straddle sold "rich" can still lose if spot moves sharply around the strike in the final days.
- The $1/K^2$ strip of a variance swap keeps dollar gamma constant, which removes this path dependence (Demeterfi et al. 1999). That is why the VRP is measured with variance swaps; straddles add path risk on top.

### Discrete hedging

With rebalancing every $\delta t$:

- Each step leaves a residual $\tfrac12\Gamma S^2\sigma^2\delta t\,(z^2-1)$, $z\sim N(0,1)$, with variance $\tfrac12(\Gamma S^2\sigma^2\delta t)^2$.
- Summed over $T/\delta t$ steps, with $\Gamma S^2$ held fixed, the hedging error's standard deviation scales as $\sqrt{\delta t}$.
- So weekly hedging is about $\sqrt5\approx2.2\times$ noisier than daily hedging, but cheaper to run. Our own simulation of a 30-day ATM call gives 2.1×, because $\Gamma S^2$ is not actually constant **[measured]**.

Bertsimas, Kogan & Lo (2000) derive the limiting distribution of this tracking error.

### Spot–vol correlation

Implied vol moves against spot. The vega term therefore hides a delta, and the BSM delta at the option's own implied vol is not the minimum-variance hedge. Which hedge ratio to use is a design choice.

### Evidence

Bakshi & Kapadia (2003) test this decomposition. Delta-hedged S&P 500 option gains are negative on average, consistent with $\sigma_i$ above expected realised vol: a negative market volatility risk premium.

---

## 3. Evidence on option-strategy returns

- **Coval & Shumway (2001).** Zero-beta, at-the-money S&P 500 straddles lose about 3% per week on average, which points to priced systematic volatility.
  - Santa-Clara & Saretto **[WP]** restate the short side: 3.15% per week, 19% weekly vol, annualised Sharpe 1.19.
- **Broadie, Chernov & Johannes (2009).** Large put-writing returns are statistically insignificant under Black–Scholes and Heston, because sampling uncertainty is extreme.
  - Market-neutral positions (straddles, delta-hedged options) reduce the noise, and jump risk premia plus estimation risk explain their returns.
  - *Lesson:* a short-OTM-put backtest cannot separate edge from compensated tail risk. Delta-hedged P&L is the better-identified test.
- **Put-writing.** Cboe's PUT index sells at-the-money monthly SPX puts against T-bill collateral.
  - Bondarenko for Cboe (2016), mid-1986 to 2015: PUT 10.13% a year compound, 10.16% standard deviation; S&P 500 9.85% and 15.26%.
  - Cboe (2019): skewness −2.09 for PUT vs −0.81 for the S&P 500.
  - **[Measured]**, 2007-01-03 to 2026-10-27:

    | Index | CAGR | Vol | Max drawdown |
    |---|---|---|---|
    | PUT | 7.28% | 13.78% | −37.09% |
    | SPX (price) | 8.94% | 19.62% | −56.78% |

    Not like for like: PUT includes T-bill interest, while the SPX price index leaves out dividends.
- **Goyal & Saretto (2009).** They sort *individual equity* options on historical minus implied vol. Long–short straddle and delta-hedged portfolios earn significant monthly returns that risk factors do not explain.
  - *Caveat:* this is **cross-sectional**. Our signal is a time series on one index, so the result supports the idea but does not transfer directly.
- **Calendar spreads.** Santa-Clara & Saretto include them among their strategies. In principle, short front / long back harvests the front-end premium (Dew-Becker et al.) while partly hedging vol-level shifts. The P&L is front gamma rent plus back vega, minus the vega mismatch, and it is exposed to changes in SLOPE (Johnson).

---

## 4. Why paper returns disappear: costs, margin, tails

### Santa-Clara & Saretto **[WP]**

Data: options on S&P 500 futures, 1985–2001; OptionMetrics index-option closing quotes for spreads.

- **Sharpe on paper.** Short-option Sharpe ratios reach 1.69 annualised, for a near-maturity strangle. Crashes would need to be 2–3 times more frequent than in the sample to deter an investor.
- **Spreads.** The volume-weighted closing spread is 10.28% of mid for calls and 10.69% for puts. Near-maturity ATM is about 7%; 5%-OTM near-maturity is 17.4% for calls and 13.9% for puts.
- **Bid/ask vs mid.** Bid/ask fills cut short-put returns by 4–6.9% a month and the near-maturity straddle by 4.9%. Far-maturity straddles and strangles go to negative Sharpe.
- **Margin.** With one dollar of capital and margin calls met by liquidation, the optimal portfolio containing a short near-maturity 5% strangle goes from +2.7% a month (Sharpe 0.474) to −1.0%. The published abstract keeps this headline: margin calls turn some of the best Sharpe ratios negative.

### Muravyev & Pearson (2020)

- Option quote changes are predictable at high frequency. Traders who time executions pay effective spreads under 40% of conventional measures; the overall average effective spread is one-quarter smaller.
- **Mid is optimistic and full bid/ask is pessimistic.** The truth depends on execution skill, which a daily backtest cannot model.

### Spreads widen in stress

See Aug-2024 in §6. A fixed cost in basis points understates costs exactly when a short-vol book is losing.

### Peso and crash risk

Short gamma loses with the square of the move, and a sample can miss the crash. Santa-Clara & Saretto's sample has one crash in 17 years; Broadie, Chernov & Johannes make the same point through sampling error.

### The capital base

A short option needs no cash up front, so "return" needs a denominator:

- the premium received (meaningless);
- the notional (the fully cash-secured PUT index);
- the margin posted (levered and path-dependent).

Constant leverage does not change the Sharpe ratio of excess returns: it scales the mean and the standard deviation alike. What leverage changes is the path. Margin calls force sales at the worst prices, ruin ends the series, and a margin-based denominator moves with vol. Sharpe also ignores negative skew, which Cboe's 2019 summary notes.

---

## 5. Forecasting realised vol for the signal

The signal is $\widehat{\text{VRP}}_t=\text{IV30}_t^2-\widehat{RV}_{t\to t+h}$.

### HAR-RV (Corsi 2009)

$$RV^{(d)}_{t+1}=c+\beta^{(d)}RV^{(d)}_t+\beta^{(w)}RV^{(w)}_t+\beta^{(m)}RV^{(m)}_t+\omega_{t+1}$$

- $RV^{(w)}_t=\tfrac15\sum_{j=0}^{4}RV^{(d)}_{t-j}$, and $RV^{(m)}$ is the 22-day average.
- Fitted by OLS. It is a restricted AR(22) that mimics long memory.
- Corsi works in realised *volatility* and notes that variance and log versions are analogous.
- His data are USD/CHF, S&P 500 futures (1990–2007) and T-bond futures. **He evaluates 1-day, 1-week and 2-week forecasts, which is shorter than the ~21-day horizon we need.**

### GARCH(1,1) and GJR

- GARCH(1,1) (Bollerslev 1986): $\sigma^2_{t+1}=\omega+\alpha\varepsilon_t^2+\beta\sigma_t^2$.
- GJR (Glosten, Jagannathan & Runkle 1993) adds $\gamma\varepsilon_t^2\mathbf 1[\varepsilon_t<0]$, so with $\gamma>0$ negative shocks raise variance more than positive ones.
- The $k$-step forecast is $\mathbb{E}_t\sigma^2_{t+k}=\bar\sigma^2+\phi^{k-1}(\sigma^2_{t+1}-\bar\sigma^2)$, with $\phi=\alpha+\beta$, or $\alpha+\beta+\gamma/2$ for GJR with symmetric shocks. Average over $k=1..h$.

### Match the forecast to the option

IV30 covers 30 calendar days, about 21 trading days, so the target is $\tfrac{252}{21}\sum_{i=1}^{21}r_{t+i}^2$. Estimate HAR directly on that target, or iterate the one-step model.

- **Same horizon.** A one-day forecast set against a 30-day implied vol puts term-structure shape into the "signal".
- **Same measure.** Variance against variance, the same annualisation, overnight returns included.
- **No look-ahead.** IV30 is taken at the close on day $t$, the forecast uses only data to $t$, and the trade fills at $t+1$.

---

## 6. The named stress episodes

The table is **[measured]** from Cboe daily files (VIX, VIX3M, SPX, PUT). Drawdowns are peak to trough, close to close.

| Episode | VIX | SPX | PUT index |
|---|---|---|---|
| **Feb-2018** | 17.31 → 37.32 close, 5 Feb (+115.6%, largest one-day close-to-close rise since 1990) | −4.10% on 5 Feb; −10.16% from 26 Jan to 8 Feb | −3.86% on 5 Feb |
| **Mar-2020** | 82.69 close on 16 Mar, the highest in the 1990–2026 file | −11.98% on 16 Mar; −33.92% from 19 Feb to 23 Mar | −28.93% drawdown |
| **2022** | mean 25.6; highest close 36.45 (7 Mar); VIX/VIX3M above 1 on 15 of 252 days | −19.44% for the year; −25.43% max drawdown | −7.66% for the year |
| **Aug-2024** | 23.39 close (2 Aug) → intraday high 65.73 → 38.57 close (5 Aug); 27.71 on 6 Aug | −3.00% on 5 Aug; −8.49% from 16 Jul to 5 Aug | −2.65% on 5 Aug; +2.85% from 16 Jul to 30 Aug |
| **Apr-2025** | 45.31 close (4 Apr); 60.13 high (7 Apr); 52.33 close (8 Apr), highest since 2020-04-01 | −4.84% on 3 Apr, −5.97% on 4 Apr, +9.52% on 9 Apr; −18.90% from 19 Feb to 8 Apr | −5.67% on 4 Apr |

### Feb-2018 ("Volmageddon")

- XIV hit its acceleration trigger, an intraday indicative value at or below 20% of the prior close, on 5 Feb. It was redeemed at the 15 Feb valuation (Credit Suisse).
- Augustin, Cheng & Van den Bergen (2021) report one-day losses above 90% for short-vol ETPs. They blame a feedback loop: the products had to buy VIX futures to rebalance just as their assets shrank.
- VIX/VIX3M peaked at 1.33. VIX was 11–17 in the preceding week, and the next 21 days realised about 25% **[measured]**.

### Mar-2020

- The largest realised shock in the sample (§1).
- Allianz Global Investors' "Structured Alpha" options funds lost investors over USD 5 bn of about USD 11 bn invested. The SEC charged the firm with concealing the funds' downside risk (SEC 2022).

### 2022

- Implied vol stayed high, the curve rarely inverted, and the realised variance premium stayed **positive** (+89 var pts **[measured]**).
- Put-writing lost money because it is long delta, but far less than the index: −7.7% vs −19.4%.
- **Short vol did comparatively well. A grinding bear market is not a volatility shock.**

### Aug-2024

- **Cause.** A yen-funded carry-trade unwind. BIS Bulletin 90's rough middle estimate of the positions going in is ¥40 trillion, about USD 250 bn.
- **The VIX spike was largely a *quote* effect.** VIX uses mid-quotes, and dealers widened put spreads (BIS Bulletin 95). The SEC DERA paper finds that VIX passed 65 before the open on OTM put mid-quotes, while VIX futures stayed below 35.
- **Aftermath.** Selling at the 5 Aug close (VIX 38.57) was followed by only 16.2% realised vol over 21 days **[measured]**.

### Apr-2025

- Tariffs were announced on 2 Apr, and a 90-day pause on most of them (not China's) followed on 9 Apr (AP).
- VIX more than doubled in four sessions, then fell 35.8% on 9 Apr as SPX rose 9.52% **[measured]**.
- A book stopped out on 4–8 Apr missed the reversal, and once-a-day hedging faced gaps in both directions.

---

## 7. Implications for our design

The details are being decided in `docs/adr/`.

- **Fills.**
  - Never fill at mid: mid-to-mid overstates short-option returns by several percent a month (Santa-Clara & Saretto).
  - Full bid/ask is a *conservative* bound (Muravyev & Pearson). Make the fill a parameter, mid ± $k\cdot$half-spread, and report $k=1$ alongside a sweep.
  - Use each day's actual quoted spread, not a fixed number of basis points.
- **Fill timing.**
  - The signal is computed on day $t$ and fills at $t+1$ quotes.
  - Never mark, stop out or make margin decisions on pre-open quotes (Aug-2024).
  - **Still to check:** a broker's documentation lists SPY options as trading until 4:15 p.m. ET, while SPY closes at 4:00 p.m. **[unverified against exchange rules]**. If true, end-of-day option and stock prices are not synchronous, which affects both IV and delta.
- **Volume caps.** Liquidity is concentrated in near-dated ATM options (Santa-Clara & Saretto). Cap each trade as a fraction of that contract's daily volume.
- **Greek budgets.** Limit dollar gamma ($\Gamma S^2$) and vega. Decompose daily P&L into gamma, theta and vega (§2); a large unexplained residual signals a bug.
- **Hedge frequency.** Hedge daily at the close by default. Report the hedging error and its sensitivity to frequency, since the error scales as $\sqrt{\delta t}$.
- **Capital base.** Report returns on a stated base: cash-secured notional, or margin with forced liquidation. Report skew and max drawdown next to Sharpe.
- **Regime splits.** Report the five stress windows separately, and results by VIX level and VIX/VIX3M.
- **Multiple testing.** We will try many strikes, tenors, thresholds and models, so report the Deflated Sharpe Ratio (Bailey & López de Prado 2014).

---

## 8. References

**Academic**

- Augustin, P., Cheng, I.-H., & Van den Bergen, L. (2021). Volmageddon and the failure of short volatility products. *Financial Analysts Journal* 77(3), 35–51. https://doi.org/10.1080/0015198X.2021.1913040
- Bailey, D. H., & López de Prado, M. (2014). The Deflated Sharpe Ratio: Correcting for selection bias, backtest overfitting, and non-normality. *Journal of Portfolio Management* 40(5), 94–107. https://doi.org/10.3905/jpm.2014.40.5.094
- Bakshi, G., & Kapadia, N. (2003). Delta-hedged gains and the negative market volatility risk premium. *Review of Financial Studies* 16(2), 527–566. https://doi.org/10.1093/rfs/hhg002
- Bertsimas, D., Kogan, L., & Lo, A. W. (2000). When is time continuous? *Journal of Financial Economics* 55(2), 173–204. https://doi.org/10.1016/S0304-405X(99)00049-5
- Bollerslev, T. (1986). Generalized autoregressive conditional heteroskedasticity. *Journal of Econometrics* 31(3), 307–327. https://doi.org/10.1016/0304-4076(86)90063-1
- Britten-Jones, M., & Neuberger, A. (2000). Option prices, implied price processes, and stochastic volatility. *Journal of Finance* 55(2), 839–866. https://doi.org/10.1111/0022-1082.00228
- Broadie, M., Chernov, M., & Johannes, M. (2009). Understanding index option returns. *Review of Financial Studies* 22(11), 4493–4529. https://doi.org/10.1093/rfs/hhp032
- Carr, P., & Wu, L. (2009). Variance risk premiums. *Review of Financial Studies* 22(3), 1311–1341. https://doi.org/10.1093/rfs/hhn038. The figures above are from the May 2004 working paper: https://engineering.nyu.edu/sites/default/files/2019-01/CarrReviewofFinStudiesMarch2009-a.pdf
- Corsi, F. (2009). A simple approximate long-memory model of realized volatility. *Journal of Financial Econometrics* 7(2), 174–196. https://doi.org/10.1093/jjfinec/nbp001
- Coval, J. D., & Shumway, T. (2001). Expected option returns. *Journal of Finance* 56(3), 983–1009. https://doi.org/10.1111/0022-1082.00352
- Demeterfi, K., Derman, E., Kamal, M., & Zou, J. (1999). A guide to volatility and variance swaps. *Journal of Derivatives* 6(4), 9–32. https://doi.org/10.3905/jod.1999.319129
- Dew-Becker, I., Giglio, S., Le, A., & Rodriguez, M. (2017). The price of variance risk. *Journal of Financial Economics* 123(2), 225–250. https://doi.org/10.1016/j.jfineco.2016.04.003. Working paper: https://www.nber.org/papers/w21182
- El Karoui, N., Jeanblanc-Picqué, M., & Shreve, S. E. (1998). Robustness of the Black and Scholes formula. *Mathematical Finance* 8(2), 93–126. https://doi.org/10.1111/1467-9965.00047
- Glosten, L. R., Jagannathan, R., & Runkle, D. E. (1993). On the relation between the expected value and the volatility of the nominal excess return on stocks. *Journal of Finance* 48(5), 1779–1801. https://doi.org/10.1111/j.1540-6261.1993.tb05128.x
- Goyal, A., & Saretto, A. (2009). Cross-section of option returns and volatility. *Journal of Financial Economics* 94(2), 310–326. https://doi.org/10.1016/j.jfineco.2009.01.001
- Johnson, T. L. (2017). Risk premia and the VIX term structure. *Journal of Financial and Quantitative Analysis* 52(6), 2461–2490. https://doi.org/10.1017/S0022109017000825
- Muravyev, D., & Pearson, N. D. (2020). Options trading costs are lower than you think. *Review of Financial Studies* 33(11), 4973–5014. https://doi.org/10.1093/rfs/hhaa010
- Santa-Clara, P., & Saretto, A. (2009). Option strategies: Good deals and margin calls. *Journal of Financial Markets* 12(3), 391–417. https://doi.org/10.1016/j.finmar.2009.01.002. The figures above are from the Nov 2004 working paper: https://escholarship.org/uc/item/0499w44p

**Industry, regulators and news**

- Associated Press (4 May 2025). How the stock market made back all its losses after Trump escalated the trade war. https://www.news4jax.com/news/politics/2025/05/04/how-the-stock-market-made-back-all-its-losses-after-trump-escalated-the-trade-war/
- BIS Bulletin 90 (Aquilina, Lombardi, Schrimpf & Sushko, 27 Aug 2024). The market turbulence and carry trade unwind of August 2024. https://www.bis.org/publ/bisbull90.htm
- BIS Bulletin 95 (Todorov & Vilkov, 29 Oct 2024). Anatomy of the VIX spike in August 2024. https://www.bis.org/publ/bisbull95.htm
- Cboe (27 Jan 2016). New study on weekly, monthly S&P 500 PutWrite indexes released. https://ir.cboe.com/news/news-details/2016/New-Study-On-Weekly-Monthly-SP-500-PutWrite-Indexes-Released-01-27-2016/default.aspx
- Cboe (29 May 2019). White paper shows volatility risk premium facilitated higher risk-adjusted returns for PUT index. https://www.cboe.com/insights/posts/white-paper-shows-volatility-risk-premium-facilitated-higher-risk-adjusted-returns-for-put-index/
- Cboe Volatility Index Methodology, v6.0 (rev. 26 Feb 2026). https://cdn.cboe.com/api/global/us_indices/governance/VIX_Methodology.pdf
- Cboe daily index histories (VIX, VIX3M, SPX, PUT), downloaded 2026-10-28. https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv (replace `VIX` with the symbol)
- Credit Suisse (6 Feb 2018). Credit Suisse AG announces event acceleration of its XIV ETNs, via Mondo Visione. https://mondovisione.com/news/credit-suisse-ag-announces-event-acceleration-of-its-daily-inverse-vix-short-ter-201826
- CXO Advisory. VIX term structure slope and variance asset future returns (secondary summary of Johnson). https://www.cxoadvisory.com/volatility-effects/vix-term-structure-slope-and-variance-asset-future-returns/
- Li, S., & Askanazi, R. (Apr 2025). Demystify the surge in VIX. SEC DERA Working Paper. https://www.sec.gov/files/dera-vix-working-paper-2504.pdf
- SEC Press Release 2022-84 (17 May 2022). Charges against Allianz Global Investors U.S. and three former portfolio managers. https://www.sec.gov/news/press-release/2022-84

**How the [measured] figures were computed.** From Cboe daily closes. RV is the zero-mean, close-to-close variance of SPX log returns over the next 21 trading days, ×252/21, from overlapping windows, compared with $(\text{VIX}_t/100)^2$. SPX is a price index (no dividends); PUT includes T-bill interest. These are one-off calculations, not yet a notebook in this repo.

---

## Questions to test yourself

1. Derive the delta-hedged P&L of a long option under BSM marking. Where does the PDE enter, and what does theta pay for?
2. A 30-day straddle is sold at $\sigma_i=20\%$, and realised vol over its life is exactly 20%. Why can the P&L still be far from zero, and how does a variance swap avoid this?
3. Why does a VRP measured as $\text{VIX}^2$ against close-to-close RV differ from one measured against intraday RV? Which is right for an option seller?
4. If forward variance claims earn about zero (Dew-Becker et al.), what does that imply for a calendar spread that is short the front month and long the back?
5. On 5 Aug 2024 VIX touched 65.73 while VIX futures stayed below 35. What does that say about marking a short-vol book at mid, and about margin-driven exits?
6. Why might a short-put strategy with a high Sharpe over 2007–2026 still be indistinguishable from fair compensation for risk? How does the Deflated Sharpe Ratio change the test?

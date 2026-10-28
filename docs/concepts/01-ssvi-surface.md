# The SSVI implied-vol surface

Milestone 0 draws an **illustrative** SSVI surface as the app's 3D hero ([`src/volbt/illustrative.py`](../../src/volbt/illustrative.py)). It is a made-up shape, not market data. This note derives its maths from first principles and fixes the surface vocabulary later milestones reuse. Numbers tagged **[run]** were reproduced by the script in §9. Lemma, theorem and remark numbers (Lemmas 2.1, 2.2 and 4.2, Theorems 4.1 and 4.2, Remarks 4.3 and 4.4, Example 4.2) were re-read against arXiv:1204.0646v4 of Gatheral & Jacquier (§10); I did not check the journal's numbering.

---

## 1. Coordinates of a vol surface

An option is pinned down by a strike $K$ and an expiry. Four quantities locate a point on the surface:

- **Log-moneyness** $k=\ln(K/F)$, where $F$ is the forward price for that expiry. The forward absorbs rates and dividends, so $k=0$ is at-the-forward at every expiry. $k<0$ is a low-strike (put-side) option; $k=-0.1$ means $K=e^{-0.1}F\approx0.905F$ **[run]**.
- **Time** $T$ in years. The code uses DTE/365 (`illustrative.py:41`).
- **Implied vol** $\sigma(k,T)$: the Black–Scholes vol that reproduces the option's price.
- **Total implied variance** $w(k,T)=\sigma(k,T)^2\,T$.

**Why $w$ is the natural coordinate.**

1. A Black–Scholes call price, undiscounted and per unit of forward, depends on vol and time only through $w$. Price is a function of $(k,w)$.
2. Variance accumulates. At the money, $w(0,T_2)-w(0,T_1)$ is roughly the variance priced for the stretch between two expiries, and it cannot be negative.
3. Calendar no-arbitrage is therefore one clean statement: at fixed $k$, $w(k,T)$ is non-decreasing in $T$. In vol terms it is awkward: $\sigma$ may fall with $T$ (inverted term structure) with no arbitrage, because $T$ grows faster than $\sigma^2$ shrinks.

## 2. Smile and skew

Plot $\sigma$ against $k$ at one expiry. Black–Scholes predicts a flat line; equity indices give a downward slope called the **skew** (the curvature is the **smile**). Two stories, which reinforce each other:

- **Crash demand.** Investors buy out-of-the-money puts to insure portfolios, and dealers who sell them charge for gap risk. That bids up low-strike vol.
- **Leverage effect.** When a stock falls, leverage rises and equity gets riskier, so vol rises when prices fall. In stochastic-vol models this negative spot–vol correlation produces the skew; SSVI's $\rho$ plays that role. [00-background](00-background.md) §1 reports a daily SPX–VIX-change correlation of $-0.79$ (measured there, not here).

**Sign of $\rho$.** $\rho<0$: low strikes carry more vol (the equity shape). $\rho>0$: the mirror image. $\rho=0$: symmetric smile. The code ships $\rho=-0.7$ (`illustrative.py:35`).

## 3. SSVI

SSVI ("surface SVI") writes the whole surface through the ATM total variance $\theta(T)=w(0,T)=\sigma_{\text{ATM}}(T)^2\,T$:

$$w(k,\theta)=\frac{\theta}{2}\left(1+\rho\,\varphi(\theta)\,k+\sqrt{\big(\varphi(\theta)\,k+\rho\big)^2+1-\rho^2}\right),\qquad \varphi(\theta)=\frac{\eta}{\sqrt{\theta}} .$$

In the code, $\varphi(\theta)=\eta/\sqrt\theta$ is `phi()` (`illustrative.py:60–62`) and the formula is `total_variance` (lines 65–70). $\theta(T)$ is `atm_total_variance` (lines 54–57), with $\sigma_{\text{ATM}}$ a straight line from 16% at 7 days to 20% at 365 (`sigma_atm`, lines 48–51; constants, lines 31–32). Shipped parameters: $\rho=-0.7$, $\eta=1$ (lines 35–36).

**Worked example.** Use the point in `tests/test_illustrative.py`: 365 days, so $T=1$, $\sigma_{\text{ATM}}=0.20$, $\theta=0.2^2\cdot1=0.04$.

**(a) At the money, $k=0$.** Then $\varphi k=0$ and

$$w=\frac{\theta}{2}\Big(1+0+\sqrt{\rho^2+1-\rho^2}\Big)=\frac{\theta}{2}(1+1)=\theta=0.04 ,$$

for any $\rho$. **[run]**

**(b) Off the money, $k=-0.1$.**

- $\varphi=1/\sqrt{0.04}=1/0.2=5$, so $\varphi k=-0.5$.
- $\rho\varphi k=(-0.7)(-0.5)=0.35$.
- $(\varphi k+\rho)^2=(-1.2)^2=1.44$ and $1-\rho^2=1-0.49=0.51$, so the radicand is $1.95$ and $\sqrt{1.95}=1.39642$.
- $w=0.02\,(1+0.35+1.39642)=0.02\times2.74642=0.054928$. **[run]**

At $k=+0.1$: $\varphi k=0.5$, $\rho\varphi k=-0.35$, $(0.5-0.7)^2=0.04$, radicand $0.04+0.51=0.55$, $\sqrt{0.55}=0.74162$, so $w=0.02\,(1-0.35+0.74162)=0.027832$. **[run]**

**(c) Total variance to IV.** $\sigma=\sqrt{w/T}$, and here $T=1$:

- $k=-0.1$: $\sqrt{0.054928}=0.234368$, **23.44%**.
- $k=0$: $\sqrt{0.04}=0.20$, **20%**.
- $k=+0.1$: $\sqrt{0.027832}=0.166830$, **16.68%**. **[run]**

**$T$ matters.** Take the same $k=-0.1$ at 7 days: $T=7/365=0.019178$, $\sigma_{\text{ATM}}=0.16$, $\theta=0.0256\times0.019178=0.00049096$. Then $\varphi=1/\sqrt\theta=45.13$ and $\varphi k=-4.513$. The formula gives $w=0.0023127$ and $\sigma=\sqrt{0.0023127/0.019178}=$ **34.73%**, against 16% at the money. **[run]** For a one-week option, 10% below the forward is deep in the wings.

## 4. What each parameter does

- **$\theta(T)$: level and term structure.** At $k=0$, $w=\theta$ exactly, so $\theta$ sets each slice's height. Shipped: $\theta=0.00049$ at 7 days, $0.0165$ at 186 days, $0.04$ at 365 **[run]**, with ATM vol drifting up from 16% to 20%.
- **$\rho$: tilt.** It rotates the smile about the money. Far out, $w$ grows linearly in $|k|$ with slopes $(1-\rho)\theta\varphi/2$ on the left and $(1+\rho)\theta\varphi/2$ on the right (G&J Remark 4.3; I re-derived it from the formula). At $\theta=0.04$ and $\rho=-0.7$ these are $0.17$ and $0.03$ **[run]**: steep put wing, nearly flat call wing. Positive $\rho$ mirrors the picture (tested in `test_positive_rho_flips_the_skew`).
- **$\eta$: curvature and wings.** Since $\varphi k=\eta\,k/\sqrt\theta$, and $\sqrt\theta=\sigma_{\text{ATM}}\sqrt T$ is the standard deviation of the log-return implied by ATM vol, the smile depends on moneyness only through $k$ *measured in ATM standard deviations*. $\eta$ scales how fast the smile bends per standard deviation. The same $k$ is far more standard deviations out at 7 days than at one year; that is why the 7-day IV above is 34.7% and the one-year IV 23.4%.

The ATM skew implied by this $\varphi$ is $\partial_k\sigma|_{k=0}=\rho\eta/(2\sqrt T)$ (G&J Example 4.2): $-0.35$ at one year, $-2.53$ at 7 days **[run, by finite difference]**. Skew steepens as $T^{-1/2}$.

## 5. No-arbitrage

An arbitrage is a portfolio that costs nothing or less, can never lose, and can win. *Static* arbitrage needs no model of how prices move, only the surface.

**Butterfly.** Buy calls at $K-h$ and $K+h$, sell two at $K$. The payoff is never negative, so the price must be $\ge0$: call prices must be convex in $K$. As $h\to0$ the cost per $h^2$ becomes $\partial^2C/\partial K^2$, which (Breeden–Litzenberger) is the discounted risk-neutral density at $K$. So convexity fails exactly where the density is negative. G&J Lemma 2.2 turns this into a test on the smile: a slice is free of butterfly arbitrage **if and only if** $g(k)\ge0$ for all $k$ (their eq. 2.1, a combination of $w$, $w'$ and $w''$) **and** the single right-wing limit $\lim_{k\to+\infty}d_+(k)=-\infty$, where $d_\pm(k)=-k/\sqrt{w(k)}\pm\sqrt{w(k)}/2$. There is no separate left-wing condition in the lemma.

**Calendar.** With proportional dividends and equal forward-moneyness, a longer-dated call is worth at least as much as a shorter-dated one (G&J Lemma 2.1; the underlying-over-forward ratio is a martingale and the call payoff is convex). If $w$ fell with $T$ at some $k$, the longer option would be cheaper: buy it, sell the shorter, and collect a credit. Lemma 2.1 states it as an if-and-only-if: no calendar arbitrage $\iff\partial_t w(k,t)\ge0$ for all $k$ and $t>0$.

**SSVI sufficient conditions** (G&J 2014; Theorems 4.1 and 4.2 in the arXiv preprint, journal numbering not checked). For all $\theta>0$:

1. $\theta\varphi(\theta)(1+|\rho|)<4$
2. $\theta\varphi(\theta)^2(1+|\rho|)\le4$

together rule out butterfly arbitrage. Condition 1 caps the wing slope of $w$ at 2, Lee's moment-formula bound (G&J Remark 4.3); its non-strict form is necessary (G&J Lemma 4.2). Calendar (Theorem 4.1): $\theta$ non-decreasing in $T$, and $0\le\partial_\theta(\theta\varphi)\le\frac{1}{\rho^2}\big(1+\sqrt{1-\rho^2}\big)\varphi$ for all $\theta>0$ (the upper bound is infinite at $\rho=0$); this is if-and-only-if.

**Not every $\varphi$ is certified for every expiry.** For a power law $\varphi=\eta\theta^{-\gamma}$ (ours is $\gamma=\tfrac12$), condition 1 above needs $\theta\varphi(1+|\rho|)<4$ at every $\theta$, but $\theta\varphi=\eta\theta^{1-\gamma}$ grows without bound, so by G&J Remark 4.4 such a surface can be certified arbitrage-free only up to a maximum expiry $t^*_0$, where $\theta\varphi(1+|\rho|)$ reaches 4. For $\gamma=\tfrac12$ that is $\theta=\big(4/(\eta(1+|\rho|))\big)^2=(4/1.7)^2=5.54$, about 138 years at a flat 20% vol **[run]**: irrelevant for a one-year grid, but it is why the guarantee is "up to $t^*_0$" and not "for all expiries".

**By hand for the shipped parameters.** With $\varphi=\eta/\sqrt\theta$: $\theta\varphi=\eta\sqrt\theta$ and $\theta\varphi^2=\eta^2$.

- Condition 1: $\eta\sqrt\theta(1+|\rho|)$ peaks at the longest expiry: $1\times0.2\times1.7=0.34<4$ (0.038 at 7 days).
- Condition 2: $\eta^2(1+|\rho|)=1.7\le4$ at *every* expiry; $\theta$ cancels.
- Calendar: $\theta$ rises from 0.00049 to 0.04; the smallest step between adjacent grid expiries is 0.0014. And $\partial_\theta(\theta\varphi)=\eta/(2\sqrt\theta)=\varphi/2$, so the ratio is $\tfrac12$, inside $[0,\,(1+\sqrt{0.51})/0.49=3.498]$. This holds for *every* $\theta$, $\eta$ and $|\rho|<1$ (it needs only $\rho^2/2\le\tfrac12<1\le1+\sqrt{1-\rho^2}$), so for this $\varphi$ Theorem 4.1 reduces to "$\theta$ non-decreasing". The $w$ table agrees: its smallest rise between adjacent expiries, over $k\in[-1,1]$, is $6.3\times10^{-4}$ (at $k=0.08$, first two expiries). **[run]**
- **$\eta=2$:** condition 2 gives $4\times1.7=6.8>4$, so it fails (condition 1 gives $0.68$, fine). The threshold is $\eta\le\sqrt{4/1.7}=1.534$. Condition 1 alone would not fail until $\eta\approx11.8$ at $T=1$.

**What the code checks, and does not.** `butterfly_conditions(theta, rho, eta)` (`illustrative.py:88-113`) is a pure function of its arrays: condition 1 is a strict `< 4`, condition 2 is `<= 4`, and both must hold at every expiry passed in. Their boundaries are tested exactly, with values that are exact in binary (`rho = 0`, `theta = 1` or `16`): `test_butterfly_2_passes_exactly_at_4`, `test_butterfly_1_fails_exactly_at_4_because_it_is_strict` and the just-above and just-below tests next to them (`tests/test_illustrative.py`). `no_arbitrage_checks` (`:129-164`) adds `calendar`, in two parts (`calendar_condition`, `:116-126`):

1. $\theta(T)$ must be non-decreasing; and
2. the total variance table $w(k,T)$, built from those expiries over 201 log-moneyness points $k\in[-1,1]$ (`CALENDAR_CHECK_K`, wider than the drawn $[-0.30,0.20]$), must be non-decreasing in $T$ at every $k$ (Lemma 2.1).

The ATM term structure is a parameter (`sigma_short`, `sigma_long`, defaulting to 16% and 20%), so the check can fail: with 100% vol at 7 days and 5% at one year, $\theta$ falls from 0.0192 to 0.0025 and `calendar` is `False` while both butterfly flags stay `True`, and the exporter raises instead of writing the file **[run]** (`test_inverted_term_structure_fails_calendar_only`; `test_refuses_to_export_an_inverted_term_structure` in `tests/test_export.py`). Before, $\theta$ was a hard-coded rising function of DTE, so `np.diff(theta) >= 0` could not be `False` and the exporter's guard could never trip on calendar.

*What the check adds, honestly.* For $\varphi=\eta/\sqrt\theta$ the second condition of Theorem 4.1 holds identically (§5, by hand), so $\theta$ rising already implies $w$ rising at every $k$: the $w$ table can never disagree with the $\theta$ comparison. `test_phi_condition_of_gatheral_jacquier_theorem_4_1_holds_for_phi_eta_over_sqrt_theta` checks the inequality numerically for several $\rho$ including the shipped one, by finite difference of $\theta\varphi$. The table comparison is therefore a direct check on the numbers we draw, not extra detection power, and it samples 201 values of $k$; the analytic argument is what covers every $k$. Two gaps remain. It checks only the expiries passed in, not all $\theta>0$ (G&J Remark 4.4, above: for $\varphi=\eta/\sqrt\theta$ condition 1 stops holding beyond $t^*_0$). And it never inspects an option price or a density.

**The conditions are sufficient, not necessary.** Testing $g(k)\ge0$ directly for $k\in[-6,6]$ **[run]**: at $\rho=-0.7$ and expiries of 7 and 365 days, $\eta=1$ and $\eta=2$ both stay positive (minimum $g\approx0.2$ to $0.26$). So $\eta=2$ fails the sufficient test yet shows no negative density there. $\eta=3$ goes negative (minimum $-0.113$ at 365 days, near $k=-0.1$): a genuine negative density. The exporter refuses any parameters failing the check (`tools/export_app_data.py:48–50`), so it is deliberately stricter than necessary.

## 6. Assumptions and where it breaks

- **A parametric fit, not data.** Two shape parameters plus a $\theta$ curve describe the whole surface. Real quotes have bid/ask spreads, gaps, noise and discrete strikes, and SPY options are American on a dividend-paying ETF ([00-background](00-background.md) §1).
- **One shape for every expiry.** $\varphi=\eta/\sqrt\theta$ forces one shape in $k/\sqrt\theta$; real expiries can bend independently.
- **Short-dated skew.** Combining $\partial_k\sigma=\rho\sqrt\theta\varphi/(2\sqrt T)$ with condition 2 gives $|\partial_k\sigma|\le|\rho|/\sqrt{(1+|\rho|)T}$ (my derivation, inside the sufficient conditions only): $3.88$ at 7 days (shipped: $2.53$) and $0.537$ at one year (shipped: $0.35$) **[run]**. For fixed $\rho$, a market skew growing faster than $T^{-1/2}$ as $T\to0$ falls outside the certified region. Whether SPY does is a milestone 1 question; I have not checked.
- **Statics only.** A surface is a snapshot. When spot moves, **sticky strike** keeps each strike's IV fixed (the smile slides along $k$); **sticky delta** keeps IV fixed per moneyness (the smile stays put in $k$). They imply different hedge ratios and P&L. SSVI chooses neither; the hedging engine (milestone 3) must.
- **Why "illustrative — not market data".** The 16% and 20% ATM vols were chosen "for looks" (`illustrative.py:28–30`); $\rho=-0.7$ is described there as a typical equity-index skew and $\eta=1$ as well inside the no-arbitrage limits (lines 33–34). None is fit to any date. The JSON carries `"illustrative": true` and the label (`export_app_data.py:31,53–54`).

## 7. Where this goes next

Milestone 1 loads and cleans the real SPY option quotes (the data layer and quality filters); it does not replace the hero. Milestone 2, the pricing core, does: it implies a forward per expiry from put-call parity, solves implied vols, and fits smiles in total variance, which is the first point at which a real surface exists. The same $(k,T,w)$ coordinates apply, but the §5 conditions become diagnostics on noisy data rather than guarantees of a clean formula. The app's surface "cinema" will animate those surfaces through time.

## 8. Explain it back

1. Why is $w=\sigma^2T$, not $\sigma$, the right coordinate for calendar no-arbitrage? Give a case where $\sigma$ falls with $T$ and nothing is wrong.
2. Compute $w$ and the IV at $k=+0.1$ for $\theta=0.04$, $\rho=-0.7$, $\eta=1$. Why is it below the $k=-0.1$ value?
3. A butterfly has a non-negative payoff. Show that a negative price means a negative risk-neutral density.
4. For $\varphi=\eta/\sqrt\theta$, what do $\theta\varphi$ and $\theta\varphi^2$ reduce to? Why does the code flag $\eta=2$ if its density is positive?
5. Name two things SSVI cannot tell a hedging engine.
6. For $\varphi=\eta/\sqrt\theta$, why can the $w$-table calendar check never disagree with "$\theta$ non-decreasing"? What would you have to change for the table check to catch something the $\theta$ check misses?

## 9. Reproduce

From the repo root. `uv run python` imports `volbt` directly: the package is installed in editable mode by the `uv_build` backend, so no `PYTHONPATH` is needed.

```bash
uv run python - <<'EOF'
import numpy as np
from volbt import illustrative as ill
r, e = ill.RHO, ill.ETA
a = 1 + abs(r)
th = float(ill.atm_total_variance(365))
print(th, ill.total_variance(0.0, th))                       # (a)
for k in (-0.1, 0.1):
    w = ill.total_variance(k, th); print(k, w, np.sqrt(w))   # (b), (c)
th7 = float(ill.atm_total_variance(7)); w7 = ill.total_variance(-0.1, th7)
print(th7, 1/np.sqrt(th7), w7, np.sqrt(w7/(7/365)))          # the 7-day point
print(np.exp(-0.1), float(ill.atm_total_variance(186)))      # sections 1, 4
print((1 - r)*e*np.sqrt(th)/2, (1 + r)*e*np.sqrt(th)/2)      # wing slopes
iv = lambda k, d: np.sqrt(ill.total_variance(k, float(ill.atm_total_variance(d)))/(d/365))
print([(iv(1e-5, d) - iv(-1e-5, d))/2e-5 for d in (7, 365)]) # ATM skew
print([abs(r)/np.sqrt(a*d/365) for d in (7, 365)])           # skew cap, section 6
_, grid, _ = ill.iv_grid(); t = ill.atm_total_variance(grid)
print(e*np.sqrt(t[-1])*a, e*np.sqrt(t[0])*a, e**2*a)         # conditions 1 (365d, 7d), 2
print(2*np.sqrt(t[-1])*a, 2**2*a, np.sqrt(4/a), 4/(0.2*a))   # eta = 2; thresholds
print((1 + np.sqrt(1 - r*r))/(r*r), np.diff(t).min())        # calendar bound; smallest step
print(ill.no_arbitrage_checks(grid), ill.no_arbitrage_checks(grid, eta=2.0))
print(ill.no_arbitrage_checks(grid, sigma_short=1.0, sigma_long=0.05))  # inverted term structure: calendar False
w = ill.total_variance(ill.CALENDAR_CHECK_K[None, :], t[:, None]); d = np.diff(w, axis=0)
print(d.min(), ill.CALENDAR_CHECK_K[d.argmin() % d.shape[1]])           # smallest w rise between expiries; its k
print((4/(e*a))**2, (4/(e*a))**2/0.2**2)                                # t*_0: theta, then years at a flat 20%

def g(k, t, r, e):                                           # G&J (2014) eq. 2.1, by hand
    p = e/np.sqrt(t); x = p*k + r; s = np.sqrt(x*x + 1 - r*r); w = t/2*(1 + r*p*k + s)
    w1 = t/2*(r*p + p*x/s); w2 = t/2*p*p*(1 - r*r)/s**3
    return (1 - k*w1/(2*w))**2 - w1**2/4*(1/w + .25) + w2/2
ks = np.linspace(-6, 6, 24001)
for eta in (1, 2, 3):                                        # min g over k, at 7d and 365d
    print(eta, [round(float(g(ks, float(ill.atm_total_variance(d)), r, eta).min()), 3) for d in (7, 365)])
EOF
```

## 10. References

- Gatheral, J., & Jacquier, A. (2014). Arbitrage-free SVI volatility surfaces. *Quantitative Finance* 14(1), 59–71. https://doi.org/10.1080/14697688.2013.819986 (DOI and bibliographic details confirmed via Crossref). Theorem statements and numbering above are from the preprint, arXiv:1204.0646v4.
- Gatheral, J. (2006). *The Volatility Surface: A Practitioner's Guide.* Wiley. ISBN 978-0-471-79251-2 (background; bibliographic details from bookseller listings, not opened).
- Lee, R. W. (2004). The moment formula for implied volatility at extreme strikes. *Mathematical Finance* 14(3), 469–480. https://doi.org/10.1111/j.0960-1627.2004.00200.x (details confirmed via Crossref; I cite it only as G&J do, and did not read it).

# Black-76: pricing an option on the forward

## First principles

An option's value today is the discounted average of what it pays at expiry. What it pays depends on one number: the stock price at expiry, *S_T*. So the model only needs two things about *S_T*: where it is centred, and how spread out it is.

Terms:
- **Forward price** *F*: the price agreed today for delivery of the stock at expiry, with nothing paid up front. Under the pricing measure it is the expected value of *S_T*, so it is the centre of the distribution. Put-call parity reads it straight off the market's call and put quotes ([concept 03](03-put-call-parity-forward-and-spot.md)).
- **Strike** *K*: the price at which the option lets you buy (a call) or sell (a put).
- **Time to expiry** τ: calendar days to expiry divided by 365 (ADR-0008 §5).
- **Rate** *r*: the continuous interest rate, from FRED DGS3MO (ADR-0007). **Discount factor** *DF* = e^(−r·τ).
- **Volatility** σ: the standard deviation of ln(*S_T*/*F*) per square root of a year, as a decimal (0.20 = 20%).
- *N*(x): the standard normal cumulative distribution; *n*(x) its density.

**Why the forward and not the spot.** Black-Scholes is written in the spot *S* and needs to know how the stock gets from *S* today to *F* at expiry: the interest rate minus a dividend yield *q*. SPY does not pay a yield. It pays four discrete dividends a year, mostly on expiry Fridays, so a continuous *q* misprices the forward by about one dividend across an ex-date (ADR-0008, Alternatives). Black (1976) writes the same model in *F* directly. The dividend is already inside *F*, so the model never needs *q*. That is the whole reason this project uses Black-76.

## The maths

Assume ln(*S_T*/*F*) is normal with variance σ²τ and mean −½σ²τ (so that the average of *S_T* is *F*). Then:

- d₁ = (ln(F/K) + ½σ²τ) / (σ√τ), and d₂ = d₁ − σ√τ
- C = DF · [F·N(d₁) − K·N(d₂)]
- P = DF · [K·N(−d₂) − F·N(−d₁)]

*N*(d₂) is the probability that the call ends in the money. *F*·*N*(d₁) is E[*S_T*·1{*S_T* > *K*}]: the expected stock at expiry counting only the paths that end in the money (a path that ends out of it adds 0), so not an average over those paths. That average, E[*S_T* | *S_T* > *K*], is *F*·*N*(d₁)/*N*(d₂), which is above *K*. So C = DF·[E(*S_T*·1{*S_T* > *K*}) − *K*·P(*S_T* > *K*)] = DF·E[(*S_T* − *K*)⁺].

**Put-call parity** falls out of the formulas: C − P = DF·(F − K), because N(x) + N(−x) = 1.

**No-arbitrage bounds.** A call is worth more than its discounted intrinsic value and less than the discounted forward: DF·max(F − K, 0) < C < DF·F. A put: DF·max(K − F, 0) < P < DF·K. A price on or outside a bound has no σ at all, which is why the IV solver checks them first ([concept 09](09-implied-vol-solving.md)).

**Worked example**, ADR-0008 test 3 (computed with `uv run python -c` against `src/volbt/pricing/black76.py`, 2026-10-29): F = K = 400, σ = 0.20, τ = 30/365, r = 0.

- σ√τ = 0.20 × √0.082192 = 0.0573382
- d₁ = (0 + ½ × 0.0573382²)/0.0573382 = 0.0286691; d₂ = −0.0286691
- C = 400 × [N(0.0286691) − N(−0.0286691)] = 400 × (0.5114358 − 0.4885642) = **9.148603**
- At the money with r = 0 the put is the same, 9.148603: C − P = DF·(F − K) = 0.

`tests/test_black76.py` pins this value, Hull's textbook Black's-model put (futures 20, strike 20, r = 9%, σ = 25%, 4 months: 1.117), and parity and the bounds on 2,000 random cases.

## Assumptions

- **Lognormal at one σ.** One σ for one strike and expiry. The market's σ differs by strike (the smile), so each quote gets its own implied σ ([concept 11](11-smile-in-total-variance.md)).
- **European exercise.** SPY options are American. The surface is made European-equivalent first, by taking the early-exercise premium off each mid ([concept 10](10-crr-lattice-and-de-americanisation.md)).
- **One rate for every expiry.** In Black-76 itself r enters only through *DF*. But *F* is parity on mids with their early-exercise premium removed, and that premium is priced on a lattice whose carry runs at the same rate, so a rate error moves *F* too (M2 round 2, design claim 9, which refuted "leaves *F* alone"): a one-day change of DGS3MO on 2023-03-20 moved forwards within 60 days by up to 0.53 bp (`uv run python tools/report_m2.py`, block "the rate's date"), and a per-expiry carry-consistent rate would move forwards beyond 180 days by up to +42.5 bp (the round-2 reviewer's measurement; ADR-0008 amendment 8, proposed).
- **A forward that is right.** Everything is relative to *F*; a forward wrong by 5 bp shifts every log-moneyness by 5 bp.

## Where it breaks

- **At expiry.** τ = 0 makes σ√τ = 0 and d₁ a division by zero. On the expiry date the contract is worth its intrinsic value and no formula is evaluated (ADR-0008 test 6).
- **American quotes taken as European.** At 5% rates an American put's premium lowers C − P and drags the parity forward low: about −4.3 bp on ADR-0008's synthetic chain (test 8).
- **Prices too small for floats.** Deep out-of-the-money, short-dated, low-vol prices underflow to exactly 0, which is on the lower bound, or to a few float steps above it. They have no IV: the solver returns `IV_FAIL` with the reason `below_lower_bound` or `unresolved` instead of guessing (`tests/test_iv.py`).

## In this project

- `src/volbt/pricing/black76.py:52` `d1_d2`, `:60` `price`, `:70` `intrinsic`, `:76` `price_bounds`, `:90` `vega`.
- `src/volbt/pricing/forward.py:72` `parity_forward`: the *F* every price is computed on.
- `src/volbt/pricing/chain.py:85` `price_chain`: every quote of a snapshot priced on its expiry's de-Americanised forward.

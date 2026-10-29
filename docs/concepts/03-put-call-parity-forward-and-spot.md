# Put-call parity: the implied forward and the implied spot

## First principles

Take a call and a put on the same stock, with the same strike *K* and the same expiry. Buy the call and sell the put. At expiry you hold exactly one share minus *K* dollars, whatever the price does:

- if the stock ends above *K*, the call pays *S − K* and the put is worthless;
- if it ends below *K*, the call is worthless and you pay *K − S* on the put, which is again *S − K*.

So "long call, short put" is a **forward contract**: an agreement to buy the stock at *K* on the expiry date. Two portfolios with the same payoff must cost the same today. That is **put-call parity**.

Terms:
- **Forward price** *F*: the price agreed today for delivery at expiry, with nothing paid up front.
- **Discount factor** *DF* = e^(−r·τ): what one dollar paid at expiry is worth today, at the continuous rate *r* over τ years.
- **Dividends**: a share bought today collects the dividends paid before expiry; a forward does not. So the forward is lower than the spot by their value.

## The maths

For European options:

C − P = DF · (F − K)

So each strike gives its own estimate of the forward, **F_K = K + (C − P) / DF**.

The forward and the spot are tied by the carry: F = (S − PV(dividends)) / DF. Turn it round to get the **implied spot**:

S = F · DF + PV(dividends), with PV(dividends) = Σ D_i · e^(−r·τ_i) over the ex-dates before expiry.

Worked example (computed with `uv run python`, 2026-10-29). S = 400, r = 5%, τ = 14/365, no dividend:

- DF = e^(−0.05 × 14/365) = 0.9980840
- F = 400 / DF = 400.76786
- At K = 400 the call must cost 0.76639 more than the put: C − P = DF × (F − K).
- Reading it back, F_K = 400 + 0.76639 / 0.9980840 = 400.76786, and F · DF = 400.00000.

With a $1.50 dividend going ex in 4 days, PV = 1.5 × e^(−0.05 × 4/365) = 1.49918, so F = 399.26580. Adding the PV back gives the spot, 400.00000. Leaving it out would make the spot $1.50 too low (about 37 bp). `tests/test_crossvendor.py` checks both cases.

**Which F.** One strike is noisy. ADR-0008 §3 takes K\*, the strike where C and P are closest (the money), and uses the median F_K over the 5 strikes nearest K\*. We use the same rule (`src/volbt/data/crossvendor.py:107-131`).

**The rate.** FRED's DGS3MO is a 91-day bill yield in percent, on the investment basis. ADR-0007 converts it: r_cc = (365/91) · ln(1 + y/100 · 91/365). DGS3MO = 5.25 gives 0.0521594 (`tests/test_reference.py`).

## Assumptions

- **European exercise.** SPY options are American. An American put can be worth more than its European twin, which pushes C − P down and the implied forward low. ADR-0008 measured 4-7 bp at 5% rates. M1 does not correct this; M2 does (de-Americanisation). The M1 data show it: OptionsDX's parity spot sits a median +1.08 bp from the SPY close in 2020 and −2.49 bp in 2023, as the mean DGS3MO rose from 0.35% to 5.28% (`uv run python tools/report_m1.py`, block "cross-vendor", the per-year lines).
- **Known dividends.** We use the dividends SPY really paid (yfinance). That is fine for a diagnostic. A strategy may not use future dividends.
- **Both quotes are real.** The mids must come from two-sided quotes: no null side, no zero bid, not crossed.
- **Same moment.** The call, the put and the spot we compare with were all observed at the same time.

## Where it breaks

- **Stale or one-sided quotes** give a wrong mid and a wrong F_K. The median over 5 strikes damps one bad strike, not five.
- **Very short expiries.** With τ near zero, a one-cent error in C − P is a large error in F. We skip expiries under 7 days (`crossvendor.py:48`).
- **The last assumption is the point of the test.** If a vendor snapshots at 3:30 pm, its implied spot tracks the 3:30 price, not the 4:00 close. That is how we read a snapshot time from quotes alone.

On 2020-23 (572 dates where both vendors exist), the implied spot from OptionsDX, stamped at 16:00, sits a median −0.6 bp from the SPY close (5-95%: −10.3 to +12.7 bp). DoltHub's sits +1.3 bp (−18.2 to +21.2). Against the open, both miss by about 70 bp on average. So DoltHub's snapshot is near the close, but noisier. Source: `data/store/build_summary.json`, built by `uv run python tools/build_data.py` on 2026-10-29 (the rebuild after round 2 of the M1 review).

## In this project

- `src/volbt/data/crossvendor.py:107-131`: `parity_spot`.
- `src/volbt/data/reference.py:48-51`: `r_cc_from_dgs3mo`.
- `src/volbt/data/reference.py:160-169`: `spy_dividends_pv`.
- M2 (ADR-0008 §3) uses the same forward for pricing, after removing the American premium.

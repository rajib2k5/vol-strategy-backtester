# The OSI option symbol

## First principles

A listed option is fixed by four facts: the **underlying** (its root, such as SPY), the **expiry date**, the **side** (call or put) and the **strike**. Two vendors that describe the same contract with different column names still mean the same four facts.

The **OSI symbol** (Options Symbology Initiative, adopted by the US options industry in 2010) writes those four facts as one fixed-width string of 21 characters. Brokers and the OCC use it. Because every field has a fixed place and width:

- the string is **unique** per contract;
- it **sorts** by root, then expiry, then side, then strike;
- it can be **parsed back** without any lookup table.

That makes it a good key for `option_quotes`: one row per (`source`, `quote_date`, `osi_symbol`).

## The maths

```
SPY   240315C00450000
^^^^^^                 root, left-justified, padded with spaces to 6 characters
      ^^^^^^           expiry as yymmdd: 2024-03-15
            ^          C (call) or P (put)
             ^^^^^^^^  strike x 1000, zero-padded to 8 digits: 450.000 -> 00450000
```

Worked examples (printed by `uv run python` with `volbt.data.osi`, 2026-10-29):

- (SPY, 2024-03-15, C, 450.00) → `SPY   240315C00450000`
- (SPY, 2022-06-17, P, 365.50) → `SPY   220617P00365500`
- `parse_osi("SPY   220617P00365500")` → `('SPY', date(2022, 6, 17), 'P', Decimal('365.500'))`

**Why thousandths as an integer.** The strike field counts thousandths of a dollar. We compute it with `Decimal`, not with a float. In binary floating point 1.005 × 1000 is 1004.9999999999999, so `int()` would write 1004 instead of 1005. The vectorised builder rounds to the nearest integer and refuses any strike more than 10⁻⁶ away from the 1/1000 grid (`src/volbt/data/osi.py:69-82`).

## Assumptions

- The root has 1 to 6 characters.
- The expiry year is 2000-2099: the year has only two digits.
- The strike is between 0 and 99,999.999 dollars, in whole thousandths.
- One root per table. Our tables hold SPY only, so the symbol is a function of (expiry, side, strike).

## Where it breaks

- **Adjusted contracts.** After a split or a special dividend, the OCC lists "adjusted" options with a new root (for example `SPY1`). Their deliverable is not 100 shares. SPY has never split, and neither vendor lists adjusted SPY roots, so M1 does not handle them.
- **Strikes beyond 8 digits** or **finer than 1/1000** cannot be written. The builder raises instead of rounding silently.
- **Non-standard expiries.** The symbol records the date, not the type (monthly, weekly, end-of-month). A strategy that wants monthlies must work that out from the date (ADR-0002 §5).

## In this project

- `src/volbt/data/osi.py:35-43`: `strike_to_milli`.
- `src/volbt/data/osi.py:46-54`: `osi_symbol`, and `:57-66` `parse_osi`, its inverse.
- `src/volbt/data/osi.py:69-82`: `osi_symbols`, the same strings for millions of rows; a test checks it agrees with the scalar version.
- `src/volbt/data/quotes.py:107`: every clean row gets its symbol.
- `src/volbt/data/mask.py:35-36`: the mask matches strikes on the same integer thousandths.

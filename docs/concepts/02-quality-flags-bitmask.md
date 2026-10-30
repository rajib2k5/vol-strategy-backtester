# Quality flags as a bitmask

> **Data notice.** The DoltHub figures in this document (counts, dates, quantiles and summaries, in its text and in its tables) are derived from the DoltHub database `post-no-preference/options` (<https://www.dolthub.com/repositories/post-no-preference/options>), licensed [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/), and are shared under the same licence. Changes: we aggregated it into counts, shares and quantiles, compared it with OptionsDX and ran our pricing build on it; no quote row is reproduced. The rest of this repository is MIT. See [DATA.md](../../DATA.md).

## First principles

A quote can be bad in several ways at once. Its bid can be zero. Its vendor IV can be missing, or zero, or negative. Its date can be a holiday. We want to keep every quote and say exactly what is wrong with it.

A **bitmask** does that with one integer. An integer is stored as bits, each 0 or 1. We give each problem its own bit. Bit *b* has the value 2^*b*, written `1 << b` in Python ("1 shifted left by b places").

- To **set** several problems, add their bits with OR (`|`). OR keeps every bit that is 1 in either number.
- To **test** one problem, AND (`&`) the mask with that bit. The result is non-zero only if the bit is set.

Each consumer then reads only the bits it cares about. The marking rule (ADR-0004) asks about `ZERO_BID`. The fill rule (ADR-0002) asks about `CROSSED`. Nobody has to agree on one "good quote" rule, and no row is deleted.

## The maths

ADR-0009 §3 fixes 13 bits, 0 to 12 (`src/volbt/data/flags.py:34-46`).

Worked example. A quote with a zero bid and no usable vendor IV:

- `ZERO_BID` is bit 2, so its value is 2² = 4.
- `VENDOR_IV_INVALID` is bit 11, so its value is 2¹¹ = 2048. It is set when the vendor's IV is null or ≤ 0.
- The mask is 4 | 2048 = 2052, binary `0b100000000100`.
- 2052 & 4 = 4, which is non-zero: the bid is zero.
- 2052 & 8 = 0: the quote is not `CROSSED` (bit 3).

These values were printed by `uv run python -c "from volbt.data import flags; print(flags.ZERO_BID | flags.VENDOR_IV_INVALID, flags.flag_names(2052))"` on 2026-10-29: `2052 ['ZERO_BID', 'VENDOR_IV_INVALID']`.

Two of the 13 bits never appear on a stored quote. `NON_SESSION_DATE` (bit 7, value 128) marks a vendor date in the calendar's own table, `calendar_actions`, and every such date is dropped. `RELABELLED` (bit 8, value 256) is reserved and never set: the relabel rule it marked was removed in round 2 of the M1 review.

**Why cents.** The price tests run on whole cents, not on dollars in floating point. In binary floating point, 420.42/420 − 1 is `0.001000000000000112`, which is above 0.001. A float test would flag a gap of exactly 0.10% as a mismatch. In cents the test is `1000 × |42042 − 42000| > 42000`, which is `42000 > 42000`, false, as the rule says (`flags.py:120`). Every vendor price is a whole number of cents: 0 of the 9,468,584 OptionsDX rows has a fractional cent in any bid, ask or underlying, and DoltHub stores `decimal(7,2)` (DuckDB scan, 2026-10-29).

## Assumptions

- The problems are independent yes/no facts. Each fits one bit.
- 13 bits fit easily in a 32-bit integer.
- Prices are whole cents, so cents lose nothing.
- Every consumer knows the bit numbers. They are fixed in one module and pinned by a test (`tests/test_flags.py`).

## Where it breaks

- **A bit number changes.** Old stored masks then mean something else. That is why the bit order is pinned in a test and must never be reused.
- **A rule needs a degree, not a yes/no.** "How wide is the spread?" does not fit one bit. We store the price columns too, so a consumer can compute degrees itself.
- **A rule tests the wrong thing.** Bit 11 was first `VENDOR_IV_NULL`, set only for a missing IV. The M1 review found IVs that are present but unusable: 216,700 OptionsDX rows from −0.0005 to −0.00001, 5,984 at exactly 0, and 70 DoltHub rows at 0 (216,665 and 5,983 in the store rebuilt after round 2, which dropped the 2022-06-20 rows). The bit kept its number, so stored masks keep their meaning for every row the old rule flagged, and was renamed `VENDOR_IV_INVALID` (null or ≤ 0). A bit's number is fixed for ever; its name and rule can still be corrected, and old stores must then be rebuilt.
- **A rule is withdrawn.** `RELABELLED` marked rows the calendar moved to the previous session. The rule moved one OptionsDX date, 2022-06-20, whose prices were 06-17's but whose contract list was 06-20's, so it was removed. The bit is not reused or renumbered: bit 9 is still `VOLUME_UNRELIABLE`, and a mask stored before the change still reads the same. The bit stays in `FLAG_NAMES`, documented as reserved.
- **Two flags overlap by accident.** `0.00 / 0.05` has a relative spread of 200%, so a naive `WIDE` rule would also fire. ADR-0009's test says it must set only `ZERO_BID`, so `WIDE` needs a bid above zero (`flags.py:89`). The mutation run broke this guard and the test failed.

## In this project

- `src/volbt/data/flags.py:34-58`: the 13 bits (bit 8 reserved), and the 3 IV bits reserved for M2's separate `quote_iv.iv_flags`.
- `src/volbt/data/flags.py:80-90`: `mid_flags`, the bits that need only the quote.
- `src/volbt/data/flags.py:93-128`: `quote_flags`, all 13 bits for a whole table at once; `VENDOR_IV_INVALID` is `:122-126`.
- `src/volbt/data/quality.py:75-83`: the report counts each bit per source and year with `(flags >> bit) & 1`.

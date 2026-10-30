# The pricing fixture (milestone 2)

`pricing_chain.csv` is one made-up snapshot for `tests/test_chain.py`, written by hand (not by
`tools/make_fixtures.py`, which owns `tests/fixtures/`): spot 440.00, r = 5%, no dividend, two
expiries (29 and 64 days). The mids of the clean rows are Black-76 prices at sigma = 0.15 on the
carry forward (441.7514 and 443.8745), rounded to the cent. Every other row is damaged on purpose,
one row (or one strike) per IV flag of ADR-0009 §3, and its `why` column says how;
`expected_iv_flags` is the hand-worked answer (IV_FAIL = 1, PARITY_OUTLIER = 2,
FORWARD_FALLBACK = 4).

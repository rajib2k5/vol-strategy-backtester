"""ADR-0009 test 5: the OSI symbol and its inverse. Expected strings are written out by hand."""

from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from volbt.data import osi


def test_the_adr_example():
    # Root padded to 6, yymmdd, C or P, strike x 1000 as 8 digits: 450.00 -> 00450000.
    assert osi.osi_symbol("SPY", date(2024, 3, 15), "C", 450.00) == "SPY   240315C00450000"


def test_the_inverse_parses_it_back():
    assert osi.parse_osi("SPY   240315C00450000") == ("SPY", date(2024, 3, 15), "C", Decimal("450.000"))


@pytest.mark.parametrize("strike, field", [
    (450.5, "00450500"),      # half strikes keep their .5
    (5.0, "00005000"),        # the smallest OptionsDX strike
    (6400.0, "06400000"),     # the largest
    (0.01, "00000010"),
    (99999.999, "99999999"),  # the largest the 8 digits can hold
])
def test_strike_field(strike, field):
    assert osi.osi_symbol("SPY", date(2010, 1, 15), "P", strike)[-8:] == field


def test_put_and_a_long_root():
    assert osi.osi_symbol("SPXW", date(2023, 12, 29), "P", 4750) == "SPXW  231229P04750000"


@pytest.mark.parametrize("symbol", [
    "SPY   240315C00450000",
    "SPY   100115P00005000",
    "SPXW  231229P04750000",
    "SPY   260116C00500500",
])
def test_round_trip(symbol):
    root, expiry, call_put, strike = osi.parse_osi(symbol)
    assert osi.osi_symbol(root, expiry, call_put, strike) == symbol


@pytest.mark.parametrize("args", [
    ("SPY", date(2024, 3, 15), "X", 450.0),       # not C or P
    ("SPY", date(2024, 3, 15), "C", 100000.0),    # too big for 8 digits
    ("SPY", date(2024, 3, 15), "C", -1.0),
    ("SPY", date(2024, 3, 15), "C", 450.0005),    # finer than 1/1000 of a dollar
    ("TOOLONG", date(2024, 3, 15), "C", 450.0),   # root over 6 characters
])
def test_bad_contracts_raise(args):
    with pytest.raises(ValueError):
        osi.osi_symbol(*args)


@pytest.mark.parametrize("symbol", ["SPY240315C00450000", "SPY   241315C00450000", "SPY   240315Z00450000"])
def test_bad_symbols_raise(symbol):
    with pytest.raises(ValueError):
        osi.parse_osi(symbol)


def test_the_vectorised_builder_agrees_with_the_scalar_one():
    # The pipeline builds millions of symbols at once; it must give the same strings.
    expiries = [date(2010, 1, 15), date(2024, 3, 15), date(2023, 12, 29), date(2026, 1, 16)]
    strikes = [5.0, 450.0, 450.5, 6400.0]
    sides = ["C", "P", "C", "P"]
    vector = osi.osi_symbols(pd.Series(expiries), pd.Series(sides), pd.Series(strikes))
    assert vector.tolist() == [osi.osi_symbol("SPY", e, s, k) for e, s, k in zip(expiries, sides, strikes)]
    assert vector.tolist()[1] == "SPY   240315P00450000"

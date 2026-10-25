"""Live open-interest tests for NYMEX crude oil contracts.

These tests really hit TradingView and are opt-in so the default suite stays
offline::

    TV_LIVE=1 pytest tests/test_open_interest_live.py -v

They mirror the two scripts reported in the issue: the same four contracts
with and without ``fut_contract=1``.  Every call must return a non-null
``open_interest`` column.
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tvDatafeed import Interval, TvDatafeed  # noqa: E402

pytestmark = pytest.mark.skipif(
    os.getenv("TV_LIVE") != "1",
    reason="live tests are opt-in: set TV_LIVE=1 to run them",
)

CONTRACTS = ["CL", "CL1!", "CLZ2026", "CLK2027"]


def _assert_oi(df):
    assert df is not None and len(df) >= 1
    assert "open_interest" in df.columns
    assert df["open_interest"].notna().any(), "open_interest is all NaN"
    values = df["open_interest"].dropna()
    assert (values > 0).all(), f"invalid open interest values: {values.tolist()}"


@pytest.mark.parametrize("contract", CONTRACTS)
def test_open_interest_without_fut_contract(contract):
    tv = TvDatafeed()  # nologin
    df = tv.get_hist(
        symbol=contract,
        exchange="NYMEX",
        interval=Interval.in_daily,
        n_bars=2,
        open_interest=True,
    )
    _assert_oi(df)
    # A bare root falls back to the continuous front contract.
    if contract == "CL":
        assert df["symbol"].iloc[0] == "NYMEX:CL1!"
    else:
        assert df["symbol"].iloc[0] == f"NYMEX:{contract}"


@pytest.mark.parametrize("contract", CONTRACTS)
def test_open_interest_with_fut_contract(contract):
    tv = TvDatafeed()  # nologin
    df = tv.get_hist(
        symbol=contract,
        exchange="NYMEX",
        interval=Interval.in_daily,
        fut_contract=1,
        n_bars=2,
        open_interest=True,
    )
    _assert_oi(df)
    # Explicit contracts must not receive a second "1!" suffix.
    expected = "NYMEX:CL1!" if contract == "CL" else f"NYMEX:{contract}"
    assert df["symbol"].iloc[0] == expected


def test_open_interest_respects_timezone_and_weekly_bars():
    tv = TvDatafeed()  # nologin
    df = tv.get_hist(
        symbol="CLK2027",
        exchange="NYMEX",
        interval=Interval.in_weekly,
        n_bars=3,
        timezone="America/New_York",
        open_interest=True,
    )
    _assert_oi(df)
    assert str(df.index.tz) == "America/New_York"

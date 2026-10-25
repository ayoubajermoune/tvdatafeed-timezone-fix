"""Offline tests for the open-interest mapping helpers.

TradingView publishes open interest once per trading session.  The tests
below use synthetic daily OI frames (the same shape returned by
``TvDatafeed._TvDatafeed__create_df``) and verify that OI is attached to
the correct bars without broadcasting a single value.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tvDatafeed.main import (  # noqa: E402
    Interval,
    _build_resolve_payload,
    _map_open_interest_to_bars,
)


def _df(index, aligned=False):
    index = pd.DatetimeIndex(index, name="datetime")
    frame = pd.DataFrame(
        {
            "symbol": "NYMEX:CL1!",
            "open": 1.0,
            "high": 2.0,
            "low": 0.5,
            "close": 1.5,
            "volume": 100.0,
        },
        index=index,
    )
    frame.attrs["aligned_to_trading_day"] = aligned
    return frame


def _oi(index, values):
    index = pd.DatetimeIndex(index, name="datetime")
    return pd.DataFrame(
        {
            "symbol": "NYMEX:CL1!_OI",
            "open": 0.0,
            "high": 0.0,
            "low": 0.0,
            "close": values,
            "volume": 0.0,
        },
        index=index,
    )


def test_resolve_payload_has_leading_equals():
    payload = _build_resolve_payload("NYMEX:CL1!_OI")
    assert payload.startswith('={"symbol":"NYMEX:CL1!_OI"')
    assert '"session":"regular"' in payload
    assert '"session":"extended"' in _build_resolve_payload(
        "NYMEX:CL1!_OI", extended_session=True
    )


def test_daily_aligned_oi_uses_session_before_label():
    # With the default alignment, a daily bar is labelled by its closing day
    # (e.g. the 2026-10-13 bar covers the session that opened 2026-10-12
    # 22:00).  Its OI must be the 2026-10-12 22:00 value, not the next one.
    df = _df(
        [
            "2026-10-13 22:00:00+00:00",
            "2026-10-14 22:00:00+00:00",
            "2026-10-15 22:00:00+00:00",
        ],
        aligned=True,
    )
    oi = _oi(
        [
            "2026-10-11 22:00:00+00:00",
            "2026-10-12 22:00:00+00:00",
            "2026-10-13 22:00:00+00:00",
            "2026-10-14 22:00:00+00:00",
        ],
        [100.0, 101.0, 102.0, 103.0],
    )

    out = _map_open_interest_to_bars(df, oi, interval=Interval.in_daily)

    assert out.tolist() == [101.0, 102.0, 103.0]
    assert out.nunique() > 1  # regression: never a single broadcast value


def test_daily_unaligned_oi_uses_same_session_open():
    # With align_daily_to_trading_day=False the bar label is the raw session
    # open, so the OI value at that exact timestamp belongs to the bar.
    df = _df(
        [
            "2026-10-12 22:00:00+00:00",
            "2026-10-13 22:00:00+00:00",
            "2026-10-14 22:00:00+00:00",
        ],
        aligned=False,
    )
    oi = _oi(
        [
            "2026-10-12 22:00:00+00:00",
            "2026-10-13 22:00:00+00:00",
            "2026-10-14 22:00:00+00:00",
        ],
        [100.0, 101.0, 102.0],
    )

    out = _map_open_interest_to_bars(df, oi, interval=Interval.in_daily)

    assert out.tolist() == [100.0, 101.0, 102.0]


def test_intraday_oi_is_constant_within_a_session():
    # NYMEX CL sessions open at 22:00 UTC.  Bars at 20:00/21:00 belong to
    # session 2026-10-13; bars at 22:00/23:00 belong to the next session.
    df = _df(
        [
            "2026-10-13 20:00:00+00:00",
            "2026-10-13 21:00:00+00:00",
            "2026-10-13 22:00:00+00:00",
            "2026-10-13 23:00:00+00:00",
        ]
    )
    oi = _oi(
        [
            "2026-10-12 22:00:00+00:00",
            "2026-10-13 22:00:00+00:00",
        ],
        [100.0, 200.0],
    )

    out = _map_open_interest_to_bars(df, oi, interval=Interval.in_1_hour)

    assert out.tolist() == [100.0, 100.0, 200.0, 200.0]


def test_daily_oi_with_gap_fills_from_last_available_session():
    # Friday's bar keeps Friday's OI; Monday's bar still gets the latest
    # available (Friday) value until Monday's OI is published.
    df = _df(
        [
            "2026-10-16 22:00:00+00:00",
            "2026-10-19 22:00:00+00:00",
        ],
        aligned=False,
    )
    oi = _oi(
        [
            "2026-10-15 22:00:00+00:00",
            "2026-10-16 22:00:00+00:00",
        ],
        [115.0, 116.0],
    )

    out = _map_open_interest_to_bars(
        df,
        oi,
        interval=Interval.in_daily,
        aligned_to_trading_day=True,
    )

    assert out.tolist() == [115.0, 116.0]


def test_weekly_oi_uses_last_daily_value_of_period():
    # Weekly bars are labelled at the week's session open (Sunday 22:00).
    df = _df(
        [
            "2026-10-04 22:00:00+00:00",
            "2026-10-11 22:00:00+00:00",
            "2026-10-18 22:00:00+00:00",
        ]
    )
    oi = _oi(
        [
            "2026-10-05 22:00:00+00:00",
            "2026-10-09 22:00:00+00:00",
            "2026-10-12 22:00:00+00:00",
            "2026-10-16 22:00:00+00:00",
            "2026-10-19 22:00:00+00:00",
            "2026-10-21 22:00:00+00:00",
        ],
        [105.0, 109.0, 112.0, 116.0, 119.0, 121.0],
    )

    out = _map_open_interest_to_bars(df, oi, interval=Interval.in_weekly)

    assert out.tolist() == [109.0, 116.0, 121.0]


def test_monthly_oi_uses_last_daily_value_of_period():
    # Monthly bars are labelled at the previous month's last session open.
    df = _df(
        [
            "2026-08-31 22:00:00+00:00",  # September
            "2026-09-30 22:00:00+00:00",  # October (still forming)
        ]
    )
    oi = _oi(
        [
            "2026-09-15 22:00:00+00:00",
            "2026-09-29 22:00:00+00:00",
            "2026-10-15 22:00:00+00:00",
            "2026-10-21 22:00:00+00:00",
        ],
        [915.0, 929.0, 1015.0, 1021.0],
    )

    out = _map_open_interest_to_bars(df, oi, interval=Interval.in_monthly)

    assert out.tolist() == [929.0, 1021.0]


def test_missing_oi_returns_nan_not_a_constant():
    df = _df(["2026-10-13 22:00:00+00:00", "2026-10-14 22:00:00+00:00"])

    for empty in (None, _oi([], [])):
        out = _map_open_interest_to_bars(df, empty, interval=Interval.in_daily)
        assert len(out) == len(df)
        assert out.isna().all()


def test_naive_indexes_are_supported():
    df = _df(["2026-10-13 22:00:00", "2026-10-14 22:00:00"])
    oi = _oi(["2026-10-12 22:00:00"], [100.0])

    out = _map_open_interest_to_bars(df, oi, interval=Interval.in_daily)

    assert out.tolist() == [100.0, 100.0]


def test_empty_dataframe_is_supported():
    df = _df([])
    out = _map_open_interest_to_bars(
        df,
        _oi(["2026-10-12 22:00:00"], [100.0]),
        interval=Interval.in_daily,
    )
    assert len(out) == 0


@pytest.mark.parametrize(
    "bad_values",
    [
        [None, None],
        ["bad", "data"],
    ],
)
def test_invalid_oi_values_are_dropped(bad_values):
    df = _df(["2026-10-13 22:00:00+00:00", "2026-10-14 22:00:00+00:00"])
    oi = _oi(
        ["2026-10-12 22:00:00+00:00", "2026-10-13 22:00:00+00:00"],
        bad_values,
    )

    out = _map_open_interest_to_bars(df, oi, interval=Interval.in_daily)

    assert out.isna().all()

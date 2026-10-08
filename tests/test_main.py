"""Tests for the timezone + daily-date fixes in tvDatafeed.main.

These tests are fully offline: they feed the parser the same raw WebSocket
payload shape that TradingView really sends (captured against
BLACKBULL:XAUUSD daily) instead of opening a connection.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tvDatafeed.main import Interval, TvDatafeed  # noqa: E402

# ---------------------------------------------------------------------------
# Fixture: real payload captured from TradingView (BLACKBULL:XAUUSD, 1D, 10 bars)
# ---------------------------------------------------------------------------
ROWS = [
    # timestamp,                        open,    high,    low,     close,   volume
    [1789077600.0, 4318.83, 4402.43, 4291.94, 4348.48, 608872.0],
    [1789336800.0, 4334.83, 4355.54, 4253.55, 4299.10, 595762.0],
    [1789423200.0, 4300.04, 4317.51, 4261.40, 4293.22, 525284.0],
    [1789509600.0, 4294.23, 4367.15, 4235.05, 4263.68, 550176.0],
    [1789596000.0, 4264.20, 4381.73, 4257.43, 4341.27, 570146.0],
    [1789682400.0, 4342.01, 4399.78, 4334.28, 4378.36, 543559.0],
    [1789941600.0, 4374.47, 4383.61, 4322.66, 4343.30, 495671.0],
    [1790028000.0, 4344.00, 4375.94, 4291.49, 4357.44, 572600.0],
    [1790114400.0, 4357.68, 4369.60, 4274.86, 4287.89, 502959.0],
    [1790200800.0, 4288.34, 4303.18, 4244.36, 4251.62, 431228.0],
]


def make_raw(rows=ROWS, interval="1D", symbol_resolved=True):
    """Build a raw WebSocket payload string in the real TradingView shape."""
    candles = ",".join(
        '{"i":%d,"v":[%s,%s,%s,%s,%s,%s]}'
        % (i, *[f"{v:.2f}" if isinstance(v, float) else v for v in row])
        for i, row in enumerate(rows)
    )
    parts = []
    if symbol_resolved:
        parts.append(
            '{"m":"symbol_resolved","p":["cs_x","symbol_1",{'
            '"description":"Gold vs US-Dollar","session":"1800-1700",'
            '"timezone":"America/New_York","exchange":"BlackBull Markets",'
            '"name":"XAUUSD"}],"t":1}'
        )
    parts.append(
        '{"m":"timescale_update","p":["cs_x",{"s1":{"node":"n1","s":[%s],'
        '"ns":{"d":"","indexes":[]},"t":"s1","lbs":{"bar_close_time":1790283599}}'
        '},"index":0,"zoffset":0}],"t":1}' % candles
    )
    parts.append('{"m":"series_completed","p":["cs_x","s1","streaming","s1"]}')
    return "\n".join(parts) + "\n"


RAW = make_raw()
SYMBOL = "BLACKBULL:XAUUSD"


def parse(**kwargs):
    kwargs.setdefault("timezone", "UTC")
    kwargs.setdefault("interval", Interval.in_daily)
    # get_hist() always extracts the exchange timezone from the payload;
    # mirror that here by default.
    kwargs.setdefault(
        "exchange_tz",
        TvDatafeed._TvDatafeed__extract_exchange_timezone(RAW),
    )
    return TvDatafeed._TvDatafeed__create_df(RAW, SYMBOL, **kwargs)


# ---------------------------------------------------------------------------
# 1) timezone is explicit and controllable
# ---------------------------------------------------------------------------
def test_default_timezone_is_utc_and_tz_aware():
    df = parse()
    assert df.index.tz is not None
    assert str(df.index.tz) == "UTC"
    assert df.attrs["timezone"] == "UTC"


def test_specific_timezone():
    df = parse(timezone="America/New_York")
    assert str(df.index.tz) == "America/New_York"
    # 22:00 UTC == 18:00 EDT
    assert df.index[0].hour == 18


def test_exchange_mode_is_naive_exchange_clock():
    df = parse(timezone="exchange")
    assert df.index.tz is None  # legacy: naive
    # exchange clock of BLACKBULL:XAUUSD is America/New_York -> 18:00, not 22:00
    assert df.index[0].hour == 18


def test_exchange_timezone_extraction():
    assert TvDatafeed._TvDatafeed__extract_exchange_timezone(RAW) == "America/New_York"


# ---------------------------------------------------------------------------
# 2) the daily "yesterday's date" bug is fixed
# ---------------------------------------------------------------------------
def test_daily_bars_aligned_to_trading_day():
    df = parse()  # UTC, aligned (default)
    # Weekday dates; no weekend bars; the last (forming) bar is dated "today".
    assert [d.strftime("%Y-%m-%d") for d in df.index.date] == [
        "2026-09-11", "2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17",
        "2026-09-18", "2026-09-21", "2026-09-22", "2026-09-23", "2026-09-24",
    ]
    # Before the fix the last bar was labelled 2026-09-23 22:00 (session open).
    assert df.index[-1] == pd.Timestamp("2026-09-24 22:00:00", tz="UTC")


def test_alignment_off_keeps_raw_open_date():
    df = parse(align_daily_to_trading_day=False)
    assert df.index[-1] == pd.Timestamp("2026-09-23 22:00:00", tz="UTC")


def test_alignment_depends_on_target_timezone():
    # In Asia/Riyadh (UTC+3) the 22:00 UTC open is already 01:00 the next
    # calendar day, so it must NOT be shifted again.
    df = parse(timezone="Asia/Riyadh")
    assert df.index[-1] == pd.Timestamp("2026-09-24 01:00:00", tz="Asia/Riyadh")


def test_intraday_bars_are_never_shifted():
    rows = [[1789077600.0, 1.0, 2.0, 0.5, 1.5, 100.0]]  # 22:00 UTC bar
    df = make_raw(rows=rows)
    out = TvDatafeed._TvDatafeed__create_df(df, SYMBOL, timezone="UTC", interval=Interval.in_1_hour)
    assert out.index[0] == pd.Timestamp("2026-09-10 22:00:00", tz="UTC")


# ---------------------------------------------------------------------------
# 3) data integrity + validation
# ---------------------------------------------------------------------------
def test_ohlcv_values_intact():
    df = parse()
    assert list(df.columns) == ["symbol", "open", "high", "low", "close", "volume"]
    assert df["close"].iloc[0] == 4348.48
    assert df["volume"].iloc[0] == 608872.0
    assert df["symbol"].iloc[0] == SYMBOL


def test_invalid_timezone_raises_without_network():
    tv = TvDatafeed.__new__(TvDatafeed)  # skip __init__ (no network)
    with pytest.raises(ValueError, match="Invalid timezone"):
        tv.get_hist("XAUUSD", "BLACKBULL", timezone="Not/AZone")

def test_index_name_is_datetime():
    """reset_index() must yield a predictable 'datetime' column."""
    df = parse()
    assert df.index.name == "datetime"
    assert list(df.reset_index().columns)[0] == "datetime"


# ---------------------------------------------------------------------------
# 4) search_symbol() never raises, returns parsed data or an empty list
# ---------------------------------------------------------------------------
from unittest import mock


def _tv(proxies=None):
    # build a TvDatafeed without touching the network (skip __init__)
    tv = TvDatafeed.__new__(TvDatafeed)
    tv.proxies = proxies or {}
    return tv


def _resp(status_code, text, exc=None):
    r = mock.Mock()
    r.status_code = status_code
    r.text = text
    if exc is not None:
        r.raise_for_status.side_effect = exc
    else:
        r.raise_for_status.return_value = None
    return r


def test_search_symbol_parses_valid_json():
    tv = _tv()
    payload = (
        '[{"symbol":"XAUUSD","exchange":"BLACKBULL",'
        '"description":"Gold/US Dollar","type":"commodity"}]'
    )
    with mock.patch("tvDatafeed.main.requests.get", return_value=_resp(200, payload)) as get:
        out = tv.search_symbol("XAUUSD", "BLACKBULL")
    get.assert_called_once()
    assert get.call_args[1]["timeout"] == 10  # request is bounded
    assert out == [
        {"symbol": "XAUUSD", "exchange": "BLACKBULL",
         "description": "Gold/US Dollar", "type": "commodity"}
    ]


def test_search_symbol_returns_empty_list_on_http_error():
    tv = _tv()
    bad = _resp(403, "<html>403 Forbidden</html>",
                exc=__import__("requests").exceptions.HTTPError("403"))
    with mock.patch("tvDatafeed.main.requests.get", return_value=bad):
        assert tv.search_symbol("gold") == []


def test_search_symbol_returns_empty_list_on_non_json_body():
    tv = _tv()
    with mock.patch("tvDatafeed.main.requests.get",
                    return_value=_resp(200, "")):
        assert tv.search_symbol("gold") == []


def test_search_symbol_returns_empty_list_on_connection_error():
    tv = _tv()
    with mock.patch("tvDatafeed.main.requests.get",
                    side_effect=__import__("requests").exceptions.ConnectionError("boom")):
        assert tv.search_symbol("gold") == []


def test_search_symbol_sends_user_agent_and_proxies():
    tv = _tv(proxies={"https": "http://proxy.example:8080"})
    with mock.patch("tvDatafeed.main.requests.get", return_value=_resp(200, "[]")) as get:
        tv.search_symbol("gold")
    kwargs = get.call_args[1]
    assert kwargs["timeout"] == 10
    assert kwargs["proxies"] == {"https": "http://proxy.example:8080"}
    ua = kwargs["headers"]["User-Agent"]
    assert ua.startswith("Mozilla/5.0")
    assert "Chrome" in ua


def test_tvdatafeed_accepts_proxies_param_offline():
    """TvDatafeed(proxies=...) must not need network (nologin path)."""
    tv = TvDatafeed(proxies={"https": "http://proxy.example:8080"})
    assert tv.proxies == {"https": "http://proxy.example:8080"}


def test_tvdatafeed_proxies_defaults_to_empty_dict():
    tv = TvDatafeed()
    assert tv.proxies == {}



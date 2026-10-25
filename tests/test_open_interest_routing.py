"""Offline tests for contract formatting and open-interest routing.

The tests fake the TradingView websocket so they never touch the network.
They cover the bugs fixed in this fork:

* ``fut_contract`` must not be appended to an already explicit contract
  (``CL1!`` / ``CLZ2026``).
* open interest must be fetched even when ``fut_contract`` is not given.
* open-interest symbols must be built from the final resolved symbol
  (``NYMEX:CLZ2026`` -> ``NYMEX:CLZ2026_OI``).
* a bare root such as ``NYMEX:CL`` must fall back to the continuous front
  contract (``NYMEX:CL1!``) instead of failing.
"""
import json
import logging
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tvDatafeed.main import (  # noqa: E402
    Interval,
    TvDatafeed,
    _continuous_symbol,
    _is_bare_root,
    _is_explicit_contract,
    _oi_raw_status,
    _oi_symbol_candidates,
)

# 2026-10-21 22:00 UTC (OI session) and 2026-10-22 22:00 UTC (price bar).
OI_TS = 1792620000.0
BAR_TS = 1792706400.0


# ---------------------------------------------------------------------------
# formatting helpers
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "symbol,exchange,contract,expected",
    [
        ("CL", "NYMEX", 1, "NYMEX:CL1!"),
        ("CL1!", "NYMEX", 1, "NYMEX:CL1!"),
        ("CLZ2026", "NYMEX", 1, "NYMEX:CLZ2026"),
        ("CLK2027", "NYMEX", 1, "NYMEX:CLK2027"),
        ("NYMEX:CL", "NSE", 1, "NYMEX:CL1!"),
        ("NYMEX:CL1!", "NSE", 1, "NYMEX:CL1!"),
        ("CL", "NYMEX", None, "NYMEX:CL"),
        ("CLZ2026", "NYMEX", None, "NYMEX:CLZ2026"),
        ("NIFTY", "NSE", 2, "NSE:NIFTY2!"),
    ],
)
def test_format_symbol_does_not_duplicate_contract(
    symbol, exchange, contract, expected
):
    assert (
        TvDatafeed._TvDatafeed__format_symbol(symbol, exchange, contract)
        == expected
    )


def test_format_symbol_rejects_invalid_contract():
    with pytest.raises(ValueError):
        TvDatafeed._TvDatafeed__format_symbol("CL", "NYMEX", "1")


@pytest.mark.parametrize(
    "ticker,expected",
    [
        ("CL", False),
        ("CL1!", True),
        ("CLZ2026", True),
        ("CLK2027", True),
        ("ESZ5", True),
        ("NIFTY", False),
        ("AAPL", False),
    ],
)
def test_explicit_contract_detection(ticker, expected):
    assert _is_explicit_contract(ticker) is expected
    assert _is_bare_root(ticker) is (not expected)


def test_continuous_symbol():
    assert _continuous_symbol("NYMEX:CL") == "NYMEX:CL1!"
    assert _continuous_symbol("CL") == "CL1!"
    assert _continuous_symbol("NYMEX:CL1!") == "NYMEX:CL1!"


@pytest.mark.parametrize(
    "symbol,contract,expected",
    [
        ("NYMEX:CL1!", None, ["NYMEX:CL1!_OI"]),
        ("NYMEX:CL1!", 1, ["NYMEX:CL1!_OI"]),
        ("NYMEX:CLZ2026", None, ["NYMEX:CLZ2026_OI"]),
        ("NYMEX:CLZ2026", 1, ["NYMEX:CLZ2026_OI"]),
        ("NYMEX:CLK2027", 1, ["NYMEX:CLK2027_OI"]),
        ("NYMEX:CL", None, ["NYMEX:CL_OI", "NYMEX:CL1!_OI"]),
        ("NYMEX:CL", 1, ["NYMEX:CL1!_OI", "NYMEX:CL_OI"]),
    ],
)
def test_oi_symbol_candidates(symbol, contract, expected):
    assert _oi_symbol_candidates(symbol, contract) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("", "empty"),
        ("   \n", "empty"),
        ('{"m":"timescale_update","p":[{"s":[{"i":0,"v":[1]}]}]}', "data"),
        ('{"m":"symbol_error","p":[]}', "symbol_error"),
        ('{"m":"series_error","p":[]}', "series_error"),
        ('{"m":"heartbeat","p":[]}', "no_data"),
    ],
)
def test_oi_raw_status(raw, expected):
    assert _oi_raw_status(raw) == expected


# ---------------------------------------------------------------------------
# fake websocket
# ---------------------------------------------------------------------------
class FakeWebSocket:
    """Minimal websocket-client stand-in driven by a routing function."""

    def __init__(self, router):
        self.router = router
        self.sent = []
        self.closed = False
        self._queue = []
        self._started = False

    def send(self, message):
        self.sent.append(message)

    def recv(self):
        if not self._started:
            self._started = True
            self._queue = self.router(self.sent)
        if not self._queue:
            raise ConnectionError("no more messages")
        return self._queue.pop(0)

    def close(self):
        self.closed = True


def _requested_symbol(messages):
    """Extract the symbol from the sent ``resolve_symbol`` message."""
    for message in messages:
        if '"m":"resolve_symbol"' in message:
            payload = message.split("~m~")[-1]
            data = json.loads(payload)
            resolve_payload = data["p"][2]
            assert resolve_payload.startswith("=")
            return json.loads(resolve_payload[1:])["symbol"]
    return None


def _timescale_message(value, oi=False):
    if oi:
        row = [OI_TS, 0.0, 0.0, 0.0, value, 0.0]
    else:
        row = [BAR_TS, 99.1, 103.92, 98.84, 103.27, 313170.0]
    candles = '{"i":0,"v":[%s]}' % ",".join(
        str(item) for item in row
    )
    return (
        '{"m":"timescale_update","p":["cs_x",{"s1":{"node":"n1",'
        '"s":[%s],"ns":{"d":"","indexes":[]},"t":"s1",'
        '"lbs":{"bar_close_time":1792789799}},"index":0,"zoffset":0}],'
        '"t":1}' % candles
    )


def _completed_message():
    return '{"m":"series_completed","p":["cs_x","s1","streaming","s1"]}'


def _error_messages():
    return [
        '{"m":"symbol_error","p":["cs_x","symbol_1","invalid symbol"]}',
        '{"m":"series_error","p":["cs_x","s1","s1","resolve error"]}',
    ]


def _fake_connection(requests, values, connections):
    """Return a ``create_connection`` replacement with per-symbol payloads."""

    def factory(*args, **kwargs):
        def router(messages):
            symbol = _requested_symbol(messages)
            requests.append(symbol)
            if symbol in values:
                return [
                    _timescale_message(values[symbol], oi=symbol.endswith("_OI")),
                    _completed_message(),
                ]
            return _error_messages()

        ws = FakeWebSocket(router)
        connections.append(ws)
        return ws

    return factory


def _tv():
    return TvDatafeed()  # no credentials -> no auth request


# ---------------------------------------------------------------------------
# get_hist routing
# ---------------------------------------------------------------------------
def test_bare_root_falls_back_to_continuous_and_gets_oi():
    requests, connections = [], []
    values = {"NYMEX:CL1!": 103.27, "NYMEX:CL1!_OI": 311983.0}

    with mock.patch(
        "tvDatafeed.main.create_connection",
        _fake_connection(requests, values, connections),
    ):
        df = _tv().get_hist(
            "CL",
            "NYMEX",
            interval=Interval.in_daily,
            n_bars=1,
            open_interest=True,
        )

    assert df is not None
    assert df["symbol"].iloc[0] == "NYMEX:CL1!"
    assert df["open_interest"].iloc[0] == 311983.0
    assert requests == ["NYMEX:CL", "NYMEX:CL1!", "NYMEX:CL1!_OI"]
    assert all(ws.closed for ws in connections)


def test_dated_contract_is_not_suffixed_again():
    requests, connections = [], []
    values = {"NYMEX:CLZ2026": 103.27, "NYMEX:CLZ2026_OI": 311983.0}

    with mock.patch(
        "tvDatafeed.main.create_connection",
        _fake_connection(requests, values, connections),
    ):
        df = _tv().get_hist(
            "CLZ2026",
            "NYMEX",
            interval=Interval.in_daily,
            fut_contract=1,
            n_bars=1,
            open_interest=True,
        )

    assert df is not None
    assert df["symbol"].iloc[0] == "NYMEX:CLZ2026"
    assert df["open_interest"].iloc[0] == 311983.0
    assert requests == ["NYMEX:CLZ2026", "NYMEX:CLZ2026_OI"]
    assert all(ws.closed for ws in connections)


def test_continuous_contract_is_not_suffixed_again():
    requests, connections = [], []
    values = {"NYMEX:CL1!": 103.27, "NYMEX:CL1!_OI": 311983.0}

    with mock.patch(
        "tvDatafeed.main.create_connection",
        _fake_connection(requests, values, connections),
    ):
        df = _tv().get_hist(
            "CL1!",
            "NYMEX",
            interval=Interval.in_daily,
            fut_contract=1,
            n_bars=1,
            open_interest=True,
        )

    assert df is not None
    assert requests == ["NYMEX:CL1!", "NYMEX:CL1!_OI"]


def test_oi_is_fetched_without_fut_contract():
    requests, connections = [], []
    values = {"NYMEX:CLK2027": 91.02, "NYMEX:CLK2027_OI": 48837.0}

    with mock.patch(
        "tvDatafeed.main.create_connection",
        _fake_connection(requests, values, connections),
    ):
        df = _tv().get_hist(
            "CLK2027",
            "NYMEX",
            interval=Interval.in_daily,
            n_bars=1,
            open_interest=True,
        )

    assert df is not None
    assert df["open_interest"].iloc[0] == 48837.0
    assert requests == ["NYMEX:CLK2027", "NYMEX:CLK2027_OI"]


def test_oi_is_not_requested_when_disabled():
    requests, connections = [], []
    values = {"NYMEX:CL1!": 103.27}

    with mock.patch(
        "tvDatafeed.main.create_connection",
        _fake_connection(requests, values, connections),
    ):
        df = _tv().get_hist(
            "CL1!",
            "NYMEX",
            interval=Interval.in_daily,
            n_bars=1,
        )

    assert df is not None
    assert "open_interest" not in df.columns
    assert requests == ["NYMEX:CL1!"]


def test_missing_oi_adds_nan_column():
    requests, connections = [], []
    values = {"NYMEX:CLK2027": 91.02}  # OI symbol intentionally missing

    with mock.patch(
        "tvDatafeed.main.create_connection",
        _fake_connection(requests, values, connections),
    ):
        df = _tv().get_hist(
            "CLK2027",
            "NYMEX",
            interval=Interval.in_daily,
            n_bars=1,
            open_interest=True,
        )

    assert df is not None
    assert "open_interest" in df.columns
    assert df["open_interest"].isna().all()
    assert requests == ["NYMEX:CLK2027", "NYMEX:CLK2027_OI"]


def test_missing_oi_warning_lists_candidate_statuses(caplog):
    requests, connections = [], []
    values = {"NYMEX:CLK2027": 91.02}

    with caplog.at_level(logging.WARNING, logger="tvDatafeed.main"):
        with mock.patch(
            "tvDatafeed.main.create_connection",
            _fake_connection(requests, values, connections),
        ):
            _tv().get_hist(
                "CLK2027",
                "NYMEX",
                interval=Interval.in_daily,
                n_bars=1,
                open_interest=True,
            )

    assert "NYMEX:CLK2027_OI (symbol_error)" in caplog.text


def test_transient_empty_oi_is_retried_once():
    requests, connections = [], []
    values = {"NYMEX:CLK2027": 91.02, "NYMEX:CLK2027_OI": 48837.0}
    state = {"empty_sent": False}

    def factory(*args, **kwargs):
        def router(messages):
            symbol = _requested_symbol(messages)
            requests.append(symbol)
            if symbol == "NYMEX:CLK2027_OI" and not state["empty_sent"]:
                state["empty_sent"] = True
                return []  # dropped/empty response, must be retried
            if symbol in values:
                return [
                    _timescale_message(
                        values[symbol], oi=symbol.endswith("_OI")
                    ),
                    _completed_message(),
                ]
            return _error_messages()

        ws = FakeWebSocket(router)
        connections.append(ws)
        return ws

    with mock.patch("tvDatafeed.main.create_connection", factory):
        df = _tv().get_hist(
            "CLK2027",
            "NYMEX",
            interval=Interval.in_daily,
            n_bars=1,
            open_interest=True,
        )

    assert df is not None
    assert df["open_interest"].iloc[0] == 48837.0
    assert requests == [
        "NYMEX:CLK2027",
        "NYMEX:CLK2027_OI",
        "NYMEX:CLK2027_OI",
    ]
    assert all(ws.closed for ws in connections)


def test_symbol_error_is_not_retried():
    requests, connections = [], []
    values = {"NYMEX:CLK2027": 91.02}

    with mock.patch(
        "tvDatafeed.main.create_connection",
        _fake_connection(requests, values, connections),
    ):
        _tv().get_hist(
            "CLK2027",
            "NYMEX",
            interval=Interval.in_daily,
            n_bars=1,
            open_interest=True,
        )

    # symbol_error is final: exactly one OI attempt.
    assert requests.count("NYMEX:CLK2027_OI") == 1

"""Live tests against the real TradingView symbol-search API.

These tests really hit the network and verify that the search results are
correct. They are opt-in so the default suite stays fully offline::

    TV_LIVE=1 pytest tests/test_search_live.py -v
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tvDatafeed import Interval, TvDatafeed, search_symbol  # noqa: E402

pytestmark = pytest.mark.skipif(
    os.getenv("TV_LIVE") != "1",
    reason="live tests are opt-in: set TV_LIVE=1 to run them",
)


def _only_types(records):
    return sorted({r["type"] for r in records})


# ---------------------------------------------------------------------------
# works without any account / login
# ---------------------------------------------------------------------------
def test_search_works_without_login_and_returns_nonempty():
    out = search_symbol("gold")
    assert isinstance(out, list) and out
    for record in out:
        assert isinstance(record, dict)
        assert record.get("symbol")
        assert record.get("exchange")
    assert any(r["type"] == "commodity" for r in out)


def test_full_name_is_consistent_with_exchange_and_symbol():
    out = search_symbol("XAUUSD", "OANDA")
    assert out
    for record in out:
        assert record["full_name"] == f"{record['exchange_id']}:{record['symbol']}"


# ---------------------------------------------------------------------------
# asset types: Arabic + English, real data
# ---------------------------------------------------------------------------
def test_commodity_type_in_arabic_returns_commodities_only():
    out = search_symbol("gold", type="السلع")
    assert out
    assert _only_types(out) == ["commodity"]


def test_bond_type_in_arabic_returns_bonds_only():
    out = search_symbol("apple", type="السندات")
    assert out
    assert _only_types(out) == ["bond"]


def test_forex_type_in_arabic_returns_forex_only():
    out = search_symbol("EURUSD", type="الفوريكس")
    assert out
    assert _only_types(out) == ["forex"]


def test_stock_type_returns_stocks():
    out = search_symbol("apple", type="stock", country="US")
    assert out
    assert set(_only_types(out)) <= {"stock", "dr"}
    assert all(r["country"] == "US" for r in out)


def test_index_futures_crypto_options_types():
    assert _only_types(search_symbol("SPX", type="index")) == ["index"]
    assert _only_types(search_symbol("CL", type="futures")) == ["futures"]
    assert set(_only_types(search_symbol("BTC", type="crypto"))) <= {
        "crypto", "spot", "swap", "index", "commodity", "futures",
    }
    assert _only_types(search_symbol("AAPL", type="options")) == ["option"]


# ---------------------------------------------------------------------------
# country filtering: Arabic + ISO codes
# ---------------------------------------------------------------------------
def test_country_arabic_returns_only_that_country():
    out = search_symbol("bank", country="السعودية")
    assert out
    assert all(r["country"] == "SA" for r in out)
    assert any(r["exchange"] == "TADAWUL" for r in out)


def test_country_iso_code_works():
    out = search_symbol("bank", country="EG")
    assert out
    assert all(r["country"] == "EG" for r in out)


def test_country_and_type_combine():
    out = search_symbol("bank", country="السعودية", type="الأسهم")
    assert out
    assert all(r["country"] == "SA" for r in out)
    assert all(r["type"] in {"stock", "dr"} for r in out)


def test_commodities_have_no_country_but_the_key_always_exists():
    out = search_symbol("XAUUSD", type="السلع")
    assert out
    for record in out:
        assert "country" in record  # the key is always present


# ---------------------------------------------------------------------------
# text handling: Arabic text + special characters
# ---------------------------------------------------------------------------
def test_arabic_text_search_finds_the_symbol():
    out = search_symbol("أرامكو")
    assert any(r["full_name"] == "TADAWUL:2222" for r in out)
    saudi = next(r for r in out if r["full_name"] == "TADAWUL:2222")
    assert saudi["description"] == "Saudi Arabian Oil Co."
    assert saudi["country"] == "SA"


def test_special_characters_never_break_the_query():
    # spaces, ampersands, hashes, slashes must be URL-encoded, never inject
    for weird in ["Saudi Aramco", "a&b=c", "BRK/B"]:
        out = search_symbol(weird)
        assert isinstance(out, list)  # never raises, never returns broken data


def test_arabic_text_with_arabic_asset_type():
    out = search_symbol("أرامكو", type="الأسهم", country="السعودية")
    assert any(r["full_name"] == "TADAWUL:2222" for r in out)


# ---------------------------------------------------------------------------
# exchange handling (case-insensitive convenience + exactness)
# ---------------------------------------------------------------------------
def test_exchange_case_insensitive_fallback():
    out = search_symbol("XAUUSD", exchange="blackbull")
    assert out
    assert any(r["full_name"] == "BLACKBULL:XAUUSD" for r in out)


def test_unknown_exchange_really_returns_nothing():
    assert search_symbol("gold", exchange="NOTAREALEXCHANGE") == []


# ---------------------------------------------------------------------------
# limit + validation
# ---------------------------------------------------------------------------
def test_limit_is_respected():
    out = search_symbol("gold", limit=5)
    assert len(out) == 5


@pytest.mark.parametrize(
    "kwargs",
    [dict(type="nope"), dict(country="XYZ"), dict(text=""), dict(limit=0)],
)
def test_invalid_arguments_raise_valueerror(kwargs):
    text = kwargs.pop("text", "gold")
    with pytest.raises(ValueError):
        search_symbol(text, **kwargs)


# ---------------------------------------------------------------------------
# round trip: a symbol found by search can be downloaded by get_hist
# ---------------------------------------------------------------------------
def test_search_result_can_be_downloaded_by_get_hist():
    tv = TvDatafeed()  # nologin
    out = search_symbol("XAUUSD", "BLACKBULL", limit=3)
    assert out
    hit = next(r for r in out if r["full_name"] == "BLACKBULL:XAUUSD")
    df = tv.get_hist(symbol=hit["symbol"], exchange=hit["exchange_id"],
                     interval=Interval.in_daily, n_bars=5)
    assert df is not None and len(df) >= 1
    assert list(df.columns) == ["symbol", "open", "high", "low", "close", "volume"]
    assert (df["close"] > 0).all()
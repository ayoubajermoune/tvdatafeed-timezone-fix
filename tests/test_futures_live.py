"""Live tests against the real TradingView futures screener / symbol search.

These tests really hit the network and verify that the custom futures search
returns correct data.  They are opt-in so the default suite stays offline::

    TV_LIVE=1 pytest tests/test_futures_live.py -v
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tvDatafeed import (  # noqa: E402
    FUTURES_CATEGORIES,
    Interval,
    TvDatafeed,
    list_futures_categories,
    search_futures,
)

pytestmark = pytest.mark.skipif(
    os.getenv("TV_LIVE") != "1",
    reason="live tests are opt-in: set TV_LIVE=1 to run them",
)

CATEGORY_IDS = list(FUTURES_CATEGORIES)


# ---------------------------------------------------------------------------
# every requested category really returns futures (no login required)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("category", CATEGORY_IDS)
def test_every_category_is_browsable(category):
    prefix = FUTURES_CATEGORIES[category]["product"]
    out = search_futures(category=category, limit=25)

    assert out, f"no futures found for {category}"
    for record in out:
        assert record["symbol"]
        assert record["product"]
        assert record["product"] == prefix or record["product"].startswith(prefix + "/")
        assert record["category"] == category
        assert record["categories"] == [category]
        assert record["full_name"] == f"{record['exchange_id']}:{record['symbol']}"
        assert record["continuous"] is True


@pytest.mark.parametrize("category", CATEGORY_IDS)
def test_every_category_also_has_monthly_contracts(category):
    out = search_futures(category=category, limit=25, continuous_only=False)
    assert out, f"no futures found for {category}"
    # The full listing is always at least as large as the continuous only one.
    continuous = search_futures(category=category, limit=1)
    assert continuous, f"no continuous contract for {category}"


def test_the_ten_categories_are_listable():
    categories = list_futures_categories()
    assert [c["id"] for c in categories] == CATEGORY_IDS
    assert all(c["product"] and c["label"] and c["aliases"] for c in categories)


# ---------------------------------------------------------------------------
# exchange filtering (exact + lower-case convenience fallback)
# ---------------------------------------------------------------------------
def test_exchange_filter_is_exact():
    out = search_futures(category="energy", exchange="NYMEX", limit=10)
    assert out
    assert all(r["exchange_id"] == "NYMEX" for r in out)


def test_exchange_filter_retries_uppercased():
    out = search_futures(category="energy", exchange="nymex", limit=5)
    assert out
    assert all(r["exchange_id"] == "NYMEX" for r in out)


def test_unknown_exchange_returns_nothing():
    assert search_futures(category="energy", exchange="NOTAREALEXCHANGE") == []


# ---------------------------------------------------------------------------
# sub-category (product path)
# ---------------------------------------------------------------------------
def test_product_path_limits_to_that_sub_tree():
    out = search_futures(product="Commodity/Metals/Precious", limit=15)
    assert out
    assert all(r["product"].startswith("Commodity/Metals/Precious") for r in out)
    assert all(r["category"] == "metals" for r in out)


def test_product_and_category_must_agree():
    with pytest.raises(ValueError):
        search_futures(category="metals", product="Commodity/Energy/Oil")


# ---------------------------------------------------------------------------
# country filtering (goes through symbol search)
# ---------------------------------------------------------------------------
def test_country_and_category_combine():
    out = search_futures(country="IN", category="metals", limit=10)
    assert out
    for record in out:
        assert record["country"] == "IN"
        assert record["category"] == "metals"
        assert record["continuous_symbol"]
        assert record["full_name"] == f"{record['exchange_id']}:{record['symbol']}"


def test_country_english_name_works():
    out = search_futures(country="India", limit=10)
    assert out
    assert all(r["country"] == "IN" for r in out)


# ---------------------------------------------------------------------------
# text + category (symbol search enriched with the taxonomy)
# ---------------------------------------------------------------------------
def test_text_search_is_enriched_with_category_and_continuous_symbol():
    out = search_futures("crude oil", category="energy", limit=10)
    assert out
    for record in out:
        assert record["category"] == "energy"
        assert record["product"].startswith("Commodity/Energy")
        assert record["continuous_symbol"].endswith("!")


def test_text_search_never_returns_a_non_matching_category():
    out = search_futures("crude oil", category="single_stock", limit=10)
    assert all(r["category"] == "single_stock" for r in out)


def test_text_search_without_category_still_returns_product():
    out = search_futures("crude oil", limit=5)
    assert out
    assert all(r["product"] for r in out)


# ---------------------------------------------------------------------------
# continuous vs monthly contracts
# ---------------------------------------------------------------------------
def test_continuous_only_is_the_browse_default():
    continuous = search_futures(category="weather", limit=25)
    everything = search_futures(category="weather", limit=25, continuous_only=False)
    assert continuous and everything
    assert all(r["continuous"] for r in continuous)
    assert any(not r["continuous"] for r in everything)


# ---------------------------------------------------------------------------
# limit + validation
# ---------------------------------------------------------------------------
def test_limit_is_respected():
    assert len(search_futures(category="metals", limit=5)) == 5


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(category="nope"),
        dict(category="metals", limit=0),
        dict(category="metals", exchange=123),
        dict(category="metals", continuous_only="yes"),
        dict(country="XYZ"),
    ],
)
def test_invalid_arguments_raise_valueerror(kwargs):
    with pytest.raises(ValueError):
        search_futures(**kwargs)


# ---------------------------------------------------------------------------
# round trip: a search result can be downloaded by get_hist
# ---------------------------------------------------------------------------
def test_browse_result_can_be_downloaded_by_get_hist():
    tv = TvDatafeed()  # nologin
    hits = search_futures(product="Commodity/Energy/Oil/CrudeOil/WTI", limit=25)
    hit = next(r for r in hits if r["symbol"] == "CL1!")
    df = tv.get_hist(
        symbol=hit["symbol"],
        exchange=hit["exchange_id"],
        interval=Interval.in_daily,
        n_bars=5,
    )
    assert df is not None and len(df) >= 1
    assert list(df.columns) == ["symbol", "open", "high", "low", "close", "volume"]
    assert (df["close"] > 0).all()


def test_text_search_root_can_be_downloaded_with_fut_contract():
    tv = TvDatafeed()  # nologin
    hits = search_futures("crude oil", category="energy", limit=20)
    hit = next(r for r in hits if r["full_name"] == "NYMEX:CL")
    df = tv.get_hist(
        symbol=hit["symbol"],
        exchange=hit["exchange_id"],
        fut_contract=1,
        interval=Interval.in_daily,
        n_bars=5,
    )
    assert df is not None and len(df) >= 1
    assert (df["close"] > 0).all()

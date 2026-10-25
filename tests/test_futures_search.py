"""Offline tests for the custom futures search (``tvDatafeed.futures``).

Everything here is mocked: no request ever leaves the process.  The live
counterpart lives in ``tests/test_futures_live.py`` (opt-in via ``TV_LIVE=1``).
"""
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests  # noqa: E402

from tvDatafeed import TvDatafeed, search_futures  # noqa: E402
from tvDatafeed import futures as futures_module  # noqa: E402
from tvDatafeed.futures import (  # noqa: E402
    FUTURES_CATEGORIES,
    category_for_product,
    categories_for_product,
    list_futures_categories,
)

POST_TARGET = "tvDatafeed.futures.requests.post"
GET_TARGET = "tvDatafeed.search.requests.get"

SCAN_COLUMNS = futures_module._SCAN_COLUMNS


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _resp(payload=None, raise_exc=None, json_exc=None):
    """Build a mock ``requests`` response."""
    r = mock.Mock()
    if raise_exc is not None:
        r.raise_for_status.side_effect = raise_exc
    else:
        r.raise_for_status.return_value = None
    if json_exc is not None:
        r.json.side_effect = json_exc
    else:
        r.json.return_value = payload
    return r


def _scan_row(name, exchange="NYMEX", product="Commodity/Energy/Oil/CrudeOil",
              description="Crude Oil Futures", logoid="crude-oil"):
    """Build one screener row payload (``d`` array matches _SCAN_COLUMNS)."""
    values = [
        name, description, exchange, product, logoid,
        "futures", ["continuous", "synthetic"], "USD", 95.22, 0.13,
    ]
    return {"s": f"{exchange}:{name}", "d": values}


def _scan_payload(rows, total=None):
    return {"totalCount": len(rows) if total is None else total, "data": rows}


def _call_browse(post_side_effect=None, post_return=None, **kwargs):
    """Call search_futures() with the screener POST mocked out."""
    if post_side_effect is not None:
        patcher = mock.patch(POST_TARGET, side_effect=post_side_effect)
    else:
        patcher = mock.patch(
            POST_TARGET,
            return_value=post_return if post_return is not None else _resp(_scan_payload([])),
        )
    with patcher as post:
        out = search_futures(**kwargs)
    return out, post


def _call_text(get_records=None, get_side_effect=None, scan_rows=None,
               scan_side_effect=None, **kwargs):
    """Call the text/country code path (symbol search + screener lookup)."""
    if get_side_effect is None:
        get_side_effect = [_resp(payload=get_records if get_records is not None else [])]
    if scan_side_effect is not None:
        post_patcher = mock.patch(POST_TARGET, side_effect=scan_side_effect)
    else:
        post_patcher = mock.patch(
            POST_TARGET,
            return_value=_resp(_scan_payload(scan_rows if scan_rows is not None else [])),
        )
    with mock.patch(GET_TARGET, side_effect=get_side_effect) as get:
        with post_patcher as post:
            out = search_futures(**kwargs)
    return out, get, post


def _body(post):
    """Return the JSON body of the last screener request."""
    return post.call_args[1]["json"]


def _filters(body):
    return body["filter"]


def _right_of(filters, column):
    for flt in filters:
        if flt.get("left") == column:
            return flt.get("right")
    return None


def _search_record(symbol="CL", exchange="NYMEX", description="Crude Oil Futures",
                   country="US", source_id="NYMEX", logoid="crude-oil",
                   contracts=None):
    """One raw symbol-search record (as TradingView returns it)."""
    if contracts is None:
        contracts = [
            {"symbol": f"{symbol}1!", "typespecs": ["continuous", "synthetic"]},
            {"symbol": f"{symbol}2!", "typespecs": ["continuous", "synthetic"]},
            {"symbol": f"{symbol}X2026", "description": "Nov 2026"},
        ]
    record = {
        "symbol": symbol,
        "description": description,
        "type": "futures",
        "exchange": exchange,
        "source_id": source_id,
        "source2": {"id": source_id, "name": exchange},
        "country": country,
        "currency_code": "USD",
        "logoid": logoid,
        "found_by_isin": False,
        "found_by_cusip": False,
    }
    if contracts is not None:
        record["contracts"] = contracts
    return record


# ---------------------------------------------------------------------------
# 1) screener request shape
# ---------------------------------------------------------------------------
def test_scan_url_is_the_futures_screener():
    _, post = _call_browse(category="metals")
    assert post.call_args[0][0] == "https://scanner.tradingview.com/futures/scan"


def test_scan_is_a_json_post_with_browser_headers():
    _, post = _call_browse(category="metals")
    kwargs = post.call_args[1]
    assert kwargs["headers"]["Content-Type"] == "application/json"
    assert kwargs["headers"]["Origin"] == "https://www.tradingview.com"
    assert kwargs["headers"]["User-Agent"].startswith("Mozilla/5.0")
    assert "json" in kwargs and "params" not in kwargs


def test_scan_body_columns_range_and_sort():
    _, post = _call_browse(category="metals", limit=7)
    body = _body(post)
    assert body["range"] == [0, 7]
    assert body["sort"] == {"sortBy": "name", "sortOrder": "asc"}
    for column in ("name", "description", "exchange", "product", "logoid",
                   "type", "typespecs", "currency", "close", "change"):
        assert column in body["columns"]


def test_scan_timeout_and_proxies_are_forwarded():
    _, post = _call_browse(category="metals", timeout=3,
                           proxies={"https": "http://p:1"})
    kwargs = post.call_args[1]
    assert kwargs["timeout"] == 3
    assert kwargs["proxies"] == {"https": "http://p:1"}


# ---------------------------------------------------------------------------
# 2) categories: aliases become the anchored product regex
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "given,expected_regex",
    [
        ("single_stock", "^Financial/Equity"),
        ("Single stock", "^Financial/Equity"),
        ("single-stock", "^Financial/Equity"),
        ("world_indices", "^Financial/Index"),
        ("World indices", "^Financial/Index"),
        ("currencies", "^Financial/Currency"),
        ("interest_rates", "^Financial/InterestRate"),
        ("energy", "^Commodity/Energy"),
        ("ENERGY", "^Commodity/Energy"),
        ("agriculture", "^Commodity/Agriculture"),
        ("metals", "^Commodity/Metals"),
        ("weather", "^Commodity/Weather"),
        ("building_materials", "^Commodity/BuildingMaterials"),
        ("building-materials", "^Commodity/BuildingMaterials"),
        ("chemicals", "^Commodity/Chemicals"),
    ],
)
def test_category_aliases_become_product_regex(given, expected_regex):
    _, post = _call_browse(category=given)
    flt = _filters(_body(post))[0]
    assert flt["left"] == "product"
    assert flt["operation"] == "match"
    assert flt["right"] == expected_regex


def test_the_ten_requested_categories_exist():
    assert list(FUTURES_CATEGORIES) == [
        "single_stock", "world_indices", "currencies", "interest_rates",
        "energy", "agriculture", "metals", "weather",
        "building_materials", "chemicals",
    ]


def test_unknown_category_raises_with_supported_list():
    with pytest.raises(ValueError) as exc:
        search_futures(category="crypto futures")
    msg = str(exc.value)
    assert "energy" in msg and "Energy" in msg and "chemicals" in msg


@pytest.mark.parametrize("bad", ["", "   ", "nope"])
def test_empty_or_unknown_category_raises(bad):
    with pytest.raises(ValueError, match="category"):
        search_futures(category=bad)


def test_non_string_category_raises():
    with pytest.raises(ValueError, match="category must be a string"):
        search_futures(category=7)


def test_list_futures_categories_shape():
    categories = list_futures_categories()
    assert len(categories) == 10
    for entry in categories:
        assert set(entry) == {"id", "product", "en", "label", "aliases"}
        assert entry["product"] == FUTURES_CATEGORIES[entry["id"]]["product"]
        assert entry["aliases"]


# ---------------------------------------------------------------------------
# 3) sub-category (product path)
# ---------------------------------------------------------------------------
def test_product_filter_is_anchored_and_escaped():
    _, post = _call_browse(product="Commodity/Metals/Precious/Gold")
    flt = _filters(_body(post))[0]
    assert flt["right"] == "^Commodity/Metals/Precious/Gold"


def test_product_with_regex_characters_is_escaped():
    _, post = _call_browse(product="Commodity/A+B")
    assert _filters(_body(post))[0]["right"] == "^Commodity/A\\+B"


def test_product_wins_over_category_when_consistent():
    _, post = _call_browse(category="metals", product="Commodity/Metals/Ferrous")
    assert _filters(_body(post))[0]["right"] == "^Commodity/Metals/Ferrous"


def test_product_must_belong_to_the_given_category():
    with pytest.raises(ValueError, match="does not belong to category"):
        search_futures(category="metals", product="Commodity/Energy/Oil")


def test_empty_product_is_ignored():
    _, post = _call_browse(product="   ")
    assert _right_of(_filters(_body(post)), "product") is None


# ---------------------------------------------------------------------------
# 4) exchange + continuous browsing
# ---------------------------------------------------------------------------
def test_browse_defaults_to_continuous_contracts_only():
    _, post = _call_browse(category="metals", exchange="COMEX")
    filters = _filters(_body(post))
    assert _right_of(filters, "name") == "[0-9]!$"
    exchange_filter = next(f for f in filters if f["left"] == "exchange")
    assert exchange_filter["operation"] == "equal"
    assert exchange_filter["right"] == "COMEX"


def test_continuous_only_false_drops_the_name_filter():
    _, post = _call_browse(category="metals", continuous_only=False)
    assert _right_of(_filters(_body(post)), "name") is None


def test_exchange_retries_uppercased_when_first_attempt_is_empty():
    out, post = _call_browse(
        category="metals",
        exchange="comex",
        post_side_effect=[
            _resp(_scan_payload([])),
            _resp(_scan_payload([_scan_row("GC1!", exchange="COMEX", product="Commodity/Metals/Precious/Gold")])),
        ],
    )
    assert len(post.call_args_list) == 2
    first = _right_of(_filters(post.call_args_list[0][1]["json"]), "exchange")
    second = _right_of(_filters(post.call_args_list[1][1]["json"]), "exchange")
    assert first == "comex" and second == "COMEX"
    assert out[0]["full_name"] == "COMEX:GC1!"


def test_exchange_is_not_retried_when_the_first_attempt_works():
    out, post = _call_browse(category="metals", exchange="COMEX")
    assert len(post.call_args_list) == 1


# ---------------------------------------------------------------------------
# 5) normalisation
# ---------------------------------------------------------------------------
def test_record_has_every_documented_key():
    out, _ = _call_browse(
        category="metals",
        post_return=_resp(_scan_payload([_scan_row(
            "GC1!", exchange="COMEX", product="Commodity/Metals/Precious/Gold",
            description="Gold Futures", logoid="metal/gold")])),
    )
    record = out[0]
    for key in ("symbol", "full_name", "description", "exchange", "exchange_id",
                "type", "country", "currency_code", "typespecs", "provider_id",
                "product", "category", "categories", "logoid", "close", "change",
                "continuous"):
        assert key in record
    assert record["symbol"] == "GC1!"
    assert record["full_name"] == "COMEX:GC1!"
    assert record["description"] == "Gold Futures"
    assert record["exchange"] == record["exchange_id"] == "COMEX"
    assert record["type"] == "futures"
    assert record["country"] is None           # documented for the screener
    assert record["currency_code"] == "USD"
    assert record["typespecs"] == ["continuous", "synthetic"]
    assert record["product"] == "Commodity/Metals/Precious/Gold"
    assert record["category"] == "metals"
    assert record["categories"] == ["metals"]
    assert record["logoid"] == "metal/gold"
    assert record["continuous"] is True


def test_continuous_flag_is_false_for_monthly_contracts():
    out, _ = _call_browse(
        category="metals", continuous_only=False,
        post_return=_resp(_scan_payload([_scan_row("GCZ2026", exchange="COMEX")])),
    )
    assert out[0]["continuous"] is False


def test_limit_slices_the_results():
    rows = [_scan_row(f"X{i}1!") for i in range(10)]
    out, post = _call_browse(
        category="energy", limit=3, post_return=_resp(_scan_payload(rows))
    )
    assert len(out) == 3
    assert _body(post)["range"] == [0, 3]


# ---------------------------------------------------------------------------
# 6) taxonomy helpers
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "product,expected",
    [
        ("Financial/Equity", "single_stock"),
        ("Financial/Index", "world_indices"),
        ("Financial/Currency", "currencies"),
        ("Financial/InterestRate", "interest_rates"),
        ("Commodity/Energy", "energy"),
        ("Commodity/Energy/Oil/CrudeOil/WTI", "energy"),
        ("Commodity/Agriculture/Softs/Sugar/Raw", "agriculture"),
        ("Commodity/Metals/Precious/Gold", "metals"),
        ("Commodity/Weather", "weather"),
        ("Commodity/BuildingMaterials", "building_materials"),
        ("Commodity/Chemicals", "chemicals"),
        (None, None),
        ("", None),
        ("Something/Else", None),
    ],
)
def test_category_for_product(product, expected):
    assert category_for_product(product) == expected


def test_categories_for_product_is_empty_for_unknown_values():
    assert categories_for_product("Something/Else") == []
    assert categories_for_product(None) == []
    assert categories_for_product("Commodity/Metals") == ["metals"]


# ---------------------------------------------------------------------------
# 7) argument validation
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("bad_limit", [0, -1, "5", 5.5, True])
def test_invalid_limit_raises(bad_limit):
    with pytest.raises(ValueError, match="limit"):
        search_futures(category="metals", limit=bad_limit)


def test_limit_is_clamped_to_the_server_maximum():
    rows = [_scan_row(f"X{i}1!") for i in range(60)]
    out, post = _call_browse(
        category="energy", limit=500, post_return=_resp(_scan_payload(rows))
    )
    assert _body(post)["range"] == [0, 50]
    assert len(out) == 50


@pytest.mark.parametrize("bad_timeout", [0, -1, "10", None])
def test_invalid_timeout_raises(bad_timeout):
    with pytest.raises(ValueError, match="timeout"):
        search_futures(category="metals", timeout=bad_timeout)


def test_invalid_exchange_raises():
    with pytest.raises(ValueError, match="exchange must be a string"):
        search_futures(category="metals", exchange=5)


def test_invalid_text_raises():
    with pytest.raises(ValueError, match="text must be a string"):
        search_futures(text=7)


def test_invalid_continuous_only_raises():
    with pytest.raises(ValueError, match="continuous_only must be a boolean"):
        search_futures(category="metals", continuous_only="yes")


def test_invalid_lang_raises():
    with pytest.raises(ValueError, match="lang"):
        search_futures(category="metals", lang="")


def test_unknown_country_raises():
    with pytest.raises(ValueError, match="country"):
        search_futures(country="XYZ")


def test_empty_text_is_allowed_and_browses():
    out, post = _call_browse(text="", category="metals")
    assert post.called
    assert out == []


# ---------------------------------------------------------------------------
# 8) failure modes never raise (network problems -> [])
# ---------------------------------------------------------------------------
def test_connection_error_returns_empty_list():
    out, _ = _call_browse(
        category="metals",
        post_side_effect=requests.exceptions.ConnectionError("boom"),
    )
    assert out == []


def test_http_error_returns_empty_list():
    out, _ = _call_browse(
        category="metals", post_return=_resp(raise_exc=requests.exceptions.HTTPError("403"))
    )
    assert out == []


def test_non_json_body_returns_empty_list():
    out, _ = _call_browse(category="metals", post_return=_resp(json_exc=ValueError("nope")))
    assert out == []


def test_error_object_payload_returns_empty_list():
    out, _ = _call_browse(
        category="metals", post_return=_resp({"error": "unsupported filter"})
    )
    assert out == []


def test_non_dict_payload_returns_empty_list():
    out, _ = _call_browse(category="metals", post_return=_resp([1, 2, 3]))
    assert out == []


def test_malformed_rows_are_dropped():
    payload = _scan_payload([_scan_row("CL1!"), "junk", {"s": "NYMEX:X"}, {"d": [1, 2]}])
    out, _ = _call_browse(category="energy", post_return=_resp(payload))
    assert [r["symbol"] for r in out] == ["CL1!"]


# ---------------------------------------------------------------------------
# 9) text / country code path (symbol search + taxonomy lookup)
# ---------------------------------------------------------------------------
def test_text_search_uses_symbol_search_with_type_futures():
    out, get, post = _call_text(get_records=[_search_record()], text="crude",
                                scan_rows=[_scan_row("CL1!")])
    params = get.call_args[1]["params"]
    assert params["type"] == "futures"
    assert params["text"] == "crude"
    assert get.call_args[0][0] == "https://symbol-search.tradingview.com/symbol_search/"


def test_country_is_resolved_to_iso_and_forwarded():
    _, get, _ = _call_text(get_records=[_search_record(country="SA")],
                           country="Saudi Arabia", scan_rows=[_scan_row("CL1!")])
    assert get.call_args[1]["params"]["country"] == "SA"


def test_country_only_search_browses_with_an_empty_text():
    _, get, _ = _call_text(get_records=[_search_record(country="IN")], country="IN",
                           scan_rows=[_scan_row("CL1!")])
    assert get.call_args[1]["params"]["text"] == ""
    assert get.call_args[1]["params"]["country"] == "IN"


def test_text_search_enriches_product_and_category():
    out, _, post = _call_text(
        get_records=[_search_record()],
        text="crude",
        scan_rows=[_scan_row("CL1!", product="Commodity/Energy/Oil/CrudeOil/WTI")],
    )
    record = out[0]
    assert record["category"] == "energy"
    assert record["categories"] == ["energy"]
    assert record["product"] == "Commodity/Energy/Oil/CrudeOil/WTI"
    assert record["continuous_symbol"] == "CL1!"
    assert record["full_name"] == "NYMEX:CL"
    assert record["country"] == "US"


def test_lookup_uses_the_continuous_contract_of_the_root():
    _, _, post = _call_text(
        get_records=[_search_record()], text="crude",
        scan_rows=[_scan_row("CL1!")],
    )
    lookup_filter = _filters(_body(post))[0]
    assert lookup_filter["left"] == "name"
    assert lookup_filter["operation"] == "in_range"
    assert lookup_filter["right"] == ["CL1!"]


def test_lookup_falls_back_to_root1_when_no_contracts_are_listed():
    record = _search_record()
    record.pop("contracts")
    _, _, post = _call_text(get_records=[record], text="crude",
                            scan_rows=[_scan_row("CL1!")])
    assert _filters(_body(post))[0]["right"] == ["CL1!"]


def test_text_search_filters_out_other_categories():
    out, _, _ = _call_text(
        get_records=[_search_record("AAPL", exchange="NASDAQ",
                                    description="Apple Futures")],
        text="apple", category="energy",
        scan_rows=[_scan_row("AAPL1!", exchange="NASDAQ", product="Financial/Equity")],
    )
    assert out == []


def test_text_search_keeps_matching_categories():
    out, _, _ = _call_text(
        get_records=[_search_record("AAPL", exchange="NASDAQ",
                                    description="Apple Futures")],
        text="apple", category="single_stock",
        scan_rows=[_scan_row("AAPL1!", exchange="NASDAQ", product="Financial/Equity")],
    )
    assert out and out[0]["category"] == "single_stock"


def test_text_search_product_filter_uses_prefixes():
    out, _, _ = _call_text(
        get_records=[_search_record()], text="gold",
        product="Commodity/Metals/Precious",
        scan_rows=[_scan_row("CL1!", exchange="COMEX",
                             product="Commodity/Metals/Precious/Gold")],
    )
    assert out and out[0]["category"] == "metals"


def test_text_search_exchange_retries_uppercased():
    out, get, _ = _call_text(
        get_side_effect=[
            _resp(payload=[]),
            _resp(payload=[_search_record(exchange="NYMEX")]),
        ],
        text="crude", exchange="nymex",
        scan_rows=[_scan_row("CL1!")],
    )
    assert len(get.call_args_list) == 2
    assert get.call_args_list[0][1]["params"]["exchange"] == "nymex"
    assert get.call_args_list[1][1]["params"]["exchange"] == "NYMEX"
    assert out and out[0]["exchange_id"] == "NYMEX"


def test_text_search_returns_empty_when_symbol_search_is_empty():
    out, _, post = _call_text(get_records=[], text="nothing-matches-this")
    assert out == []
    assert not post.called  # no screener lookup needed


def test_text_search_network_failure_returns_empty_list():
    out, _, _ = _call_text(get_records=[], text="crude")
    assert out == []


def test_text_search_respects_the_limit():
    records = [_search_record(f"CL{i}") for i in range(5)]
    rows = [_scan_row(f"CL{i}1!") for i in range(5)]
    out, _, _ = _call_text(get_records=records, text="cl", limit=2, scan_rows=rows)
    assert len(out) == 2


def test_text_search_keeps_extra_fields_and_strips_markup():
    record = _search_record(description="<em>Crude</em> Oil Futures")
    out, _, _ = _call_text(get_records=[record], text="crude",
                           scan_rows=[_scan_row("CL1!")])
    assert out[0]["description"] == "Crude Oil Futures"
    assert len(out[0]["contracts"]) == 3


# ---------------------------------------------------------------------------
# 10) integration with the client class / package exports
# ---------------------------------------------------------------------------
def _client(proxies=None):
    tv = TvDatafeed.__new__(TvDatafeed)
    tv.proxies = proxies or {}
    return tv


def test_instance_method_reuses_instance_proxies():
    tv = _client(proxies={"https": "http://proxy.example:8080"})
    with mock.patch(POST_TARGET, return_value=_resp(_scan_payload([]))) as post:
        tv.search_futures(category="metals")
    assert post.call_args[1]["proxies"] == {"https": "http://proxy.example:8080"}
    assert post.call_args[1]["timeout"] == 10


def test_instance_method_forwards_filters():
    tv = _client()
    with mock.patch(POST_TARGET, return_value=_resp(_scan_payload([]))) as post:
        tv.search_futures(exchange="COMEX", category="metals", limit=5,
                          continuous_only=False)
    filters = _filters(_body(post))
    assert _right_of(filters, "product") == "^Commodity/Metals"
    assert _right_of(filters, "exchange") == "COMEX"
    assert _right_of(filters, "name") is None
    assert _body(post)["range"] == [0, 5]


def test_package_exports_futures_search():
    import tvDatafeed

    assert tvDatafeed.search_futures is search_futures
    assert tvDatafeed.FUTURES_CATEGORIES is FUTURES_CATEGORIES
    assert tvDatafeed.list_futures_categories is list_futures_categories
    assert callable(tvDatafeed.list_futures_categories)


def test_version_bumped_for_the_new_feature():
    import tvDatafeed

    assert tvDatafeed.__version__ == "2.3.3"

"""Offline tests for the rebuilt symbol search (``tvDatafeed.search``).

Everything here is mocked: no request ever leaves the process.  The live
counterpart lives in ``tests/test_search_live.py`` (opt-in via ``TV_LIVE=1``).
"""
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests  # noqa: E402

from tvDatafeed import Interval, TvDatafeed, search_symbol  # noqa: E402
from tvDatafeed import datafeed  # noqa: E402
from tvDatafeed import search as search_module  # noqa: E402

PATCH_TARGET = "tvDatafeed.search.requests.get"

GOLD = {
    "symbol": "XAUUSD",
    "description": "Gold",
    "type": "commodity",
    "exchange": "OANDA",
    "currency_code": "USD",
    "typespecs": ["cfd"],
    "provider_id": "oanda",
}


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


def _ok(records):
    return _resp(payload=records)


def _call(patch_target=PATCH_TARGET, responses=None, side_effect=None, **kwargs):
    """Call search_symbol() with requests.get mocked out."""
    if side_effect is None:
        side_effect = [_ok(r) for r in responses] if responses is not None else [_ok([])]
    with mock.patch(patch_target, side_effect=side_effect) as get:
        out = search_symbol(**kwargs)
    return out, get


def _client(proxies=None):
    """A TvDatafeed built without touching the network."""
    tv = TvDatafeed.__new__(TvDatafeed)
    tv.proxies = proxies or {}
    return tv


def _live():
    """A TvDatafeedLive built without touching the network (or __del__)."""
    import threading

    live = datafeed.TvDatafeedLive.__new__(datafeed.TvDatafeedLive)
    live._lock = threading.Lock()
    live._sat = datafeed.TvDatafeedLive._SeisesAndTrigger()
    live._main_thread = None
    return live


# ---------------------------------------------------------------------------
# 1) request shape: URL building, headers, encoding
# ---------------------------------------------------------------------------
def test_request_uses_params_not_string_interpolation():
    """`&`/`#`/spaces in the text must never be able to alter the query."""
    _, get = _call(text="a&b=c d")
    args, kwargs = get.call_args
    assert kwargs["params"]["text"] == "a&b=c d"
    assert "text=" not in args[0]  # url is passed positionally, no query string


def test_request_has_required_headers():
    _, get = _call(text="gold")
    headers = get.call_args[1]["headers"]
    assert headers["Origin"] == "https://www.tradingview.com"
    assert headers["User-Agent"].startswith("Mozilla/5.0")
    assert "Chrome" in headers["User-Agent"]


def test_request_default_params():
    _, get = _call(text="gold")
    params = get.call_args[1]["params"]
    assert params == {"text": "gold", "hl": 0, "lang": "en", "domain": "production"}


def test_request_is_bounded_and_carries_proxies():
    _, get = _call(text="gold", proxies={"https": "http://p:1"})
    kwargs = get.call_args[1]
    assert kwargs["timeout"] == 10
    assert kwargs["proxies"] == {"https": "http://p:1"}


def test_search_url_is_the_known_endpoint():
    _, get = _call(text="gold")
    assert get.call_args[0][0] == "https://symbol-search.tradingview.com/symbol_search/"


def test_exchange_and_type_and_country_are_sent():
    _, get = _call(text="bank", exchange="TADAWUL", type="stock", country="SA")
    params = get.call_args[1]["params"]
    assert params["exchange"] == "TADAWUL"
    assert params["type"] == "stock"
    assert params["country"] == "SA"


def test_optional_filters_are_omitted_when_not_given():
    _, get = _call(text="gold")
    params = get.call_args[1]["params"]
    assert "type" not in params
    assert "country" not in params
    assert "exchange" not in params


def test_extra_params_are_forwarded_verbatim():
    _, get = _call(text="gold", extra={"sort_by": "name", "foo": "bar"})
    params = get.call_args[1]["params"]
    assert params["sort_by"] == "name"
    assert params["foo"] == "bar"


# ---------------------------------------------------------------------------
# 2) asset types: English + Arabic aliases
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "given,expected_server",
    [
        ("stock", "stock"),
        ("الأسهم", "stock"),
        ("bonds", "bond"),
        ("السندات", "bond"),
        ("forex", "forex"),
        ("الفوريكس", "forex"),
        ("فوركس", "forex"),
        ("index", "index"),
        ("المؤشرات", "index"),
        ("crypto", "crypto"),
        ("العملات الرقمية", "crypto"),
        ("futures", "futures"),
        ("العقود الآجلة", "futures"),
        ("options", "options"),
        ("الخيارات", "options"),
        ("etf", "etf"),
        ("funds", "funds"),
        ("cfds", "cfd"),
        ("عقود الفروقات", "cfd"),
        ("warrants", "warrant"),
        ("STOCK", "stock"),  # case-insensitive
    ],
)
def test_asset_type_aliases_map_to_server_values(given, expected_server):
    _, get = _call(text="x", type=given)
    assert get.call_args[1]["params"]["type"] == expected_server


def test_commodity_is_sent_as_cfd_but_returned_commodities_only():
    """TradingView rejects type=commodity -> query the CFD screen, filter locally."""
    mixed = [
        {"symbol": "XAUUSD", "exchange": "OANDA", "type": "commodity"},
        {"symbol": "EURUSD", "exchange": "OANDA", "type": "forex"},
        {"symbol": "XTIUSD", "exchange": "FOREXCOM", "type": "commodity"},
    ]
    out, get = _call(responses=[mixed], text="gold", type="السلع")
    assert get.call_args[1]["params"]["type"] == "cfd"
    assert [r["type"] for r in out] == ["commodity", "commodity"]


def test_stock_is_narrowed_locally_to_stock_and_dr():
    """The server's type=stock screen also returns fund hits -> filter them."""
    mixed = [
        {"symbol": "AAPL", "exchange": "NASDAQ", "type": "stock"},
        {"symbol": "AAEU", "exchange": "NASDAQ", "type": "fund"},
        {"symbol": "AAPL", "exchange": "BMV", "type": "dr"},
    ]
    out, get = _call(responses=[mixed], text="apple", type="stock")
    assert get.call_args[1]["params"]["type"] == "stock"
    assert [r["type"] for r in out] == ["stock", "dr"]


def test_commodity_falls_back_to_an_unfiltered_request():
    """If the CFD screen yields no commodity, retry without a type filter."""
    no_cfd_hits = []
    unfiltered_hits = [{"symbol": "TVC:GOLD", "exchange": "TVC", "type": "commodity"}]
    out, get = _call(
        responses=[no_cfd_hits, unfiltered_hits], text="gold", type="commodity"
    )
    assert len(get.call_args_list) == 2
    assert "type" not in get.call_args_list[1][1]["params"]
    assert out == [
        {
            "symbol": "TVC:GOLD",
            "full_name": "TVC:GOLD",  # symbol already contains the exchange
            "description": None,
            "exchange": "TVC",
            "exchange_id": "TVC",
            "type": "commodity",
            "country": None,
            "currency_code": None,
            "typespecs": [],
            "provider_id": None,
        }
    ]


def test_unknown_asset_type_raises_with_supported_list():
    with pytest.raises(ValueError) as exc:
        search_symbol("gold", type="سلعة غير موجودة")
    msg = str(exc.value)
    assert "commodity" in msg and "السلع" in msg and "bond" in msg


def test_non_string_asset_type_raises():
    with pytest.raises(ValueError, match="type must be a string"):
        search_symbol("gold", type=7)


# ---------------------------------------------------------------------------
# 3) countries: ISO codes + Arabic/English names
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "given,expected",
    [
        ("SA", "SA"),
        ("sa", "SA"),
        ("السعودية", "SA"),
        ("المملكة العربية السعودية", "SA"),
        ("Saudi Arabia", "SA"),
        ("مصر", "EG"),
        ("الإمارات", "AE"),
        ("usa", "US"),
        ("Germany", "DE"),
    ],
)
def test_country_aliases_map_to_iso_codes(given, expected):
    _, get = _call(text="bank", country=given)
    assert get.call_args[1]["params"]["country"] == expected


@pytest.mark.parametrize("bad", ["XYZ", "السعودية العربية", "Saudi", "", "   "])
def test_unknown_country_raises(bad):
    with pytest.raises(ValueError, match="country"):
        search_symbol("gold", country=bad)


def test_non_string_country_raises():
    with pytest.raises(ValueError, match="country must be a string"):
        search_symbol("gold", country=123)


def test_country_key_is_always_present_even_when_none():
    """Commodities/forex carry no country: the key must exist and be None."""
    out, _ = _call(responses=[[{"symbol": "XAUUSD", "exchange": "OANDA", "type": "commodity"}]],
                   text="gold")
    assert out[0]["country"] is None
    assert "country" in out[0]


# ---------------------------------------------------------------------------
# 4) argument validation
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("bad_text", ["", "   ", 123, None])
def test_invalid_text_raises(bad_text):
    with pytest.raises(ValueError, match="text"):
        search_symbol(bad_text)


@pytest.mark.parametrize("bad_limit", [0, -1, "5", 5.5, True])
def test_invalid_limit_raises(bad_limit):
    with pytest.raises(ValueError, match="limit"):
        search_symbol("gold", limit=bad_limit)


def test_limit_is_clamped_to_the_server_maximum():
    out, _ = _call(responses=[[dict(GOLD) for _ in range(50)]], text="gold", limit=500)
    assert len(out) == 50


def test_limit_slices_the_results():
    out, _ = _call(responses=[[dict(GOLD) for _ in range(10)]], text="gold", limit=3)
    assert len(out) == 3


@pytest.mark.parametrize("bad_timeout", [0, -1, "10", None])
def test_invalid_timeout_raises(bad_timeout):
    with pytest.raises(ValueError, match="timeout"):
        search_symbol("gold", timeout=bad_timeout)


def test_invalid_extra_raises():
    with pytest.raises(ValueError, match="extra"):
        search_symbol("gold", extra=["sort_by"])


def test_invalid_exchange_raises():
    with pytest.raises(ValueError, match="exchange must be a string"):
        search_symbol("gold", exchange=5)


def test_invalid_lang_raises():
    with pytest.raises(ValueError, match="lang"):
        search_symbol("gold", lang="")


# ---------------------------------------------------------------------------
# 5) response normalisation
# ---------------------------------------------------------------------------
def test_em_markup_is_stripped():
    hl_payload = [{"symbol": "<em>XAU</em>USD", "description": "<em>Gold</em> vs US Dollar",
                   "exchange": "OANDA", "type": "commodity"}]
    out, _ = _call(responses=[hl_payload], text="xau")
    assert out[0]["symbol"] == "XAUUSD"
    assert out[0]["description"] == "Gold vs US Dollar"


def test_full_name_is_built_from_exchange_and_symbol():
    out, _ = _call(responses=[[dict(GOLD)]], text="gold")
    assert out[0]["full_name"] == "OANDA:XAUUSD"


def test_normalised_record_has_every_documented_key():
    out, _ = _call(responses=[[{"symbol": "XAUUSD", "exchange": "OANDA"}]], text="gold")
    for key in ("symbol", "full_name", "description", "exchange", "exchange_id",
                "type", "country", "currency_code", "typespecs", "provider_id"):
        assert key in out[0]
    assert out[0]["typespecs"] == []          # never None -> always iterable
    assert out[0]["description"] is None


def test_exchange_id_uses_source_id_not_the_display_name():
    """'BlackBull Markets' is the display name; the id is 'BLACKBULL'."""
    record = {
        "symbol": "XAUUSD",
        "exchange": "BlackBull Markets",
        "source_id": "BLACKBULL",
        "source2": {"id": "BLACKBULL", "name": "BlackBull Markets"},
        "type": "commodity",
    }
    out, _ = _call(responses=[[record]], text="xauusd")
    assert out[0]["exchange"] == "BlackBull Markets"
    assert out[0]["exchange_id"] == "BLACKBULL"
    assert out[0]["full_name"] == "BLACKBULL:XAUUSD"


def test_exchange_id_falls_back_to_source2_id():
    record = {
        "symbol": "XAUUSD",
        "exchange": "OANDA",
        "source2": {"id": "OANDA"},
        "type": "commodity",
    }
    out, _ = _call(responses=[[record]], text="xauusd")
    assert out[0]["exchange_id"] == "OANDA"


def test_exchange_id_falls_back_to_exchange_when_no_id_is_present():
    out, _ = _call(responses=[[dict(GOLD)]], text="gold")
    assert out[0]["exchange_id"] == "OANDA"


def test_extra_fields_from_tradingview_are_kept():
    out, _ = _call(responses=[[dict(GOLD, logoid="metal/gold")]], text="gold")
    assert out[0]["logoid"] == "metal/gold"
    assert out[0]["symbol"] == "XAUUSD"  # documented keys come first/unchanged


def test_returns_a_list_of_dicts():
    out, _ = _call(responses=[[dict(GOLD)]], text="gold")
    assert isinstance(out, list) and isinstance(out[0], dict)


# ---------------------------------------------------------------------------
# 6) failure modes never raise (network problems -> [])
# ---------------------------------------------------------------------------
def test_http_error_returns_empty_list():
    bad = _resp(raise_exc=requests.exceptions.HTTPError("403 Client Error"))
    with mock.patch(PATCH_TARGET, return_value=bad) as get:
        assert search_symbol("gold") == []
    get.assert_called_once()


def test_non_json_body_returns_empty_list():
    bad = _resp(json_exc=ValueError("not json"))
    with mock.patch(PATCH_TARGET, return_value=bad):
        assert search_symbol("gold") == []


def test_connection_error_returns_empty_list():
    with mock.patch(PATCH_TARGET, side_effect=requests.exceptions.ConnectionError("boom")):
        assert search_symbol("gold") == []


def test_error_object_payload_returns_empty_list():
    """HTTP 400 answers ``{"error": ...}`` -- must not be iterated as a list."""
    err = _resp(payload={"error": "converted_search_type_not_found: x"})
    with mock.patch(PATCH_TARGET, return_value=err):
        assert search_symbol("gold") == []


def test_non_dict_records_are_dropped():
    out, _ = _call(responses=[[dict(GOLD), "junk", None]], text="gold")
    assert len(out) == 1


# ---------------------------------------------------------------------------
# 7) exchange case sensitivity fallback
# ---------------------------------------------------------------------------
def test_exchange_retries_with_uppercase_when_first_attempt_is_empty():
    out, get = _call(
        responses=[[], [dict(GOLD, exchange="BLACKBULL")]],
        text="XAUUSD",
        exchange="blackbull",
    )
    assert len(get.call_args_list) == 2
    assert get.call_args_list[0][1]["params"]["exchange"] == "blackbull"
    assert get.call_args_list[1][1]["params"]["exchange"] == "BLACKBULL"
    assert out[0]["full_name"] == "BLACKBULL:XAUUSD"


def test_exchange_is_not_uppercased_when_the_first_attempt_works():
    out, get = _call(responses=[[dict(GOLD, exchange="OANDA")]], text="XAUUSD", exchange="oanda")
    assert len(get.call_args_list) == 1
    assert out[0]["exchange"] == "OANDA"


# ---------------------------------------------------------------------------
# 8) integration with the client classes
# ---------------------------------------------------------------------------
def test_module_level_function_needs_no_client_object():
    """search_symbol() must work without TvDatafeed() and without login."""
    out, _ = _call(responses=[[dict(GOLD)]], text="gold")
    assert out[0]["symbol"] == "XAUUSD"
    # no TvDatafeed instance involved anywhere in this test


def test_instance_method_reuses_instance_proxies():
    tv = _client(proxies={"https": "http://proxy.example:8080"})
    with mock.patch(PATCH_TARGET, return_value=_ok([])) as get:
        tv.search_symbol("gold")
    kwargs = get.call_args[1]
    assert kwargs["proxies"] == {"https": "http://proxy.example:8080"}
    assert kwargs["timeout"] == 10


def test_instance_method_signature_is_backwards_compatible():
    tv = _client()
    with mock.patch(PATCH_TARGET, return_value=_ok([])) as get:
        tv.search_symbol("XAUUSD", "BLACKBULL")  # old positional call
    params = get.call_args[1]["params"]
    assert params["text"] == "XAUUSD"
    assert params["exchange"] == "BLACKBULL"


def test_instance_method_forwards_new_arguments():
    tv = _client()
    with mock.patch(PATCH_TARGET, return_value=_ok([])) as get:
        tv.search_symbol("gold", type="السلع", country="SA", limit=5, lang="ar")
    # first request carries the resolved type filter (the mock returns no
    # records, so the commodity fallback issues a second unfiltered request)
    params = get.call_args_list[0][1]["params"]
    assert params["type"] == "cfd"
    assert params["country"] == "SA"
    assert params["lang"] == "ar"


def test_args_invalid_detects_a_missing_symbol():
    live = _live()
    live.search_symbol = lambda text, exchange: [
        {"symbol": "XAUUSD", "exchange": "BLACKBULL"}
    ]
    assert live._args_invalid("XAUUSD", "BLACKBULL") is False
    assert live._args_invalid("XAUUSD", "OANDA") is True
    assert live._args_invalid("NOPE", "BLACKBULL") is True


def test_args_invalid_is_true_when_search_fails():
    """A network failure ([] ) must not be mistaken for a valid symbol."""
    live = _live()
    live.search_symbol = lambda text, exchange: []
    assert live._args_invalid("XAUUSD", "BLACKBULL") is True


def test_new_seis_still_rejects_unknown_symbols():
    live = _live()
    live.search_symbol = lambda text, exchange: []
    with pytest.raises(ValueError, match="not listed in TradingView"):
        live.new_seis("XAUUSD", "BLACKBULL", Interval.in_daily)


def test_package_exports_search_symbol():
    import tvDatafeed

    assert tvDatafeed.search_symbol is search_symbol
    assert tvDatafeed.search_symbol is search_module.search_symbol

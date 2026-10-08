"""Symbol search for TradingView -- works without logging in.

The public endpoint used here

    https://symbol-search.tradingview.com/symbol_search/

does **not** require a TradingView account, a session cookie or an auth
token.  It does however reject requests that do not carry an ``Origin``
header (nginx answers ``403 Forbidden``), which is why the headers below
are mandatory.

The module is intentionally free of any dependency on :class:`TvDatafeed`
so that symbols can be looked up without creating a client object::

    from tvDatafeed import search_symbol
    search_symbol("gold", type="السلع", country="السعودية")
"""

from __future__ import annotations

import html
import logging
import re

import requests

logger = logging.getLogger(__name__)

__all__ = ["search_symbol", "ASSET_TYPES", "USER_AGENT", "SEARCH_URL"]

SEARCH_URL = "https://symbol-search.tradingview.com/symbol_search/"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# TradingView's nginx refuses the request unless an Origin header points
# back at tradingview.com.  A browser User-Agent alone (or User-Agent +
# Referer) is answered with 403 -- verified empirically.
_SEARCH_HEADERS = {
    "User-Agent": USER_AGENT,
    "Origin": "https://www.tradingview.com",
    "Referer": "https://www.tradingview.com/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

# The endpoint always answers with at most 50 records per request.
MAX_LIMIT = 50

_TAG_RE = re.compile(r"<[^>]*>")


# ---------------------------------------------------------------------------
# Asset types
# ---------------------------------------------------------------------------
# ``server`` is the value sent in the ``type`` query parameter.  TradingView
# does NOT accept ``type=commodity`` (400 converted_search_type_not_found):
# spot commodities (gold, oil, ...) are reachable through the ``cfd`` screen,
# so commodities are fetched with ``type=cfd`` and then narrowed down locally
# with ``filter``.
ASSET_TYPES = {
    "stock": {
        "server": "stock",
        "expected": {"stock", "dr"},
        "label": "الأسهم / Stocks",
        "aliases": ["stocks", "share", "shares", "equity", "equities", "أسهم", "اسهم", "سهم", "الأسهم"],
    },
    "commodity": {
        "server": "cfd",
        "filter": "commodity",
        "expected": {"commodity"},
        "label": "السلع / Commodities",
        "aliases": ["commodities", "commodity", "commoditie", "سلع", "السلع", "سلعة", "السلعة"],
    },
    "bond": {
        "server": "bond",
        "expected": {"bond"},
        "label": "السندات / Bonds",
        "aliases": ["bonds", "bond", "سندات", "السندات", "سند", "السند"],
    },
    "forex": {
        "server": "forex",
        "expected": {"forex"},
        "label": "الفوريكس / Forex",
        "aliases": ["fx", "currency", "currencies", "فوريكس", "فوركس", "الفوريكس", "الفوركس", "عملات", "العملات"],
    },
    "index": {
        "server": "index",
        "expected": {"index"},
        "label": "المؤشرات / Indices",
        "aliases": ["indices", "indexes", "مؤشرات", "المؤشرات", "مؤشر", "المؤشر"],
    },
    "crypto": {
        "server": "crypto",
        # crypto instruments are typed spot/swap/index/commodity... -> no
        # reliable local filter; trust the server's screen.
        "label": "العملات الرقمية / Crypto",
        "aliases": [
            "cryptocurrency", "cryptocurrencies", "كريبتو",
            "عملات رقمية", "العملات الرقمية", "الرقمية",
        ],
    },
    "futures": {
        "server": "futures",
        "expected": {"futures"},
        "label": "العقود الآجلة / Futures",
        "aliases": ["future", "عقود آجلة", "العقود الآجلة", "آجلة", "مستقبلية", "المستقبلية", "فواتشر"],
    },
    "etf": {
        "server": "etf",
        "expected": {"fund"},
        "label": "صناديق ETF",
        "aliases": ["etfs", "exchange traded fund", "إي تي إف", "صناديق مؤشرات"],
    },
    "fund": {
        "server": "funds",
        "expected": {"fund"},
        "label": "الصناديق / Funds",
        "aliases": ["funds", "mutual fund", "mutual funds", "صناديق", "الصناديق", "صندوق"],
    },
    "cfd": {
        "server": "cfd",
        # spot CFDs are typed commodity/forex/index -> trust the server's screen.
        "label": "عقود الفروقات / CFDs",
        "aliases": ["cfds", "عقود فروقات", "عقود الفروقات", "فروقات", "الفروقات"],
    },
    "option": {
        "server": "options",
        "expected": {"option"},
        "label": "الخيارات / Options",
        "aliases": ["options", "خيارات", "الخيارات"],
    },
    "warrant": {
        "server": "warrant",
        "expected": {"warrant"},
        "label": "الأسهم الواردة / Warrants",
        "aliases": ["warrants", "شهادات", "شهادة"],
    },
}

# alias (casefolded) -> canonical type
_TYPE_LOOKUP = {}
for _canonical, _spec in ASSET_TYPES.items():
    for _alias in _spec["aliases"] + [_canonical]:
        _TYPE_LOOKUP.setdefault(_alias.casefold(), _canonical)

_TYPE_HELP = ", ".join(f"{name} ({spec['label']})" for name, spec in ASSET_TYPES.items())


# ---------------------------------------------------------------------------
# Countries
# ---------------------------------------------------------------------------
# Accepts either an ISO-3166 alpha-2 code ("SA", "us") or a country name in
# Arabic/English.  Filtering by country is optional: commodities, forex and
# crypto records frequently carry no country at all and are returned with
# ``country=None``.
COUNTRY_ALIASES = {
    # Middle East & North Africa
    "السعودية": "SA", "المملكة العربية السعودية": "SA", "saudi arabia": "SA", "ksa": "SA",
    "مصر": "EG", "egypt": "EG",
    "الإمارات": "AE", "الامارات": "AE", "الإمارات العربية المتحدة": "AE",
    "uae": "AE", "united arab emirates": "AE",
    "قطر": "QA", "qatar": "QA",
    "الكويت": "KW", "kuwait": "KW",
    "البحرين": "BH", "bahrain": "BH",
    "عمان": "OM", "عُمان": "OM", "oman": "OM",
    "الأردن": "JO", "الاردن": "JO", "jordan": "JO",
    "المغرب": "MA", "morocco": "MA",
    "تونس": "TN", "tunisia": "TN",
    "الجزائر": "DZ", "algeria": "DZ",
    "العراق": "IQ", "iraq": "IQ",
    "لبنان": "LB", "lebanon": "LB",
    "سوريا": "SY", "syria": "SY",
    "اليمن": "YE", "yemen": "YE",
    "ليبيا": "LY", "libya": "LY",
    "السودان": "SD", "sudan": "SD",
    "فلسطين": "PS", "palestine": "PS",
    # Major markets
    "أمريكا": "US", "الولايات المتحدة": "US", "الولايات المتحدة الأمريكية": "US",
    "usa": "US", "united states": "US", "united states of america": "US",
    "بريطانيا": "GB", "المملكة المتحدة": "GB", "uk": "GB", "united kingdom": "GB", "england": "GB",
    "ألمانيا": "DE", "المانيا": "DE", "germany": "DE",
    "فرنسا": "FR", "france": "FR",
    "إيطاليا": "IT", "ايطاليا": "IT", "italy": "IT",
    "إسبانيا": "ES", "اسبانيا": "ES", "spain": "ES",
    "هولندا": "NL", "netherlands": "NL",
    "سويسرا": "CH", "switzerland": "CH",
    "السويد": "SE", "sweden": "SE",
    "النرويج": "NO", "norway": "NO",
    "الدنمارك": "DK", "denmark": "DK",
    "فنلندا": "FI", "finland": "FI",
    "بلجيكا": "BE", "belgium": "BE",
    "النمسا": "AT", "austria": "AT",
    "البرتغال": "PT", "portugal": "PT",
    "اليونان": "GR", "greece": "GR",
    "أيرلندا": "IE", "ايرلندا": "IE", "ireland": "IE",
    "بولندا": "PL", "poland": "PL",
    "روسيا": "RU", "russia": "RU",
    "تركيا": "TR", "turkey": "TR", "turkiye": "TR",
    "الصين": "CN", "china": "CN",
    "اليابان": "JP", "japan": "JP",
    "كوريا": "KR", "كوريا الجنوبية": "KR", "south korea": "KR", "korea": "KR",
    "هونغ كونغ": "HK", "hong kong": "HK",
    "تايوان": "TW", "taiwan": "TW",
    "سنغافورة": "SG", "singapore": "SG",
    "الهند": "IN", "india": "IN",
    "باكستان": "PK", "pakistan": "PK",
    "إندونيسيا": "ID", "اندونيسيا": "ID", "indonesia": "ID",
    "ماليزيا": "MY", "malaysia": "MY",
    "تايلاند": "TH", "thailand": "TH",
    "الفلبين": "PH", "philippines": "PH",
    "فيتنام": "VN", "vietnam": "VN",
    "إسرائيل": "IL", "اسرائيل": "IL", "israel": "IL",
    "البرازيل": "BR", "brazil": "BR",
    "كندا": "CA", "canada": "CA",
    "أستراليا": "AU", "استراليا": "AU", "australia": "AU",
    "نيوزيلندا": "NZ", "new zealand": "NZ",
    "جنوب أفريقيا": "ZA", "جنوب افريقيا": "ZA", "south africa": "ZA",
    "المكسيك": "MX", "mexico": "MX",
    "نيجيريا": "NG", "nigeria": "NG",
    "كينيا": "KE", "kenya": "KE",
}

# normalised lookup: casefolded name -> ISO code
_COUNTRY_LOOKUP = {name.casefold(): code for name, code in COUNTRY_ALIASES.items()}


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------
def _type_name(value):
    """``type(value).__name__`` that also works where ``type`` is shadowed."""
    return type(value).__name__


def _resolve_type(value):
    """Map a user supplied asset type onto its ASSET_TYPES spec (or None)."""
    if value is None:
        return None

    if not isinstance(value, str):
        raise ValueError(
            f"type must be a string, got {_type_name(value)}. "
            f"Supported types: {_TYPE_HELP}."
        )

    key = value.strip().casefold()
    if not key:
        raise ValueError(f"Unknown asset type {value!r}. Supported types: {_TYPE_HELP}.")

    canonical = _TYPE_LOOKUP.get(key)
    if canonical is None:
        raise ValueError(
            f"Unknown asset type {value!r}. Supported types: {_TYPE_HELP}."
        )

    return ASSET_TYPES[canonical]


def _resolve_country(value):
    """Map a user supplied country onto an ISO-3166 alpha-2 code (or None)."""
    if value is None:
        return None

    if not isinstance(value, str):
        raise ValueError(
            f"country must be a string, got {type(value).__name__}. "
            "Use an ISO-3166 alpha-2 code such as 'SA' or 'US', or a country "
            "name such as 'السعودية' / 'Saudi Arabia'."
        )

    raw = value.strip()
    if not raw:
        raise ValueError(
            "country must not be empty. Use an ISO-3166 alpha-2 code such as "
            "'SA' or 'US', or a country name such as 'السعودية' / 'Saudi Arabia'."
        )

    if len(raw) == 2 and raw.isalpha():
        return raw.upper()

    code = _COUNTRY_LOOKUP.get(raw.casefold())
    if code is None:
        raise ValueError(
            f"Unknown country {value!r}. Use an ISO-3166 alpha-2 code such as "
            "'SA' or 'US', or a country name such as 'السعودية' / 'Saudi Arabia'."
        )
    return code


def _validate_text(text):
    if not isinstance(text, str):
        raise ValueError(f"text must be a string, got {type(text).__name__}.")
    cleaned = text.strip()
    if not cleaned:
        raise ValueError("text must not be empty.")
    return cleaned


def _validate_limit(limit):
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise ValueError(f"limit must be an integer, got {type(limit).__name__}.")
    if limit < 1:
        raise ValueError(f"limit must be >= 1, got {limit}.")
    if limit > MAX_LIMIT:
        logger.debug("limit %d clamped to the maximum of %d", limit, MAX_LIMIT)
        return MAX_LIMIT
    return limit


def _validate_lang(lang):
    if not isinstance(lang, str) or not lang.strip():
        raise ValueError(f"lang must be a non-empty string, got {lang!r}.")
    return lang.strip()


def _validate_timeout(timeout):
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
        raise ValueError(f"timeout must be a number of seconds, got {timeout!r}.")
    if timeout <= 0:
        raise ValueError(f"timeout must be > 0, got {timeout!r}.")
    return timeout


def _validate_extra(extra):
    if extra is None:
        return {}
    if not isinstance(extra, dict):
        raise ValueError(f"extra must be a dict of query parameters, got {type(extra).__name__}.")
    return dict(extra)


# ---------------------------------------------------------------------------
# Request + normalisation
# ---------------------------------------------------------------------------
def _request(params, timeout, proxies):
    """Perform one search request.  Returns a list of raw records or []."""
    try:
        response = requests.get(
            SEARCH_URL,
            params=params,
            headers=_SEARCH_HEADERS,
            timeout=timeout,
            proxies=proxies,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:  # network, HTTP or JSON failure
        logger.warning("symbol search failed for %r: %s", params.get("text"), exc)
        return []

    if not isinstance(payload, list):
        # TradingView answers {"error": ...} with HTTP 400 for bad filters.
        logger.warning(
            "unexpected symbol search response for %r: %r", params.get("text"), payload
        )
        return []

    return [record for record in payload if isinstance(record, dict)]


def _clean(value):
    """Strip ``<em>`` highlight markup (and any other tag) from strings."""
    if isinstance(value, str):
        return html.unescape(_TAG_RE.sub("", value))
    if isinstance(value, list):
        return [_clean(item) for item in value]
    return value


def _normalize(record):
    """Return a stable, documented dict for one search hit.

    Every documented key is always present: symbols that carry no country
    (commodities, forex, crypto, indices ...) simply get ``country=None``.

    ``exchange`` keeps TradingView's *display name* (e.g. "BlackBull
    Markets") while ``exchange_id`` is the canonical id used in
    ``EXCHANGE:SYMBOL`` notation and accepted by ``get_hist``
    (e.g. "BLACKBULL").
    """
    cleaned = {key: _clean(value) for key, value in record.items()}

    symbol = cleaned.get("symbol")
    exchange = cleaned.get("exchange")

    # The canonical exchange id lives in source_id / source2.id; the bare
    # ``exchange`` field is a human-readable display name.
    exchange_id = cleaned.get("source_id")
    source2 = cleaned.get("source2")
    if not exchange_id and isinstance(source2, dict):
        exchange_id = source2.get("id")
    if not exchange_id:
        exchange_id = exchange

    full_name = cleaned.get("full_name")
    if not full_name:
        if not symbol:
            full_name = None
        elif ":" in symbol:
            full_name = symbol          # already in EXCHANGE:SYMBOL form
        elif exchange_id:
            full_name = f"{exchange_id}:{symbol}"
        else:
            full_name = symbol

    return {
        "symbol": symbol,
        "full_name": full_name,
        "description": cleaned.get("description"),
        "exchange": exchange,
        "exchange_id": exchange_id,
        "type": cleaned.get("type"),
        "country": cleaned.get("country"),
        "currency_code": cleaned.get("currency_code"),
        "typespecs": cleaned.get("typespecs") or [],
        "provider_id": cleaned.get("provider_id"),
        **{
            key: value
            for key, value in cleaned.items()
            if key
            not in {
                "symbol", "full_name", "description", "exchange",
                "exchange_id", "type", "country", "currency_code",
                "typespecs", "provider_id",
            }
        },
    }


def search_symbol(
    text: str,
    exchange: str = "",
    type: str = None,
    country: str = None,
    limit: int = 50,
    lang: str = "en",
    timeout: float = 10,
    proxies: dict = None,
    extra: dict = None,
) -> list:
    """Search TradingView symbols -- **no account / login required**.

    Args:
        text: symbol name or description, e.g. ``"XAUUSD"``, ``"أرامكو"``.
        exchange: optional exchange id to restrict the search to, e.g.
            ``"BLACKBULL"`` or ``"TADAWUL"`` (ids are case sensitive on
            TradingView's side; an upper-cased retry is done automatically
            when the first attempt returns nothing).
        type: optional asset type, in English or Arabic:
            ``stock/الأسهم``, ``commodity/السلع``, ``bond/السندات``,
            ``forex/الفوريكس``, ``index/المؤشرات``,
            ``crypto/العملات الرقمية``, ``futures/العقود الآجلة``,
            ``etf``, ``fund/الصناديق``, ``cfd/عقود الفروقات``,
            ``option/الخيارات``, ``warrant``.
        country: optional ISO-3166 alpha-2 code (``"SA"``) or country name
            (``"السعودية"``, ``"Saudi Arabia"``).  Optional by nature:
            commodities/forex/crypto results simply come back with
            ``country=None``.
        limit: maximum number of records (1..50; TradingView never returns
            more than 50 per request, larger values are clamped).
        lang: interface language passed to TradingView (``"en"``, ``"ar"``...).
        timeout: per-request timeout in seconds.
        proxies: optional ``{"https": "http://..."}`` mapping.
        extra: optional extra query parameters forwarded verbatim, so new
            TradingView filters can be used without changing this module.

    Returns:
        list[dict]: normalised records.  Always contains the keys
        ``symbol``, ``full_name`` (``"EXCHANGE:SYMBOL"``), ``description``,
        ``exchange``, ``type``, ``country``, ``currency_code``,
        ``typespecs``, ``provider_id`` plus any extra fields TradingView
        returns.  Network/HTTP/JSON failures return ``[]`` (never raise).

    Raises:
        ValueError: if ``text``/``type``/``country``/``limit``/``lang``/
            ``timeout``/``extra`` are invalid -- invalid *arguments* fail
            fast, only *network* problems return ``[]``.
    """
    text = _validate_text(text)
    asset_spec = _resolve_type(type)
    server_type = asset_spec["server"] if asset_spec else None
    filter_type = asset_spec.get("filter") if asset_spec else None
    expected_types = asset_spec.get("expected") if asset_spec else None
    iso_country = _resolve_country(country)
    limit = _validate_limit(limit)
    lang = _validate_lang(lang)
    timeout = _validate_timeout(timeout)
    extra_params = _validate_extra(extra)

    if exchange is not None and not isinstance(exchange, str):
        raise ValueError(f"exchange must be a string, got {_type_name(exchange)}.")
    exchange = (exchange or "").strip()

    params = {"text": text, "hl": 0, "lang": lang, "domain": "production"}
    if exchange:
        params["exchange"] = exchange
    if server_type:
        params["type"] = server_type
    if iso_country:
        params["country"] = iso_country
    params.update(extra_params)

    records = _request(params, timeout, proxies)

    # TradingView's exchange filter is case sensitive (``blackbull`` -> 0
    # hits, ``BLACKBULL`` -> 9).  Retry upper-cased once when needed.
    if not records and exchange and exchange != exchange.upper():
        upper_params = {**params, "exchange": exchange.upper()}
        records = _request(upper_params, timeout, proxies)

    # ``commodity`` is not a valid server-side filter: we query the CFD
    # screen and narrow the records down locally (with one last unfiltered
    # attempt so no commodity can be missed).
    if filter_type:
        narrowed = [r for r in records if r.get("type") == filter_type]
        if not narrowed:
            unfiltered = {k: v for k, v in params.items() if k != "type"}
            fallback = _request(unfiltered, timeout, proxies)
            narrowed = [r for r in fallback if r.get("type") == filter_type]
        records = narrowed
    elif expected_types:
        # Precise local filter for the classes TradingView's broad screen
        # mixes in (e.g. ``type=stock`` also returns fund/structured hits).
        records = [r for r in records if r.get("type") in expected_types]

    return [_normalize(record) for record in records[:limit]]

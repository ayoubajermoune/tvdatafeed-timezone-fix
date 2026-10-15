"""Custom futures search for TradingView -- no account / login required.

TradingView's public *symbol search* endpoint (used by
:mod:`tvDatafeed.search`) can filter instruments by ``type=futures``, by
``exchange`` and by ``country``, but it has **no notion of a futures
category**.  That information lives in TradingView's futures *screener*::

    POST https://scanner.tradingview.com/futures/scan

whose ``product`` column is a small hierarchical taxonomy that maps exactly
onto the ten futures categories supported here::

    Financial/Equity            -> single_stock        (الأسهم الفردية)
    Financial/Index             -> world_indices       (المؤشرات العالمية)
    Financial/Currency          -> currencies          (العملات)
    Financial/InterestRate      -> interest_rates      (أسعار الفائدة)
    Commodity/Energy/...        -> energy              (الطاقة)
    Commodity/Agriculture/...   -> agriculture         (الزراعة)
    Commodity/Metals/...        -> metals              (المعادن)
    Commodity/Weather           -> weather             (الطقس)
    Commodity/BuildingMaterials -> building_materials  (مواد البناء)
    Commodity/Chemicals         -> chemicals           (المواد الكيميائية)

Examples
--------
The module is standalone (no client object and no login needed) and mirrors
the :func:`tvDatafeed.search.search_symbol` contract -- invalid *arguments*
raise ``ValueError`` while *network* failures return ``[]``::

    from tvDatafeed import search_futures

    search_futures(category="الطاقة", exchange="NYMEX")   # energy on NYMEX
    search_futures(country="السعودية", category="metals")  # by country
    search_futures("crude", category="energy")            # text + category
    search_futures(product="Commodity/Weather")           # sub-category
"""

from __future__ import annotations

import logging
import re

import requests

try:
    from .search import (
        MAX_LIMIT,
        USER_AGENT,
        _normalize,
        _request,
        _resolve_country,
        _validate_lang,
        _validate_limit,
        _validate_timeout,
    )
except ImportError:  # pragma: no cover - running ``python tvDatafeed/futures.py``
    from search import (
        MAX_LIMIT,
        USER_AGENT,
        _normalize,
        _request,
        _resolve_country,
        _validate_lang,
        _validate_limit,
        _validate_timeout,
    )

logger = logging.getLogger(__name__)

__all__ = [
    "search_futures",
    "list_futures_categories",
    "category_for_product",
    "categories_for_product",
    "FUTURES_CATEGORIES",
    "SCAN_URL",
    "MAX_LIMIT",
]

SCAN_URL = "https://scanner.tradingview.com/futures/scan"

# The screener answers plain JSON POSTs.  ``Origin``/``Referer`` are not
# strictly required (unlike the symbol-search endpoint) but we send the same
# browser-like headers TradingView itself uses.
_SCAN_HEADERS = {
    "User-Agent": USER_AGENT,
    "Origin": "https://www.tradingview.com",
    "Referer": "https://www.tradingview.com/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Content-Type": "application/json",
}

# Columns read from the futures screener.  ``product`` is the category
# taxonomy used for filtering, ``logoid`` keeps TradingView's fine-grained
# icon id (e.g. ``metal/gold``, ``weather/cool``).
_SCAN_COLUMNS = [
    "name",
    "description",
    "exchange",
    "product",
    "logoid",
    "type",
    "typespecs",
    "currency",
    "close",
    "change",
]

# Continuous contracts (``CL1!``, ``CL2!`` ...) end with ``<digit>!``.
_CONTINUOUS_RE = re.compile(r"[0-9]!$")

# How many symbol names to send in a single ``in_range`` lookup.
_LOOKUP_CHUNK = 100
# How many rows to allow for such a lookup (a name can exist on several
# exchanges, so the answer can be larger than the number of names sent).
_LOOKUP_ROWS_PER_NAME = 5


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------
# ``product`` is TradingView's own hierarchical value (the ``product`` column
# of the futures screener).  Filtering is done server-side with a regex
# anchored at the start, so ``Commodity/Metals`` also matches
# ``Commodity/Metals/Precious/Gold`` -- exactly the "family" semantics wanted
# for a category.
FUTURES_CATEGORIES = {
    "single_stock": {
        "product": "Financial/Equity",
        "en": "Single stock",
        "label": "الأسهم الفردية / Single stock",
        "aliases": [
            "single stock", "single stocks", "single stock futures",
            "single_stock", "single-stock", "stock", "stocks", "share",
            "shares", "equity", "equities",
            "أسهم فردية", "الأسهم الفردية", "سهم", "أسهم", "اسهم", "الأسهم",
        ],
    },
    "world_indices": {
        "product": "Financial/Index",
        "en": "World indices",
        "label": "المؤشرات العالمية / World indices",
        "aliases": [
            "world indices", "world index", "world_indices", "indices",
            "indexes", "index", "stock index", "stock indices",
            "مؤشرات", "المؤشرات", "المؤشرات العالمية", "مؤشرات عالمية",
            "مؤشر عالمي", "مؤشر",
        ],
    },
    "currencies": {
        "product": "Financial/Currency",
        "en": "Currencies",
        "label": "العملات / Currencies",
        "aliases": [
            "currencies", "currency", "forex", "fx", "currency futures",
            "عملات", "العملات", "فوريكس", "فوركس", "الفوريكس", "الفوركس",
        ],
    },
    "interest_rates": {
        "product": "Financial/InterestRate",
        "en": "Interest rates",
        "label": "أسعار الفائدة / Interest rates",
        "aliases": [
            "interest rates", "interest rate", "rates", "rate", "yield",
            "yields", "interest_rates", "interest-rates",
            "أسعار الفائدة", "سعر الفائدة", "الفائدة", "فوائد", "العوائد",
        ],
    },
    "energy": {
        "product": "Commodity/Energy",
        "en": "Energy",
        "label": "الطاقة / Energy",
        "aliases": [
            "energy", "oil", "crude", "crude oil", "gas", "natural gas",
            "gasoline", "electricity", "coal", "طاقة", "الطاقة", "نفط",
            "النفط", "خام", "الخام", "غاز", "الغاز", "كهرباء", "فحم",
        ],
    },
    "agriculture": {
        "product": "Commodity/Agriculture",
        "en": "Agriculture",
        "label": "الزراعة / Agriculture",
        "aliases": [
            "agriculture", "agricultural", "agri", "farming",
            "زراعة", "الزراعة", "زراعي", "محاصيل", "المحاصيل", "منتجات زراعية",
        ],
    },
    "metals": {
        "product": "Commodity/Metals",
        "en": "Metals",
        "label": "المعادن / Metals",
        "aliases": [
            "metals", "metal", "metals futures",
            "معادن", "المعادن", "معدن",
        ],
    },
    "weather": {
        "product": "Commodity/Weather",
        "en": "Weather",
        "label": "الطقس / Weather",
        "aliases": [
            "weather", "weather futures", "temperature",
            "طقس", "الطقس", "مناخ", "المناخ", "حرارة", "الحرارة",
        ],
    },
    "building_materials": {
        "product": "Commodity/BuildingMaterials",
        "en": "Building materials",
        "label": "مواد البناء / Building materials",
        "aliases": [
            "building materials", "building material", "construction",
            "lumber", "timber", "building_materials", "building-materials",
            "مواد البناء", "مواد بناء", "البناء", "خشب", "الأخشاب", "أخشاب",
        ],
    },
    "chemicals": {
        "product": "Commodity/Chemicals",
        "en": "Chemicals",
        "label": "المواد الكيميائية / Chemicals",
        "aliases": [
            "chemicals", "chemical", "chemical futures",
            "مواد كيميائية", "المواد الكيميائية", "كيماويات", "الكيماويات",
            "كيمياء",
        ],
    },
}

# Display order (also the order used when several categories could match).
FUTURES_CATEGORY_ORDER = tuple(FUTURES_CATEGORIES)


def _normalise_key(value):
    """Casefold + collapse spaces/hyphens/underscores for alias lookups."""
    return re.sub(r"[\s_-]+", " ", value.strip().casefold())


# normalised alias -> canonical category
_CATEGORY_LOOKUP = {}
for _canonical in FUTURES_CATEGORY_ORDER:
    _spec = FUTURES_CATEGORIES[_canonical]
    for _alias in [_canonical, _spec["en"], *_spec["aliases"]]:
        _CATEGORY_LOOKUP.setdefault(_normalise_key(_alias), _canonical)

_CATEGORY_HELP = ", ".join(
    f"{name} ({spec['label']})" for name, spec in FUTURES_CATEGORIES.items()
)


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------
def _type_name(value):
    """``type(value).__name__`` that also works where ``type`` is shadowed."""
    return type(value).__name__


def _resolve_category(value):
    """Map a user supplied futures category onto its canonical key (or None)."""
    if value is None:
        return None

    if not isinstance(value, str):
        raise ValueError(
            f"category must be a string, got {_type_name(value)}. "
            f"Supported categories: {_CATEGORY_HELP}."
        )

    key = _normalise_key(value)
    if not key:
        raise ValueError(
            f"Unknown futures category {value!r}. Supported categories: "
            f"{_CATEGORY_HELP}."
        )

    canonical = _CATEGORY_LOOKUP.get(key)
    if canonical is None:
        raise ValueError(
            f"Unknown futures category {value!r}. Supported categories: "
            f"{_CATEGORY_HELP}."
        )
    return canonical


def _validate_text(text):
    """``text`` may be empty (browse mode) but must be a string when given."""
    if text is None:
        return ""
    if not isinstance(text, str):
        raise ValueError(f"text must be a string, got {_type_name(text)}.")
    return text.strip()


def _validate_exchange(exchange):
    if exchange is None:
        return ""
    if not isinstance(exchange, str):
        raise ValueError(
            f"exchange must be a string, got {_type_name(exchange)}."
        )
    return exchange.strip()


def _validate_product(product):
    """A product path such as ``Commodity/Metals/Precious`` (prefix match)."""
    if product is None:
        return None
    if not isinstance(product, str):
        raise ValueError(f"product must be a string, got {_type_name(product)}.")
    cleaned = product.strip().strip("/")
    return cleaned or None


def _validate_bool(value, name):
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean, got {_type_name(value)}.")
    return value


def _is_under(product, prefix):
    """True when ``product`` equals ``prefix`` or lives below it."""
    return product == prefix or product.startswith(prefix + "/")


def _product_regex(category, product):
    """Build the anchored regex used to filter the ``product`` column."""
    if product:
        return "^" + re.escape(product)
    if category:
        return "^" + re.escape(FUTURES_CATEGORIES[category]["product"])
    return None


def _product_matches(product, category, product_filter):
    """Local check mirroring the server-side ``product`` filter."""
    if product_filter:
        return bool(product) and _is_under(product, product_filter)
    if category:
        return category in categories_for_product(product)
    return True


# ---------------------------------------------------------------------------
# Product taxonomy helpers
# ---------------------------------------------------------------------------
def category_for_product(product):
    """Return the canonical category of a ``product`` value (or ``None``).

    ``"Commodity/Metals/Precious/Gold"`` -> ``"metals"``.
    """
    matched = categories_for_product(product)
    return matched[0] if matched else None


def categories_for_product(product):
    """Return every category a ``product`` value belongs to (usually one)."""
    if not isinstance(product, str) or not product:
        return []
    return [
        name
        for name in FUTURES_CATEGORY_ORDER
        if _is_under(product, FUTURES_CATEGORIES[name]["product"])
    ]


def list_futures_categories():
    """Return the supported futures categories as a list of dicts.

    Each entry has ``id``, ``product`` (TradingView's hierarchy prefix),
    ``en``, ``label`` (Arabic/English) and ``aliases``.
    """
    return [
        {
            "id": name,
            "product": FUTURES_CATEGORIES[name]["product"],
            "en": FUTURES_CATEGORIES[name]["en"],
            "label": FUTURES_CATEGORIES[name]["label"],
            "aliases": list(FUTURES_CATEGORIES[name]["aliases"]),
        }
        for name in FUTURES_CATEGORY_ORDER
    ]


# ---------------------------------------------------------------------------
# Screener (scanner.tradingview.com) access
# ---------------------------------------------------------------------------
def _chunks(items, size):
    for start in range(0, len(items), size):
        yield items[start:start + size]


def _scan(filters, limit, timeout, proxies, sort_by="name", sort_order="asc"):
    """Run one futures screener query.

    Returns ``(rows, total)`` where ``rows`` are ``dict`` records built from
    the requested columns.  Network/HTTP/JSON failures return ``([], None)``.
    """
    body = {
        "columns": list(_SCAN_COLUMNS),
        "filter": list(filters),
        "range": [0, limit],
        "sort": {"sortBy": sort_by, "sortOrder": sort_order},
    }

    try:
        response = requests.post(
            SCAN_URL,
            json=body,
            headers=_SCAN_HEADERS,
            timeout=timeout,
            proxies=proxies,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:  # network, HTTP or JSON failure
        logger.warning("futures scan failed for %r: %s", filters, exc)
        return [], None

    if not isinstance(payload, dict):
        logger.warning("unexpected futures scan response: %r", payload)
        return [], None

    data = payload.get("data")
    if not isinstance(data, list):
        # TradingView answers {"error": ...} for unsupported filters.
        logger.warning(
            "unexpected futures scan response for %r: %r", filters, payload
        )
        return [], None

    rows = []
    for item in data:
        if not isinstance(item, dict):
            continue
        values = item.get("d")
        if not isinstance(values, list):
            continue
        row = dict(zip(_SCAN_COLUMNS, values))
        row["_symbol_id"] = item.get("s")
        rows.append(row)

    return rows, payload.get("totalCount")


def _with_exchange(filters, exchange):
    return [
        {**flt, "right": exchange} if flt.get("left") == "exchange" else flt
        for flt in filters
    ]


def _scan_with_exchange_retry(filters, limit, timeout, proxies, exchange):
    """Retry upper-cased when TradingView's exchange filter matches nothing.

    ``exchange`` is case sensitive server-side (``nymex`` -> 0 hits,
    ``NYMEX`` -> many), so the same convenience fallback as ``search_symbol``
    is applied here.
    """
    rows, total = _scan(filters, limit, timeout, proxies)
    if not rows and exchange and exchange != exchange.upper():
        upper = _with_exchange(filters, exchange.upper())
        if upper != filters:
            rows, total = _scan(upper, limit, timeout, proxies)
    return rows, total


def _normalize_scan_rows(rows, limit):
    """Normalise screener rows, dropping records without a usable name."""
    out = []
    for row in rows:
        name = row.get("name")
        if not isinstance(name, str) or not name:
            continue
        out.append(_normalize_scan_row(row))
        if len(out) >= limit:
            break
    return out


def _normalize_scan_row(row):
    """Return the documented, stable dict for one screener record."""
    raw_name = row.get("name")
    name = raw_name if isinstance(raw_name, str) else (
        str(raw_name) if raw_name is not None else None
    )
    exchange = row.get("exchange")
    product = row.get("product")

    return {
        "symbol": name,
        "full_name": f"{exchange}:{name}" if exchange and name else name,
        "description": row.get("description"),
        "exchange": exchange,
        "exchange_id": exchange,
        "type": row.get("type") or "futures",
        "country": None,  # not provided by the futures screener
        "currency_code": row.get("currency"),
        "typespecs": row.get("typespecs") or [],
        "provider_id": None,
        "product": product,
        "category": category_for_product(product),
        "categories": categories_for_product(product),
        "logoid": row.get("logoid"),
        "close": row.get("close"),
        "change": row.get("change"),
        "continuous": bool(name and _CONTINUOUS_RE.search(name)),
    }


# ---------------------------------------------------------------------------
# Symbol-search bridge (used for ``text`` and ``country``)
# ---------------------------------------------------------------------------
def _lookup_symbol(record):
    """Pick the symbol used to classify a symbol-search record.

    Symbol search returns *roots* (``CL``) whose ``contracts`` list carries
    the listed contracts (``CL1!``, ``CLX2026`` ...).  The continuous
    contract (``CL1!``) is used for the screener lookup because that is what
    the screener indexes.
    """
    contracts = record.get("contracts")
    candidates = []
    if isinstance(contracts, list):
        for contract in contracts:
            if not isinstance(contract, dict):
                continue
            symbol = contract.get("symbol")
            if not isinstance(symbol, str) or not symbol:
                continue
            specs = contract.get("typespecs") or []
            match = re.search(r"(\d+)!$", symbol)
            rank = (
                0 if "continuous" in specs else 1,
                int(match.group(1)) if match else 99,
                symbol,
            )
            candidates.append((rank, symbol))

    if candidates:
        candidates.sort()
        return candidates[0][1]

    symbol = record.get("symbol")
    if isinstance(symbol, str) and symbol:
        return symbol if symbol.endswith("!") else f"{symbol}1!"
    return None


def _lookup_products(symbols, timeout, proxies):
    """Map screener ``name`` -> ``product`` for a list of symbols."""
    products = {}
    if not symbols:
        return products

    for chunk in _chunks(sorted(set(symbols)), _LOOKUP_CHUNK):
        rows, _ = _scan(
            [{"left": "name", "operation": "in_range", "right": list(chunk)}],
            len(chunk) * _LOOKUP_ROWS_PER_NAME,
            timeout,
            proxies,
        )
        for row in rows:
            name = row.get("name")
            if name is not None and name not in products:
                products[name] = row.get("product")
    return products


def _search_via_symbol_search(
    text, exchange, country, category, product, limit, lang, timeout, proxies
):
    """text/country based search, enriched with the screener taxonomy."""
    params = {
        "text": text,
        "hl": 0,
        "lang": lang,
        "domain": "production",
        "type": "futures",
    }
    if exchange:
        params["exchange"] = exchange
    if country:
        params["country"] = country

    records = _request(params, timeout, proxies)

    # Same case-sensitivity convenience as search_symbol().
    if not records and exchange and exchange != exchange.upper():
        records = _request({**params, "exchange": exchange.upper()}, timeout, proxies)

    if not records:
        return []

    lookups = {}
    for record in records:
        symbol = _lookup_symbol(record)
        if symbol:
            lookups.setdefault(symbol, []).append(record)

    products = _lookup_products(list(lookups), timeout, proxies)

    results = []
    for record in records:
        symbol = _lookup_symbol(record)
        product_value = products.get(symbol)
        if not _product_matches(product_value, category, product):
            continue

        normalized = _normalize(record)
        normalized["continuous_symbol"] = symbol
        normalized["product"] = product_value
        normalized["category"] = category_for_product(product_value)
        normalized["categories"] = categories_for_product(product_value)
        results.append(normalized)
        if len(results) >= limit:
            break

    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def search_futures(
    text: str = "",
    exchange: str = None,
    category: str = None,
    product: str = None,
    country: str = None,
    limit: int = 50,
    continuous_only: bool = True,
    lang: str = "en",
    timeout: float = 10,
    proxies: dict = None,
) -> list:
    """Search **futures contracts** by country, exchange and category.

    Args:
        text: optional search text (symbol or description, English/Arabic).
            May be empty -- the other filters then act as a browse query.
        exchange: optional exchange id to restrict to, e.g. ``"NYMEX"``,
            ``"CME"``, ``"EUREX"`` (matched case sensitively server-side,
            with an automatic upper-cased retry).
        category: optional futures category, in English or Arabic:
            ``single_stock/الأسهم الفردية``,
            ``world_indices/المؤشرات العالمية``, ``currencies/العملات``,
            ``interest_rates/أسعار الفائدة``, ``energy/الطاقة``,
            ``agriculture/الزراعة``, ``metals/المعادن``, ``weather/الطقس``,
            ``building_materials/مواد البناء``, ``chemicals/المواد الكيميائية``.
        product: optional sub-category path from TradingView's taxonomy,
            e.g. ``"Commodity/Metals/Precious/Gold"`` or
            ``"Commodity/Energy/Oil"`` (prefix match: everything *under* it).
            When both ``category`` and ``product`` are given, ``product`` must
            belong to ``category``.
        country: optional ISO-3166 alpha-2 code (``"SA"``) or country name
            (``"السعودية"`` / ``"Saudi Arabia"``).  Country is not part of the
            futures screener, so it goes through TradingView's symbol search
            (which caps a single query at 50 instruments).
        limit: maximum number of records (1..50, larger values are clamped).
        continuous_only: when browsing without ``text``/``country``, return
            only continuous contracts (``CL1!``) instead of every monthly
            contract.  Ignored for text/country searches, which return one
            *instrument* per root (with its ``continuous_symbol``).
        lang: interface language passed to TradingView (``"en"``, ``"ar"``...).
        timeout: per-request timeout in seconds.
        proxies: optional ``{"https": "http://..."}`` mapping.

    Returns:
        list[dict]: normalised records.  Every record always contains the keys
        ``symbol``, ``full_name`` (``"EXCHANGE:SYMBOL"``, ready for
        ``get_hist``), ``description``, ``exchange``, ``exchange_id``,
        ``type``, ``country``, ``currency_code``, ``typespecs``,
        ``provider_id`` plus the futures specific ``product``, ``category``,
        ``categories``, ``logoid``, ``close`` and ``change``.  Text/country
        searches additionally expose ``contracts`` and ``continuous_symbol``
        (pass it -- or the root with ``fut_contract=1`` -- to ``get_hist``).
        Network/HTTP/JSON failures return ``[]`` (never raise).

    Raises:
        ValueError: if ``text``/``exchange``/``category``/``product``/
            ``country``/``limit``/``continuous_only``/``lang``/``timeout``
            are invalid -- invalid *arguments* fail fast, only *network*
            problems return ``[]``.
    """
    text = _validate_text(text)
    exchange = _validate_exchange(exchange)
    resolved_category = _resolve_category(category)
    product_filter = _validate_product(product)
    iso_country = _resolve_country(country)
    limit = _validate_limit(limit)
    continuous_only = _validate_bool(continuous_only, "continuous_only")
    lang = _validate_lang(lang)
    timeout = _validate_timeout(timeout)

    if product_filter and resolved_category:
        prefix = FUTURES_CATEGORIES[resolved_category]["product"]
        if not _is_under(product_filter, prefix):
            raise ValueError(
                f"product {product!r} does not belong to category "
                f"{category!r} ({prefix})."
            )

    # Text and country live in the symbol-search endpoint; everything else
    # (category/sub-category/exchange browsing) is answered by the screener.
    if text or iso_country:
        return _search_via_symbol_search(
            text,
            exchange,
            iso_country,
            resolved_category,
            product_filter,
            limit,
            lang,
            timeout,
            proxies,
        )

    filters = []
    product_regex = _product_regex(resolved_category, product_filter)
    if product_regex:
        filters.append(
            {"left": "product", "operation": "match", "right": product_regex}
        )
    if exchange:
        filters.append(
            {"left": "exchange", "operation": "equal", "right": exchange}
        )
    if continuous_only:
        filters.append(
            {"left": "name", "operation": "match", "right": _CONTINUOUS_RE.pattern}
        )

    rows, _total = _scan_with_exchange_retry(
        filters, limit, timeout, proxies, exchange
    )
    # The server honours ``range`` already; normalising with ``limit`` keeps
    # the contract even if it ever answers with more rows than requested.
    return _normalize_scan_rows(rows, limit)

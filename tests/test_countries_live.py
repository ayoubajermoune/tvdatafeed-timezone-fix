"""Live tests for the ``country`` parameter of both search entry points.

These tests really hit TradingView and verify, for every supported country,
that the ``country`` value carried by the results matches the requested
country (input -> output consistency).  They are opt-in so the default suite
stays fully offline::

    TV_LIVE=1 pytest tests/test_countries_live.py -v
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tvDatafeed import search_futures, search_symbol  # noqa: E402
from tvDatafeed.search import _resolve_country  # noqa: E402

pytestmark = pytest.mark.skipif(
    os.getenv("TV_LIVE") != "1",
    reason="live tests are opt-in: set TV_LIVE=1 to run them",
)

# English name -> ISO-3166 alpha-2 code: the full TradingView country list.
COUNTRIES = {
    "United States": "US",
    "Canada": "CA",
    "Austria": "AT",
    "Belgium": "BE",
    "Bulgaria": "BG",
    "Croatia": "HR",
    "Cyprus": "CY",
    "Czech Republic": "CZ",
    "Denmark": "DK",
    "Estonia": "EE",
    "European Union": "EU",
    "Finland": "FI",
    "France": "FR",
    "Germany": "DE",
    "Greece": "GR",
    "Hungary": "HU",
    "Iceland": "IS",
    "Ireland": "IE",
    "Italy": "IT",
    "Latvia": "LV",
    "Lithuania": "LT",
    "Luxembourg": "LU",
    "Netherlands": "NL",
    "Norway": "NO",
    "Poland": "PL",
    "Portugal": "PT",
    "Romania": "RO",
    "Russia": "RU",
    "Serbia": "RS",
    "Slovakia": "SK",
    "Slovenia": "SI",
    "Spain": "ES",
    "Sweden": "SE",
    "Switzerland": "CH",
    "Turkey": "TR",
    "United Kingdom": "GB",
    "Bahrain": "BH",
    "Egypt": "EG",
    "Israel": "IL",
    "Kenya": "KE",
    "Kuwait": "KW",
    "Morocco": "MA",
    "Nigeria": "NG",
    "Qatar": "QA",
    "Saudi Arabia": "SA",
    "South Africa": "ZA",
    "Tunisia": "TN",
    "United Arab Emirates": "AE",
    "Argentina": "AR",
    "Brazil": "BR",
    "Chile": "CL",
    "Colombia": "CO",
    "Mexico": "MX",
    "Peru": "PE",
    "Venezuela": "VE",
    "Australia": "AU",
    "Bangladesh": "BD",
    "Hong Kong, China": "HK",
    "India": "IN",
    "Indonesia": "ID",
    "Japan": "JP",
    "Mainland China": "CN",
    "Malaysia": "MY",
    "New Zealand": "NZ",
    "Pakistan": "PK",
    "Philippines": "PH",
    "Singapore": "SG",
    "South Korea": "KR",
    "Sri Lanka": "LK",
    "Taiwan, China": "TW",
    "Thailand": "TH",
    "Vietnam": "VN",
}

# Countries whose futures screen carries instruments tagged with the country.
FUTURES_COUNTRIES = (
    "US", "CA", "BE", "DK", "EU", "FI", "FR", "DE", "HU", "IT", "NL", "NO",
    "PL", "PT", "RU", "SE", "TR", "GB", "AE", "AR", "BR", "AU", "HK", "IN",
    "JP", "CN", "MY", "NZ", "SG", "KR", "TW", "TH", "VN",
)

# A text term that really matches instruments for the given country (proves
# the country filter returns data, not merely that it never mismatches).
SEARCH_PROBES = {
    "US": "bank",
    "GB": "bank",
    "DE": "bank",
    "JP": "bank",
    "IN": "bank",
    "SA": "bank",
    "BR": "bank",
    "AU": "bank",
    "CN": "bank",
    "EU": "DAX",
}


# ---------------------------------------------------------------------------
# English names resolve to their ISO codes
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name,code", sorted(COUNTRIES.items()))
def test_country_name_resolves_to_iso_code(name, code):
    assert _resolve_country(name) == code
    assert _resolve_country(code) == code


# ---------------------------------------------------------------------------
# search_symbol: the returned country always equals the requested one
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("code", sorted(set(COUNTRIES.values())))
def test_search_symbol_country_never_mismatches(code):
    out = search_symbol("a", country=code, limit=10)
    assert all(record["country"] == code for record in out)


@pytest.mark.parametrize("code,text", sorted(SEARCH_PROBES.items()))
def test_search_symbol_country_filter_returns_results(code, text):
    out = search_symbol(text, country=code, limit=5)
    assert out, f"no symbols returned for country {code!r}"
    assert all(record["country"] == code for record in out)


@pytest.mark.parametrize("name,code", sorted(COUNTRIES.items()))
def test_search_symbol_accepts_the_english_name(name, code):
    out = search_symbol("a", country=name, limit=5)
    assert all(record["country"] == code for record in out)


# ---------------------------------------------------------------------------
# search_futures: the returned country always equals the requested one
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("code", sorted(set(COUNTRIES.values())))
def test_search_futures_country_never_mismatches(code):
    out = search_futures(country=code, limit=10)
    assert all(record["country"] == code for record in out)


@pytest.mark.parametrize("code", sorted(FUTURES_COUNTRIES))
def test_search_futures_countries_actually_return_results(code):
    out = search_futures(country=code, limit=5)
    assert out, f"no futures returned for country {code!r}"
    for record in out:
        assert record["country"] == code
        assert record["continuous_symbol"]


@pytest.mark.parametrize("name,code", sorted(COUNTRIES.items()))
def test_search_futures_accepts_the_english_name(name, code):
    out = search_futures(country=name, limit=5)
    assert all(record["country"] == code for record in out)

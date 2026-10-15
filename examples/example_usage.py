"""
Example usage of the fixed tvDatafeed (timezone fix).

Shows the main differences from the original version:
  1) You can control the timezone and know exactly which one the data uses.
  2) Today's bar (the last row) is dated with the real trading day, not the
     session-open date which usually falls on yesterday.

Example usage of the fixed tvDatafeed (timezone fix).
"""
from tvDatafeed import Interval, TvDatafeed

tv = TvDatafeed()  # optional: TvDatafeed(username, password)

print("=" * 70)
print("1) Default: UTC (explicit, known timezone)")
print("   Default: UTC -- timezone-aware index")
print("=" * 70)
data = tv.get_hist(symbol="XAUUSD", exchange="BLACKBULL",
                   interval=Interval.in_daily, n_bars=10)
print(data)
print("\n-> data timezone:", data.index.tz)   # tz.UTC

print("\n" + "=" * 70)
print("2) Explicit timezone (example: Africa/Cairo)")
print("   Explicit timezone: Africa/Cairo")
print("=" * 70)
data_cairo = tv.get_hist(symbol="XAUUSD", exchange="BLACKBULL",
                         interval=Interval.in_daily, n_bars=10,
                         timezone="Africa/Cairo")
print(data_cairo.tail(3))
print("\n-> data timezone:", data_cairo.index.tz)

print("\n" + "=" * 70)
print("3) Legacy mode (exchange): naive, exchange clock")
print("   Legacy mode: naive, exchange clock")
print("=" * 70)
data_ex = tv.get_hist(symbol="XAUUSD", exchange="BLACKBULL",
                      interval=Interval.in_daily, n_bars=10,
                      timezone="exchange")
print(data_ex.tail(3))
print("\n-> data timezone:", data_ex.index.tz, "(naive / no tz)")

print("\n" + "=" * 70)
print("4) Turn OFF the trading-day alignment (raw TradingView labels)")
print("   Turn OFF the trading-day alignment if you want raw open-date labels")
print("=" * 70)
data_raw = tv.get_hist(symbol="XAUUSD", exchange="BLACKBULL",
                       interval=Interval.in_daily, n_bars=10,
                       align_daily_to_trading_day=False)
print(data_raw.tail(3))

print("\n" + "=" * 70)
print("5) Symbol search -- by asset type & country, no login needed")
print("   Symbol search -- by asset type & country, no login needed")
print("=" * 70)
# 5.1) general search, no object and no login
from tvDatafeed import search_symbol

results = search_symbol("gold")
print("gold ->", [(r["full_name"], r["exchange"], r["type"]) for r in results[:3]])

# 5.2) filter by type (English aliases)
gold = search_symbol("gold", type="commodity")     # commodities only
bonds = search_symbol("apple", type="bond")        # bonds only
forex = search_symbol("EURUSD", type="forex")      # forex only
print("commodities:", sorted({r["type"] for r in gold}))
print("bonds:", sorted({r["type"] for r in bonds}))
print("forex:", sorted({r["type"] for r in forex}))

# 5.3) filter by country + type
sa_banks = search_symbol("bank", country="SA", type="stock")
print("SA banks:", [(r["full_name"], r["description"], r["country"]) for r in sa_banks[:3]])

# 5.4) search by text, then download the found symbol
aramco = search_symbol("Saudi Arabian Oil")
hit = next(r for r in aramco if r["full_name"] == "TADAWUL:2222")
print("Aramco ->", hit["full_name"], hit["description"], hit["country"])
print("=> pass the resolved ids to get_hist:")
print(tv.get_hist(symbol=hit["symbol"], exchange=hit["exchange_id"],
                  interval=Interval.in_daily, n_bars=5).tail(2))

print("\n" + "=" * 70)
print("6) Futures search -- country + exchange + category + sub-category")
print("   Futures search -- country + exchange + category + sub-category")
print("=" * 70)
from tvDatafeed import list_futures_categories, search_futures

# 6.1) the ten available categories (English) and their TradingView source
for cat in list_futures_categories():
    print(f"   {cat['id']:<18} {cat['product']:<32} {cat['label']}")

# 6.2) browse a full category on a given exchange (continuous contracts only -- default)
energy = search_futures(category="energy", exchange="NYMEX", limit=5)
print("NYMEX energy (continuous):", [(r["symbol"], r["product"]) for r in energy])

# 6.3) country + category together (goes through symbol search, then classified)
mcx_metals = search_futures(country="IN", category="metals", limit=5)
print("India metals:", [(r["full_name"], r["category"]) for r in mcx_metals])

# 6.4) sub-category (prefix match: everything under the path)
gold_only = search_futures(product="Commodity/Metals/Precious/Gold", limit=5)
print("gold only:", [(r["full_name"], r["product"]) for r in gold_only])

# 6.5) every monthly contract, not just the continuous one
months = search_futures(category="weather", continuous_only=False, limit=5)
print("weather months:", [(r["symbol"], r["continuous"]) for r in months])

# 6.6) text + category: returns the root + the continuous contract, then download
hits = search_futures("crude oil", category="energy", limit=5)
cl = next((r for r in hits if r["full_name"] == "NYMEX:CL"), None)
if cl:
    print("CL ->", cl["full_name"], cl["category"], cl["continuous_symbol"])
    print(tv.get_hist(symbol=cl["symbol"], exchange=cl["exchange_id"],
                      fut_contract=1, interval=Interval.in_daily,
                      n_bars=5).tail(2))

# 6.7) invalid arguments raise ValueError immediately (only network failures return [])
try:
    search_futures(category="crypto futures")
except ValueError as exc:
    print("ValueError ->", str(exc)[:70], "...")

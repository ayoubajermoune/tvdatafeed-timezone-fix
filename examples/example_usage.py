"""
مثال على استخدام tvDatafeed المُصلح (timezone fix).

يعرض الفرق الرئيسي بين النسخة الأصلية والنسخة المُصلحة:
  1) يمكنك تحديد المنطقة الزمنية ومعرفة المنطقة التي تتعامل معها بالضبط.
  2) شمعة اليوم (آخر صف) تُوسم بتاريخ يوم التداول الفعلي وليس تاريخ فتح
     الجلسة الذي غالباً ما يكون بالأمس.

Example usage of the fixed tvDatafeed (timezone fix).
"""
from tvDatafeed import Interval, TvDatafeed

tv = TvDatafeed()  # اختياري: TvDatafeed(username, password)

print("=" * 70)
print("1) الافتراضي: UTC (منطقة زمنية معروفة وصريحة)")
print("   Default: UTC -- timezone-aware index")
print("=" * 70)
data = tv.get_hist(symbol="XAUUSD", exchange="BLACKBULL",
                   interval=Interval.in_daily, n_bars=10)
print(data)
print("\n-> المنطقة الزمنية للبيانات:", data.index.tz)   # tz.UTC

print("\n" + "=" * 70)
print("2) تحديد منطقة زمنية محددة (مثال: القاهرة)")
print("   Explicit timezone: Africa/Cairo")
print("=" * 70)
data_cairo = tv.get_hist(symbol="XAUUSD", exchange="BLACKBULL",
                         interval=Interval.in_daily, n_bars=10,
                         timezone="Africa/Cairo")
print(data_cairo.tail(3))
print("\n-> المنطقة الزمنية للبيانات:", data_cairo.index.tz)

print("\n" + "=" * 70)
print("3) الوضع القديم (exchange): نايف على ساعة البورصة")
print("   Legacy mode: naive, exchange clock")
print("=" * 70)
data_ex = tv.get_hist(symbol="XAUUSD", exchange="BLACKBULL",
                      interval=Interval.in_daily, n_bars=10,
                      timezone="exchange")
print(data_ex.tail(3))
print("\n-> المنطقة الزمنية للبيانات:", data_ex.index.tz, "(naive / بدون توقيت)")

print("\n" + "=" * 70)
print("4) إيقاف تصحيح تاريخ شمعة اليوم (إن أردت سلوك TradingView الخام)")
print("   Turn OFF the trading-day alignment if you want raw open-date labels")
print("=" * 70)
data_raw = tv.get_hist(symbol="XAUUSD", exchange="BLACKBULL",
                       interval=Interval.in_daily, n_bars=10,
                       align_daily_to_trading_day=False)
print(data_raw.tail(3))

print("\n" + "=" * 70)
print("5) البحث عن الرمز — بالنوع والدولة، بدون تسجيل دخول")
print("   Symbol search -- by asset type & country, no login needed")
print("=" * 70)
# 5.1) بحث عام بدون كائن ودون تسجيل دخول
from tvDatafeed import search_symbol

results = search_symbol("gold")
print("gold ->", [(r["full_name"], r["exchange"], r["type"]) for r in results[:3]])

# 5.2) الفلترة بالنوع (مرادفات عربية/إنجليزية)
gold = search_symbol("gold", type="السلع")          # commodities only
bonds = search_symbol("apple", type="السندات")      # bonds only
forex = search_symbol("EURUSD", type="الفوريكس")    # forex only
print("commodities:", sorted({r["type"] for r in gold}))
print("bonds:", sorted({r["type"] for r in bonds}))
print("forex:", sorted({r["type"] for r in forex}))

# 5.3) الفلترة بالدولة + النوع
sa_banks = search_symbol("bank", country="السعودية", type="الأسهم")
print("SA banks:", [(r["full_name"], r["description"], r["country"]) for r in sa_banks[:3]])

# 5.4) بحث بنص عربي
aramco = search_symbol("أرامكو")
hit = next(r for r in aramco if r["full_name"] == "TADAWUL:2222")
print("أرامكو ->", hit["full_name"], hit["description"], hit["country"])
print("=> تمرير المعرّفات الجاهزة إلى get_hist:")
print(tv.get_hist(symbol=hit["symbol"], exchange=hit["exchange_id"],
                  interval=Interval.in_daily, n_bars=5).tail(2))
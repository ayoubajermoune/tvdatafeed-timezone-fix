# tvdatafeed-timezone-fix

إصلاح مشكلتين جوهريتين في مكتبة [rongardF/tvdatafeed](https://github.com/rongardF/tvdatafeed):

1. **لا يمكن تحديد المنطقة الزمنية** للبيانات، ولا حتى معرفة المنطقة الزمنية التي تتعامل معها.
2. **آخر صف (بيانات اليوم الفعلي) يظهر بتاريخ الأمس** — عمود التاريخ خاطئ في الشموع اليومية.

A timezone-safe fork of `tvdatafeed`: explicit, controllable timezones + correct daily-bar dates.

---

## المشكلة (The problem)

```python
data = tv.get_hist(symbol='XAUUSD', exchange='BLACKBULL', interval=Interval.in_daily, n_bars=10)
```

```
datetime             open     high     low      close    volume
2026-09-22 22:00:00  4357.68  4369.60  4274.86  4287.89  502959.0
2026-09-23 22:00:00  4288.34  4303.18  4244.36  4268.42  344281.0   ← last row
```

- الصف الأخير هو شمعة **اليوم** الجارية، لكنه مؤرخ بـ **22:00 من يوم الأمس**.
- لا توجد أي `timezone` في الـ index ولا معامل للتحكم بها.
- الناتج يتغير صامتاً حسب توقيت جهازك (الكود الأصلي يستخدم `datetime.fromtimestamp`).

## السبب الجذري (Root cause)

السبب موثّق أيضاً في قضيتين مفتوحتين على المستودع الأصلي: [#43 Wrong Assignment of Dates](https://github.com/rongardF/tvdatafeed/issues/43) و [#65 Not properly accounting for market holidays](https://github.com/rongardF/tvdatafeed/issues/65).

1. المكتبة ترسل `switch_timezone → "exchange"` **ثابتة**، ولا تسمح باختيار المنطقة الزمنية أبداً.
2. المكتبة تحلّل الطوابع الزمنية بـ `datetime.fromtimestamp()` **دون تحديد منطقة زمنية** → تحويل صامت حسب توقيت النظام المحلي.
3. TradingView يوسم الشمعة اليومية بـ **تاريخ فتح الجلسة**. جلسة الذهب (BLACKBULL:XAUUSD) تفتح عند **22:00 UTC** وتغلق في اليوم التالي، فشمعة "اليوم" تحمل تاريخ "أمس":

```
Actual bar:   opens Wed 22:00 UTC   ←→  closes Thu 21:59 UTC
Raw date:     2026-09-23            ←→  real trading day: 2026-09-24 (today)
```

> الملاحظة: قيم OHLC **صحيحة دائماً** — الخطأ في **عمود التاريخ فقط**.

## الإصلاح (The fix)

### 1. معامل `timezone` صريح + index معرف بالمنطقة الزمنية

- `"UTC"` (الافتراضي): `data.index.tz` يعيد `UTC` — محايد تماماً عن توقيت جهازك.
- أي اسم IANA مثل `"Africa/Cairo"`, `"Asia/Riyadh"`, `"America/New_York"`: الفهرس بهذا التوقيت.
- `"exchange"`: نايف على ساعة البورصة (السلوك القديم، لكن صار حتمياً لا معتمداً على الجهاز).

### 2. تصحيح تاريخ الشموع اليومية (`align_daily_to_trading_day`)

إذا فتحت شمعة يومية عند/بعد **12:00** بتوقيت الهدف، فهي تعبر منتصف الليل → تُؤرخ بـ **يوم التداول** (تاريخ الإغلاق) بدل تاريخ الفتح. النتيجة:

```
Before the fix:  ... 2026-09-22 22:00 , 2026-09-23 22:00   ← "today" shows as yesterday!
After the fix:   ... 2026-09-23 22:00 , 2026-09-24 22:00   ← real trading days (no weekend gaps)
```

الشموع داخلية (intraday) لا تُمرَّ أبداً. أضف `align_daily_to_trading_day=False` للحصول على تواريخ TradingView الخام.

---

## التثبيت (Install)

الطريقة الموصى بها — مباشرة من مستودع GitHub (نفس طريقة المكتبة الأصلية):

```bash
pip install --upgrade --no-cache-dir git+https://github.com/ayoubajermoune/tvdatafeed-timezone-fix.git
```

طرق بديلة:

```bash
# 1) clone the repository then install
git clone https://github.com/ayoubajermoune/tvdatafeed-timezone-fix
cd tvdatafeed-timezone-fix
pip install .

# 2) editable install (to modify the code)
pip install -e .
```

## الاستخدام (Usage)

```python
from tvDatafeed import TvDatafeed, Interval

tv = TvDatafeed()

# 1) default: UTC -- explicit, known timezone
data = tv.get_hist(symbol='XAUUSD', exchange='BLACKBULL',
                   interval=Interval.in_daily, n_bars=10)
print(data.index.tz)   # UTC

# 2) explicit timezone
data = tv.get_hist(symbol='XAUUSD', exchange='BLACKBULL',
                   interval=Interval.in_daily, n_bars=10,
                   timezone='Africa/Cairo')
print(data)

# 3) legacy mode: naive, exchange clock
data = tv.get_hist(..., timezone='exchange')

# 4) raw TradingView dates (no alignment)
data = tv.get_hist(..., align_daily_to_trading_day=False)
```

مثال عملي كامل في `examples/example_usage.py`.

### البحث عن الرمز — `search_symbol(...)` (بدون تسجيل دخول)

بحث في TradingView عن الرموز بالاسم/الوصف مع فلترة اختيارية **بالنوع** (commodity، bond، forex، stock، ...) و**بالدولة**، **دون الحاجة إلى حساب أو إنشاء كائن**:

```python
from tvDatafeed import search_symbol

search_symbol("gold")                            # general search
search_symbol("Saudi Arabian Oil")               # text search
search_symbol("XAUUSD", "BLACKBULL")             # within a specific exchange
search_symbol("gold", type="commodity")          # commodities only (English aliases)
search_symbol("bank", country="SA")              # Saudi market banks
search_symbol("EURUSD", type="forex")            # forex only
```

توجد أيضاً كطريقة على الكائن لتوريث الوكيل: `tv.search_symbol("XAUUSD", "BLACKBULL")`.

**المعاملات:**

| المعامل | النوع | الافتراضي | الوصف |
|---|---|---|---|
| `text` | `str` | — | نص البحث (اسم الرمز أو وصفه — عربي أو إنجليزي) |
| `exchange` | `str` | `""` | معرف البورصة (مثل `BLACKBULL`، `TADAWUL`) |
| `type` | `str` | `None` | نوع الأصل (إنجليزي): `commodity`، `bond`، `forex`، `stock`، `index`، `crypto`، `futures`، `etf`، `fund`، `cfd`، `option`، `warrant` |
| `country` | `str` | `None` | رمز ISO-2 أو اسم بالإنجليزية مثل `"SA"` أو `"US"` |
| `limit` | `int` | `50` | عدد النتائج (الحد الأقصى للخادم 50) |
| `lang` | `str` | `"en"` | لغة الواجهة المطلوبة |
| `timeout` | `float` | `10` | مهلة الطلب بالثواني |
| `proxies` | `dict` | `None` | وكيل اختياري (أو عبر منشئ `TvDatafeed`) |
| `extra` | `dict` | `None` | معاملات إضافية تُمرَّر للخادم كما هي (تخصيص مستقبلي) |

**الناتج:** قائمة قواميس دائمة البنية:

```python
{
    "symbol": "XAUUSD",
    "full_name": "BLACKBULL:XAUUSD",   # ready to pass to get_hist
    "description": "Gold",
    "exchange": "BlackBull Markets",   # display name
    "exchange_id": "BLACKBULL",        # ★ the real id required by get_hist
    "type": "commodity",
    "country": None,                   # commodities/forex carry no country -> always None, never an error
    "currency_code": "USD",
    "typespecs": ["cfd"],
    "provider_id": "blackbullmarkets",
    # ... + any extra fields from TradingView
}
```

استعمال عملي:

```python
from tvDatafeed import search_symbol, TvDatafeed

tv = TvDatafeed()
matches = search_symbol("bank", country="SA", type="stock")
if not matches:
    raise ValueError("no matching results")

hit = matches[0]
data = tv.get_hist(symbol=hit["symbol"], exchange=hit["exchange_id"], n_bars=10)
```

> **المعاملات الخاطئة** (`type` غير معروف، `country="XYZ"`، `text` فارغ، `limit=0`) ترمي `ValueError` فوراً برسالة توضيحية. **أعطال الشبكة فقط** تعيد `[]` مع رسالة في اللوج — فلا تخلط بينهما.
>
> **بدون تسجيل دخول:** الخدمة لا تتطلب مصادقة إطلاقاً؛ كل ما تحتاجه هو هيدر `Origin` الذي تُرسله المكتبة تلقائياً (أصل عطل `403`).
>
> **403 / الشبكات المحجوبة (Colab/notebooks):** مرّر وكيلاً: `tv = TvDatafeed(proxies={...})` أو `search_symbol(..., proxies={...})`.

التفاصيل الكاملة (جداول المرادفات لكل الأنواع والدول، بنية الأخطاء، أمثلة) في [`docs/USAGE.md`](docs/USAGE.md) وقسم 5 من [`examples/example_usage.py`](examples/example_usage.py).

### البحث عن العقود الآجلة — `search_futures(...)` (بدون تسجيل دخول)

بحث مخصّص في **العقود الآجلة (Futures)** حسب **الدولة + البورصة + التصنيف + التصنيف الفرعي**، **دون حساب أو إنشاء كائن**. يعتمد على مجمّع TradingView للعقود الآجلة (`scanner.tradingview.com/futures/scan`) الذي يوفّر عمود `product` الهرمي — وهو المصدر الرسمي للتصنيف — إضافةً إلى بحث الرموز نفسه عند الفلترة بالدولة:

```python
from tvDatafeed import search_futures, list_futures_categories

list_futures_categories()                        # the ten categories (English names + sub-category)
search_futures(category="energy", exchange="NYMEX")   # energy on NYMEX (continuous contracts)
search_futures(category="metals", limit=10)           # all metals worldwide
search_futures(country="IN", category="metals")        # ★ country + category together
search_futures("crude oil", category="energy")         # text + category (returns the root + continuous contract)
search_futures(product="Commodity/Metals/Precious")    # ★ sub-category (everything under it)
search_futures(category="weather", continuous_only=False) # every monthly contract, not just continuous
```

**التصنيفات العشرة** (`category`):

| التصنيف | مرادفات إنجليزية | تصنيف TradingView (`product`) |
|---|---|---|
| `single_stock` | single stock / stock | `Financial/Equity` |
| `world_indices` | world indices / indices | `Financial/Index` |
| `currencies` | currencies / forex | `Financial/Currency` |
| `interest_rates` | interest rates / rates | `Financial/InterestRate` |
| `energy` | energy / oil | `Commodity/Energy...` |
| `agriculture` | agriculture | `Commodity/Agriculture...` |
| `metals` | metals | `Commodity/Metals...` |
| `weather` | weather | `Commodity/Weather` |
| `building_materials` | building materials / construction | `Commodity/BuildingMaterials` |
| `chemicals` | chemicals | `Commodity/Chemicals` |

**المعاملات:**

| المعامل | النوع | الافتراضي | الوصف |
|---|---|---|---|
| `text` | `str` | `""` | نص بحث اختياري؛ فارغ يعني «استعراض» حسابات أخرى فقط |
| `exchange` | `str` | `None` | معرف البورصة (مثل `NYMEX`، `CME`، `EUREX`) — دقيق مع إعادة محاولة تلقائية بالأحرف الكبيرة |
| `category` | `str` | `None` | أحد التصنيفات العشرة أعلاه (إنجليزي) |
| `product` | `str` | `None` | التصنيف الفرعي من هرمية TradingView، مثل `Commodity/Metals/Precious/Gold` (مطابقة بالبداية: كل ما تحته) |
| `country` | `str` | `None` | رمز ISO-2 أو اسم بالإنجليزية مثل `"IN"` — يمرّ عبر بحث الرموز لأن المجمّع لا يحمل الدولة |
| `limit` | `int` | `50` | عدد النتائج (الحد الأقصى للخادم 50) |
| `continuous_only` | `bool` | `True` | في الاستعراض: العقود المستمرة فقط (`CL1!`) لا كل عقود الشهر |
| `lang` | `str` | `"en"` | لغة الواجهة المطلوبة |
| `timeout` | `float` | `10` | مهلة الطلب بالثواني |
| `proxies` | `dict` | `None` | وكيل اختياري (أو عبر `tv.search_futures(...)`) |

**الناتج:** نفس بنية `search_symbol` مع حقول مستقبليات إضافية:

```python
{
    "symbol": "GC1!",
    "full_name": "COMEX:GC1!",          # ready to pass to get_hist
    "description": "Gold Futures",
    "exchange": "COMEX",
    "exchange_id": "COMEX",
    "type": "futures",
    "country": None,                    # the screener provides no country -> always None
    "currency_code": "USD",
    "typespecs": ["continuous", "synthetic"],
    "product": "Commodity/Metals/Precious/Gold",  # full sub-category path
    "category": "metals",               # one of the ten categories
    "categories": ["metals"],
    "logoid": "metal/gold",
    "close": 4035.6, "change": 0.42,
    "continuous": True,                 # continuous contract (1!), not monthly
}
```

وفي مسار `text`/`country` (بحث الرموز) يُضاف `contracts` و`continuous_symbol` (العقد المستمر لكل جذر):

```python
hits = search_futures("crude oil", category="energy")
hit = next(r for r in hits if r["full_name"] == "NYMEX:CL")
tv.get_hist(symbol=hit["symbol"], exchange=hit["exchange_id"], fut_contract=1)  # or hit["continuous_symbol"]
```

> **متى يُستخدم المجمّع ومتى بحث الرموز؟** وجود `text` أو `country` يوجّه الطلب إلى بحث الرموز (سقف 50 لكل استعلام، ويُرجع **الجذر** مثل `CL`)، ثم يُصنَّف كل جذر عبر المجمّع. أما الاستعراض (`category`/`product`/`exchange` فقط) فيُجاب من المجمّع مباشرة (عقود محددة مثل `CL1!`).
>
> **`ValueError` مقابل `[]`:** التصنيف/الدولة/الحد/المهلة/اللغة الخاطئة ترمي `ValueError` فوراً، وكذلك `product` الذي لا ينتمي إلى `category`؛ **أعطال الشبكة فقط** تعيد `[]`.

التفاصيل الكاملة في [`docs/USAGE.md`](docs/USAGE.md) وقسم 6 من [`examples/example_usage.py`](examples/example_usage.py).

### كيف أعرف المنطقة الزمنية للبيانات؟

```python
data.index.tz        # → tz.UTC / Africa/Cairo ...
data.attrs           # → {'timezone': 'UTC', 'aligned_to_trading_day': True}
```

---

## التوثيق الكامل (Full docs)

- **دليل الاستخدام العربي المفصل (التثبيت + الدوال المتوفرة):** [`docs/USAGE.md`](docs/USAGE.md)
- **مثال عملي:** [`examples/example_usage.py`](examples/example_usage.py)

## الاختبارات (Tests)

اختبارات **بدون إنترنت** مبنية على حمولة WebSocket حقيقية ملتقطة من TradingView (BLACKBULL:XAUUSD):

```bash
pip install pytest
pytest tests -v
```

تتضمن:
- افتراض UTC صريح + تحويل لأي منطقة زمنية
- تثبيت تاريخ الشموع اليومية (آخر صف = اليوم)
- عدم تغيير الشموع داخلية
- سلامة قيم OHLCV
- رفض مناطق الزمن غير الصحيحة قبل فتح أي اتصال
- **`search_symbol`**: بناء المعاملات/الهيدرز، مرادفات الأنواع والدول، فلترة السلع، `exchange_id`/`full_name`، `ValueError` للمعاملات الخاطئة، `[]` لأعطال الشبكة، و`TvDatafeedLive.new_seis`
- **`search_futures`**: التصنيفات العشرة، بناء فلاتر المجمّع (`product` regex + `exchange` + العقود المستمرة)، التصنيف الفرعي `product`، إعادة محاولة البورصة بالأحرف الكبيرة، مسار `text`/`country` عبر بحث الرموز مع التصنيف، `ValueError` للمعاملات الخاطئة و`[]` لأعطال الشبكة

**اختبارات حية (اختيارية)** تتصل بـ TradingView فعلياً وتراجع صحة البيانات (بحث بالنوع/الدولة، نص بحث، تنزيل رمز مُرجَع عبر `get_hist`):

```bash
TV_LIVE=1 pytest tests/test_search_live.py tests/test_futures_live.py -v
```

---

## ملاحظات هجرة (Migration notes)

| | الأصل (`rongardF/tvdatafeed`) | هذه النسخة |
|---|---|---|
| تحديد التوقيت | غير ممكن | `timezone=` (UTC / IANA / exchange) |
| `index.tz` | `None` + قيم معتمدة على جهازك | `UTC` (أو اختيارك) — حتمي |
| تاريخ شمعة اليوم | تاريخ فتح الجلسة (أمس) ✗ | يوم التداول (اليوم) ✓ |
| ربط أيام التداول | يختل في أيام العطل | أيام تداول حقيقية |
| قيم OHLC | صحيحة | صحيحة (لم تتغير) |

للرجوع للسلوك القديم بالضبط: `timezone='exchange', align_daily_to_trading_day=False` (مع فارق بسيط: القيم نايف بساعة البورصة الحتمية بدل ساعة الجهاز).

---

## English summary

`tvdatafeed` returned daily candles labelled by their **session-open timestamp** (e.g. `22:00 UTC` for gold on BLACKBULL), so the still-forming bar for *today* looked like it had *yesterday's* date; the library also hardcoded `switch_timezone=exchange` and parsed timestamps with `datetime.fromtimestamp()` (machine-local, silently wrong on non-UTC machines).

This fork fixes both:

- **`get_hist(..., timezone=)`** — `"UTC"` (default, tz-aware), any IANA name (`"Africa/Cairo"`, `"Asia/Riyadh"`, ...), or `"exchange"` (naive, exchange clock). The index is always tz-aware / deterministic: `data.index.tz` tells you exactly what you are looking at.
- **`get_hist(..., align_daily_to_trading_day=True)`** — daily bars that open at/after 12:00 local time span midnight, so they are dated by their **closing (trading) day**. The last bar is now dated *today*.
- **`search_symbol(text, exchange='', type=None, country=None, ...)`** — look up symbols **without any login** (also exposed as a module-level standalone `search_symbol`) with optional filters by asset type (`commodity`, `bond`, `forex`, ...) and country (ISO-2 or English names). Returns normalised dicts with `full_name`, `exchange_id`, `country` (`None` for commodities/forex), `currency_code`, `typespecs`. Invalid arguments raise `ValueError`; network failures return `[]`.
- **`search_futures(text='', exchange=None, category=None, product=None, country=None, ...)`** — dedicated **futures** search by **country + exchange + category + sub-category** (`single_stock`, `world_indices`, `currencies`, `interest_rates`, `energy`, `agriculture`, `metals`, `weather`, `building_materials`, `chemicals` — English names), powered by TradingView's futures screener (`product` taxonomy) and its symbol search (for country). Returns `search_symbol`-shaped dicts plus `product`, `category`, `categories`, `continuous`; text/country lookups also expose `continuous_symbol`. Also `list_futures_categories()` and the `tv.search_futures(...)` method.

OHLCV values are untouched; only the datetime column and timezone semantics changed. Offline test suite included (`pytest tests`).

---

## الرخصة (License)

MIT — نفس رخصة المستودع الأصلي / Same license as upstream.



# دليل الاستخدام — tvdatafeed-timezone-fix

هذا المستند يشرح بالعربية: طرق التثبيت، الدوال المتوفرة، معاملاتها، والسلوك المتوقع بعد الإصلاح.

---

## 1) التثبيت

### المتطلبات
- Python ≥ 3.8
- الحزم: `pandas`, `websocket-client`, `requests` (تُثبَّت تلقائياً)

### الطريقة 1: التثبيت مباشرة من مستودع GitHub (الطريقة الموصى بها)
نفس طريقة تثبيت المكتبة الأصلية — أمر واحد مباشر:

```bash
pip install --upgrade --no-cache-dir git+https://github.com/ayoubajermoune/tvdatafeed-timezone-fix.git
```

### الطريقة 2: نسخ المستودع ثم التثبيت
```bash
git clone https://github.com/ayoubajermoune/tvdatafeed-timezone-fix
cd tvdatafeed-timezone-fix
pip install .
```

### الطريقة 3: التثبيت في وضع التطوير (لتعديل الكود)
```bash
pip install -e .
```

### الطريقة 4: إضافة المسار مباشرة (بدون تثبيت)
```python
import sys
sys.path.insert(0, "/path/to/tvdatafeed-timezone-fix")
from tvDatafeed import TvDatafeed, Interval
```

> لاحظ أننا نحافظ على اسم الحزمة `tvDatafeed` نفسه — أي كود قديم يستورد `from tvDatafeed import TvDatafeed, Interval` سيعمل دون تعديل.

---

## 2) الدوال المتوفرة

### `Interval` (enum)
القيم الزمنية المدعومة:

| العضو | القيمة | الوصف |
|---|---|---|
| `Interval.in_1_minute` | `"1"` | دقيقة |
| `Interval.in_3_minute` | `"3"` | 3 دقائق |
| `Interval.in_5_minute` | `"5"` | 5 دقائق |
| `Interval.in_15_minute` | `"15"` | 15 دقيقة |
| `Interval.in_30_minute` | `"30"` | 30 دقيقة |
| `Interval.in_45_minute` | `"45"` | 45 دقيقة |
| `Interval.in_1_hour` | `"1H"` | ساعة |
| `Interval.in_2_hour` | `"2H"` | ساعتان |
| `Interval.in_3_hour` | `"3H"` | 3 ساعات |
| `Interval.in_4_hour` | `"4H"` | 4 ساعات |
| `Interval.in_daily` | `"1D"` | يومي ← **يشمل إصلاح تاريخ الشموع** |
| `Interval.in_weekly` | `"1W"` | أسبوعي |
| `Interval.in_monthly` | `"1M"` | شهري |

---

### `TvDatafeed(username=None, password=None)`
إنشاء العميل. بدون بيانات دخول يعمل بوضع "nologin" (البيانات قد تكون محدودة).

```python
tv = TvDatafeed()                      # without login
tv = TvDatafeed("user", "pass")        # with a TradingView account
```

---

### `get_hist(...)` — تحميل البيانات التاريخية

```python
tv.get_hist(
    symbol: str,                        # symbol name, or the "EXCHANGE:SYMBOL" form
    exchange: str = "NSE",              # exchange (ignored when the symbol is EXCHANGE:SYMBOL)
    interval: Interval = Interval.in_daily,
    n_bars: int = 10,                   # number of bars (max ~5000)
    fut_contract: int = None,           # None for cash, 1/2 for continuous futures
    extended_session: bool = False,     # extended session (outside regular hours)
    timezone: str = "UTC",              # timezone
    align_daily_to_trading_day: bool = True,  # daily-bar date alignment
    open_interest: bool = False,        # add open_interest column for futures
    include_oi: bool = None,            # alias for open_interest
    include_open_interest: bool = None, # alias for open_interest
    oi: bool = None,                    # alias for open_interest
    **kwargs,                           # accepts pool/Pool/POOL/openInterest/OpenInterest
) -> pd.DataFrame
```

#### معامل `timezone` — التحكم بالمنطقة الزمنية

| القيمة | النتيجة | `data.index.tz` |
|---|---|---|
| `"UTC"` (الافتراضي) | فهرس بمنطقة زمنية UTC — محايد عن جهازك | `tz.UTC` |
| `"America/New_York"` | تحويل كامل لمنطقة أمريكا الشرقية | `America/New_York` |
| `"Africa/Cairo"` | تحويل للقاهرة | `Africa/Cairo` |
| `"Asia/Riyadh"` | تحويل للرياض | `Asia/Riyadh` |
| `"exchange"` | نايف (بدون توقيت) على ساعة البورصة نفسها (السلوك القديم) | `None` |

أي اسم IANA صالح يعمل. الأسماء غير الصالحة ترمي `ValueError` فوراً قبل فتح أي اتصال.

##### ملاحظات مهمة حول `"exchange"`
المكتبة الأصلية كانت تستخدم `datetime.fromtimestamp()` الذي يحوّل حسب **توقيت جهازك** — أي أن الناتج كان يختلف من جهاز لآخر. في هذه النسخة، `timezone="exchange"` يقرأ منطقة البورصة الفعلية من رسالة `symbol_resolved` (مثال: `America/New_York` لـ BLACKBULL) ويعيد القيم على **ساعة البورصة** بشكل حتمي.

#### معامل `align_daily_to_trading_day` — تصحيح تاريخ اليوم

- `True` (الافتراضي): الشموع اليومية التي تفتح عند/بعد 12:00 ظهراً تُؤرخ بيوم **الإغلاق** (يوم التداول الفعلي)، فيصبح آخر صف بتاريخ اليوم الحقيقي.
- `False`: تُحفظ تواريخ TradingView الخام (تاريخ فتح الجلسة).
- يؤثر فقط على `Interval.in_daily`. لا يتغير أي شيء للشموع داخلية.

#### مثال كامل
```python
from tvDatafeed import TvDatafeed, Interval

tv = TvDatafeed()

# daily gold in UTC (default) -- last row dated today
df = tv.get_hist(symbol="XAUUSD", exchange="BLACKBULL",
                 interval=Interval.in_daily, n_bars=100)

# the last row is today's forming bar, dated correctly
print(df.tail(3))
print("timezone:", df.index.tz)
```

#### بنية الناتج
`DataFrame` فهرسه `datetime` (معرّف بالمنطقة الزمنية) والأعمدة:

| العمود | الوصف |
|---|---|
| `symbol` | الرمز بالصيغة `EXCHANGE:SYMBOL` |
| `open` / `high` / `low` / `close` | سعر الافتتاح/الأعلى/الأدنى/الإغلاق |
| `volume` | الحجم |
| `open_interest` | الرصيد المفتوح التاريخي (يُضاف عند تمرير `open_interest=True` أو أحد الأسماء البديلة، مع أو بدون `fut_contract`). القيمة يومية من TradingView وتُوزّع على الشموع حسب الجلسة |

كما يُضاف `df.attrs["timezone"]` (اسم المنطقة الزمنية) و `df.attrs["aligned_to_trading_day"]` (هل طُبّق تصحيح تاريخ اليوم).

#### مثال استخدام Open Interest مع العقود الآجلة

```python
from tvDatafeed import TvDatafeed, Interval

tv = TvDatafeed()

# إضافة عمود open_interest
df = tv.get_hist("CL", "NYMEX", interval=Interval.in_1_hour, n_bars=10, fut_contract=1, open_interest=True)
print(df[["open", "close", "volume", "open_interest"]])

# العقود المستمرة والمحددة تعمل مباشرة (بدون fut_contract)
continuous = tv.get_hist("CL1!", "NYMEX", interval=Interval.in_daily, n_bars=5, open_interest=True)
dated = tv.get_hist("CLZ2026", "NYMEX", interval=Interval.in_daily, n_bars=5, open_interest=True)

# يمكن استخدام أسماء بديلة
df = tv.get_hist("CL", "NYMEX", interval=Interval.in_daily, n_bars=5, fut_contract=1, pool=True)
```

**ملاحظات:**
- القيمة الافتراضية `False` ولا يتم إضافة العمود إلا عند الطلب صراحة
- عدم تمرير المعامل أو تمريره بـ `False` لا يسبب أي خطأ
- يعمل مع الجذر الخالص + `fut_contract` (مثل `CL` → `NYMEX:CL1!`)، ومع العقود المستمرة (`CL1!`) والمحددة (`CLZ2026`) حتى بدون `fut_contract`
- `fut_contract` لا يُضاف إلى رمز يحدد العقد مسبقاً؛ فلا ينتج `NYMEX:CL1!1!` أو `NYMEX:CLZ20261!`
- إذا كان الجذر الخالص غير متداول بدون عقد (مثل `NYMEX:CL`) تُعاد المحاولة تلقائياً على العقد المستمر `NYMEX:CL1!`
- يتم جلب الرصيد المفتوح التاريخي من سلسلة TradingView اليومية (`<TICKER>_OI` أو `<TICKER>1!_OI`)، وليس من الـ screener
- TradingView ينشر الرصيد المفتوح **يومياً** فقط؛ لذلك:
  - الشموع اليومية تحصل على قيمة OI الخاصة بكل يوم
  - الشموع داخل اليوم تحصل على OI جلستها، أي تبقى ثابتة داخل الجلسة وتتغير عند بداية جلسة جديدة
  - الشموع الأسبوعية/الشهرية تحصل على آخر OI يومي داخل الفترة
- الشمعة الأخيرة (قيد التكوين) تستخدم أحدث قيمة OI منشورة
- إذا لم يتوفر تاريخ OI للرمز، يُضاف العمود بقيم `NaN` مع تسجيل تحذير، ولا يتم تكرار قيمة حالية واحدة على كل الصفوف

---

### `search_symbol(...)` — البحث عن الرمز (بدون تسجيل دخول)

بحث في TradingView بالاسم أو الوصف مع فلترة اختيارية **بالنوع** (سلع، سندات، فوريكس، أسهم، ...) و**بالدولة**، **دون الحاجة إلى حساب أو تسجيل دخول**، بل ودون الحاجة حتى إلى إنشاء كائن:

```python
from tvDatafeed import search_symbol

search_symbol("gold")                       # general search
search_symbol("Saudi Arabian Oil")          # text search
search_symbol("XAUUSD", "BLACKBULL")        # search within a specific exchange: 2nd positional arg exchange
```

كطريقة على كائن `TvDatafeed` (ترث إعدادات الوكيل `proxies` تلقائياً):

```python
from tvDatafeed import TvDatafeed
tv = TvDatafeed()                    # no credentials -- nologin
tv.search_symbol("gold")
```

#### التوقيع الكامل

```python
search_symbol(
    text: str,             # symbol name or description (free text)
    exchange: str = "",    # exchange id (e.g. "BLACKBULL" or "TADAWUL") -- optional
    type: str = None,      # asset type (see the table below)
    country: str = None,   # country: ISO-2 code or English name -- optional
    limit: int = 50,       # number of results (1..50; 50 is the server max)
    lang: str = "en",      # interface language requested from TradingView
    timeout: float = 10,   # request timeout in seconds
    proxies: dict = None,  # optional proxy {"https": "http://..."}
    extra: dict = None,    # extra params forwarded verbatim (customisation)
) -> list[dict]
```

> ملاحظة الحالة: `exchange` حساس لحالة الأحرف لدى الخادم، وتُعاد المحاولة تلقائياً بحروف كبيرة إذا كانت النتيجة فارغة.

#### الفلترة بالنوع `type`

| القيمة (إنجليزي) | الوصف |
|---|---|
| `"commodity"` | السلع (ذهب، نفط، غاز...) — تُسترجَع عبر شاشة CFD ثم تُفلتِر داخلياً على النوع `commodity` |
| `"bond"` | السندات |
| `"forex"` | سوق الصرف الأجنبي |
| `"stock"` | الأسهم وشهادات الإيداع (`stock` / `dr`) |
| `"index"` | المؤشرات |
| `"crypto"` | العملات الرقمية |
| `"futures"` | العقود الآجلة |
| `"etf"` | صناديق المؤشرات |
| `"fund"` | الصناديق |
| `"cfd"` | عقود الفروقات |
| `"option"` | الخيارات |
| `"warrant"` | الشهادات/الأسهم الواردة |

المطابقة غير حساسة لحالة الأحرف. أي قيمة غير معروفة ترمي `ValueError` فوراً مع سرد الأنواع الصالحة.

#### الفلترة بالدولة `country`

تقبل رمز ISO-3166 alpha-2 (مثل `"SA"` أو `"US"`) أو اسماً بالإنجليزية من قاعدة مرادفات تغطي الأسواق الرئيسية والدول العربية:

```python
search_symbol("bank", country="SA")                # -> country=SA -- every result is TADAWUL
search_symbol("Saudi Arabian Oil", country="SA")   # text search + ISO country
search_symbol("bank", country="SA", type="stock")
```

> **الدولة اختيارية بطبيعتها**: السلع والفوريكس والعملات الرقمية لا تحمل دولة في بيانات TradingView، لذا يُعرض `country=None` — المفتاح موجود دائماً في النتيجة لكن قيمته قد تكون `None`، ولا يحدث أي خطأ.

#### بنية الناتج

عنصر نموذجي من القائمة المعادة:

```python
{
    "symbol": "XAUUSD",
    "full_name": "BLACKBULL:XAUUSD",   # ready to pass to get_hist (EXCHANGE:SYMBOL form)
    "description": "Gold",
    "exchange": "BlackBull Markets",   # display name on TradingView
    "exchange_id": "BLACKBULL",        # ★ the real id required by get_hist
    "type": "commodity",
    "country": None,                   # None for commodities/forex/... (the key is always present)
    "currency_code": "USD",
    "typespecs": ["cfd"],              # always a list ([] when absent)
    "provider_id": "blackbullmarkets",
    # ... any extra fields TradingView returns are kept (logoid, isin, ...)
}
```

> `TradingView` ترجع حقلاً اسمه `exchange` هو الاسم المعروض (مثل `"BlackBull Markets"`)، بينما `source_id` هو المعرّف الحقيقي (`"BLACKBULL"`). نضيف لك **`exchange_id`** وتَبني **`full_name`** من المعرّف ليكون جاهزاً للاستهلاك، فتمرير القيم إلى `get_hist` يكون مباشراً:

```python
hit = next(r for r in search_symbol("XAUUSD", "BLACKBULL") if r["full_name"] == "BLACKBULL:XAUUSD")
df = tv.get_hist(symbol=hit["symbol"], exchange=hit["exchange_id"], n_bars=100)
```

#### الأخطاء

| الحالة | النتيجة |
|---|---|
| معامل غير صالح (`type`/`country`/`text` فارغ/`limit` ≤ 0 ...) | `ValueError` فوري مع رسالة توضيحية |
| انقطاع شبكة / HTTP غير 200 / استجابة غير JSON | قائمة فارغة `[]` + رسالة في اللوج — لا يُرمى استثناء |
| قيمة `type` مثل `"commodity"` غير مدعومة من الخادم | تُعالَج تلقائياً عبر شاشة CFD مع فلترة محلية |
| `exchange` بحالة خاطئة (`blackbull` بدل `BLACKBULL`) | إعادة محاولة تلقائية بحروف كبيرة |

> **403 / الشبكات المحجوبة (Colab/notebooks):** إذا كنت داخل بيئة سحابية محجوب IP فيها، مرّر وكيلاً (`proxies=`) أو استخدم `TvDatafeed(proxies={...})`. وإذا كان IP بيئتك متاحاً (محلياً) لا تحتاج أي شيء — الفلترة لا تتطلب دخولاً.

#### أمثلة عملية كاملة

```python
from tvDatafeed import search_symbol, TvDatafeed, Interval

tv = TvDatafeed()

# 1) all Saudi Aramco symbols (text search + country)
aramco = search_symbol("Saudi Arabian Oil", country="SA")
print([r["full_name"] for r in aramco])          # ['TADAWUL:2222', ...]

# 2) commodities only -- gold and oil
gold = search_symbol("gold", type="commodity", limit=10)
oil  = search_symbol("oil",  type="commodity", limit=10)
print(all(r["type"] == "commodity" for r in gold + oil))   # True

# 3) bonds and forex
print(len(search_symbol("apple",  type="bond")))            # > 0
print(len(search_symbol("EURUSD", type="forex")))           # > 0

# 4) download data for the first search hit
hit = search_symbol("XAUUSD", "BLACKBULL")[0]
df = tv.get_hist(symbol=hit["symbol"], exchange=hit["exchange_id"],
                 interval=Interval.in_daily, n_bars=50, timezone="UTC")
print(df.tail(3))
```

---

### `search_futures(...)` — البحث في العقود الآجلة حسب الدولة/البورصة/التصنيف (بدون تسجيل دخول)

بحث مخصّص لسوق **العقود الآجلة (Futures)** يفلتر بـ:

1. **الدولة** (`country`)
2. **البورصة** (`exchange`)
3. **التصنيف** (`category`) — التصنيفات العشرة
4. **التصنيف الفرعي** (`product`) — هرمية TradingView الكاملة

كل ذلك **دون حساب**، وبدون حتى إنشاء كائن:

```python
from tvDatafeed import search_futures, list_futures_categories

search_futures(category="energy", exchange="NYMEX")      # NYMEX energy
search_futures(country="IN", category="metals")           # MCX gold/silver/copper
search_futures("crude oil", category="energy")           # text + category
search_futures(product="Commodity/Metals/Precious")      # sub-category
list_futures_categories()                                # the categories table
```

كطريقة على كائن `TvDatafeed` (ترث إعدادات الوكيل `proxies` تلقائياً):

```python
from tvDatafeed import TvDatafeed
tv = TvDatafeed()                    # no credentials -- nologin
tv.search_futures(category="weather", continuous_only=False)
```

#### التوقيع الكامل

```python
search_futures(
    text: str = "",              # optional text -- empty = browse using the other filters
    exchange: str = None,        # exchange id ("NYMEX", "CME", "EUREX", ...)
    category: str = None,        # category (see the table below)
    product: str = None,         # sub-category (hierarchy path, prefix match)
    country: str = None,         # country: ISO-2 or English name
    limit: int = 50,             # number of results (1..50; 50 is the server max)
    continuous_only: bool = True,# when browsing: continuous contracts only (CL1!)
    lang: str = "en",            # interface language
    timeout: float = 10,         # request timeout in seconds
    proxies: dict = None,        # optional proxy {"https": "http://..."}
) -> list[dict]
```

#### التصنيفات العشرة `category`

المصدر هو عمود `product` في مجمّع TradingView للعقود الآجلة، وهو تصنيف هرمي مطابق تماماً للتصنيفات المطلوبة:

| القيمة (إنجليزي) | مرادفات إنجليزية | تصنيف TradingView (`product`) | أمثلة |
|---|---|---|---|
| `"single_stock"` | `single stock`، `stock` | `Financial/Equity` | عقود أسهم فردية |
| `"world_indices"` | `world indices`، `indices` | `Financial/Index` | S&P 500، DAX، Nikkei |
| `"currencies"` | `currencies`، `forex` | `Financial/Currency` | EUR/USD، JPY |
| `"interest_rates"` | `interest rates`، `rates` | `Financial/InterestRate` | السندات قصيرة/طويلة الأجل |
| `"energy"` | `energy`، `oil` | `Commodity/Energy...` | خام WTI، برنت، غاز، بنزين |
| `"agriculture"` | `agriculture` | `Commodity/Agriculture...` | قمح، ذرة، سكر، قهوة |
| `"metals"` | `metals` | `Commodity/Metals...` | ذهب، فضة، نحاس، ألومنيوم |
| `"weather"` | `weather` | `Commodity/Weather` | HDD/CDD لحرارة/برودة |
| `"building_materials"` | `building materials`، `construction` | `Commodity/BuildingMaterials` | زجاج مسطح، خشب |
| `"chemicals"` | `chemicals` | `Commodity/Chemicals` | مواد كيميائية |

المطابقة غير حساسة لحالة الأحرف ولا للشرطات/الشرطات السفلية (`"building-materials"` = `"building_materials"`). أي قيمة غير معروفة ترمي `ValueError` فوراً مع سرد التصنيفات الصالحة.

#### التصنيف الفرعي `product`

`product` هو المسار الكامل في هرمية TradingView، والمطابقة **بالبداية** (كل ما تحت المسار):

```python
search_futures(product="Commodity/Metals")               # all metals
search_futures(product="Commodity/Metals/Precious")      # precious metals only
search_futures(product="Commodity/Metals/Precious/Gold") # gold only
search_futures(product="Commodity/Energy/Oil/CrudeOil")  # crude oil only
```

عند تمرير `category` و`product` معاً يجب أن ينتمي `product` إلى `category` وإلا يُرمى `ValueError`:

```python
search_futures(category="metals", product="Commodity/Metals/Ferrous")   # ✓ works
search_futures(category="metals", product="Commodity/Energy/Oil")       # ✗ ValueError
```

#### الفلترة بالبورصة `exchange` والدولة `country`

```python
search_futures(category="energy", exchange="NYMEX")      # specific exchange
search_futures(category="energy", exchange="nymex")      # automatic upper-case retry
search_futures(country="IN")                             # all India contracts
search_futures(country="IN", category="metals")          # ★ country + category together
search_futures(country="US", category="world_indices")
```

> **كيف تعمل الفلترة بالدولة؟** مجمّع العقود الآجلة لا يحمل حقل الدولة إطلاقاً، لذا تمرّ الفلترة بالدولة عبر **بحث الرموز** (`symbol-search`) ثم يُصنَّف كل رمز عبر المجمّع. سقف استعلام بحث الرموز 50 نتيجة (كما في `search_symbol`). أما فلاتر التصنيف/التصنيف الفرعي/البورصة فتُنفَّذ على الخادم مباشرة في المجمّع.

#### العقود المستمرة مقابل الشهرية

- **الاستعراض** (`text=""` و`country=None`) يعيد **عقود الشهر أيضاً** ما لم تُمرّر `continuous_only=True` (الافتراضي)، أي العقود المستمرة فقط: `CL1!`، `GC1!`، ...
- **البحث بـ `text`/`country`** يعيد **الجذر** (`CL`) لأنه ما يرجع من بحث الرموز، مع إضافة `continuous_symbol` (`CL1!`) لتمكين التحميل المباشر.

#### بنية الناتج

عنصر نموذجي (من الاستعراض):

```python
{
    "symbol": "GC1!",
    "full_name": "COMEX:GC1!",         # ready to pass to get_hist
    "description": "Gold Futures",
    "exchange": "COMEX",
    "exchange_id": "COMEX",
    "type": "futures",
    "country": None,                   # the screener provides no country -> always None
    "currency_code": "USD",
    "typespecs": ["continuous", "synthetic"],
    "product": "Commodity/Metals/Precious/Gold",  # full sub-category path
    "category": "metals",              # one of the ten categories
    "categories": ["metals"],
    "logoid": "metal/gold",
    "close": 4035.6,
    "change": 0.42,
    "continuous": True,                # continuous contract (1!), not monthly
}
```

وفي مسار `text`/`country` تحتوي النتيجة أيضاً على `contracts` (قائمة عقود الجذر مع `typespecs`) و`continuous_symbol` (`CL1!`).

#### الأخطاء

| الحالة | النتيجة |
|---|---|
| `category` غير معروف / فارغ | `ValueError` فوري مع سرد التصنيفات العشرة |
| `product` لا ينتمي إلى `category` | `ValueError` فوري |
| `country="XYZ"` / `limit` ≤ 0 / `timeout` ≤ 0 / `lang` فارغ | `ValueError` فوري |
| `exchange` بحالة خاطئة (`nymex` بدل `NYMEX`) | إعادة محاولة تلقائية بحروف كبيرة |
| بورصة/تصنيف لا نتائج له | قائمة فارغة `[]` (بلا استثناء) |
| انقطاع شبكة / HTTP غير 200 / استجابة غير JSON | قائمة فارغة `[]` + رسالة في اللوج |

#### أمثلة عملية كاملة

```python
from tvDatafeed import search_futures, list_futures_categories, TvDatafeed, Interval

tv = TvDatafeed()

# 1) list the available categories
for c in list_futures_categories():
    print(c["id"], "->", c["product"], "|", c["label"])

# 2) NYMEX energy (continuous) + download data
hits = search_futures(category="energy", exchange="NYMEX", limit=10)
df = tv.get_hist(symbol=hits[0]["symbol"], exchange=hits[0]["exchange_id"],
                 interval=Interval.in_daily, n_bars=100)

# 3) text + category: root then continuous contract
hits = search_futures("crude oil", category="energy")
cl = next(r for r in hits if r["full_name"] == "NYMEX:CL")
df = tv.get_hist(symbol=cl["symbol"], exchange=cl["exchange_id"], fut_contract=1, n_bars=100)
# or directly: tv.get_hist(symbol=cl["continuous_symbol"], exchange=cl["exchange_id"], n_bars=100)

# 4) country + category
mcx_metals = search_futures(country="IN", category="metals", limit=20)
print([r["full_name"] for r in mcx_metals])

# 5) sub-category
gold_only = search_futures(product="Commodity/Metals/Precious/Gold", limit=20)
print(all(r["product"].startswith("Commodity/Metals/Precious/Gold") for r in gold_only))  # True

# 6) every monthly contract, not just continuous
months = search_futures(category="weather", continuous_only=False, limit=20)
```

---

### قائمة الدول المدعومة (Supported countries)

يمرّر المعامل `country` في الدالتين `search_symbol` و`search_futures` إلى نفس طرفية بحث الرموز في TradingView، ويمكن إدخاله بإحدى صورتين:

1. **رمز ISO-3166 alpha-2** بأحرف كبيرة أو صغيرة (مثل `"SA"` أو `"sa"` أو `"US"`).
2. **اسم الدولة بالإنجليزية** (مثل `"Saudi Arabia"` أو `"Bulgaria"`) — يُحوَّل داخلياً إلى رمز ISO.

الجدول التالي يجمع كل الدول التي تحمل رمزاً في TradingView مع رمزها ISO واسمها الإنجليزي، ويبيّن أي دالة تُرجع لها نتائج فعلية عند الفلترة بالدولة، مع مثال رمز حقيقي.

| الدولة | الاسم الإنجليزي | رمز ISO | `search_symbol` | `search_futures` | مثال (بورصة:رمز) |
|---|---|---|---|---|---|
| **أمريكا الشمالية** | | | | | |
| الولايات المتحدة الأمريكية | United States | `US` | ✅ | ✅ | `AMEX:SPY` |
| كندا | Canada | `CA` | ✅ | ✅ | `TSX:SHOP` |
| **أوروبا** | | | | | |
| النمسا | Austria | `AT` | ✅ | — | `VIE:FTG` |
| بلجيكا | Belgium | `BE` | ✅ | ✅ | `EURONEXT:ABI` |
| بلغاريا | Bulgaria | `BG` | ✅ | — | `BSESOF:RBL` |
| كرواتيا | Croatia | `HR` | ✅ | — | `ZSE:KOEI` |
| قبرص | Cyprus | `CY` | ✅ | — | `CSECY:BOCH` |
| جمهورية التشيك | Czech Republic | `CZ` | ✅ | — | `PSECZ:CSG` |
| الدانمارك | Denmark | `DK` | ✅ | ✅ | `OMXCOP:NOVO_B` |
| إستونيا | Estonia | `EE` | ✅ | — | `OMXTSE:LHV1T` |
| الاتحاد الأوروبي | European Union | `EU` | ✅ <sup>1</sup> | ✅ | `EUREX:FDAX` |
| فنلندا | Finland | `FI` | ✅ | ✅ | `OMXHEX:NOKIA` |
| فرنسا | France | `FR` | ✅ | ✅ | `EURONEXT:MC` |
| ألمانيا | Germany | `DE` | ✅ | ✅ | `XETR:RHM` |
| اليونان | Greece | `GR` | ✅ | — | `ATHEX:ALWN` |
| المجر | Hungary | `HU` | ✅ | ✅ | `BET:OTP` |
| آيسلندا | Iceland | `IS` | ✅ | — | `OMXICE:ALVO` |
| أيرلندا | Ireland | `IE` | ✅ | — | `EURONEXT:RYA` |
| إيطاليا | Italy | `IT` | ✅ | ✅ | `MIL:RACE` |
| لاتفيا | Latvia | `LV` | ✅ | — | `OMXRSE:EGG` |
| ليتوانيا | Lithuania | `LT` | ✅ | — | `OMXVSE:IGN1L` |
| لوكسمبورغ | Luxembourg | `LU` | ✅ | — | `LUXSE:LU2420245917` |
| هولندا | Netherlands | `NL` | ✅ | ✅ | `EURONEXT:ASML` |
| النرويج | Norway | `NO` | ✅ | ✅ | `OSL:KOG` |
| بولندا | Poland | `PL` | ✅ | ✅ | `GPW:XTB` |
| البرتغال | Portugal | `PT` | ✅ | ✅ | `EURONEXT:BCP` |
| رومانيا | Romania | `RO` | ✅ | — | `BVB:TVBETETF` |
| روسيا | Russia | `RU` | ✅ | ✅ | `RUS:GAZP` |
| صربيا | Serbia | `RS` | ✅ | — | `BELEX:PUUE` |
| سلوفاكيا | Slovakia | `SK` | ✅ | — | `BSSE:1ACI001E` |
| سلوفينيا | Slovenia | `SI` | ✅ | — | `LJSE:KRKG` |
| إسبانيا | Spain | `ES` | ✅ | — | `BME:SAN` |
| السويد | Sweden | `SE` | ✅ | ✅ | `OMXSTO:SIVE` |
| سويسرا | Switzerland | `CH` | ✅ | — | `SIX:NESN` |
| تركيا | Turkey | `TR` | ✅ | ✅ | `BIST:THYAO` |
| المملكة المتحدة | United Kingdom | `GB` | ✅ | ✅ | `LSE:VWRA` |
| **الشرق الأوسط / أفريقيا** | | | | | |
| البحرين | Bahrain | `BH` | ✅ | — | `BAHRAIN:NBB` |
| مصر | Egypt | `EG` | ✅ | — | `EGX:COMI` |
| إسرائيل | Israel | `IL` | ✅ | — | `TASE:GOLD` |
| كينيا | Kenya | `KE` | ✅ | — | `NSEKE:SCOM` |
| الكويت | Kuwait | `KW` | ✅ | — | `KSE:KFH` |
| المغرب | Morocco | `MA` | ✅ | — | `CSEMA:GTM` |
| نيجيريا | Nigeria | `NG` | ✅ | — | `NSENG:GTCO` |
| قطر | Qatar | `QA` | ✅ | — | `QSE:MARK` |
| المملكة العربية السعودية | Saudi Arabia | `SA` | ✅ | — | `TADAWUL:2222` |
| جنوب أفريقيا | South Africa | `ZA` | ✅ | — | `JSE:SOL` |
| تونس | Tunisia | `TN` | ✅ | — | `BVMT:BNA` |
| الإمارات العربية المتحدة | United Arab Emirates | `AE` | ✅ | ✅ | `DFM:EMAAR` |
| **المكسيك وأمريكا الجنوبية** | | | | | |
| الأرجنتين | Argentina | `AR` | ✅ | ✅ | `BCBA:TSMC` |
| البرازيل | Brazil | `BR` | ✅ | ✅ | `BMFBOVESPA:VALE3` |
| تشيلي | Chile | `CL` | ✅ | — | `BCS:LTM` |
| كولومبيا | Colombia | `CO` | ✅ | — | `BVC:ECOPETROL` |
| المكسيك | Mexico | `MX` | ✅ | — | `BMV:CEMEX/CPO` |
| بيرو | Peru | `PE` | ✅ | — | `BVL:CREDITC1` |
| فنزويلا | Venezuela | `VE` | ✅ | — | `BVCV:SVS` |
| **آسيا / المحيط الهادئ** | | | | | |
| أستراليا | Australia | `AU` | ✅ | ✅ | `ASX:BHP` |
| بنجلاديش | Bangladesh | `BD` | ✅ | — | `DSEBD:BRACBANK` |
| هونغ كونغ، الصين | Hong Kong, China | `HK` | ✅ | ✅ | `HKEX:1810` |
| الهند | India | `IN` | ✅ | ✅ | `NSE:RELIANCE` |
| إندونيسيا | Indonesia | `ID` | ✅ | — | `IDX:BBCA` |
| اليابان | Japan | `JP` | ✅ | ✅ | `TSE:285A` |
| بر الصين الرئيسي | Mainland China | `CN` | ✅ | ✅ | `SSE:688825` |
| ماليزيا | Malaysia | `MY` | ✅ | ✅ | `MYX:MAYBANK` |
| نيوزيلندا | New Zealand | `NZ` | ✅ | ✅ | `NZX:EBO` |
| باكستان | Pakistan | `PK` | ✅ | — | `PSX:PRL` |
| الفلبين | Philippines | `PH` | ✅ | — | `PSE:ICT` |
| سنغافورة | Singapore | `SG` | ✅ | ✅ | `SGX:D05` |
| كوريا الجنوبية | South Korea | `KR` | ✅ | ✅ | `KRX:000660` |
| سريلانكا | Sri Lanka | `LK` | ✅ | — | `CSELK:SAMP.N0000` |
| تايوان، الصين | Taiwan, China | `TW` | ✅ | ✅ | `TWSE:2330` |
| تايلاند | Thailand | `TH` | ✅ | ✅ | `SET:DELTA` |
| فيتنام | Vietnam | `VN` | ✅ | ✅ | `HOSE:FPT` |

**ملاحظات:**

- <sup>1</sup> `EU` رمز خاص بالاتحاد الأوروبي عند TradingView (ليس دولة ISO بالمعنى الدقيق). لا يحمل أي ورقة **أسهم** (لذلك `search_symbol("...", country="EU", type="stock")` يعيد `[]`)، لكنه يحمل **عقوداً آجلة** (مثل `EUREX:FDAX`)، لذا يعمل معه `search_symbol(..., type="futures")` و`search_futures(country="EU")`.
- عمود `search_symbol` يعني أن فلترة الدولة تعمل وأن الطرفية تُرجع أدوات مُوسمة بهذه الدولة. تذكّر أن `search_symbol` **يتطلّب نص بحث غير فارغ** (`text`)، بينما `search_futures` يستطيع الاستعراض بـ`country` وحده (`text=""`).
- عمود `search_futures` يشير إلى وجود **عقود آجلة** موسومة بهذه الدولة في الطرفية؛ الدول التي عليها `—` لا تحتوي أدوات آجلة في TradingView حالياً، فتُعيد `search_futures(country=...)` قائمة فارغة `[]`.
- للدول التي لا تعرض نتائج في وضع الاستعراض (نص فارغ)، استخدم نصاً من اسم الرمز أو وصفه (مثل `search_symbol("2222", country="SA")` أو `search_symbol("bank", country="CN")`).
- أي رمز حرفين غير مذكور هنا (مثل `"XX"`) لا يرمي خطأ، بل يُمرَّر للطرفية ويعيد قائمة فارغة `[]`.
- القائمة مبنية على تحقق حيّ من TradingView؛ وقد تتغير تغطية الدول مع الوقت.

---

## 3) مثال مقارنة قبل / بعد

```python
from tvDatafeed import TvDatafeed, Interval

tv = TvDatafeed()
args = {"symbol": "XAUUSD", "exchange": "BLACKBULL",
        "interval": Interval.in_daily, "n_bars": 5}

before = tv.get_hist(**args, align_daily_to_trading_day=False)  # original
after  = tv.get_hist(**args)                                     # fixed

print("before:", before.index.tolist())
print("after:", after.index.tolist())
```

```
before: [2026-09-20 22:00, 2026-09-21 22:00, 2026-09-22 22:00, 2026-09-23 22:00]
after: [2026-09-21 22:00, 2026-09-22 22:00, 2026-09-23 22:00, 2026-09-24 22:00]
```

---

## 4) التحقق من الإصلاح

```bash
cd tvdatafeed-timezone-fix
pip install pytest
pytest tests -v
```

كل الاختبارات محلية (بدون إنترنت) وتستخدم حمولة حقيقية ملتقطة من TradingView. تشمل:
- اختبارات `search_symbol` الكاملة (مرادفات الأنواع والدول، بناء الطلب، مسارات الأخطاء، `ValueError` مقابل `[]`).

اختبارات **حية** (اختيارية) تتحقق من صحة البيانات الفعلية من TradingView بدون تسجيل دخول:

```bash
TV_LIVE=1 pytest tests/test_search_live.py tests/test_futures_live.py tests/test_countries_live.py -v
```

يتحقق `tests/test_countries_live.py` من **تطابق مدخل `country` مع مخرج الدالتين** لكل الدول المذكورة في «قائمة الدول المدعومة»، ومن أن الأسماء الإنجليزية تُحلّ إلى رموز ISO الصحيحة.

---

## 5) أسئلة شائعة

**هل تتغير قيم OHLC؟** لا — القيم كانت صحيحة. التغيير في عمود التاريخ والمنطقة الزمنية فقط.

**كيف أعود للسلوك القديم بالضبط؟**
```python
tv.get_hist(..., timezone="exchange", align_daily_to_trading_day=False)
```

**لماذا آخر صف دائماً بتاريخ اليوم؟** لأن TradingView يرسل الشمعة الجارية (القيد التكوين) ضمن النتيجة؛ نعيد تسميتها بتاريخ يوم التداول الفعلي.

**هل تعمل مناطق توقيت مثل DST؟** نعم — التحويل يتم من UTC المعروف، فلا توجد أخطاء غموض التوقيت الصيفي.

**كيف أبحث في العقود الآجلة حسب التصنيف (energy/metals/weather...)؟** استخدم `search_futures(category=...)` — الجدول الكامل أعلاه. التصنيف يأتي من شاشة TradingView للعقود الآجلة نفسها (عمود `product` الهرمي)، فلا حاجة إلى أي قائمة يدوية، ويمكن النزول للتصنيف الفرعي عبر `product=`.

**لماذا `country=None` في نتائج `search_futures`؟** لأن **مجمّع** العقود الآجلة (مصدر نتائج الاستعراض) لا يوفّر حقل الدولة إطلاقاً وتُعرض قيمته `None` بلا خطأ. أما إذا فلترت بـ `country=` فالنتائج تأتي من بحث الرموز وتحمل الدولة فعلاً (`"IN"`، `"US"`...).

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
sys.path.insert(0, "/المسار/إلى/tvdatafeed-timezone-fix")
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
tv = TvDatafeed()                      # بدون تسجيل دخول
tv = TvDatafeed("user", "pass")        # بحساب TradingView
```

---

### `get_hist(...)` — تحميل البيانات التاريخية

```python
tv.get_hist(
    symbol: str,                        # رمز السهم/السلعة، أو بالصيغة "EXCHANGE:SYMBOL"
    exchange: str = "NSE",              # البورصة (تُتجاهل إذا كان الرمز بصيغة EXCHANGE:SYMBOL)
    interval: Interval = Interval.in_daily,
    n_bars: int = 10,                   # عدد الشموع (الحد الأقصى ~5000)
    fut_contract: int = None,           # None للنقد، 1/2 للعقود الآجلة المستمرة
    extended_session: bool = False,     # جلسة ممتدة (خارج أوقات العمل الرسمية)
    timezone: str = "UTC",              # ★ الإضافة الجديدة — المنطقة الزمنية
    align_daily_to_trading_day: bool = True,  # ★ الإضافة الجديدة — تصحيح تاريخ الشموع اليومية
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

# ذهب يومي بتوقيت UTC (الافتراضي) — آخر صف بتاريخ اليوم
df = tv.get_hist(symbol="XAUUSD", exchange="BLACKBULL",
                 interval=Interval.in_daily, n_bars=100)

# آخر صف هو شمعة اليوم الجارية بتاريخ اليوم الصحيح
print(df.tail(3))
print("المنطقة الزمنية:", df.index.tz)
```

#### بنية الناتج
`DataFrame` فهرسه `datetime` (معرّف بالمنطقة الزمنية) والأعمدة:

| العمود | الوصف |
|---|---|
| `symbol` | الرمز بالصيغة `EXCHANGE:SYMBOL` |
| `open` / `high` / `low` / `close` | سعر الافتتاح/الأعلى/الأدنى/الإغلاق |
| `volume` | الحجم |

كما يُضاف `df.attrs["timezone"]` (اسم المنطقة الزمنية) و `df.attrs["aligned_to_trading_day"]` (هل طُبّق تصحيح تاريخ اليوم).

---

### `search_symbol(...)` — البحث عن الرمز (بدون تسجيل دخول)

بحث في TradingView بالاسم أو الوصف مع فلترة اختيارية **بالنوع** (سلع، سندات، فوريكس، أسهم، ...) و**بالدولة**، **دون الحاجة إلى حساب أو تسجيل دخول**، بل ودون الحاجة حتى إلى إنشاء كائن:

```python
from tvDatafeed import search_symbol

search_symbol("gold")                       # بحث عام
search_symbol("أرامكو")                     # نص عربي — يعمل مباشرة
search_symbol("XAUUSD", "BLACKBULL")        # بحث داخل بورصة محددة: المعامل الثاني exchange
```

كطريقة على كائن `TvDatafeed` (ترث إعدادات الوكيل `proxies` تلقائياً):

```python
from tvDatafeed import TvDatafeed
tv = TvDatafeed()                    # بدون بيانات دخول — nologin
tv.search_symbol("gold")
```

#### التوقيع الكامل

```python
search_symbol(
    text: str,             # اسم الرمز أو وصفه (عربي أو إنجليزي)
    exchange: str = "",    # معرف البورصة (مثل "BLACKBULL" أو "TADAWUL") — اختياري
    type: str = None,      # نوع الأصل — عربي أو إنجليزي (الجدول أدناه)
    country: str = None,   # الدولة: رمز ISO-2 أو اسم عربي/إنجليزي — اختياري
    limit: int = 50,       # عدد النتائج (1..50، والـ 50 حدّ الخادم الأقصى)
    lang: str = "en",      # لغة الواجهة المطلوبة من TradingView
    timeout: float = 10,   # مهلة الطلب بالثواني
    proxies: dict = None,  # وكيل اختياري {"https": "http://..."}
    extra: dict = None,    # معاملات إضافية تُمرَّر للخادم كما هي (تخصيص)
) -> list[dict]
```

> ملاحظة الحالة: `exchange` حساس لحالة الأحرف لدى الخادم، وتُعاد المحاولة تلقائياً بحروف كبيرة إذا كانت النتيجة فارغة.

#### الفلترة بالنوع `type`

| القيمة (إنجليزي) | مرادفات عربية مقبولة | الوصف |
|---|---|---|
| `"commodity"` | `"السلع"`، `"سلع"` | السلع (ذهب، نفط، غاز...) — تُسترجَع عبر شاشة CFD ثم تُفلتِر داخلياً على النوع `commodity` |
| `"bond"` | `"السندات"`، `"سندات"` | السندات |
| `"forex"` | `"الفوريكس"`، `"فوركس"`، `"عملات"` | سوق الصرف الأجنبي |
| `"stock"` | `"الأسهم"`، `"أسهم"` | الأسهم وشهادات الإيداع (`stock` / `dr`) |
| `"index"` | `"المؤشرات"`، `"مؤشرات"` | المؤشرات |
| `"crypto"` | `"العملات الرقمية"`، `"كريبتو"`، `"الرقمية"` | العملات الرقمية |
| `"futures"` | `"العقود الآجلة"` | العقود الآجلة |
| `"etf"` | `"صناديق مؤشرات"` | صناديق المؤشرات |
| `"fund"` | `"الصناديق"`، `"صناديق"` | الصناديق |
| `"cfd"` | `"عقود الفروقات"`، `"فروقات"` | عقود الفروقات |
| `"option"` | `"الخيارات"` | الخيارات |
| `"warrant"` | `"الشهادات"`، `"شهادات"` | الشهادات/الأسهم الواردة |

المطابقة غير حساسة لحالة الأحرف. أي قيمة غير معروفة ترمي `ValueError` فوراً مع سرد الأنواع الصالحة.

#### الفلترة بالدولة `country`

تقبل رمز ISO-3166 alpha-2 (مثل `"SA"` أو `"US"`) أو اسماً بالعربية/الإنجليزية من قاعدة مرادفات تغطي الأسواق الرئيسية والدول العربية:

```python
search_symbol("bank", country="السعودية")          # → country=SA — كل النتائج TADAWUL
search_symbol("أرامكو", country="SA")               # نص عربي كامل يعمل + رمز الدولة
search_symbol("bank", country="السعودية", type="الأسهم")
```

> **الدولة اختيارية بطبيعتها**: السلع والفوريكس والعملات الرقمية لا تحمل دولة في بيانات TradingView، لذا يُعرض `country=None` — المفتاح موجود دائماً في النتيجة لكن قيمته قد تكون `None`، ولا يحدث أي خطأ.

#### بنية الناتج

عنصر نموذجي من القائمة المعادة:

```python
{
    "symbol": "XAUUSD",
    "full_name": "BLACKBULL:XAUUSD",   # جاهزة للإرسال إلى get_hist (الصيغة EXCHANGE:SYMBOL)
    "description": "Gold",
    "exchange": "BlackBull Markets",   # الاسم المعروض لدى TradingView
    "exchange_id": "BLACKBULL",        # ★ المعرف الحقيقي المطلوب في get_hist
    "type": "commodity",
    "country": None,                   # None للسلع/الفوريكس/... (المفتاح موجود دائماً)
    "currency_code": "USD",
    "typespecs": ["cfd"],              # قائمة دائماً ([] إن لم توجد)
    "provider_id": "blackbullmarkets",
    # ... أي حقول إضافية ترجعها TradingView تبقى كما هي (logoid, isin, ...)
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

# 1) كل رموز أرامكو السعودية (نص عربي + دولة)
aramco = search_symbol("أرامكو", country="السعودية")
print([r["full_name"] for r in aramco])          # ['TADAWUL:2222', ...]

# 2) السلع فقط — ذهب ونفط
gold = search_symbol("gold", type="السلع", limit=10)
oil  = search_symbol("oil",  type="commodity", limit=10)
print(all(r["type"] == "commodity" for r in gold + oil))   # True

# 3) السندات والفوريكس
print(len(search_symbol("apple",  type="bond")))            # > 0
print(len(search_symbol("EURUSD", type="الفوريكس")))        # > 0

# 4) تحميل بيانات لأول نتيجة بحث
hit = search_symbol("XAUUSD", "BLACKBULL")[0]
df = tv.get_hist(symbol=hit["symbol"], exchange=hit["exchange_id"],
                 interval=Interval.in_daily, n_bars=50, timezone="UTC")
print(df.tail(3))
```

---

## 3) مثال مقارنة قبل / بعد

```python
from tvDatafeed import TvDatafeed, Interval

tv = TvDatafeed()
args = {"symbol": "XAUUSD", "exchange": "BLACKBULL",
        "interval": Interval.in_daily, "n_bars": 5}

before = tv.get_hist(**args, align_daily_to_trading_day=False)  # الأصلي
after  = tv.get_hist(**args)                                     # المُصلح

print("قبل:", before.index.tolist())
print("بعد:", after.index.tolist())
```

```
قبل: [2026-09-20 22:00, 2026-09-21 22:00, 2026-09-22 22:00, 2026-09-23 22:00]
بعد: [2026-09-21 22:00, 2026-09-22 22:00, 2026-09-23 22:00, 2026-09-24 22:00]
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
TV_LIVE=1 pytest tests/test_search_live.py -v
```

---

## 5) أسئلة شائعة

**هل تتغير قيم OHLC؟** لا — القيم كانت صحيحة. التغيير في عمود التاريخ والمنطقة الزمنية فقط.

**كيف أعود للسلوك القديم بالضبط؟**
```python
tv.get_hist(..., timezone="exchange", align_daily_to_trading_day=False)
```

**لماذا آخر صف دائماً بتاريخ اليوم؟** لأن TradingView يرسل الشمعة الجارية (القيد التكوين) ضمن النتيجة؛ نعيد تسميتها بتاريخ يوم التداول الفعلي.

**هل تعمل مناطق توقيت مثل DST؟** نعم — التحويل يتم من UTC المعروف، فلا توجد أخطاء غموض التوقيت الصيفي.
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
2026-09-23 22:00:00  4288.34  4303.18  4244.36  4268.42  344281.0   ← آخر صف
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
الشمعة الفعلية:  تفتح Wed 22:00 UTC  ←→  تغلق Thu 21:59 UTC
التاريخ الخام:   2026-09-23           ←→  يوم التداول الحقيقي: 2026-09-24 (اليوم)
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
قبل الإصلاح:  ... 2026-09-22 22:00 , 2026-09-23 22:00   ← "اليوم" يظهر بالأمس!
بعد الإصلاح:  ... 2026-09-23 22:00 , 2026-09-24 22:00   ← أيام تداول حقيقية (بدون نهايات أسبوع)
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
# 1) نسخ المستودع ثم التثبيت
git clone https://github.com/ayoubajermoune/tvdatafeed-timezone-fix
cd tvdatafeed-timezone-fix
pip install .

# 2) التثبيت في وضع التطوير (لتعديل الكود)
pip install -e .
```

## الاستخدام (Usage)

```python
from tvDatafeed import TvDatafeed, Interval

tv = TvDatafeed()

# 1) الافتراضي: UTC — منطقة زمنية معروفة صراحة
data = tv.get_hist(symbol='XAUUSD', exchange='BLACKBULL',
                   interval=Interval.in_daily, n_bars=10)
print(data.index.tz)   # UTC

# 2) منطقة زمنية محددة
data = tv.get_hist(symbol='XAUUSD', exchange='BLACKBULL',
                   interval=Interval.in_daily, n_bars=10,
                   timezone='Africa/Cairo')
print(data)

# 3) الوضع القديم: نايف على ساعة البورصة
data = tv.get_hist(..., timezone='exchange')

# 4) تواريخ TradingView الخام (بدون تصحيح)
data = tv.get_hist(..., align_daily_to_trading_day=False)
```

مثال عملي كامل في `examples/example_usage.py`.

### البحث عن الرمز — `search_symbol(...)` (بدون تسجيل دخول)

بحث في TradingView عن الرموز بالاسم/الوصف مع فلترة اختيارية **بالنوع** (السلع، السندات، الفوريكس، الأسهم، ...) و**بالدولة**، **دون الحاجة إلى حساب أو إنشاء كائن**:

```python
from tvDatafeed import search_symbol

search_symbol("gold")                            # بحث عام
search_symbol("أرامكو")                          # نص عربي
search_symbol("XAUUSD", "BLACKBULL")             # داخل بورصة محددة
search_symbol("gold", type="السلع")              # سلع فقط (مرادفات عربية/إنجليزية)
search_symbol("bank", country="السعودية")        # بنوك السوق السعودي
search_symbol("EURUSD", type="الفوريكس")         # فوريكس فقط
```

توجد أيضاً كطريقة على الكائن لتوريث الوكيل: `tv.search_symbol("XAUUSD", "BLACKBULL")`.

**المعاملات:**

| المعامل | النوع | الافتراضي | الوصف |
|---|---|---|---|
| `text` | `str` | — | نص البحث (اسم الرمز أو وصفه — عربي أو إنجليزي) |
| `exchange` | `str` | `""` | معرف البورصة (مثل `BLACKBULL`، `TADAWUL`) |
| `type` | `str` | `None` | نوع الأصل: `commodity/السلع`، `bond/السندات`، `forex/الفوريكس`، `stock/الأسهم`، `index/المؤشرات`، `crypto/العملات الرقمية`، `futures/العقود الآجلة`، `etf`، `fund/الصناديق`، `cfd/عقود الفروقات`، `option/الخيارات`، `warrant/الشهادات` |
| `country` | `str` | `None` | رمز ISO-2 أو اسم (عربي/إنجليزي) مثل `"السعودية"` أو `"US"` |
| `limit` | `int` | `50` | عدد النتائج (الحد الأقصى للخادم 50) |
| `lang` | `str` | `"en"` | لغة الواجهة المطلوبة |
| `timeout` | `float` | `10` | مهلة الطلب بالثواني |
| `proxies` | `dict` | `None` | وكيل اختياري (أو عبر منشئ `TvDatafeed`) |
| `extra` | `dict` | `None` | معاملات إضافية تُمرَّر للخادم كما هي (تخصيص مستقبلي) |

**الناتج:** قائمة قواميس دائمة البنية:

```python
{
    "symbol": "XAUUSD",
    "full_name": "BLACKBULL:XAUUSD",   # جاهزة للإرسال إلى get_hist
    "description": "Gold",
    "exchange": "BlackBull Markets",   # الاسم المعروض
    "exchange_id": "BLACKBULL",        # ★ المعرّف الحقيقي المطلوب في get_hist
    "type": "commodity",
    "country": None,                   # السلع/الفوريكس لا تحمل دولة → None دائماً بدون خطأ
    "currency_code": "USD",
    "typespecs": ["cfd"],
    "provider_id": "blackbullmarkets",
    # ... + أي حقول إضافية من TradingView
}
```

استعمال عملي:

```python
from tvDatafeed import search_symbol, TvDatafeed

tv = TvDatafeed()
matches = search_symbol("bank", country="السعودية", type="الأسهم")
if not matches:
    raise ValueError("لا توجد نتائج مطابقة")

hit = matches[0]
data = tv.get_hist(symbol=hit["symbol"], exchange=hit["exchange_id"], n_bars=10)
```

> **المعاملات الخاطئة** (`type` غير معروف، `country="XYZ"`، `text` فارغ، `limit=0`) ترمي `ValueError` فوراً برسالة توضيحية. **أعطال الشبكة فقط** تعيد `[]` مع رسالة في اللوج — فلا تخلط بينهما.
>
> **بدون تسجيل دخول:** الخدمة لا تتطلب مصادقة إطلاقاً؛ كل ما تحتاجه هو هيدر `Origin` الذي تُرسله المكتبة تلقائياً (أصل عطل `403`).
>
> **403 / الشبكات المحجوبة (Colab/notebooks):** مرّر وكيلاً: `tv = TvDatafeed(proxies={...})` أو `search_symbol(..., proxies={...})`.

التفاصيل الكاملة (جداول المرادفات العربية لكل الأنواع والدول، بنية الأخطاء، أمثلة) في [`docs/USAGE.md`](docs/USAGE.md) وقسم 5 من [`examples/example_usage.py`](examples/example_usage.py).

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

**اختبارات حية (اختيارية)** تتصل بـ TradingView فعلياً وتراجع صحة البيانات (بحث بالنوع/الدولة، نص عربي، تنزيل رمز مُرجَع عبر `get_hist`):

```bash
TV_LIVE=1 pytest tests/test_search_live.py -v
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
- **`search_symbol(text, exchange='', type=None, country=None, ...)`** — look up symbols **without any login** (also exposed as a module-level standalone `search_symbol`) with optional filters by asset type (`commodity/سلع`, `bond/سندات`, `forex/فوريكس`, ...) and country (ISO-2 or Arabic/English names). Returns normalised dicts with `full_name`, `exchange_id`, `country` (`None` for commodities/forex), `currency_code`, `typespecs`. Invalid arguments raise `ValueError`; network failures return `[]`.

OHLCV values are untouched; only the datetime column and timezone semantics changed. Offline test suite included (`pytest tests`).

---

## الرخصة (License)

MIT — نفس رخصة المستودع الأصلي / Same license as upstream.



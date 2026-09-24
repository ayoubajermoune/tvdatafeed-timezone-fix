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

### `search_symbol(text, exchange='')` — البحث عن رمز

```python
tv.search_symbol("gold")        # قائمة بالرموز المطابقة
tv.search_symbol("XAUUSD", "BLACKBULL")
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

كل الاختبارات محلية (بدون إنترنت) وتستخدم حمولة حقيقية ملتقطة من TradingView.

---

## 5) أسئلة شائعة

**هل تتغير قيم OHLC؟** لا — القيم كانت صحيحة. التغيير في عمود التاريخ والمنطقة الزمنية فقط.

**كيف أعود للسلوك القديم بالضبط؟**
```python
tv.get_hist(..., timezone="exchange", align_daily_to_trading_day=False)
```

**لماذا آخر صف دائماً بتاريخ اليوم؟** لأن TradingView يرسل الشمعة الجارية (القيد التكوين) ضمن النتيجة؛ نعيد تسميتها بتاريخ يوم التداول الفعلي.

**هل تعمل مناطق توقيت مثل DST؟** نعم — التحويل يتم من UTC المعروف، فلا توجد أخطاء غموض التوقيت الصيفي.
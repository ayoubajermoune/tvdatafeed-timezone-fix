import enum
import json
import logging
import random
import re
import string
import zoneinfo

import pandas as pd
from websocket import create_connection

import requests

try:
    from .search import USER_AGENT as _USER_AGENT
    from .search import search_symbol as _module_search_symbol
    from .futures import search_futures as _module_search_futures
except ImportError:  # pragma: no cover - running ``python tvDatafeed/main.py``
    from search import USER_AGENT as _USER_AGENT
    from search import search_symbol as _module_search_symbol
    from futures import search_futures as _module_search_futures

logger = logging.getLogger(__name__)


def _build_resolve_payload(symbol, extended_session=False):
    """Build a TradingView ``resolve_symbol`` payload.

    The leading ``=`` is mandatory: TradingView expects the value to be a
    JSON string prefixed with ``=``.  Omitting it makes every symbol
    resolution fail with ``symbol_error: invalid symbol`` (this was the
    root cause of the constant ``open_interest`` column, because the OI
    request used a payload without the prefix).
    """
    session = "extended" if extended_session else "regular"
    return (
        '={"symbol":"'
        + symbol
        + '","adjustment":"splits","session":"'
        + session
        + '"}'
    )


def _map_open_interest_to_bars(
    df,
    oi_df,
    interval=None,
    aligned_to_trading_day=None,
):
    """Map daily open interest onto the bars of ``df``.

    TradingView publishes open interest once per trading session, so the OI
    series is always requested with a daily resolution.  Each bar receives
    the OI of the session it belongs to; weekly/monthly bars receive the last
    daily OI inside their period.  The last (still forming) bar receives the
    latest OI value available.

    Args:
        df: OHLCV DataFrame returned by ``get_hist``.
        oi_df: daily OI DataFrame returned by ``__create_df`` (OI value in
            the ``close`` column).
        interval: optional :class:`Interval` of ``df``.  It is used to decide
            whether period-end mapping is needed (weekly/monthly) and to
            handle the daily trading-day alignment.
        aligned_to_trading_day: whether daily bars were shifted to their
            closing day.  Defaults to ``df.attrs["aligned_to_trading_day"]``.

    Returns:
        pd.Series: float64 series indexed like ``df``; values are ``NaN``
        where no historical OI is available.
    """
    if df is None:
        return pd.Series(dtype="float64")
    if len(df) == 0:
        return pd.Series(dtype="float64", index=df.index)

    if aligned_to_trading_day is None:
        aligned_to_trading_day = bool(
            df.attrs.get("aligned_to_trading_day", False)
        )

    nan_series = pd.Series(float("nan"), index=df.index, dtype="float64")
    if oi_df is None or len(oi_df) == 0:
        return nan_series

    oi_series = oi_df["close"] if "close" in oi_df.columns else oi_df.iloc[:, -1]
    oi_series = pd.to_numeric(oi_series, errors="coerce").dropna().sort_index()
    oi_series = oi_series[~oi_series.index.duplicated(keep="last")]
    if len(oi_series) == 0:
        return nan_series

    def _merge_index(index):
        """Use one datetime unit for both merge sides (pandas 3 uses us)."""
        idx = pd.DatetimeIndex(index)
        if idx.tz is not None:
            idx = idx.tz_convert("UTC").tz_localize(None)
        return idx.astype("datetime64[ns]")

    # Build the upper bound used to look up each bar's OI:
    # - weekly/monthly: the last session inside the period (next bar start
    #   minus 1 ns); the final bar gets the latest OI available.
    # - aligned daily bars are dated by their closing day, so the session's
    #   OI (published at the previous session open) must be strictly before
    #   the bar label.  Subtracting 1 ns gives that strict bound.
    # - intraday and unaligned daily bars: the session OI is at or before
    #   the bar timestamp.
    if interval in (Interval.in_weekly, Interval.in_monthly):
        keys = pd.Series(df.index, index=df.index).shift(-1)
        keys.iloc[-1] = df.index[-1] + pd.Timedelta(days=36500)
        keys = keys - pd.Timedelta(nanoseconds=1)
    elif interval == Interval.in_daily and aligned_to_trading_day:
        shifted = (df.index.hour >= 12).astype("int64")
        keys = pd.Series(
            df.index - pd.to_timedelta(shifted, unit="ns"),
            index=df.index,
        )
    else:
        keys = pd.Series(df.index, index=df.index)

    oi_series.index = _merge_index(oi_series.index)
    keys = pd.Series(_merge_index(keys), index=df.index)

    left = pd.DataFrame({"__oi_key": keys}).sort_values("__oi_key")
    right = oi_series.rename("open_interest").to_frame().sort_index()
    merged = pd.merge_asof(
        left,
        right,
        left_on="__oi_key",
        right_index=True,
        direction="backward",
    )
    merged = merged.sort_index()
    return merged["open_interest"].astype("float64")


class Interval(enum.Enum):
    in_1_minute = "1"
    in_3_minute = "3"
    in_5_minute = "5"
    in_15_minute = "15"
    in_30_minute = "30"
    in_45_minute = "45"
    in_1_hour = "1H"
    in_2_hour = "2H"
    in_3_hour = "3H"
    in_4_hour = "4H"
    in_daily = "1D"
    in_weekly = "1W"
    in_monthly = "1M"


class TvDatafeed:
    __sign_in_url = 'https://www.tradingview.com/accounts/signin/'
    __ws_headers = json.dumps({"Origin": "https://data.tradingview.com"})
    __signin_headers = {'Referer': 'https://www.tradingview.com'}
    __user_agent = _USER_AGENT
    __ws_timeout = 5

    def __init__(
        self,
        username: str = None,
        password: str = None,
        proxies: dict = None,
    ) -> None:
        """Create TvDatafeed object

        Args:
            username (str, optional): tradingview username. Defaults to None.
            password (str, optional): tradingview password. Defaults to None.
            proxies (dict, optional): http(s) proxy mapping used for all REST
                calls, e.g. ``{"https": "http://user:pass@proxy:8080"}``.
                Useful to bypass IP blocks in cloud/notebook environments.
                Defaults to None (no proxy).
        """

        self.proxies = proxies or {}
        self.ws_debug = False

        self.token = self.__auth(username, password)

        if self.token is None:
            self.token = "unauthorized_user_token"
            logger.warning(
                "you are using nologin method, data you access may be limited"
            )

        self.ws = None
        self.session = self.__generate_session()
        self.chart_session = self.__generate_chart_session()

    def __auth(self, username, password):

        if (username is None or password is None):
            token = None

        else:
            data = {"username": username,
                    "password": password,
                    "remember": "on"}
            try:
                headers = {**self.__signin_headers,
                           "User-Agent": self.__user_agent}
                response = requests.post(
                    url=self.__sign_in_url, data=data, headers=headers,
                    timeout=10, proxies=self.proxies)
                token = response.json()['user']['auth_token']
            except Exception as e:
                logger.error('error while signin')
                token = None

        return token

    def __create_connection(self):
        logging.debug("creating websocket connection")
        self.ws = create_connection(
            "wss://data.tradingview.com/socket.io/websocket", headers=self.__ws_headers, timeout=self.__ws_timeout
        )

    @staticmethod
    def __filter_raw_message(text):
        try:
            found = re.search('"m":"(.+?)",', text).group(1)
            found2 = re.search('"p":(.+?"}"])}', text).group(1)

            return found, found2
        except AttributeError:
            logger.error("error in filter_raw_message")

    @staticmethod
    def __generate_session():
        stringLength = 12
        letters = string.ascii_lowercase
        random_string = "".join(random.choice(letters)
                                for i in range(stringLength))
        return "qs_" + random_string

    @staticmethod
    def __generate_chart_session():
        stringLength = 12
        letters = string.ascii_lowercase
        random_string = "".join(random.choice(letters)
                                for i in range(stringLength))
        return "cs_" + random_string

    @staticmethod
    def __prepend_header(st):
        return "~m~" + str(len(st)) + "~m~" + st

    @staticmethod
    def __construct_message(func, param_list):
        return json.dumps({"m": func, "p": param_list}, separators=(",", ":"))

    def __create_message(self, func, paramList):
        return self.__prepend_header(self.__construct_message(func, paramList))

    def __send_message(self, func, args):
        m = self.__create_message(func, args)
        if self.ws_debug:
            print(m)
        self.ws.send(m)

    @staticmethod
    def __extract_exchange_timezone(raw_data: str):
        """Return the exchange timezone reported by TradingView.

        The ``symbol_resolved`` message contains the exchange timezone of the
        requested symbol, e.g. ``"timezone":"America/New_York"``. It is used
        (only) when ``timezone="exchange"`` so the returned timestamps are
        deterministic instead of depending on the local system timezone.

        Returns:
            str | None: an IANA timezone name, or None if it cannot be found.
        """
        match = re.search(r'"m":"symbol_resolved".*?"timezone":"([^"]+)"', raw_data)
        return match.group(1) if match else None

    @staticmethod
    def __create_df(
        raw_data: str,
        symbol: str,
        timezone: str = "UTC",
        interval: "Interval" = None,
        align_daily_to_trading_day: bool = True,
        exchange_tz: str = None,
    ) -> pd.DataFrame:
        """Parse the raw WebSocket payload into a DataFrame.

        Args:
            raw_data: the raw messages received from TradingView.
            symbol: the resolved symbol name.
            timezone:
                - ``"exchange"``: naive timestamps on the exchange clock.
                - ``"UTC"``: timezone-aware UTC timestamps.
                - an IANA name (e.g. ``"Asia/Riyadh"``): timestamps in that
                  timezone.
            interval: the requested ``Interval`` (used for the daily-bar fix).
            align_daily_to_trading_day: shift daily bars that open at/after
                12:00 local time one day forward (see ``get_hist``).
            exchange_tz: the exchange timezone from ``symbol_resolved``.

        Returns:
            pd.DataFrame: sohlcv DataFrame indexed by datetime, or None.
        """
        try:
            out = re.search(r'"s":\[(.+?)\}\]', raw_data).group(1)
            x = out.split(',{"')
            data = list()
            volume_data = True

            for xi in x:
                xi = re.split(r"\[|:|,|\]", xi)

                # TradingView sends true UTC unix timestamps. Parse them
                # explicitly as UTC so the result never depends on the local
                # system timezone (upstream used datetime.fromtimestamp(),
                # which silently converted to the machine's local time).
                ts = pd.to_datetime(float(xi[4]), unit="s", utc=True).tz_localize(None)

                row = [ts]

                for i in range(5, 10):

                    # skip converting volume data if does not exists
                    if not volume_data and i == 9:
                        row.append(0.0)
                        continue
                    try:
                        row.append(float(xi[i]))

                    except ValueError:
                        volume_data = False
                        row.append(0.0)
                        logger.debug('no volume data')

                data.append(row)

            data = pd.DataFrame(
                data, columns=["datetime", "open",
                               "high", "low", "close", "volume"]
            ).set_index("datetime")
            data.index.name = "datetime"

            # ------------------------------------------------------------------
            # 1) Timezone handling
            #    The index currently holds true-UTC wall-clock values. Attach the
            #    requested timezone so the caller always knows (and controls)
            #    which timezone the data is in.
            # ------------------------------------------------------------------
            if timezone == "exchange":
                target_tz = exchange_tz or "UTC"
            else:
                target_tz = timezone

            idx = data.index.tz_localize("UTC").tz_convert(target_tz)

            # ------------------------------------------------------------------
            # 2) Trading-day alignment for daily bars
            #    TradingView labels a daily bar with its *open* date. Sessions
            #    that start late in the day (e.g. gold/forex opening at 22:00
            #    UTC) therefore produce bars dated one day behind the trading
            #    day they represent -- the still-forming bar for "today" appears
            #    to have yesterday's date. If a daily bar opens at/after 12:00
            #    local time it spans midnight, so date it by its closing day.
            #    Intraday bars are never shifted.
            # ------------------------------------------------------------------
            aligned = False
            if align_daily_to_trading_day and interval == Interval.in_daily:
                shift = pd.to_timedelta((idx.hour >= 12).astype("int64"), unit="D")
                if shift.any():
                    idx = idx + shift
                    aligned = True

            if timezone == "exchange":
                # Legacy-compatible output: plain (naive) timestamps, but now
                # deterministically on the exchange clock instead of the
                # machine's local clock.
                idx = idx.tz_localize(None)

            # Index arithmetic (e.g. the +1 day shift above) silently drops the
            # index name; restore it so df.reset_index() yields a consistent
            # "datetime" column for downstream consumers.
            idx.name = "datetime"
            data.index = idx
            data.attrs["timezone"] = target_tz
            data.attrs["aligned_to_trading_day"] = aligned
            data.insert(0, "symbol", value=symbol)
            return data
        except AttributeError:
            logger.error("no data, please check the exchange and symbol")

    @staticmethod
    def __format_symbol(symbol, exchange, contract: int = None):

        if ":" in symbol:
            pass
        elif contract is None:
            symbol = f"{exchange}:{symbol}"

        elif isinstance(contract, int):
            symbol = f"{exchange}:{symbol}{contract}!"

        else:
            raise ValueError("not a valid contract")

        return symbol

    def get_hist(
        self,
        symbol: str,
        exchange: str = "NSE",
        interval: Interval = Interval.in_daily,
        n_bars: int = 10,
        fut_contract: int = None,
        extended_session: bool = False,
        timezone: str = "UTC",
        align_daily_to_trading_day: bool = True,
        open_interest: bool = False,
        include_oi: bool = None,
        include_open_interest: bool = None,
        oi: bool = None,
        **kwargs,
    ) -> pd.DataFrame:
        """get historical data

        Args:
            symbol (str): symbol name
            exchange (str, optional): exchange, not required if symbol is in format EXCHANGE:SYMBOL. Defaults to None.
            interval (Interval, optional): chart interval. Defaults to Interval.in_daily.
            n_bars (int, optional): no of bars to download, max 5000. Defaults to 10.
            fut_contract (int, optional): None for cash, 1 for continuous current contract in front, 2 for continuous next contract in front. Defaults to None.
            extended_session (bool, optional): regular session if False, extended session if True, Defaults to False.
            timezone (str, optional): timezone of the returned index. Defaults to "UTC".
                - "UTC" (default): the index is timezone-aware UTC. The data is
                  always downloaded as true UTC, so the result never depends on
                  your machine's timezone.
                - "exchange": naive timestamps on the exchange's own clock
                  (e.g. America/New_York for BLACKBULL:XAUUSD). Matches the
                  legacy behaviour, but is now deterministic.
                - any IANA timezone name, e.g. "America/New_York",
                  "Africa/Cairo", "Asia/Riyadh": the index is returned in that
                  timezone (timezone-aware).
            align_daily_to_trading_day (bool, optional): only affects
                Interval.in_daily. Daily bars are opened when the session starts
                (e.g. 22:00 UTC for gold) and close the next calendar day, but
                TradingView labels them with the open date -- which makes
                "today's" bar look like it has yesterday's date. When True
                (default), a daily bar opening at/after 12:00 local time is
                dated one day forward so every bar is dated by the trading day
                it represents. Set False to keep TradingView's raw open-date
                labels.

        Returns:
            pd.Dataframe: dataframe with sohlcv as columns, indexed by a
            datetime index that is timezone-aware (except timezone="exchange")
        """
        # Normalize open_interest parameter - accept various forms for flexibility
        _include_oi = open_interest
        if include_oi is not None and isinstance(include_oi, bool):
            _include_oi = include_oi
        if include_open_interest is not None and isinstance(include_open_interest, bool):
            _include_oi = include_open_interest
        if oi is not None and isinstance(oi, bool):
            _include_oi = oi
        # Also check for legacy names
        for k in ('pool', 'Pool', 'POOL', 'openInterest', 'OpenInterest'):
            if k in kwargs:
                v = kwargs.get(k)
                if isinstance(v, bool):
                    _include_oi = v
                    break
                elif v is not None:
                    try:
                        if isinstance(v, str):
                            _include_oi = v.strip().lower() in ('1', 'true', 'yes', 'y', 'on')
                        else:
                            _include_oi = bool(v)
                        break
                    except Exception:
                        pass

        if not isinstance(_include_oi, bool):
            _include_oi = False

        # Validate before touching the network so a bad timezone fails fast.
        if timezone != "exchange":
            try:
                zoneinfo.ZoneInfo(timezone)
            except Exception:
                raise ValueError(
                    f"Invalid timezone {timezone!r}. Use 'exchange', 'UTC' or an "
                    "IANA timezone name such as 'America/New_York', 'Africa/Cairo', "
                    "'Asia/Riyadh'."
                ) from None

        symbol_formatted = self.__format_symbol(
            symbol=symbol, exchange=exchange, contract=fut_contract
        )

        interval_value = interval.value

        self.__create_connection()

        self.__send_message("set_auth_token", [self.token])
        self.__send_message("chart_create_session", [self.chart_session, ""])
        self.__send_message("quote_create_session", [self.session])
        self.__send_message(
            "quote_set_fields",
            [
                self.session,
                "ch",
                "chp",
                "current_session",
                "description",
                "local_description",
                "language",
                "exchange",
                "fractional",
                "is_tradable",
                "lp",
                "lp_time",
                "minmov",
                "minmove2",
                "original_name",
                "pricescale",
                "pro_name",
                "short_name",
                "type",
                "update_mode",
                "volume",
                "currency_code",
                "rchp",
                "rtc",
            ],
        )

        self.__send_message(
            "quote_add_symbols", [self.session, symbol_formatted,
                                  {"flags": ["force_permission"]}]
        )
        self.__send_message("quote_fast_symbols", [self.session, symbol_formatted])

        self.__send_message(
            "resolve_symbol",
            [
                self.chart_session,
                "symbol_1",
                _build_resolve_payload(symbol_formatted, extended_session),
            ],
        )
        self.__send_message(
            "create_series",
            [self.chart_session, "s1", "s1", "symbol_1", interval_value, n_bars],
        )
        # Let TradingView chart the requested timezone (or the exchange clock).
        self.__send_message("switch_timezone", [self.chart_session, timezone])

        raw_data = ""

        logger.debug(f"getting data for {symbol_formatted}...")
        while True:
            try:
                result = self.ws.recv()
                raw_data = raw_data + result + "\n"
            except Exception as e:
                logger.error(e)
                break

            if "series_completed" in result:
                break

        df = self.__create_df(
            raw_data,
            symbol_formatted,
            timezone=timezone,
            interval=interval,
            align_daily_to_trading_day=align_daily_to_trading_day,
            exchange_tz=self.__extract_exchange_timezone(raw_data),
        )
        if df is None:
            return df
        try:
            if _include_oi and fut_contract is not None:
                try:
                    oi_df = None
                    sym_base = symbol
                    exch_base = exchange
                    oi_symbol_candidates = []
                    if isinstance(sym_base, str):
                        # Accept both "CL" and "NYMEX:CL1!" and always build
                        # candidates from the bare ticker.
                        ticker = sym_base.rsplit(":", 1)[-1]
                        ticker = re.sub(r"\d+!$", "", ticker)
                        if fut_contract and isinstance(fut_contract, int):
                            oi_symbol_candidates.append(f"{ticker}{fut_contract}!_OI")
                            oi_symbol_candidates.append(f"{ticker}_OI")
                        else:
                            oi_symbol_candidates.append(f"{ticker}_OI")
                    # OI is published daily.  Ask for enough daily bars to
                    # cover the whole requested range (weekly/monthly bars
                    # span many days).
                    try:
                        _span_days = max((df.index[-1] - df.index[0]).days, 0)
                    except Exception:
                        _span_days = 0
                    oi_n_bars = min(5000, max(int(n_bars), _span_days + 10))
                    for oi_sym_cand in oi_symbol_candidates:
                        try:
                            oi_symbol_formatted = self.__format_symbol(oi_sym_cand, exch_base, contract=None)
                        except Exception:
                            continue
                        try:
                            # Use a fresh connection for OI to avoid conflicts
                            import websocket
                            from websocket import create_connection
                            ws_oi = create_connection("wss://data.tradingview.com/socket.io/websocket", headers=TvDatafeed._TvDatafeed__ws_headers, timeout=TvDatafeed._TvDatafeed__ws_timeout)
                            def send_oi(func, args):
                                msg = self.__prepend_header(self.__construct_message(func, args))
                                ws_oi.send(msg)
                            oi_chart = self.__generate_chart_session()
                            oi_quote = self.__generate_session()
                            send_oi("set_auth_token", [self.token])
                            send_oi("chart_create_session", [oi_chart, ""])
                            send_oi("quote_create_session", [oi_quote])
                            send_oi("quote_add_symbols", [oi_quote, oi_symbol_formatted, {"flags": ["force_permission"]}])
                            send_oi("quote_fast_symbols", [oi_quote, oi_symbol_formatted])
                            send_oi(
                                "resolve_symbol",
                                [oi_chart, "symbol_oi", _build_resolve_payload(oi_symbol_formatted, extended_session)],
                            )
                            # The _OI symbol only supports a daily resolution;
                            # intraday requests fail with series_error.
                            oi_interval = "1D"
                            send_oi("create_series", [oi_chart, "s_oi", "s_oi", "symbol_oi", oi_interval, oi_n_bars])
                            send_oi("switch_timezone", [oi_chart, timezone])
                            raw_oi = ""
                            while True:
                                try:
                                    result = ws_oi.recv()
                                    raw_oi += result + "\n"
                                except Exception:
                                    break
                                if "series_completed" in result:
                                    break
                                # Don't wait for the socket timeout when the
                                # candidate symbol/resolution is invalid.
                                if "series_error" in result or "symbol_error" in result:
                                    break
                            try:
                                ws_oi.close()
                            except Exception:
                                pass
                            if '"s":[' in raw_oi:
                                # Keep the raw session-open timestamps: the
                                # mapper works with session boundaries and
                                # also supports intraday output.
                                oi_df = self.__create_df(
                                    raw_oi,
                                    oi_symbol_formatted,
                                    timezone=timezone,
                                    interval=Interval.in_daily,
                                    align_daily_to_trading_day=False,
                                    exchange_tz=self.__extract_exchange_timezone(raw_oi),
                                )
                                if oi_df is not None and len(oi_df) > 0:
                                    break
                        except Exception:
                            continue
                    if oi_df is not None and len(oi_df) > 0:
                        try:
                            aligned_daily = bool(
                                df.attrs.get("aligned_to_trading_day", False)
                            )
                            attrs = dict(df.attrs)
                            df = df.copy()
                            df.attrs.update(attrs)
                            df['open_interest'] = _map_open_interest_to_bars(
                                df,
                                oi_df,
                                interval=interval,
                                aligned_to_trading_day=aligned_daily,
                            )
                        except Exception as exc:
                            logger.warning(
                                "failed to map open interest for %s: %s",
                                symbol_formatted,
                                exc,
                            )
                except Exception as exc:
                    logger.warning(
                        "failed to fetch open interest for %s: %s",
                        symbol_formatted,
                        exc,
                    )
                if 'open_interest' not in df.columns:
                    # No historical OI available.  Never broadcast the
                    # current scanner value across every row: that would
                    # silently invent data.
                    logger.warning(
                        "open interest history is not available for %s; "
                        "the open_interest column will contain NaN",
                        symbol_formatted,
                    )
                    df = df.copy()
                    df['open_interest'] = float('nan')
                elif df['open_interest'].isna().all():
                    logger.warning(
                        "open interest history is empty for %s; "
                        "the open_interest column contains NaN",
                        symbol_formatted,
                    )
        except Exception:
            pass
        return df

    def search_symbol(
        self,
        text: str,
        exchange: str = "",
        type: str = None,
        country: str = None,
        limit: int = 50,
        lang: str = "en",
        timeout: float = 10,
        extra: dict = None,
    ):
        """Search TradingView symbols (no login required).

        Thin wrapper around :func:`tvDatafeed.search.search_symbol` that
        reuses this client's ``proxies``.  See the module level function
        for the full description of the arguments and the return value.

        Args:
            text: symbol name or description.
            exchange: optional exchange id, e.g. ``"BLACKBULL"``.
            type: optional asset type
                (``"commodity"``, ``"bond"``, ``"forex"``, ``"stock"``...).
            country: optional ISO-3166 alpha-2 code or country name
                (``"SA"``, ``"US"``...).
            limit: maximum number of records (1..50).
            lang: TradingView interface language.
            timeout: per-request timeout in seconds.
            extra: optional extra query parameters forwarded verbatim.

        Returns:
            list[dict]: normalised records (``[]`` on network failure).

        Raises:
            ValueError: if any argument is invalid.
        """
        return _module_search_symbol(
            text,
            exchange=exchange,
            type=type,
            country=country,
            limit=limit,
            lang=lang,
            timeout=timeout,
            proxies=getattr(self, "proxies", None),
            extra=extra,
        )

    def search_futures(
        self,
        text: str = "",
        exchange: str = None,
        category: str = None,
        product: str = None,
        country: str = None,
        limit: int = 50,
        continuous_only: bool = True,
        lang: str = "en",
        timeout: float = 10,
    ):
        """Search **futures contracts** by country, exchange and category.

        Thin wrapper around :func:`tvDatafeed.futures.search_futures` that
        reuses this client's ``proxies``.  See the module level function for
        the full description of the arguments and the return value.

        Args:
            text: optional search text (symbol or description).
            exchange: optional exchange id, e.g. ``"NYMEX"``.
            category: optional futures category
                (``"energy"``, ``"metals"``, ``"weather"``...).
            product: optional sub-category path, e.g.
                ``"Commodity/Metals/Precious/Gold"``.
            country: optional ISO-3166 alpha-2 code or country name.
            limit: maximum number of records (1..50).
            continuous_only: browse continuous contracts only.
            lang: TradingView interface language.
            timeout: per-request timeout in seconds.

        Returns:
            list[dict]: normalised records (``[]`` on network failure).

        Raises:
            ValueError: if any argument is invalid.
        """
        return _module_search_futures(
            text,
            exchange=exchange,
            category=category,
            product=product,
            country=country,
            limit=limit,
            continuous_only=continuous_only,
            lang=lang,
            timeout=timeout,
            proxies=getattr(self, "proxies", None),
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    tv = TvDatafeed()
    print(tv.get_hist("CRUDEOIL", "MCX", fut_contract=1))
    print(tv.get_hist("NIFTY", "NSE", fut_contract=1))
    print(
        tv.get_hist(
            "EICHERMOT",
            "NSE",
            interval=Interval.in_1_hour,
            n_bars=500,
            extended_session=False,
        )
    )


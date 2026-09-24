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

logger = logging.getLogger(__name__)


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
    __search_url = 'https://symbol-search.tradingview.com/symbol_search/?text={}&hl=1&exchange={}&lang=en&type=&domain=production'
    __ws_headers = json.dumps({"Origin": "https://data.tradingview.com"})
    __signin_headers = {'Referer': 'https://www.tradingview.com'}
    __ws_timeout = 5

    def __init__(
        self,
        username: str = None,
        password: str = None,
    ) -> None:
        """Create TvDatafeed object

        Args:
            username (str, optional): tradingview username. Defaults to None.
            password (str, optional): tradingview password. Defaults to None.
        """

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
                response = requests.post(
                    url=self.__sign_in_url, data=data, headers=self.__signin_headers)
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

        symbol = self.__format_symbol(
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
            "quote_add_symbols", [self.session, symbol,
                                  {"flags": ["force_permission"]}]
        )
        self.__send_message("quote_fast_symbols", [self.session, symbol])

        self.__send_message(
            "resolve_symbol",
            [
                self.chart_session,
                "symbol_1",
                '={"symbol":"'
                + symbol
                + '","adjustment":"splits","session":'
                + ('"regular"' if not extended_session else '"extended"')
                + "}",
            ],
        )
        self.__send_message(
            "create_series",
            [self.chart_session, "s1", "s1", "symbol_1", interval_value, n_bars],
        )
        # Let TradingView chart the requested timezone (or the exchange clock).
        self.__send_message("switch_timezone", [self.chart_session, timezone])

        raw_data = ""

        logger.debug(f"getting data for {symbol}...")
        while True:
            try:
                result = self.ws.recv()
                raw_data = raw_data + result + "\n"
            except Exception as e:
                logger.error(e)
                break

            if "series_completed" in result:
                break

        return self.__create_df(
            raw_data,
            symbol,
            timezone=timezone,
            interval=interval,
            align_daily_to_trading_day=align_daily_to_trading_day,
            exchange_tz=self.__extract_exchange_timezone(raw_data),
        )

    def search_symbol(self, text: str, exchange: str = ''):
        url = self.__search_url.format(text, exchange)
        try:
            resp = requests.get(url)

            symbols_list = json.loads(resp.text.replace(
                '</em>', '').replace('<em>', ''))
        except Exception as e:
            logger.error(e)

        return symbols_list


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
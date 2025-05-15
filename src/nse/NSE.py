import json
import pickle
import zlib
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple, Union
from zipfile import ZipFile

HAS_HTTPX = HAS_REQUESTS = False

try:
    from httpx import Client, Cookies, ReadTimeout

    HAS_HTTPX = True
except ModuleNotFoundError:
    pass

try:
    from requests import Session
    from requests.exceptions import ReadTimeout

    HAS_REQUESTS = True
except ModuleNotFoundError:
    pass

from mthrottle import Throttle

throttleConfig = {
    "default": {
        "rps": 3,
    },
}

th = Throttle(throttleConfig, 10)


class NSE:
    """An Unofficial Python API for the NSE India stock exchange.

    Methods will raise
        - ``TimeoutError`` if request takes too long.
        - ``ConnectionError`` if request failed for any reason.

    :param download_folder: A folder/dir to save downloaded files and cookie files
    :type download_folder: pathlib.Path or str
    :param server: A parameter to specify whether the script is being run on a server (like AWS, Azure, Google Cloud etc).
        True if running on a server, False if run locally.
    :type server: bool
    :param timeout: Default 15. Network timeout in seconds
    :type timeout: int
    :raise ValueError: if ``download_folder`` is not a folder/dir
    :raises ImportError: If ``server`` set to True and ``httpx[http2] is not installed or ``server`` set to False and ``requests`` is not installed.
    """

    __version__ = "1.2.3"
    SEGMENT_EQUITY = "equities"
    SEGMENT_SME = "sme"
    SEGMENT_MF = "mf"
    SEGMENT_DEBT = "debt"

    HOLIDAY_CLEARING = "clearing"
    HOLIDAY_TRADING = "trading"

    FNO_BANK = "banknifty"
    FNO_NIFTY = "nifty"
    FNO_FINNIFTY = "finnifty"
    FNO_IT = "niftyit"

    __optionIndex = ("banknifty", "nifty", "finnifty", "niftyit")
    base_url = "https://www.nseindia.com/api"
    archive_url = "https://nsearchives.nseindia.com"

    def __init__(
        self,
        download_folder: Union[str, Path],
        server: bool = False,
        timeout: int = 15,
    ):
        """Initialise NSE"""

        uAgent = "Mozilla/5.0 (Windows NT 10.0; rv:109.0) Gecko/20100101 Firefox/118.0"

        headers = {
            "User-Agent": uAgent,
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Referer": "https://www.nseindia.com/get-quotes/equity?symbol=HDFCBANK",
        }

        self.dir = NSE.__getPath(download_folder, isFolder=True)
        self.server = server
        self.timeout = timeout

        if server:
            if not HAS_HTTPX:
                raise ImportError(
                    "The httpx module with HTTP/2 support is required to run NSE on server. Run `pip install httpx[http2]"
                )

            self.cookie_path = self.dir / "nse_cookies_httpx.pkl"
            self.__session = Client(http2=True)
            self.ReadTimeout = ReadTimeout
            self.Cookies = Cookies
        else:
            if not HAS_REQUESTS:
                raise ImportError(
                    "Missing requests module. Run `pip install requests`. If running NSE on server, set `server=True`"
                )

            self.cookie_path = self.dir / "nse_cookies_requests.pkl"
            self.__session = Session()
            self.ReadTimeout = ReadTimeout

        self.__session.headers.update(headers)
        self.__session.cookies.update(self.__getCookies())

    def __setCookies(self):
        r = self.__req("https://www.nseindia.com/option-chain")

        cookies = r.cookies

        if self.server:
            # cookies is an https.Cookies object which isn't directly picklable
            self.cookie_path.write_bytes(pickle.dumps(dict(cookies)))
        else:  # cookies is a RequestsCookiesJar object which is directly picklable
            self.cookie_path.write_bytes(pickle.dumps(cookies))

        return cookies

    def __getCookies(self):

        if self.cookie_path.exists():
            if self.server:
                # Expose the cookie jar object using .jar method.
                cookies = self.Cookies(
                    pickle.loads(self.cookie_path.read_bytes())
                ).jar
            else:
                cookies = pickle.loads(self.cookie_path.read_bytes())

            if NSE.__hasCookiesExpired(cookies):
                cookies = self.__setCookies()

            return cookies

        return self.__setCookies()

    @staticmethod
    def __hasCookiesExpired(cookies) -> bool:
        for cookie in cookies:
            if cookie.is_expired():
                return True
        return False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.__session.close()
        self.cookie_path.unlink(missing_ok=True)

        return False

    @staticmethod
    def __getPath(path: Union[str, Path], isFolder: bool = False):
        path = path if isinstance(path, Path) else Path(path)

        if isFolder:
            if path.is_file():
                raise ValueError(f"{path}: must be a folder")

            if not path.exists():
                path.mkdir(parents=True)

        return path

    @staticmethod
    def __unzip(file: Path, folder: Path):
        if file.suffix == ".zip":
            with ZipFile(file) as zip:
                filepath = zip.extract(member=zip.namelist()[0], path=folder)
        elif file.suffix == ".gz":
            with open(file, "rb") as f_in:
                with open(file.stem, "wb") as f_out:
                    f_out.write(zlib.decompress(f_in.read(), wbits=31))

            filepath = file.stem
        else:
            raise ValueError("Unknown file format")

        file.unlink()
        return Path(filepath)

    def __download(self, url: str, folder: Path):
        """Download a large file in chunks from the given url.
        Returns pathlib.Path object of the downloaded file"""

        fname = folder / url.split("/")[-1]

        th.check()

        if self.server:
            with self.__session.stream(
                "GET", url=url, timeout=self.timeout
            ) as r:

                contentType = r.headers.get("content-type")

                if contentType and "text/html" in contentType:
                    raise RuntimeError(
                        "NSE file is unavailable or not yet updated."
                    )

                with fname.open(mode="wb") as f:
                    for chunk in r.iter_bytes(chunk_size=1000000):
                        f.write(chunk)
        else:
            with self.__session.get(
                url, stream=True, timeout=self.timeout
            ) as r:

                contentType = r.headers.get("content-type")

                if contentType and "text/html" in contentType:
                    raise RuntimeError(
                        "NSE file is unavailable or not yet updated."
                    )

                with fname.open(mode="wb") as f:
                    for chunk in r.iter_content(chunk_size=1000000):
                        f.write(chunk)

        return fname

    def __req(self, url, params=None):
        """Make a http request"""

        th.check()

        try:
            r = self.__session.get(url, params=params, timeout=self.timeout)
        except self.ReadTimeout as e:
            raise TimeoutError(repr(e))

        if not 200 <= r.status_code < 300:
            raise ConnectionError(f"{url} {r.status_code}: {r.reason}")

        return r

    @staticmethod
    def __split_date_range(
        from_date: date, to_date: date, max_chunk_size: int = 365
    ) -> List[Tuple[date, date]]:
        """Splits a date range into non-overlapping chunks with each chunk having size at specified by
        the max_chunk_size parameter

        :param from_date: The starting date of the range
        :type from_date: datetime.date
        :param to_date: The ending date of the range
        :type to_date: datetime.date
        :param max_chunk_size: The max size of each chunk into which the range is split
        :type max_chunk_size: int
        :raise ValueError: if ``from_date`` is greater than ``to_date``
        :return: A sorted list of tuples. Each element of the list is a range (`start_date`, `end_date`)
        :rtype: List[Tuple[datetime.date, datetime.date]]
        """

        chunks = []
        current_start = from_date

        while current_start <= to_date:
            # Calculate the end of the current chunk.
            # We use max_size - 1 because the range is inclusive.
            current_end = current_start + timedelta(days=max_chunk_size - 1)

            # Don't go past the final date.
            if current_end > to_date:
                current_end = to_date

            chunks.append((current_start, current_end))

            # Start next chunk the day after the current end.
            current_start = current_end + timedelta(days=1)

        return chunks

    def exit(self):
        """Close the ``requests`` session.

        *Use at the end of script or when class is no longer required.*

        *Not required when using the ``with`` statement.*"""

        self.__session.close()
        self.cookie_path.unlink(missing_ok=True)

    def status(self) -> List[Dict]:
        """Returns market status

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/status.json>`__

        :return: Market status of all NSE market segments
        :rtype: list[dict]
        """

        return self.__req(f"{self.base_url}/marketStatus").json()["marketState"]

    def equityBhavcopy(
        self, date: datetime, folder: Union[str, Path, None] = None
    ) -> Path:
        """Download the daily Equity bhavcopy report for specified ``date``
        and return the saved filepath.

        :param date: Date of bhavcopy to download
        :type date: datetime.datetime
        :param folder: Optional folder/dir path to save file. If not specified, use ``download_folder`` specified during class initializataion.
        :type folder: pathlib.Path or str
        :raise ValueError: if ``folder`` is not a folder/dir.
        :raise FileNotFoundError: if download failed or file corrupted
        :raise RuntimeError: if report unavailable or not yet updated.
        :return: Path to saved file
        :rtype: pathlib.Path
        """

        folder = NSE.__getPath(folder, isFolder=True) if folder else self.dir

        url = "{}/content/cm/BhavCopy_NSE_CM_0_0_0_{}_F_0000.csv.zip".format(
            self.archive_url,
            date.strftime("%Y%m%d"),
        )

        file = self.__download(url, folder)

        if not file.is_file():
            file.unlink()
            raise FileNotFoundError(f"Failed to download file: {file.name}")

        return NSE.__unzip(file, file.parent)

    def deliveryBhavcopy(
        self, date: datetime, folder: Union[str, Path, None] = None
    ) -> Path:
        """Download the daily Equity delivery report for specified ``date`` and return saved file path.

        :param date: Date of delivery bhavcopy to download
        :type date: datetime.datetime
        :param folder: Optional folder/dir path to save file. If not specified, use ``download_folder`` specified during class initializataion.
        :type folder: pathlib.Path or str
        :raise ValueError: if ``folder`` is not a folder/dir
        :raise FileNotFoundError: if download failed or file corrupted
        :raise RuntimeError: if report unavailable or not yet updated.
        :return: Path to saved file
        :rtype: pathlib.Path"""

        folder = NSE.__getPath(folder, isFolder=True) if folder else self.dir

        url = "{}/products/content/sec_bhavdata_full_{}.csv".format(
            self.archive_url, date.strftime("%d%m%Y")
        )

        file = self.__download(url, folder)

        if not file.is_file():
            file.unlink()
            raise FileNotFoundError(f"Failed to download file: {file.name}")

        return file

    def indicesBhavcopy(
        self, date: datetime, folder: Union[str, Path, None] = None
    ) -> Path:
        """Download the daily Equity Indices report for specified ``date``
        and return the saved file path.

        :param date: Date of Indices bhavcopy to download
        :type date: datetime.datetime
        :param folder: Optional folder/dir path to save file. If not specified, use ``download_folder`` specified during class initializataion.
        :type folder: pathlib.Path or str
        :raise ValueError: if ``folder`` is not a folder/dir
        :raise FileNotFoundError: if download failed or file corrupted
        :raise RuntimeError: if report unavailable or not yet updated.
        :return: Path to saved file
        :rtype: pathlib.Path"""

        folder = NSE.__getPath(folder, isFolder=True) if folder else self.dir

        url = f"{self.archive_url}/content/indices/ind_close_all_{date:%d%m%Y}.csv"

        file = self.__download(url, folder)

        if not file.is_file():
            file.unlink()
            raise FileNotFoundError(f"Failed to download file: {file.name}")

        return file

    def fnoBhavcopy(
        self, date: datetime, folder: Union[str, Path, None] = None
    ) -> Path:
        """Download the daily Udiff format FnO bhavcopy report for specified ``date``
        and return the saved file path.

        :param date: Date of FnO bhavcopy to download
        :type date: datetime.datetime
        :param folder: Optional folder path to save file. If not specified, use ``download_folder`` specified during class initializataion.
        :type folder: pathlib.Path or str
        :raise ValueError: if ``folder`` is not a dir/folder
        :raise FileNotFoundError: if download failed or file corrupted
        :raise RuntimeError: if report unavailable or not yet updated.
        :return: Path to saved file
        :rtype: pathlib.Path"""

        dt_str = date.strftime("%Y%m%d")

        folder = NSE.__getPath(folder, isFolder=True) if folder else self.dir

        url = f"{self.archive_url}/content/fo/BhavCopy_NSE_FO_0_0_0_{dt_str}_F_0000.csv.zip"

        file = self.__download(url, folder)

        if not file.is_file():
            file.unlink()
            raise FileNotFoundError(f"Failed to download file: {file.name}")

        return NSE.__unzip(file, folder=file.parent)

    def priceband_report(
        self, date: datetime, folder: Union[str, Path, None] = None
    ) -> Path:
        """Download the daily priceband report for specified ``date``
        and return the saved file path.

        :param date: Report date to download
        :type date: datetime.datetime
        :param folder: Optional folder path to save file. If not specified, use ``download_folder`` specified during class initializataion.
        :type folder: pathlib.Path or str
        :raise ValueError: if ``folder`` is not a dir/folder
        :raise FileNotFoundError: if download failed or file corrupted
        :raise RuntimeError: if report unavailable or not yet updated.
        :return: Path to saved file
        :rtype: pathlib.Path"""

        dt_str = date.strftime("%d%m%Y")

        folder = NSE.__getPath(folder, isFolder=True) if folder else self.dir

        url = f"{self.archive_url}/content/equities/sec_list_{dt_str}.csv"

        file = self.__download(url, folder)

        if not file.is_file():
            file.unlink()
            raise FileNotFoundError(f"Failed to download file: {file.name}")

        return file

    def pr_bhavcopy(
        self, date: datetime, folder: Union[str, Path, None] = None
    ) -> Path:
        """Download the daily PR Bhavcopy zip report for specified ``date``
        and return the saved zipfile path.

        The file returned is a zip file containing a collection of various reports.

        It includes a `Readme.txt`, explaining the contents of each file and the file naming format.

        :param date: Report date to download
        :type date: datetime.datetime
        :param folder: Optional folder path to save file. If not specified, use ``download_folder`` specified during class initializataion.
        :type folder: pathlib.Path or str
        :raise ValueError: if ``folder`` is not a dir/folder
        :raise FileNotFoundError: if download failed or file corrupted
        :raise RuntimeError: if report unavailable or not yet updated.
        :return: Path to saved zip file
        :rtype: pathlib.Path
        """

        dt_str = date.strftime("%d%m%y")

        folder = NSE.__getPath(folder, isFolder=True) if folder else self.dir

        url = f"{self.archive_url}/archives/equities/bhavcopy/pr/PR{dt_str}.zip"

        file = self.__download(url, folder)

        if not file.is_file():
            file.unlink()
            raise FileNotFoundError(f"Failed to download file: {file.name}")

        return file

    def cm_mii_security_report(
        self, date: datetime, folder: Union[str, Path, None] = None
    ) -> Path:
        """Download the daily CM MII security file report for specified ``date``
        and return the saved and extracted file path.

        The file returned is a csv file.

        :param date: Report date to download
        :type date: datetime.datetime
        :param folder: Optional folder path to save file. If not specified, use ``download_folder`` specified during class initializataion.
        :type folder: pathlib.Path or str
        :raise ValueError: if ``folder`` is not a dir/folder
        :raise FileNotFoundError: if download failed or file corrupted
        :raise RuntimeError: if report unavailable or not yet updated.
        :return: Path to saved zip file
        :rtype: pathlib.Path
        """

        dt_str = date.strftime("%d%m%Y")

        folder = NSE.__getPath(folder, isFolder=True) if folder else self.dir

        url = f"{self.archive_url}/content/cm/NSE_CM_security_{dt_str}.csv.gz"

        file = self.__download(url, folder)

        if not file.is_file():
            file.unlink()
            raise FileNotFoundError(f"Failed to download file: {file.name}")

        return self.__unzip(file, folder=file.parent)

    def actions(
        self,
        segment: Literal["equities", "sme", "debt", "mf"] = "equities",
        symbol: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> List[Dict]:
        """Get all forthcoming corporate actions.

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/actions.json>`__

        If ``symbol`` is specified, only actions for the ``symbol`` is returned.

        If ``from_data`` and ``to_date`` are specified, actions within the date range are returned

        :param segment: One of ``equities``, ``sme``, ``debt`` or ``mf``. Default ``equities``
        :type segment: str
        :param symbol: Optional Stock symbol
        :type symbol: str or None
        :param from_date: Optional from date
        :type from_date: datetime.datetime
        :param to_date: Optional to date
        :type to_date: datetime.datetime
        :raise ValueError: if ``from_date`` is greater than ``to_date``
        :return: A list of corporate actions
        :rtype: list[dict]"""

        fmt = "%d-%m-%Y"

        params = {
            "index": segment,
        }

        if symbol:
            params["symbol"] = symbol

        if from_date and to_date:
            if from_date > to_date:
                raise ValueError("'from_date' cannot be greater than 'to_date'")

            params.update(
                {
                    "from_date": from_date.strftime(fmt),
                    "to_date": to_date.strftime(fmt),
                }
            )

        url = f"{self.base_url}/corporates-corporateActions"

        return self.__req(url, params=params).json()

    def announcements(
        self,
        index: Literal[
            "equities", "sme", "debt", "mf", "invitsreits"
        ] = "equities",
        symbol: Optional[str] = None,
        fno=False,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> List[Dict]:
        """Get all corporate announcements for current date.

        If symbol is specified, only announcements for the symbol is returned.

        If from_date and to_date are specified, announcements within the date range are returned

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/announcements.json>`__

        :param index: One of `equities`, `sme`, `debt` or `mf`. Default ``equities``
        :type index: str
        :param symbol: Optional Stock symbol
        :type symbol: str or None
        :param fno: Only FnO stocks
        :type fno: bool
        :param from_date: Optional from date
        :type from_date: datetime.datetime
        :param to_date: Optional to date
        :type to_date: datetime.datetime
        :raise ValueError: if ``from_date`` is greater than ``to_date``
        :return: A list of corporate actions
        :rtype: list[dict]"""

        fmt = "%d-%m-%Y"

        params: Dict[str, Any] = {"index": index}

        if symbol:
            params["symbol"] = symbol

        if fno:
            params["fo_sec"] = True

        if from_date and to_date:
            if from_date > to_date:
                raise ValueError("'from_date' cannot be greater than 'to_date'")

            params.update(
                {
                    "from_date": from_date.strftime(fmt),
                    "to_date": to_date.strftime(fmt),
                }
            )

        url = f"{self.base_url}/corporate-announcements"

        return self.__req(url, params=params).json()

    def boardMeetings(
        self,
        index: Literal["equities", "sme"] = "equities",
        symbol: Optional[str] = None,
        fno: bool = False,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> List[Dict]:
        """Get all forthcoming board meetings.

        If symbol is specified, only board meetings for the symbol is returned.

        If ``from_date`` and ``to_date`` are specified, board meetings within the date range are returned

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/boardMeetings.json>`__

        :param index: One of ``equities`` or ``sme``. Default ``equities``
        :type index: str
        :param symbol: Optional Stock symbol
        :type symbol: str or None
        :param fno: Only FnO stocks
        :type fno: bool
        :param from_date: Optional from date
        :type from_date: datetime.datetime
        :param to_date: Optional to date
        :type to_date: datetime.datetime
        :raise ValueError: if ``from_date`` is greater than ``to_date``
        :return: A list of corporate board meetings
        :rtype: list[dict]"""

        fmt = "%d-%m-%Y"

        params: Dict[str, Any] = {"index": index}

        if symbol:
            params["symbol"] = symbol

        if fno:
            params["fo_sec"] = True

        if from_date and to_date:
            if from_date > to_date:
                raise ValueError("'from_date' cannot be greater than 'to_date'")

            params.update(
                {
                    "from_date": from_date.strftime(fmt),
                    "to_date": to_date.strftime(fmt),
                }
            )

        url = f"{self.base_url}/corporate-board-meetings"

        return self.__req(url, params=params).json()

    def equityMetaInfo(self, symbol) -> Dict:
        """Meta info for equity symbols.

        Provides useful info like stock name, code, industry, ISIN code, current status like suspended, delisted etc.

        Also has info if stock is an FnO, ETF or Debt security

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/equityMetaInfo.json>`__

        :param symbol: Equity symbol code
        :type symbol: str
        :return: Stock meta info
        :rtype: dict"""

        url = f"{self.base_url}/equity-meta-info"

        return self.__req(url, params={"symbol": symbol.upper()}).json()

    def quote(
        self,
        symbol,
        type: Literal["equity", "fno"] = "equity",
        section: Optional[Literal["trade_info"]] = None,
    ) -> Dict:
        """Price quotes and other data for equity or derivative symbols

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/quote.json>`__

        For Market cap, delivery data and order book, use pass `section='trade_info'` as keyword argument. See sample response below:

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/quote-trade_info.json>`__

        :param symbol: Equity symbol code
        :type symbol: str
        :param type: One of ``equity`` or ``fno``. Default ``equity``
        :type type: str
        :param section: Optional. If specified must be ``trade_info``
        :raise ValueError: if ``section`` does not equal ``trade_info``
        :return: Price quote and other stock meta info
        :rtype: dict"""

        if type == "equity":
            url = f"{self.base_url}/quote-equity"
        else:
            url = f"{self.base_url}/quote-derivative"

        params = {"symbol": symbol.upper()}

        if section:
            if section != "trade_info":
                raise ValueError("'Section' if specified must be 'trade_info'")

            params["section"] = section

        return self.__req(url, params=params).json()

    def equityQuote(self, symbol) -> Dict[str, Union[str, float]]:
        """A convenience method that extracts date and OCHLV data from ``NSE.quote`` for given stock ``symbol``

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/equityQuote.json>`__

        :param symbol: Equity symbol code
        :type symbol: str
        :return: Date and OCHLV data
        :rtype: dict[str, str or float]"""

        q = self.quote(symbol, type="equity")
        v = self.quote(symbol, type="equity", section="trade_info")

        _open, minmax, close, ltp = map(
            q["priceInfo"].get,
            ("open", "intraDayHighLow", "close", "lastPrice"),
        )

        return {
            "date": q["metadata"]["lastUpdateTime"],
            "open": _open,
            "high": minmax["max"],
            "low": minmax["min"],
            "close": close or ltp,
            "volume": v["securityWiseDP"]["quantityTraded"],
        }

    def gainers(self, data: Dict, count: Optional[int] = None) -> List[Dict]:
        """Top gainers by percent change above zero.

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/gainers.json>`__

        :param data: - Output of one of ``NSE.listSME``, ``NSE.listEquityStocksByIndex``
        :type data: dict
        :param count: Optional. Limit number of result returned
        :type count: int
        :return: List of top gainers
        :rtype: list[dict]"""

        return sorted(
            filter(lambda dct: dct["pChange"] > 0, data["data"]),
            key=lambda dct: dct["pChange"],
            reverse=True,
        )[:count]

    def losers(self, data: Dict, count: Optional[int] = None) -> List[Dict]:
        """Top losers by percent change below zero.

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/losers.json>`__

        :param data: - Output of one of ``NSE.listSME``, ``NSE.listEquityStocksByIndex``
        :type data: dict
        :param count: Optional. Limit number of result returned
        :type count: int
        :return: List of top losers
        :rtype: list[dict]"""

        return sorted(
            filter(lambda dct: dct["pChange"] < 0, data["data"]),
            key=lambda dct: dct["pChange"],
        )[:count]

    def listFnoStocks(self):
        """
        .. deprecated:: 1.0.9
            Removed in version 1.0.9,

        Use `nse.listEquityStocksByIndex(index='SECURITIES IN F&O')`
        """
        pass

    def listEquityStocksByIndex(self, index="NIFTY 50") -> dict:
        """
        List Equity stocks by their Index name. Defaults to `NIFTY 50`

        :ref:`See list of acceptable values for index argument. <listEquityStocksByIndex>`

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/listEquityStocksByIndex.json>`__

        :return: A dictionary. The ``data`` key is a list of all stocks represented by a dictionary with the symbol name and other metadata.
        """
        url = f"{self.base_url}/equity-stockIndices"

        return self.__req(url, params=dict(index=index)).json()

    def listIndices(self) -> dict:
        """List all indices

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/listIndices.json>`__

        :return: A dictionary. The ``data`` key is a list of all Indices represented by a dictionary with the symbol code and other metadata.
        """

        url = f"{self.base_url}/allIndices"

        return self.__req(url).json()

    def listIndexStocks(self, index):
        """
        .. deprecated:: 1.0.9
            Removed in version 1.0.9.

        Use `nse.listEquityStocksByIndex`
        """
        pass

    def listEtf(self) -> dict:
        """List all etf stocks

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/listEtf.json>`__

        :return: A dictionary. The ``data`` key is a list of all ETF's represented by a dictionary with the symbol code and other metadata.
        """

        return self.__req(f"{self.base_url}/etf").json()

    def listSme(self) -> dict:
        """List all sme stocks

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/listSme.json>`__

        :return: A dictionary. The ``data`` key is a list of all SME's represented by a dictionary with the symbol code and other metadata.
        """

        return self.__req(f"{self.base_url}/live-analysis-emerge").json()

    def listSgb(self) -> dict:
        """List all sovereign gold bonds

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/listSgb.json>`__

        :return: A dictionary. The ``data`` key is a list of all SGB's represented by a dictionary with the symbol code and other metadata.
        """

        return self.__req(f"{self.base_url}/sovereign-gold-bonds").json()

    def listCurrentIPO(self) -> List[Dict]:
        """List current IPOs

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/listCurrentIPO.json>`__

        :return: List of Dict containing current IPOs
        :rtype: List[Dict]
        """

        return self.__req(f"{self.base_url}/ipo-current-issue").json()

    def listUpcomingIPO(self) -> List[Dict]:
        """List upcoming IPOs

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/listUpcomingIPO.json>`__

        :return: List of Dict containing upcoming IPOs
        :rtype: List[Dict]
        """

        return self.__req(
            f"{self.base_url}/all-upcoming-issues?category=ipo"
        ).json()

    def listPastIPO(
        self,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> List[Dict]:
        """List past IPOs

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/listPastIPO.json>`__

        :param from_date: Optional defaults to 90 days from to_date
        :type from_date: datetime.datetime
        :param to_date: Optional defaults to current date
        :type to_date: datetime.datetime
        :raise ValueError: if `to_date` is less than `from_date`
        :return: List of Dict containing past IPOs
        :rtype: List[Dict]
        """

        if to_date is None:
            to_date = datetime.now()

        if from_date is None:
            from_date = to_date - timedelta(90)

        if to_date < from_date:
            raise ValueError(
                "Argument `to_date` cannot be less than `from_date`"
            )

        params = dict(
            from_date=from_date.strftime("%d-%m-%Y"),
            to_date=to_date.strftime("%d-%m-%Y"),
        )

        return self.__req(
            f"{self.base_url}/public-past-issues",
            params=params,
        ).json()

    def circulars(
        self,
        subject: Optional[str] = None,
        dept_code: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> dict:
        """
        Return exchange circulars and communications by Department

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/circulars.json>`__

        :param subject: Optional keyword string used to filter circulars based on their subject.
        :type dept_code: str
        :param dept_code: Optional Department code. See table below for options
        :type dept_code: str
        :param from_date: Optional defaults to 7 days from to_date
        :type from_date: datetime.datetime
        :param to_date: Optional defaults to current date
        :type to_date: datetime.datetime
        :raise ValueError: if `to_date` is less than `from_date`

        Below is the list of `dept_code` values and their description

        - CMTR - Capital Market (Equities) Trade
        - COM - Commodity Derivatives
        - CC - Corporate Communications
        - CRM - CRM & Marketing
        - CD - Currency Derivatives
        - DS - Debt Segment
        - SME - Emerge
        - SMEITP - Emerge-ITP
        - FAAC - Finance & Accounts
        - FAO - Futures & Options
        - INSP - Inspection & Compliance
        - LEGL - Legal, ISC & Arbitration
        - CMLS - Listing
        - MA - Market Access
        - MSD - Member Service Department
        - MEMB - Membership
        - MF - Mutual Fund
        - NWPR - New Products
        - NCFM - NSE Academy Limited
        - CMPT - NSE Clearing - Capital Market
        - IPO - Primary Market Segment
        - RDM - Retail Debt Market
        - SLBS - Securities Lending & Borrowing Scheme
        - SURV - Surveillance & Investigation
        - TEL - Systems & Telecom
        - UCIBD - UCI Business Development
        - WDTR - Wholesale Debt Market
        """

        if to_date is None:
            to_date = datetime.now()

        if from_date is None:
            from_date = to_date - timedelta(7)

        if to_date < from_date:
            raise ValueError(
                "Argument `to_date` cannot be less than `from_date`"
            )

        params = dict(
            from_date=from_date.strftime("%d-%m-%Y"),
            to_date=to_date.strftime("%d-%m-%Y"),
        )

        if subject:
            params["sub"] = subject

        if dept_code:
            params["dept"] = dept_code.upper()

        return self.__req(f"{self.base_url}/circulars", params=params).json()

    def blockDeals(self) -> Dict:
        """Block deals

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/blockDeals.json>`__

        :return: Block deals. ``data`` key is a list of all block deal (Empty list if no block deals).
        :rtype: dict"""

        return self.__req(f"{self.base_url}/block-deal").json()

    def fnoLots(self) -> Dict[str, int]:
        """Get the lot size of FnO stocks.

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/fnoLots.json>`__

        :return: A dictionary with symbol code as keys and lot sizes for values
        :rtype: dict[str, int]"""

        url = "https://nsearchives.nseindia.com/content/fo/fo_mktlots.csv"

        res = self.__req(url).content

        dct = {}

        for line in res.strip().split(b"\n"):
            _, sym, _, lot, *_ = line.split(b",")

            try:
                dct[sym.strip().decode()] = int(lot.strip().decode())
            except ValueError:
                continue

        return dct

    def optionChain(
        self,
        symbol: Union[
            Literal["banknifty", "nifty", "finnifty", "niftyit"], str
        ],
    ) -> Dict:
        """Unprocessed option chain from NSE for Index futures or FNO stocks

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/optionChain.json>`__

        :param symbol: FnO stock or index futures code. For Index futures, must be one of ``banknifty``, ``nifty``, ``finnifty``, ``niftyit``
        :type symbol: str
        :return: Option chain for all expiries
        :rtype: dict"""

        if symbol in self.__optionIndex:
            url = f"{self.base_url}/option-chain-indices"
        else:
            url = f"{self.base_url}/option-chain-equities"

        params = {
            "symbol": symbol.upper(),
        }

        data = self.__req(url, params=params).json()

        return data

    @staticmethod
    def maxpain(optionChain: Dict, expiryDate: datetime) -> float:
        """Get the max pain strike price

        :param optionChain: Output of NSE.optionChain
        :type optionChain: dict
        :param expiryDate: Options expiry date
        :type expiryDate: datetime.datetime
        :return: max pain strike price
        :rtype: float"""

        out = {}

        expiryDateStr = expiryDate.strftime("%d-%b-%Y")

        for x in optionChain["records"]["data"]:
            if x["expiryDate"] != expiryDateStr:
                continue

            expiryStrike = x["strikePrice"]
            pain = 0

            for y in optionChain["records"]["data"]:
                if y["expiryDate"] != expiryDateStr:
                    continue

                diff = expiryStrike - y["strikePrice"]

                # strike expiry above strike, loss for CE writers
                if diff > 0 and "CE" in y:
                    pain += -diff * y["CE"]["openInterest"]

                # strike expiry below strike, loss for PE writers
                if diff < 0 and "PE" in y:
                    pain += diff * y["PE"]["openInterest"]

            out[expiryStrike] = pain

        return max(out.keys(), key=(lambda k: out[k]))

    def getFuturesExpiry(
        self, index: Literal["nifty", "banknifty", "finnifty"] = "nifty"
    ) -> List[str]:
        """
        Get current, next and far month expiry as a sorted list
        with order guaranteed.

        Its easy to calculate the last thursday of the month.
        But you need to consider holidays.

        This serves as a lightweight lookup option.

        :param index: One of `nifty`, `banknifty`, `finnifty`. Default `nifty`.
        :type index: str
        :return: Sorted list of current, next and far month expiry
        :rtype: list[str]
        """

        if index == "banknifty":
            idx = "nifty_bank_fut"
        elif index == "finnifty":
            idx = "finnifty_fut"
        else:
            idx = "nse50_fut"

        res: Dict = self.__req(
            f"{self.base_url}/liveEquity-derivatives",
            params={"index": idx},
        ).json()

        data = tuple(i["expiryDate"] for i in res["data"])

        return sorted(data, key=lambda x: datetime.strptime(x, "%d-%b-%Y"))

    def compileOptionChain(
        self,
        symbol: Union[
            str, Literal["banknifty", "nifty", "finnifty", "niftyit"]
        ],
        expiryDate: datetime,
    ) -> Dict[str, Union[str, float, int]]:
        """Filter raw option chain by ``expiryDate`` and calculate various statistics required for analysis. This makes it easy to build an option chain for analysis using a simple loop.

        Statistics include:
            - Max Pain,
            - Strike price with max Call and Put Open Interest,
            - Total Call and Put Open Interest
            - Total PCR ratio
            - PCR for every strike price
            - Every strike price has Last price, Open Interest, Change, Implied Volatility for both Call and Put

        Other included values: At the Money (ATM) strike price, Underlying strike price, Expiry date.

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/compileOptionChain.json>`__

        :param symbol: FnO stock or Index futures symbol code. If Index futures must be one of ``banknifty``, ``nifty``, ``finnifty``, ``niftyit``.
        :type symbol: str
        :param expiryDate: Option chain Expiry date
        :type expiryDate: datetime.datetime
        :return: Option chain filtered by ``expiryDate``
        :rtype: dict[str, str | float | int]"""

        data = self.optionChain(symbol)

        chain = {}
        oc = {}

        expiryDateStr = expiryDate.strftime("%d-%b-%Y")

        oc["expiry"] = expiryDateStr
        oc["timestamp"] = data["records"]["timestamp"]
        strike1 = data["filtered"]["data"][0]["strikePrice"]
        strike2 = data["filtered"]["data"][1]["strikePrice"]
        multiple = strike1 - strike2

        underlying = data["records"]["underlyingValue"]

        oc["underlying"] = underlying
        oc["atm"] = multiple * round(underlying / multiple)

        maxCoi = maxPoi = totalCoi = totalPoi = maxCoiStrike = maxPoiStrike = 0

        dataFields = ("openInterest", "lastPrice", "chg", "impliedVolatility")
        ocFields = ("last", "oi", "chg", "iv")

        for idx in data["records"]["data"]:
            if idx["expiryDate"] != expiryDateStr:
                continue

            strike = str(idx["strikePrice"])

            if strike not in chain:
                chain[strike] = {"pe": {}, "ce": {}}

            poi = coi = 0

            if "PE" in idx:
                poi, last, chg, iv = map(idx["PE"].get, dataFields)

                chain[strike]["pe"].update(
                    {"last": last, "oi": poi, "chg": chg, "iv": iv}
                )

                totalPoi += poi

                if poi > maxPoi:
                    maxPoi = poi
                    maxPoiStrike = int(strike)
            else:
                for f in ocFields:
                    chain[strike]["pe"][f] = 0

            if "CE" in idx:
                coi, last, chg, iv = map(idx["CE"].get, dataFields)

                chain[strike]["ce"].update(
                    {"last": last, "oi": poi, "chg": chg, "iv": iv}
                )

                totalCoi += coi

                if coi > maxCoi:
                    maxCoi = coi
                    maxCoiStrike = int(strike)
            else:
                for f in ocFields:
                    chain[strike]["ce"][f] = 0

            if poi == 0 or coi == 0:
                chain[strike]["pcr"] = None
            else:
                chain[strike]["pcr"] = round(poi / coi, 2)

        oc.update(
            {
                "maxpain": self.maxpain(data, expiryDate),
                "maxCoi": maxCoiStrike,
                "maxPoi": maxPoiStrike,
                "coiTotal": totalCoi,
                "poiTotal": totalPoi,
                "pcr": round(totalPoi / totalCoi, 2),
                "chain": chain,
            }
        )

        return oc

    def advanceDecline(self) -> List[Dict[str, str]]:
        """
        .. deprecated:: 1.0.9
            Removed in v1.0.9 as url no longer active.

        Use nse.listEquityStocksByIndex
        """
        pass

    def holidays(
        self, type: Literal["trading", "clearing"] = "trading"
    ) -> Dict[str, List[Dict]]:
        """NSE holiday list

        ``CM`` key in dictionary stands for Capital markets (Equity Market).

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/holidays.json>`__

        :param type: Default ``trading``. One of ``trading`` or ``clearing``
        :type type: str
        :return: Market holidays for all market segments.
        :rtype: dict[str, list[dict]]"""

        url = f"{self.base_url}/holiday-master"

        data = self.__req(url, params={"type": type}).json()

        return data

    def bulkdeals(self, fromdate: datetime, todate: datetime) -> List[Dict]:
        """Download the bulk deals report for the specified date range and return the data.

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/bulkdeals.json>`__

        :param fromdate: Start date of the bulk deals report to download
        :type fromdate: datetime.datetime
        :param todate: End date of the bulk deals report to download
        :type todate: datetime.datetime
        :raise ValueError: if the date range exceeds one year.
        :raise RuntimeError: if no bulk deals data is available for the specified date range.
        :return: Bulk deals data
        :rtype: dict
        """

        if (todate - fromdate).days > 365:
            raise ValueError("The date range cannot exceed one year.")

        url = "{}/historical/bulk-deals?from={}&to={}".format(
            self.base_url,
            fromdate.strftime("%d-%m-%Y"),
            todate.strftime("%d-%m-%Y"),
        )

        data = self.__req(url).json()

        if not "data" in data or len(data["data"]) < 1:
            raise RuntimeError(
                "No bulk deals data available for the specified date range."
            )

        return data["data"]

    def download_document(
        self, url: str, folder: Union[str, Path, None] = None
    ) -> Path:
        """
        Download the document from the specified URL and return the saved file path.
        If the downloaded file is a zip file, extracts its contents to the specified folder.

        :param url: URL of the document to download e.g. `https://archives.nseindia.com/annual_reports/AR_ULTRACEMCO_2010_2011_08082011052526.zip`
        :type url: str
        :param folder: Folder path to save file. If not specified, uses download_folder from class initialization.
        :type folder: pathlib.Path or str or None

        :raise ValueError: If folder is not a directory
        :raise FileNotFoundError: If download failed or file corrupted
        :raise RuntimeError: If file extraction fails

        :return: Path to saved file (or extracted file if zip)
        :rtype: pathlib.Path
        """
        folder = NSE.__getPath(folder, isFolder=True) if folder else self.dir
        file = self.__download(url, folder)

        if not file.is_file():
            file.unlink()
            raise FileNotFoundError(f"Failed to download file: {file.name}")

        # Check if downloaded file is a zip file
        if file.suffix.lower() == ".zip":
            try:
                return self.__unzip(file, folder)
            except Exception as e:
                file.unlink()
                raise RuntimeError(f"Failed to extract zip file: {str(e)}")

        return file

    def fetch_equity_historical_data(
        self,
        symbol: str,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        series: List[str] = ["EQ"],
    ) -> List[Dict]:
        """
        Downloads the historical daily price and volume data for a specified symbol within a given date range,
        from ``from_date`` to ``to_date``.

        The data is returned as a JSON object, where the primary data is stored as a list of rows (indexed starting at 0).

        Each row is represented as a dict, with column names as keys and their corresponding values.

        The date is stored under the key ``mTIMESTAMP``.

        If the provided symbol is incorrect or invalid, an empty JSON will be returned.

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/fetch_equity_historical_data.json>`__

        :param symbol: The exchange-traded symbol for which the data needs to be downloaded e.g. ``HDFCBANK``, ``SGBAPR28I`` or ``GOLDBEES``
        :type symbol: str
        :param from_date: The starting date from which we fetch the data. If None, the default date is 30 days from ``to_date``.
        :type from_date: datetime.date
        :param to_date: The ending date upto which we fetch the data. If None, today's date is taken by default.
        :type to_date: datetime.date
        :param series: The series for which we need to fetch the data. A list of the series containing elements from the below list

        :raise ValueError: if ``from_date`` is greater than ``to_date``
        :raise TypeError: if ``from_date`` or ``to_date`` is not of type datetime.date

        :return: Data as a list of rows, each row as dictionary with key as column name mapped to the value
        :rtype: List[Dict]

        The list of valid series
            - AE
            - AF
            - BE
            - BL
            - EQ
            - IL
            - RL
            - W3
            - GB
            - GS
        """
        # Simple case
        if not from_date and not to_date and series == ["EQ"]:
            data = self.__req(
                url=f"{self.base_url}/historical/cm/equity",
                params={"symbol": symbol},
            ).json()

            return data["data"][::-1]

        if from_date and not isinstance(from_date, date):
            raise TypeError(
                "Starting date must be an object of type datetime.date"
            )

        if to_date and not isinstance(to_date, date):
            raise TypeError(
                "Ending date must be an object of type datetime.date"
            )

        if not to_date:
            to_date = date.today()

        if not from_date:
            from_date = to_date - timedelta(30)

        if to_date < from_date:
            raise ValueError("The from date must occur before the to date")

        date_chunks = NSE.__split_date_range(from_date, to_date, 100)

        data = []

        for chunk in date_chunks:
            data += reversed(
                self.__req(
                    url=f"{self.base_url}/historical/cm/equity",
                    params={
                        "symbol": symbol,
                        "series": json.dumps(series),
                        "from": chunk[0].strftime("%d-%m-%Y"),
                        "to": chunk[1].strftime("%d-%m-%Y"),
                    },
                ).json()["data"]
            )

        return data

    def fetch_historical_vix_data(
        self,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> List[Dict]:
        """
        Downloads the historical India VIX within a given date range from ``from_date`` to ``to_date``.

        The data is returned as a JSON object, where the primary data is stored as a list of rows (indexed starting at 0).

        Each row is represented as a dict, with column names as keys and their corresponding values.

        The date is stored under the key ``EOD_TIMESTAMP``.

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/fetch_historical_vix_data.json>`__

        :param from_date: The starting date from which we fetch the data. If None, the default date is 30 days from ``to_date``.
        :type from_date: datetime.date
        :param to_date: The ending date upto which we fetch the data. If None, today's date is taken by default.
        :type to_date: datetime.date

        :raise ValueError: if ``from_date`` is greater than ``to_date``
        :raise TypeError: if ``from_date`` or ``to_date`` is not of type datetime.date

        :return: Data as a list of rows, each row as dictionary with key as column name mapped to the value
        :rtype: List[Dict]
        """
        if from_date and not isinstance(from_date, date):
            raise TypeError(
                "Starting date must be an object of type datetime.date"
            )

        if to_date and not isinstance(to_date, date):
            raise TypeError(
                "Ending date must be an object of type datetime.date"
            )

        if not to_date:
            to_date = date.today()

        if not from_date:
            from_date = to_date - timedelta(30)

        if to_date < from_date:
            raise ValueError("The from date must occur before the to date")

        date_chunks = NSE.__split_date_range(from_date, to_date)

        data = []

        for chunk in date_chunks:
            data += self.__req(
                url=f"{self.base_url}/historical/vixhistory",
                params={
                    "from": chunk[0].strftime("%d-%m-%Y"),
                    "to": chunk[1].strftime("%d-%m-%Y"),
                },
            ).json()["data"]

        return data

    def fetch_historical_fno_data(
        self,
        symbol: str,
        instrument: Literal[
            "FUTIDX", "FUTSTK", "OPTIDX", "OPTSTK", "FUTIVX"
        ] = "FUTIDX",
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        expiry: Optional[date] = None,
        option_type: Optional[Literal["CE", "PE"]] = None,
        strike_price: Optional[float] = None,
    ) -> List[dict]:
        """
        Downloads the historical futures and options data within a given date range from ``from_date`` to ``to_date``.

        Reference url: https://www.nseindia.com/report-detail/fo_eq_security

        The data is returned as a list of rows (indexed starting at 0).

        Each row is represented as a dict, with column names as keys and their corresponding values.

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/fetch_historical_fno_data.json>`__

        :param symbol: Symbol name.
        :type symbol: str
        :param instrument: Default ``FUTIDX``. Instrument name can be one of ``FUTIDX``, ``FUTSTK``, ``OPTIDX``, ``OPTSTK``, ``FUTIVX``.
        :type index: str
        :param from_date: Optional. The starting date from which we fetch the data. If None, the default date is 30 days from ``to_date``.
        :type from_date: datetime.date
        :param to_date: Optional. The ending date upto which we fetch the data. If None, today's date is taken by default.
        :type to_date: datetime.date
        :param expiry: Optional. Expiry date of the instrument to filter results.
        :type expiry: datetime.date
        :param option_type: Optional. Filter results by option type. Must be one of ``CE`` or ``PE``
        :type option_type: str
        :param strike_price: Optional. Filter results by option type. Must be one of ``CE`` or ``PE``
        :type strike_price: Optional[float]

        :raise ValueError: if ``from_date`` is greater than ``to_date`` or if ``instrument`` is an Option and ``option_type`` is not specified.
        :raise TypeError: if ``from_date`` or ``to_date`` or ``expiry`` is not of type datetime.date.

        :return: Data as a list of rows, each row as dictionary with key as column name mapped to the value
        :rtype: List[Dict]
        """
        if from_date and not isinstance(from_date, date):
            raise TypeError(
                "Starting date must be an object of type datetime.date"
            )

        if to_date and not isinstance(to_date, date):
            raise TypeError(
                "Ending date must be an object of type datetime.date"
            )

        if not to_date:
            to_date = date.today()

        if not from_date:
            from_date = to_date - timedelta(30)

        if to_date < from_date:
            raise ValueError("The from date must occur before the to date")

        params: Dict[str, Any] = {
            "instrumentType": instrument.upper(),
            "symbol": symbol.upper(),
        }

        if expiry:
            if not isinstance(expiry, date):
                raise TypeError(
                    "`expiry` must be an object of type datetime.date"
                )

            params["expiryDate"] = expiry.strftime("%d-%b-%Y")
            params["year"] = expiry.year

        if instrument in ("OPTIDX", "OPTSTK"):
            if not option_type:
                raise ValueError(
                    "`option_type` param is required for Stock or Index options."
                )
            else:
                params["optionType"] = option_type

            if strike_price:
                params["strikePrice"] = strike_price

        date_chunks = NSE.__split_date_range(from_date, to_date)

        data = []

        for chunk in date_chunks:
            params["from"] = chunk[0].strftime("%d-%m-%Y")
            params["to"] = chunk[1].strftime("%d-%m-%Y")

            data += self.__req(
                url=f"{self.base_url}/historical/foCPV",
                params=params,
            ).json()["data"]

        return data

    def fetch_historical_index_data(
        self,
        index: str,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> Dict[str, List[dict]]:
        """
        Downloads the historical index data within a given date range from ``from_date`` to ``to_date``.

        Reference url: https://www.nseindia.com/reports-indices-historical-index-data

        The data is returned as a dict object with ``price`` and ``turnover`` as keys.
        The values are stored as a list of rows (indexed starting at 0).

        Each row is represented as a dict, with column names as keys and their corresponding values.

        :ref:`See list of acceptable values for index parameter. <fetch_historical_index_data>`

        .. warning::

            While the NSE API returns the entire date range, date values in ``price``
            and ``turnover`` may not be in sync due to ``turnover`` containing additional dates.

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/fetch_historical_index_data.json>`__

        :param index: The name of the Index.
        :type index: str
        :param from_date: The starting date from which we fetch the data. If None, the default date is 30 days from ``to_date``.
        :type from_date: datetime.date
        :param to_date: The ending date upto which we fetch the data. If None, today's date is taken by default.
        :type to_date: datetime.date

        :raise ValueError: if ``from_date`` is greater than ``to_date``
        :raise TypeError: if ``from_date`` or ``to_date`` is not of type datetime.date

        :return: A dictionary with ``price`` and ``turnover`` as keys and the data as a list of rows, each row is dictionary.
        :rtype: Dict[str, List]
        """

        if from_date and not isinstance(from_date, date):
            raise TypeError(
                "Starting date must be an object of type datetime.date"
            )

        if to_date and not isinstance(to_date, date):
            raise TypeError(
                "Ending date must be an object of type datetime.date"
            )

        if not to_date:
            to_date = date.today()

        if not from_date:
            from_date = to_date - timedelta(30)

        if to_date < from_date:
            raise ValueError("The from date must occur before the to date")

        date_chunks = NSE.__split_date_range(from_date, to_date)

        data = dict(price=[], turnover=[])

        for chunk in date_chunks:
            dct = self.__req(
                url=f"{self.base_url}/historical/indicesHistory",
                params={
                    "indexType": index.upper(),
                    "from": chunk[0].strftime("%d-%m-%Y"),
                    "to": chunk[1].strftime("%d-%m-%Y"),
                },
            ).json()["data"]

            data["price"] += dct["indexCloseOnlineRecords"]
            data["turnover"] += dct["indexTurnoverRecords"]

        return data
    
    def fetch_fno_underlying(self) -> Dict[str, List[Dict[str, str]]]:
        """
        Fetches the indices and stocks for which FnO contracts are available to trade
        
        Reference URL: https://www.nseindia.com/market-data/securities-available-for-trading
        
        :return: A dictionary with keys '`IndexList`' and '`UnderlyingList`'. The values are the list of indices and stocks along
        with their names and tickers respectively in alphabetical order for stocks. 
        :rtype: Dict[str, List[Dict[str, str]]]
        """
        url = f"{self.base_url}/underlying-information"
        data = self.__req(url).json()["data"]
        return data

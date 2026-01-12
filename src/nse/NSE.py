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

    __version__ = "2.0.0"
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
    UDIFF_SWITCH_DATE = datetime(2024, 7, 8).date()

    _optionIndex = ("banknifty", "nifty", "finnifty", "niftyit")
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

        self.dir = NSE._getPath(download_folder, isFolder=True)
        self.server = server
        self.timeout = timeout

        if server:
            if not HAS_HTTPX:
                raise ImportError(
                    "The httpx module with HTTP/2 support is required to run NSE on server. Run `pip install httpx[http2]"
                )

            self.cookie_path = self.dir / "nse_cookies_httpx.pkl"
            self._session = Client(http2=True)
            self.ReadTimeout = ReadTimeout
            self.Cookies = Cookies
        else:
            if not HAS_REQUESTS:
                raise ImportError(
                    "Missing requests module. Run `pip install requests`. If running NSE on server, set `server=True`"
                )

            self.cookie_path = self.dir / "nse_cookies_requests.pkl"
            self._session = Session()
            self.ReadTimeout = ReadTimeout

        self._session.headers.update(headers)
        self._session.cookies.update(self._getCookies())

    def _setCookies(self):
        r = self._req("https://www.nseindia.com/option-chain")

        cookies = r.cookies

        if self.server:
            # cookies is an https.Cookies object which isn't directly picklable
            self.cookie_path.write_bytes(pickle.dumps(dict(cookies)))
        else:  # cookies is a RequestsCookiesJar object which is directly picklable
            self.cookie_path.write_bytes(pickle.dumps(cookies))

        return cookies

    def _getCookies(self):
        if self.cookie_path.exists():
            if self.server:
                # Expose the cookie jar object using .jar method.
                cookies = self.Cookies(pickle.loads(self.cookie_path.read_bytes())).jar
            else:
                cookies = pickle.loads(self.cookie_path.read_bytes())

            if NSE._hasCookiesExpired(cookies):
                cookies = self._setCookies()

            return cookies

        return self._setCookies()

    @staticmethod
    def _hasCookiesExpired(cookies) -> bool:
        for cookie in cookies:
            if cookie.is_expired():
                return True
        return False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self._session.close()
        self.cookie_path.unlink(missing_ok=True)

        return False

    @staticmethod
    def _getPath(path: Union[str, Path], isFolder: bool = False):
        path = path if isinstance(path, Path) else Path(path)
        path = path.expanduser().resolve()

        if isFolder:
            if path.is_file():
                raise ValueError(f"{path}: must be a folder")

            if not path.exists():
                path.mkdir(parents=True)

        return path

    @staticmethod
    def _unzip(file: Path, folder: Path, extract_files: Optional[List[str]] = None):
        if file.suffix == ".zip":
            with ZipFile(file) as zip:
                if extract_files:
                    zip.extractall(path=folder, members=extract_files)

                    # return the last filepath
                    filepath = folder / extract_files[-1]
                else:
                    filepath = zip.extract(member=zip.namelist()[0], path=folder)

        elif file.suffix == ".gz":
            with (
                open(file, "rb") as f_in,
                open(file.stem, "wb") as f_out,
            ):
                f_out.write(zlib.decompress(f_in.read(), wbits=31))

            filepath = file.stem
        else:
            raise ValueError("Unknown file format")

        file.unlink()
        return Path(filepath)

    def _download(self, url: str, folder: Path):
        """Download a large file in chunks from the given url.
        Returns pathlib.Path object of the downloaded file
        """
        fname = folder / url.split("/")[-1]

        th.check()

        if self.server:
            with self._session.stream("GET", url=url, timeout=self.timeout) as r:
                contentType = r.headers.get("content-type")

                if contentType and "text/html" in contentType:
                    raise RuntimeError("NSE file is unavailable or not yet updated.")

                with fname.open(mode="wb") as f:
                    for chunk in r.iter_bytes(chunk_size=1000000):
                        f.write(chunk)
        else:
            with self._session.get(url, stream=True, timeout=self.timeout) as r:
                contentType = r.headers.get("content-type")

                if contentType and "text/html" in contentType:
                    raise RuntimeError("NSE file is unavailable or not yet updated.")

                with fname.open(mode="wb") as f:
                    for chunk in r.iter_content(chunk_size=1000000):
                        f.write(chunk)

        return fname

    def _req(self, url, params=None):
        """Make a http request"""
        th.check()

        try:
            r = self._session.get(url, params=params, timeout=self.timeout)
        except self.ReadTimeout as e:
            raise TimeoutError(repr(e))

        if not 200 <= r.status_code < 300:
            reason = r.reason if hasattr(r, "reason") else r.reason_phrase

            raise ConnectionError(f"{url} {r.status_code}: {reason}")

        return r

    @staticmethod
    def _split_date_range(
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

        *Not required when using the ``with`` statement.*
        """
        self._session.close()
        self.cookie_path.unlink(missing_ok=True)

    def status(self) -> List[Dict]:
        """Returns market status

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/status.json>`__

        :return: Market status of all NSE market segments
        :rtype: list[dict]
        """
        return self._req(f"{self.base_url}/marketStatus").json()["marketState"]

    def lookup(self, query: str) -> dict:
        """
        Lookup a stock symbol by passing the company name or look up company name by passing the stock symbol.

        Returns a dictionary with the `symbols` key containing a list of dictionary results.
        The first item is usually an exact match assuming the exact company name or full symbol name was searched.

        If the symbols list is empty, no symbols matched the query.

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/lookup.json>`__

        .. code-block:: python

            with NSE("") as nse:
                result = nse.lookup(query="hdfcbank")

                print(result['symbols'][0]['symbol_info']) # company name - HDFC Bank Limited
                print(result['symbols'][0]['symbol']) # stock symbol - HDFCBANK

        :param query:
        :type query: str
        :return: A dictionary of results from the query search.
        :rtype: dict
        """
        return self._req(
            f"{self.base_url}/search/autocomplete",
            params=dict(q=query),
        ).json()

    def equityBhavcopy(
        self, date: datetime, folder: Union[str, Path, None] = None
    ) -> Path:
        """Download the daily Equity bhavcopy report for specified ``date``
        and return the saved filepath.

        If the date is before 8th July 2024, the old bhavcopy will be downloaded i.e. `cm02JAN2023bhav.csv`

        If all other cases, the latest UDIFF bhavcopy format is used .i.e `BhavCopy_NSE_CM_0_0_0_20250102_F_0000.csv`

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
        folder = NSE._getPath(folder, isFolder=True) if folder else self.dir

        if date.date() < self.UDIFF_SWITCH_DATE:
            date_str = date.strftime("%d%b%Y").upper()
            month = date_str[2:5]

            url = f"{self.archive_url}/content/historical/EQUITIES/{date.year}/{month}/cm{date_str}bhav.csv.zip"

        else:
            url = "{}/content/cm/BhavCopy_NSE_CM_0_0_0_{}_F_0000.csv.zip".format(
                self.archive_url,
                date.strftime("%Y%m%d"),
            )

        file = self._download(url, folder)

        if not file.is_file():
            file.unlink()
            raise FileNotFoundError(f"Failed to download file: {file.name}")

        return NSE._unzip(file, file.parent)

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
        :rtype: pathlib.Path
        """
        folder = NSE._getPath(folder, isFolder=True) if folder else self.dir

        url = "{}/products/content/sec_bhavdata_full_{}.csv".format(
            self.archive_url, date.strftime("%d%m%Y")
        )

        file = self._download(url, folder)

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
        :rtype: pathlib.Path
        """
        folder = NSE._getPath(folder, isFolder=True) if folder else self.dir

        url = f"{self.archive_url}/content/indices/ind_close_all_{date:%d%m%Y}.csv"

        file = self._download(url, folder)

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
        :rtype: pathlib.Path
        """
        dt_str = date.strftime("%Y%m%d")

        folder = NSE._getPath(folder, isFolder=True) if folder else self.dir

        url = f"{self.archive_url}/content/fo/BhavCopy_NSE_FO_0_0_0_{dt_str}_F_0000.csv.zip"

        file = self._download(url, folder)

        if not file.is_file():
            file.unlink()
            raise FileNotFoundError(f"Failed to download file: {file.name}")

        return NSE._unzip(file, folder=file.parent)

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
        :rtype: pathlib.Path
        """
        dt_str = date.strftime("%d%m%Y")

        folder = NSE._getPath(folder, isFolder=True) if folder else self.dir

        url = f"{self.archive_url}/content/equities/sec_list_{dt_str}.csv"

        file = self._download(url, folder)

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

        folder = NSE._getPath(folder, isFolder=True) if folder else self.dir

        url = f"{self.archive_url}/archives/equities/bhavcopy/pr/PR{dt_str}.zip"

        file = self._download(url, folder)

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

        folder = NSE._getPath(folder, isFolder=True) if folder else self.dir

        url = f"{self.archive_url}/content/cm/NSE_CM_security_{dt_str}.csv.gz"

        file = self._download(url, folder)

        if not file.is_file():
            file.unlink()
            raise FileNotFoundError(f"Failed to download file: {file.name}")

        return self._unzip(file, folder=file.parent)

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
        :rtype: list[dict]
        """
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

        return self._req(url, params=params).json()

    def announcements(
        self,
        index: Literal["equities", "sme", "debt", "mf", "invitsreits"] = "equities",
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
        :rtype: list[dict]
        """
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

        return self._req(url, params=params).json()

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
        :rtype: list[dict]
        """
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

        return self._req(url, params=params).json()

    def annual_reports(
        self, symbol: str, segment: Literal["equities", "sme"] = "equities"
    ) -> Dict[str, List[Dict[str, str]]]:
        """
        Returns the dictionary containing the list of annual reports of the symbol for every year.

        Each dictionary within the list contains the link to the annual report in PDF format.

        .. code-block:: python

            with NSE("") as nse:
                annual_reports = nse.annual_reports(symbol="HDFCBANK")

                file = nse.download_document(annual_reports["data"][0]["fileName"])

                print(file) # filepath of downloaded annual report

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/annual_reports.json>`__

        :param symbol: Stock symbol for which annual reports are to be fetched.
        :type symbol: str
        :param segment: One of ``equities`` or ``sme``. Default is ``equities``.
        :type segment: Literal["equities", "sme"]
        :return: A dictionary where keys are years and values are lists of dictionaries with PDF links to annual reports.
        :rtype: dict[str, list[dict[str, str]]]
        """
        return self._req(
            f"{self.base_url}/annual-reports", params=dict(index=segment, symbol=symbol)
        ).json()

    def equityMetaInfo(self, symbol) -> Dict:
        """Meta info for equity symbols.

        Provides useful info like stock name, code, industry, ISIN code, current status like suspended, delisted etc.

        Also has info if stock is an FnO, ETF or Debt security

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/equityMetaInfo.json>`__

        :param symbol: Equity symbol code
        :type symbol: str
        :return: Stock meta info
        :rtype: dict
        """
        url = f"{self.base_url}/equity-meta-info"

        return self._req(url, params={"symbol": symbol.upper()}).json()

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
        :rtype: dict
        """
        if type == "equity":
            url = f"{self.base_url}/quote-equity"
        else:
            url = f"{self.base_url}/quote-derivative"

        params = {"symbol": symbol.upper()}

        if section:
            if section != "trade_info":
                raise ValueError("'Section' if specified must be 'trade_info'")

            params["section"] = section

        return self._req(url, params=params).json()

    def equityQuote(self, symbol) -> Dict[str, Union[str, float]]:
        """A convenience method that extracts date and OCHLV data from ``NSE.quote`` for given stock ``symbol``

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/equityQuote.json>`__

        :param symbol: Equity symbol code
        :type symbol: str
        :return: Date and OCHLV data
        :rtype: dict[str, str or float]
        """
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
        :rtype: list[dict]
        """
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
        :rtype: list[dict]
        """
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

        return self._req(url, params=dict(index=index)).json()

    def listIndices(self) -> dict:
        """List all indices

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/listIndices.json>`__

        :return: A dictionary. The ``data`` key is a list of all Indices represented by a dictionary with the symbol code and other metadata.
        """
        url = f"{self.base_url}/allIndices"

        return self._req(url).json()

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
        return self._req(f"{self.base_url}/etf").json()

    def listSme(self) -> dict:
        """List all sme stocks

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/listSme.json>`__

        :return: A dictionary. The ``data`` key is a list of all SME's represented by a dictionary with the symbol code and other metadata.
        """
        return self._req(f"{self.base_url}/live-analysis-emerge").json()

    def listSgb(self) -> dict:
        """List all sovereign gold bonds

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/listSgb.json>`__

        :return: A dictionary. The ``data`` key is a list of all SGB's represented by a dictionary with the symbol code and other metadata.
        """
        return self._req(f"{self.base_url}/sovereign-gold-bonds").json()

    def listCurrentIPO(self) -> List[Dict]:
        """List current IPOs

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/listCurrentIPO.json>`__

        :return: List of Dict containing current IPOs
        :rtype: List[Dict]
        """
        return self._req(f"{self.base_url}/ipo-current-issue").json()

    def listUpcomingIPO(self) -> List[Dict]:
        """List upcoming IPOs

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/listUpcomingIPO.json>`__

        :return: List of Dict containing upcoming IPOs
        :rtype: List[Dict]
        """
        return self._req(f"{self.base_url}/all-upcoming-issues?category=ipo").json()

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
            raise ValueError("Argument `to_date` cannot be less than `from_date`")

        params = dict(
            from_date=from_date.strftime("%d-%m-%Y"),
            to_date=to_date.strftime("%d-%m-%Y"),
        )

        return self._req(
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
            raise ValueError("Argument `to_date` cannot be less than `from_date`")

        params = dict(
            from_date=from_date.strftime("%d-%m-%Y"),
            to_date=to_date.strftime("%d-%m-%Y"),
        )

        if subject:
            params["sub"] = subject

        if dept_code:
            params["dept"] = dept_code.upper()

        return self._req(f"{self.base_url}/circulars", params=params).json()

    def blockDeals(self) -> Dict:
        """Block deals

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/blockDeals.json>`__

        :return: Block deals. ``data`` key is a list of all block deal (Empty list if no block deals).
        :rtype: dict
        """
        return self._req(f"{self.base_url}/block-deal").json()

    def fnoLots(self) -> Dict[str, int]:
        """Get the lot size of FnO stocks.

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/fnoLots.json>`__

        :return: A dictionary with symbol code as keys and lot sizes for values
        :rtype: dict[str, int]
        """
        url = "https://nsearchives.nseindia.com/content/fo/fo_mktlots.csv"

        res = self._req(url).content

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
        symbol: Union[Literal["banknifty", "nifty", "finnifty", "niftyit"], str],
        expiry_date: Optional[datetime] = None,
    ) -> Dict:
        """
        Fetch the raw (unprocessed) option chain data from NSE for index futures or
        F&O stocks.

        If `expiry_date` is not provided, the function automatically determines the
        nearest valid expiry using the following order:

        1. Reads a locally cached expiry date from `opt-expiry.json` (if available).
        2. Validates the cached expiry against the current date.
        3. If missing or expired, fetches expiry dates from NSE’s
           `option-chain-contract-info` endpoint and selects the first (nearest)
           expiry.
        4. Updates the local cache with the resolved expiry date.

        The final option chain data is fetched from NSE’s `option-chain-v3` endpoint.

        Reference sample response:
        https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/optionChain.json

        :param symbol:
            F&O stock symbol or index futures identifier.
            For index futures, must be one of:
            ``banknifty``, ``nifty``, ``finnifty``, ``niftyit``.
        :type symbol: str

        :param expiry_date:
            Expiry date of the instrument. If ``None``, the nearest valid expiry
            is automatically resolved and cached.
        :type expiry_date: datetime or None

        :return:
            Raw JSON response from NSE containing the option chain for the
            requested symbol and expiry.
        :rtype: Dict

        :raises ValueError:
            - If the NSE response does not contain the ``expiryDates`` field.
            - If NSE returns an empty list of expiry dates.
        """
        symbol_key = symbol.lower()
        params = dict(symbol=symbol.upper())

        if not expiry_date:
            cache = {}
            cache_file = self.dir / "opt-expiry.json"

            if cache_file.exists():
                try:
                    cache = json.loads(cache_file.read_bytes())
                except (json.JSONDecodeError, OSError):
                    cache = {}

            if symbol_key in cache:
                expiry_date = datetime.fromisoformat(cache[symbol_key])

                if date.today() > expiry_date.date():
                    expiry_date = None

            if not expiry_date:
                opt_info = self._req(
                    f"{self.base_url}/option-chain-contract-info", params=params
                ).json()

                if "expiryDates" not in opt_info:
                    raise ValueError(
                        "Missing `expiryDates` field in option chain contract info"
                    )

                if not opt_info["expiryDates"]:
                    raise ValueError("No expiry dates returned from NSE")

                expiry_date = datetime.strptime(opt_info["expiryDates"][0], "%d-%b-%Y")

                cache[symbol_key] = expiry_date.isoformat()

                cache_file.write_text(json.dumps(opt_info))

        url = f"{self.base_url}/option-chain-v3"

        params["type"] = "Indices" if symbol in self._optionIndex else "Equity"

        if expiry_date:
            params["expiry"] = expiry_date.strftime("%d-%b-%Y")

        data = self._req(url, params=params).json()

        return data

    @staticmethod
    def maxpain(optionChain: Dict, expiryDate: datetime) -> float:
        """Get the max pain strike price

        :param optionChain: Output of NSE.optionChain
        :type optionChain: dict
        :param expiryDate: Options expiry date
        :type expiryDate: datetime.datetime
        :return: max pain strike price
        :rtype: float

        Uses prefix sums to pre compute values and avoid nested loops.
        The result in O(n) performance for maxpain calculation.

        See `Prefix sum for details <https://www.geeksforgeeks.org/dsa/prefix-sum-array-implementation-applications-competitive-programming/>`_
        """
        data = optionChain["records"]["data"]
        expiry = expiryDate.strftime("%d-%b-%Y")

        # filter strikes by expiry date and gather strikes and OI into lists
        ce_oi = []
        pe_oi = []
        strikes = []

        for row in data:
            if row["expiryDates"] != expiry:
                continue

            ce_oi.append(row.get("CE", {}).get("openInterest", 0))
            pe_oi.append(row.get("PE", {}).get("openInterest", 0))
            strikes.append(row["strikePrice"])

        n = len(strikes)

        # Use prefix sums or cumulative sums
        # NSE provides strikes in sorted order, so no need to sort them again
        ce_sum = [0] * n
        pe_sum = [0] * n
        ce_val = [0] * n
        pe_val = [0] * n

        # Call loss = (Settlement Price − Strike) × OI
        # can be rewritten as: Call loss = (Settlement Price * OI) - (Strike * OI)
        # We calculate the (Strike * OI) part above as ce_val and pe_val
        # Later we calculate the option value for each settlement price
        for i in range(n):
            # When i = 0, arr[i - 1] is same as arr[-1] which is 0.
            ce_sum[i] = ce_sum[i - 1] + ce_oi[i]
            ce_val[i] = ce_val[i - 1] + ce_oi[i] * strikes[i]

            pe_sum[i] = pe_sum[i - 1] + pe_oi[i]
            pe_val[i] = pe_val[i - 1] + pe_oi[i] * strikes[i]

        min_payout = float("inf")
        max_pain_strike = strikes[0]

        for i, settlement in enumerate(strikes):
            # Call pain for strikes < settlement
            call_pain = settlement * ce_sum[i] - ce_val[i]

            # Put pain: strikes > settlement
            # here pe_oi[-1] is the cumulative sum of all PUT OI values.
            # we need to calculate the difference from last value to current index
            put_pain = (pe_val[-1] - pe_val[i]) - settlement * (pe_sum[-1] - pe_sum[i])

            total_pain = call_pain + put_pain

            if total_pain < min_payout:
                min_payout = total_pain
                max_pain_strike = settlement

        return max_pain_strike

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

        res: Dict = self._req(
            f"{self.base_url}/liveEquity-derivatives",
            params={"index": idx},
        ).json()

        data = tuple(i["expiryDate"] for i in res["data"])

        return sorted(data, key=lambda x: datetime.strptime(x, "%d-%b-%Y"))

    def compileOptionChain(
        self,
        symbol: Union[str, Literal["banknifty", "nifty", "finnifty", "niftyit"]],
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
        :rtype: dict[str, str | float | int]
        """
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

        for idx in data["records"]["data"]:
            if idx["expiryDates"] != expiryDateStr:
                continue

            strike = str(idx["strikePrice"])

            if strike not in chain:
                chain[strike] = dict(pe={}, ce={})

            poi = coi = 0

            if "PE" in idx:
                poi, last, chg, iv = map(idx["PE"].get, dataFields)

                chain[strike]["pe"].update(dict(last=last, oi=poi, chg=chg, iv=iv))

                totalPoi += poi

                if poi > maxPoi:
                    maxPoi = poi
                    maxPoiStrike = int(strike)
            else:
                chain[strike]["pe"] = dict(last=0, oi=0, chg=0, iv=0)

            if "CE" in idx:
                coi, last, chg, iv = map(idx["CE"].get, dataFields)

                chain[strike]["ce"].update(dict(last=last, oi=poi, chg=chg, iv=iv))

                totalCoi += coi

                if coi > maxCoi:
                    maxCoi = coi
                    maxCoiStrike = int(strike)
            else:
                chain[strike]["ce"] = dict(last=0, oi=0, chg=0, iv=0)

            if poi == 0 or coi == 0:
                chain[strike]["pcr"] = None
            else:
                chain[strike]["pcr"] = round(poi / coi, 2)

        oc.update(
            dict(
                maxpain=self.maxpain(data, expiryDate),
                maxCoi=maxCoiStrike,
                maxPoi=maxPoiStrike,
                coiTotal=totalCoi,
                poiTotal=totalPoi,
                pcr=round(totalPoi / totalCoi, 2),
                chain=chain,
            )
        )

        return oc

    def advanceDecline(self):
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
        :rtype: dict[str, list[dict]]
        """
        url = f"{self.base_url}/holiday-master"

        data = self._req(url, params={"type": type}).json()

        return data

    def bulkdeals(
        self,
        option_type: Literal["block_deals", "bulk_deals", "short_selling"],
        fromdate: datetime,
        todate: datetime,
    ) -> List[Dict]:
        """
        Retrieve bulk, block, or short-selling deal data from NSE for a given date range.

        This method downloads historical deal data based on the selected report type.
        The requested date range must be valid and must not exceed one year.

        Sample responses:
            - Bulk deals: https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/bulkdeals-bulk_deals.json
            - Block deals: https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/bulkdeals-block_deals.json
            - Short selling: https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/bulkdeals-short_selling.json

        :param option_type:
            Type of deal report to fetch. Must be one of
            ``"bulk_deals"``, ``"block_deals"``, or ``"short_selling"``.
        :type option_type: Literal["block_deals", "bulk_deals", "short_selling"]

        :param fromdate:
            Start date of the report (inclusive).
        :type fromdate: datetime.datetime

        :param todate:
            End date of the report (inclusive).
        :type todate: datetime.datetime

        :raises ValueError:
            If ``fromdate`` is later than ``todate`` or if the date range exceeds one year.
        :raises RuntimeError:
            If no data is available for the specified date range and report type.

        :return:
            A list of dictionaries containing deal records for the requested report type.
        :rtype: List[Dict]
        """
        if fromdate > todate:
            raise ValueError("fromdate must be earlier than or equal to todate.")

        if (todate - fromdate).days > 365:
            raise ValueError("The date range cannot exceed one year.")

        params = {
            "optionType": option_type,
            "from": fromdate.strftime("%d-%m-%Y"),
            "to": todate.strftime("%d-%m-%Y"),
        }

        url = f"{self.base_url}/historicalOR/bulk-block-short-deals"

        data = self._req(url, params=params).json()

        if "data" not in data or len(data["data"]) < 1:
            raise RuntimeError(
                f"No {option_type} data available from {fromdate:%d-%m-%Y} to {todate:%d-%m-%Y}."
            )

        return data["data"]

    def download_document(
        self,
        url: str,
        folder: Union[str, Path, None] = None,
        extract_files: Optional[List[str]] = None,
    ) -> Path:
        """
        Download the document from the specified URL and return the saved file path.
        If the downloaded file is a zip file, extracts its contents to the specified folder.

        :param url: URL of the document to download e.g. `https://archives.nseindia.com/annual_reports/AR_ULTRACEMCO_2010_2011_08082011052526.zip`
        :type url: str
        :param folder: Folder path to save file. If not specified, uses download_folder from class initialization.
        :type folder: pathlib.Path or str or None
        :param extract_files: A list of filenames to be extracted. If None, the first file in zipfile will be extracted.
        :type extract_files: List[str] or None

        :raise ValueError: If folder is not a directory
        :raise FileNotFoundError: If download failed or file corrupted
        :raise RuntimeError: If file extraction fails

        :return: Path to saved file (or extracted file if zip). If extract_files is specified, the last filepath in the list is returned.
        :rtype: pathlib.Path
        """
        folder = NSE._getPath(folder, isFolder=True) if folder else self.dir
        file = self._download(url, folder)

        if not file.is_file():
            file.unlink()
            raise FileNotFoundError(f"Failed to download file: {file.name}")

        # Check if downloaded file is a zip file
        if file.suffix.lower() == ".zip":
            try:
                return self._unzip(file, folder, extract_files)
            except Exception as e:
                file.unlink()
                raise RuntimeError(f"Failed to extract zip file: {str(e)}")

        return file

    def fetch_equity_historical_data(
        self,
        symbol: str,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        series: Literal[
            "AE", "AF", "BE", "BL", "EQ", "IL", "RL", "W3", "GB", "GS"
        ] = "EQ",
    ) -> List[Dict]:
        """
        Retrieve historical daily price and volume data for an equity symbol from NSE.

        This method fetches historical trade data for the given symbol and series
        between ``from_date`` and ``to_date`` (both inclusive). If no dates are
        provided, data for the last 30 days ending today is returned.

        Data is fetched using NSE’s Next API historical trade data endpoint.

        Reference URL:
            https://www.nseindia.com/get-quote/equity/HDFCBANK/HDFC-Bank-Limited
            (Historical data section)

        The response is returned as a list of rows, where each row is represented
        as a dictionary with column names as keys and their corresponding values.
        The trade date is available under the key ``mTIMESTAMP``.

        Sample response:
            https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/fetch_equity_historical_data.json

        :param symbol:
            Exchange-traded symbol for which historical data is requested
            (e.g. ``HDFCBANK``, ``SGBAPR28I``, ``GOLDBEES``).
        :type symbol: str

        :param from_date:
            Start date of the data range. If ``None``, defaults to 30 days prior
            to ``to_date``.
        :type from_date: datetime.date, optional

        :param to_date:
            End date of the data range. If ``None``, defaults to today’s date.
        :type to_date: datetime.date, optional

        :param series:
            Equity series for which historical data is requested.
            Must be one of the valid NSE equity series values.
        :type series: Literal["AE", "AF", "BE", "BL", "EQ", "IL", "RL", "W3", "GB", "GS"]

        :raises TypeError:
            If ``from_date`` or ``to_date`` is not an instance of ``datetime.date``.
        :raises ValueError:
            If ``from_date`` occurs after ``to_date``.

        :return:
            A list of dictionaries, each representing one day of historical trade data.
            The list is ordered chronologically from oldest to newest.
        :rtype: List[Dict]
        """
        if from_date and not isinstance(from_date, date):
            raise TypeError("Starting date must be an object of type datetime.date")

        if to_date and not isinstance(to_date, date):
            raise TypeError("Ending date must be an object of type datetime.date")

        if not to_date:
            to_date = date.today()

        if not from_date:
            from_date = to_date - timedelta(30)

        if to_date < from_date:
            raise ValueError("The from date must occur before the to date")

        date_chunks = NSE._split_date_range(from_date, to_date, 100)

        data = []

        for chunk in date_chunks:
            data += reversed(
                self._req(
                    url=f"{self.base_url}/NextApi/apiClient/GetQuoteApi",
                    params=dict(
                        functionName="getHistoricalTradeData",
                        symbol=symbol,
                        series=series.upper(),
                        fromDate=chunk[0].strftime("%d-%m-%Y"),
                        toDate=chunk[1].strftime("%d-%m-%Y"),
                    ),
                ).json()
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

        Reference url: https://www.nseindia.com/reports-indices-historical-vix

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
            raise TypeError("Starting date must be an object of type datetime.date")

        if to_date and not isinstance(to_date, date):
            raise TypeError("Ending date must be an object of type datetime.date")

        if not to_date:
            to_date = date.today()

        if not from_date:
            from_date = to_date - timedelta(30)

        if to_date < from_date:
            raise ValueError("The from date must occur before the to date")

        date_chunks = NSE._split_date_range(from_date, to_date)

        data = []

        for chunk in date_chunks:
            data += self._req(
                url=f"{self.base_url}/historicalOR/vixhistory",
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
            raise TypeError("Starting date must be an object of type datetime.date")

        if to_date and not isinstance(to_date, date):
            raise TypeError("Ending date must be an object of type datetime.date")

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
                raise TypeError("`expiry` must be an object of type datetime.date")

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

        date_chunks = NSE._split_date_range(from_date, to_date)

        data = []

        for chunk in date_chunks:
            params["from"] = chunk[0].strftime("%d-%m-%Y")
            params["to"] = chunk[1].strftime("%d-%m-%Y")

            data += self._req(
                url=f"{self.base_url}/historicalOR/foCPV",
                params=params,
            ).json()["data"]

        return data[::-1]

    def fetch_historical_index_data(
        self,
        index: str,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> List[Dict]:
        """
        Retrieve historical index data for a given NSE index within a date range.

        This method downloads historical index data between ``from_date`` and
        ``to_date`` (both inclusive). Data is fetched using NSE’s
        ``/historicalOR/indicesHistory`` endpoint and returned in a flattened,
        row-based format.

        Reference URL:
            https://www.nseindia.com/reports-indices-historical-index-data

        The returned data is a list of dictionaries, where each dictionary represents
        a single trading day. Price and turnover values are merged into the same row
        where available.

        Each row is represented as a dictionary with column names as keys and their
        corresponding values.

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/fetch_historical_index_data.json>`__

        :param index:
            Name of the index for which historical data is requested.
        :type index: str

        :param from_date:
            Start date of the data range. If ``None``, defaults to 30 days prior
            to ``to_date``.
        :type from_date: datetime.date, optional

        :param to_date:
            End date of the data range. If ``None``, defaults to today’s date.
        :type to_date: datetime.date, optional

        :raises TypeError:
            If ``from_date`` or ``to_date`` is not an instance of ``datetime.date``.
        :raises ValueError:
            If ``from_date`` occurs after ``to_date``.

        :return:
            A list of dictionaries, each representing one day of historical index data.
            The list is ordered chronologically from oldest to newest.
        :rtype: List[Dict]
        """
        if from_date and not isinstance(from_date, date):
            raise TypeError("Starting date must be an object of type datetime.date")

        if to_date and not isinstance(to_date, date):
            raise TypeError("Ending date must be an object of type datetime.date")

        if not to_date:
            to_date = date.today()

        if not from_date:
            from_date = to_date - timedelta(30)

        if to_date < from_date:
            raise ValueError("The from date must occur before the to date")

        date_chunks = NSE._split_date_range(from_date, to_date)

        data = []

        for chunk in date_chunks:
            dct = self._req(
                url=f"{self.base_url}/historicalOR/indicesHistory",
                params={
                    "indexType": index.upper(),
                    "from": chunk[0].strftime("%d-%m-%Y"),
                    "to": chunk[1].strftime("%d-%m-%Y"),
                },
            ).json()["data"]

            data += dct

        return data[::-1]

    def fetch_fno_underlying(self) -> Dict[str, List[Dict[str, str]]]:
        """
        Fetches the indices and stocks for which FnO contracts are available to trade

        Reference URL: https://www.nseindia.com/market-data/securities-available-for-trading

        :return: A dictionary with keys '`IndexList`' and '`UnderlyingList`'. The values are the list of indices and stocks along
         with their names and tickers respectively in alphabetical order for stocks.
        :rtype: Dict[str, List[Dict[str, str]]]
        """
        url = f"{self.base_url}/underlying-information"
        data = self._req(url).json()["data"]
        return data

    def fetch_index_names(self) -> Dict[str, List[Tuple[str, str]]]:
        """
        Returns a dict with a list of tuples. Each tuple contains the short index name and full name of the index.

        The full name can be passed as `index` parameter to :meth:`.fetch_historical_index_data`
        """
        return self._req(f"{self.base_url}/index-names").json()

    def fetch_daily_reports_file_metadata(
        self,
        segment: Literal[
            "CM",
            "INDEX",
            "SLBS",
            "SME",
            "FO",
            "COM",
            "CD",
            "NBF",
            "WDM",
            "CBM",
            "TRI-PARTY",
        ] = "CM",
    ) -> Dict:
        """
        Returns file metadata for daily reports.

        The returned dictionary contains info about current day and previous
        day reports.

        Useful for checking if a report is ready and updated.

        :param segment: The market segment to retrieve metadata. Defaults to ``CM``.
        :type segment: Literal["CM", "INDEX", "SLBS", "SME", "FO", "COM", "CD", "NBF", "WDM", "CBM", "TRI-PARTY"]

        :return: A dictionary containing metadata about the daily report files for the specified segment.
        :rtype: Dict
        """
        return self._req(
            f"{self.base_url}/daily-reports", params=dict(key=segment)
        ).json()

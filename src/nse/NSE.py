import logging
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple, TypedDict, Union

from pyrate_limiter import Limiter

from . import utils
from .cookie_store import CookieStore
from .retry import RetryConfig
from .transport import Transport

logger = logging.getLogger(__name__)


class OHLCV(TypedDict):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int


class OptionLeg(TypedDict):
    """A single leg (PE or CE) of an option chain strike row."""

    last: float
    oi: int
    chg: float
    iv: float


class StrikeRow(TypedDict):
    """One strike price row in the compiled option chain."""

    pe: OptionLeg
    ce: OptionLeg
    pcr: Optional[float]


class CompiledOptionChain(TypedDict):
    """Result of :meth:`NSE.compile_option_chain`."""

    expiry: str
    timestamp: str
    underlying: float
    atm: float
    max_pain: float
    max_coi: int
    max_poi: int
    coi_total: int
    poi_total: int
    pcr: Optional[float]
    chain: Dict[str, StrikeRow]


class NSE:
    """An Unofficial Python API for the NSE India stock exchange.

    This class is a thin, high-level wrapper over NSE's public JSON and
    archive endpoints. Each method maps to a specific NSE page or report
    and returns the raw parsed JSON (or a downloaded file path) with minimal
    post-processing, so callers can rely on NSE's own field names.

    All network I/O is delegated to an internal transport layer, which
    applies request throttling (default: 3 requests/second), automatic
    retries with exponential backoff, and cookie management. See
    :class:`Transport` for details.

    The class is usable as a context manager. Using it in a ``with`` block
    is recommended, as it guarantees that session cookies are flushed to
    the cookie store and the underlying HTTP session is closed::

        from nse import NSE

        with NSE(download_folder=".") as nse:
            print(nse.status())

    If you prefer manual lifecycle management, call :meth:`exit` when done.

    .. note::
       A hidden ``.opt-expiry-cache/`` directory is created under
       ``download_folder`` to cache the nearest option expiry per symbol
       for :meth:`option_chain`. It is safe to delete; entries are
       refetched on demand.

    **Shared exceptions**

    Because every method issues its requests through the internal transport,
    the following exceptions may be raised by *any* method. They are not
    repeated in each method's docstring:

    :raises httpx.TimeoutException: The request exceeded the configured
        timeout and all retries were exhausted.
    :raises httpx.ConnectError: A connection to NSE could not be established
        and all retries were exhausted.
    :raises httpx.ReadError: The response body could not be read and all
        retries were exhausted.
    :raises httpx.RemoteProtocolError: The server violated the HTTP protocol.
        The session is transparently restarted and the request retried; this
        exception propagates only if all retries are exhausted.
    :raises RetryableStatusError: NSE returned a retryable status code
        (``429``, ``502``, ``503``, ``504``) and all retries were exhausted.
    :raises httpx.HTTPStatusError: NSE returned any other non-2xx status code.

    Methods that download dated reports may additionally raise
    :class:`NSEFileUnavailableError` on ``404``; this is noted on those
    methods individually.
    """

    __version__ = "4.0.1"
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

    _option_index = ("banknifty", "nifty", "finnifty", "niftyit")
    base_url = "https://www.nseindia.com/api"
    next_api_url = f"{base_url}/NextApi/apiClient/GetQuoteApi"
    archive_url = "https://nsearchives.nseindia.com"

    def __init__(
        self,
        download_folder: Union[str, Path],
        use_http2: bool = False,
        cookie_store: Optional[CookieStore] = None,
        throttle: Optional[Limiter] = None,
        retry_config: Optional[RetryConfig] = None,
        timeout: int = 15,
        cookie_filename: Optional[str] = None,
    ):
        """Initialise the NSE client.

        Creates the download directory if it does not exist, sets up the
        cookie store, rate limiter, and retry configuration, and starts an
        HTTP session. If the configured cookie store is empty, a network
        request is made to NSE immediately to fetch initial cookies (this
        is subject to the retry policy and rate limiter).

        :param download_folder: Directory for downloaded files and the default
            cookie file. Created (including parents) if it does not exist.
        :type download_folder: pathlib.Path or str

        :param use_http2: Enable HTTP/2 for the underlying client. Default
            ``False``.
        :type use_http2: bool

        :param cookie_store: Custom cookie storage backend. If ``None``, a
            :class:`FileCookieStore` is created at
            ``download_folder / cookie_filename``. Use
            :class:`MemoryCookieStore` for multi-process or multi-threaded
            deployments. Default ``None``.
        :type cookie_store: Optional[CookieStore]

        :param throttle: Custom rate limiter. If ``None``, a default limiter
            of ``3 requests per second`` shared across API and file downloads
            is used. Default ``None``.
        :type throttle: Optional[pyrate_limiter.Limiter]

        :param retry_config: Retry policy configuration. If ``None``, a
            default :class:`RetryConfig` is used. Default ``None``.
        :type retry_config: Optional[RetryConfig]

        :param timeout: Network timeout in seconds, applied per request.
            Default ``15``.
        :type timeout: int

        :param cookie_filename: Filename for the default file cookie store
            when ``cookie_store`` is not provided. If ``None``, defaults to
            ``"cookies.txt"``. Default ``None``.
        :type cookie_filename: Optional[str]

        :raises NotADirectoryError: If ``download_folder`` exists but is not
            a directory.
        """
        uAgent = "Mozilla/5.0 (Windows NT 10.0; rv:109.0) Gecko/20100101 Firefox/118.0"

        headers = {
            "User-Agent": uAgent,
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Referer": "https://www.nseindia.com/get-quotes/equity?symbol=HDFCBANK",
        }

        self.dir = utils.prepare_path(download_folder, is_folder=True)

        self._transport = Transport(
            folder=self.dir,
            headers=headers,
            use_http2=use_http2,
            cookie_store=cookie_store,
            throttle=throttle,
            retry_config=retry_config,
            timeout=timeout,
            cookie_filename=cookie_filename,
        )

        # Used by NSE.option_chain(), create the hidden directory once.
        self.opt_cache_dir = self.dir / ".opt-expiry-cache"
        self.opt_cache_dir.mkdir(exist_ok=True)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self._transport.exit()

        return False

    def exit(self):
        """Close the underlying HTTP session and persist cookies.

        Saves the current session cookies to the configured cookie store,
        then closes the ``httpx`` session. Call this at the end of a script
        when the client is no longer needed. Not required when using the
        ``with`` statement, as ``__exit__`` calls this automatically.

        Calling ``exit`` more than once is safe, though subsequent calls
        operate on an already-closed session.

        :return: ``None``
        :rtype: None
        """
        self._transport.exit()

    def status(self) -> List[Dict]:
        """Return the current market status for all NSE segments.

        Reflects NSE's live market-state feed and includes segments such as
        capital market, currency, commodity, and debt. The response changes
        throughout the trading day as segments open, close, or enter
        pre-open.

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/status.json>`__

        :return: Market status of all NSE market segments. Each item is a
            dictionary describing one segment.
        :rtype: list[dict]
        """
        return self._transport.request(f"{self.base_url}/marketStatus").json()[
            "marketState"
        ]

    def lookup(self, query: str) -> dict:
        """Look up a stock symbol by company name, or a company name by symbol.

        Returns a dictionary with the ``symbols`` key containing a list of
        matching results. The first item is usually an exact match, assuming
        the exact company name or full symbol was searched.

        If the ``symbols`` list is empty, no symbols matched the query.

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/lookup.json>`__

        .. code-block:: python

            with NSE("") as nse:
                result = nse.lookup(query="hdfcbank")

                print(result['symbols'][0]['symbol_info']) # company name - HDFC Bank Limited
                print(result['symbols'][0]['symbol']) # stock symbol - HDFCBANK

        :param query: Company name or stock symbol to search for.
        :type query: str
        :return: A dictionary of results from the query search.
        :rtype: dict
        """
        return self._transport.request(
            f"{self.base_url}/search/autocomplete",
            params=dict(q=query),
        ).json()

    def equity_bhavcopy(
        self,
        date: datetime,
        folder: Union[str, Path, None] = None,
    ) -> Path:
        """Download the daily Equity bhavcopy report for ``date`` and return
        the saved file path.

        The file format depends on the date:

        - Before 8th July 2024, the legacy bhavcopy format is downloaded,
          e.g. ``cm02JAN2023bhav.csv``.
        - On or after 8th July 2024, the UDIFF bhavcopy format is used,
          e.g. ``BhavCopy_NSE_CM_0_0_0_20250102_F_0000.csv``.

        The downloaded archive (``.zip``) is automatically extracted and the
        archive deleted; the returned path points to the extracted CSV.

        :param date: Date of the bhavcopy to download.
        :type date: datetime.datetime
        :param folder: Optional folder to save the file in. If not specified,
            the ``download_folder`` from initialization is used.
        :type folder: pathlib.Path or str or None

        :raises ValueError: If ``folder`` is not a directory.
        :raises NSEFileUnavailableError: If NSE responds with ``404``. This
            typically means the report is not yet published for ``date``
            (e.g. a weekend, holiday, or future date), or the archive has not
            yet been uploaded.

        :return: Path to the extracted CSV file.
        :rtype: pathlib.Path
        """
        folder = utils.prepare_path(folder, is_folder=True) if folder else self.dir

        if date.date() < self.UDIFF_SWITCH_DATE:
            date_str = date.strftime("%d%b%Y").upper()
            month = date_str[2:5]

            url = f"{self.archive_url}/content/historical/EQUITIES/{date.year}/{month}/cm{date_str}bhav.csv.zip"

        else:
            url = "{}/content/cm/BhavCopy_NSE_CM_0_0_0_{}_F_0000.csv.zip".format(
                self.archive_url,
                date.strftime("%Y%m%d"),
            )

        file = self._transport.download(url, folder)

        return utils.consume_archive(file, file.parent)

    def delivery_bhavcopy(
        self,
        date: datetime,
        folder: Union[str, Path, None] = None,
    ) -> Path:
        """Download the daily Equity delivery report for ``date`` and return
        the saved file path.

        The delivered file is a plain CSV (no archive extraction is needed).

        :param date: Date of the delivery bhavcopy to download.
        :type date: datetime.datetime
        :param folder: Optional folder to save the file in. If not specified,
            the ``download_folder`` from initialization is used.
        :type folder: pathlib.Path or str or None

        :raises ValueError: If ``folder`` is not a directory.
        :raises NSEFileUnavailableError: If NSE responds with ``404``. This
            typically means the report is not yet published for ``date``.

        :return: Path to the saved CSV file.
        :rtype: pathlib.Path
        """
        folder = utils.prepare_path(folder, is_folder=True) if folder else self.dir

        url = "{}/products/content/sec_bhavdata_full_{}.csv".format(
            self.archive_url, date.strftime("%d%m%Y")
        )

        file = self._transport.download(url, folder)

        return file

    def indices_bhavcopy(
        self,
        date: datetime,
        folder: Union[str, Path, None] = None,
    ) -> Path:
        """Download the daily Equity Indices report for ``date`` and return
        the saved file path.

        The delivered file is a plain CSV (no archive extraction is needed).

        :param date: Date of the Indices bhavcopy to download.
        :type date: datetime.datetime
        :param folder: Optional folder to save the file in. If not specified,
            the ``download_folder`` from initialization is used.
        :type folder: pathlib.Path or str or None

        :raises ValueError: If ``folder`` is not a directory.
        :raises NSEFileUnavailableError: If NSE responds with ``404``. This
            typically means the report is not yet published for ``date``.

        :return: Path to the saved CSV file.
        :rtype: pathlib.Path
        """
        folder = utils.prepare_path(folder, is_folder=True) if folder else self.dir

        url = f"{self.archive_url}/content/indices/ind_close_all_{date:%d%m%Y}.csv"

        file = self._transport.download(url, folder)

        return file

    def fno_bhavcopy(
        self,
        date: datetime,
        folder: Union[str, Path, None] = None,
    ) -> Path:
        """Download the daily UDIFF-format FnO bhavcopy report for ``date``
        and return the saved file path.

        The downloaded archive (``.zip``) is automatically extracted and the
        archive deleted; the returned path points to the extracted CSV.

        :param date: Date of the FnO bhavcopy to download.
        :type date: datetime.datetime
        :param folder: Optional folder to save the file in. If not specified,
            the ``download_folder`` from initialization is used.
        :type folder: pathlib.Path or str or None

        :raises ValueError: If ``folder`` is not a directory.
        :raises NSEFileUnavailableError: If NSE responds with ``404``. This
            typically means the report is not yet published for ``date``.

        :return: Path to the extracted CSV file.
        :rtype: pathlib.Path
        """
        dt_str = date.strftime("%Y%m%d")

        folder = utils.prepare_path(folder, is_folder=True) if folder else self.dir

        url = f"{self.archive_url}/content/fo/BhavCopy_NSE_FO_0_0_0_{dt_str}_F_0000.csv.zip"

        file = self._transport.download(url, folder)

        return utils.consume_archive(file, folder=file.parent)

    def priceband_report(
        self,
        date: datetime,
        folder: Union[str, Path, None] = None,
    ) -> Path:
        """Download the daily priceband report for ``date`` and return the
        saved file path.

        The delivered file is a plain CSV (no archive extraction is needed).

        :param date: Report date to download.
        :type date: datetime.datetime
        :param folder: Optional folder to save the file in. If not specified,
            the ``download_folder`` from initialization is used.
        :type folder: pathlib.Path or str or None

        :raises ValueError: If ``folder`` is not a directory.
        :raises NSEFileUnavailableError: If NSE responds with ``404``. This
            typically means the report is not yet published for ``date``.

        :return: Path to the saved CSV file.
        :rtype: pathlib.Path
        """
        dt_str = date.strftime("%d%m%Y")

        folder = utils.prepare_path(folder, is_folder=True) if folder else self.dir

        url = f"{self.archive_url}/content/equities/sec_list_{dt_str}.csv"

        file = self._transport.download(url, folder)

        return file

    def pr_bhavcopy(
        self,
        date: datetime,
        folder: Union[str, Path, None] = None,
    ) -> Path:
        """Download the daily PR Bhavcopy zip report for ``date`` and return
        the saved zip file path.

        The returned file is a zip archive containing a collection of reports,
        including a ``Readme.txt`` that explains the contents of each file and
        the file naming format. Unlike other bhavcopy methods, this archive is
        **not** extracted.

        :param date: Report date to download.
        :type date: datetime.datetime
        :param folder: Optional folder to save the file in. If not specified,
            the ``download_folder`` from initialization is used.
        :type folder: pathlib.Path or str or None

        :raises ValueError: If ``folder`` is not a directory.
        :raises NSEFileUnavailableError: If NSE responds with ``404``. This
            typically means the report is not yet published for ``date``.

        :return: Path to the saved zip file.
        :rtype: pathlib.Path
        """
        dt_str = date.strftime("%d%m%y")

        folder = utils.prepare_path(folder, is_folder=True) if folder else self.dir

        url = f"{self.archive_url}/archives/equities/bhavcopy/pr/PR{dt_str}.zip"

        file = self._transport.download(url, folder)

        return file

    def cm_mii_security_report(
        self,
        date: datetime,
        folder: Union[str, Path, None] = None,
    ) -> Path:
        """Download the daily CM MII security file report for ``date`` and
        return the saved and extracted file path.

        The downloaded ``.gz`` archive is automatically decompressed and the
        archive deleted; the returned path points to the resulting CSV.

        :param date: Report date to download.
        :type date: datetime.datetime
        :param folder: Optional folder to save the file in. If not specified,
            the ``download_folder`` from initialization is used.
        :type folder: pathlib.Path or str or None

        :raises ValueError: If ``folder`` is not a directory.
        :raises NSEFileUnavailableError: If NSE responds with ``404``. This
            typically means the report is not yet published for ``date``.

        :return: Path to the extracted CSV file.
        :rtype: pathlib.Path
        """
        dt_str = date.strftime("%d%m%Y")

        folder = utils.prepare_path(folder, is_folder=True) if folder else self.dir

        url = f"{self.archive_url}/content/cm/NSE_CM_security_{dt_str}.csv.gz"

        file = self._transport.download(url, folder)

        return utils.consume_archive(file, folder=file.parent)

    def actions(
        self,
        segment: Literal["equities", "sme", "debt", "mf"] = "equities",
        symbol: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> List[Dict]:
        """Get all forthcoming corporate actions.

        If ``symbol`` is specified, only actions for that symbol are returned.
        If ``from_date`` and ``to_date`` are both specified, only actions
        within the date range are returned.

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/actions.json>`__

        :param segment: One of ``equities``, ``sme``, ``debt`` or ``mf``.
            Default ``equities``.
        :type segment: str
        :param symbol: Optional stock symbol to filter actions.
        :type symbol: str or None
        :param from_date: Optional start date of the range.
        :type from_date: datetime.datetime or None
        :param to_date: Optional end date of the range.
        :type to_date: datetime.datetime or None

        :raises ValueError: If ``from_date`` is greater than ``to_date``.

        :return: A list of corporate actions.
        :rtype: list[dict]
        """
        fmt = "%d-%m-%Y"

        params = dict(index=segment)

        if symbol:
            params["symbol"] = symbol

        if from_date and to_date:
            if from_date > to_date:
                raise ValueError("'from_date' cannot be greater than 'to_date'")

            params.update(
                dict(
                    from_date=from_date.strftime(fmt),
                    to_date=to_date.strftime(fmt),
                )
            )

        url = f"{self.base_url}/corporates-corporateActions"

        return self._transport.request(url, params=params).json()

    def announcements(
        self,
        index: Literal["equities", "sme", "debt", "mf", "invitsreits"] = "equities",
        symbol: Optional[str] = None,
        fno=False,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> List[Dict]:
        """Get all corporate announcements.

        If ``symbol`` is specified, only announcements for that symbol are
        returned. If ``fno`` is ``True``, only announcements for FnO
        securities are returned. If ``from_date`` and ``to_date`` are both
        specified, only announcements within the date range are returned.

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/announcements.json>`__

        :param index: One of ``equities``, ``sme``, ``debt``, ``mf`` or
            ``invitsreits``. Default ``equities``.
        :type index: str
        :param symbol: Optional stock symbol to filter announcements.
        :type symbol: str or None
        :param fno: If ``True``, restrict results to FnO stocks. Default
            ``False``.
        :type fno: bool
        :param from_date: Optional start date of the range.
        :type from_date: datetime.datetime or None
        :param to_date: Optional end date of the range.
        :type to_date: datetime.datetime or None

        :raises ValueError: If ``from_date`` is greater than ``to_date``.

        :return: A list of corporate announcements.
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
                dict(
                    from_date=from_date.strftime(fmt),
                    to_date=to_date.strftime(fmt),
                )
            )

        url = f"{self.base_url}/corporate-announcements"

        return self._transport.request(url, params=params).json()

    def board_meetings(
        self,
        index: Literal["equities", "sme"] = "equities",
        symbol: Optional[str] = None,
        fno: bool = False,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> List[Dict]:
        """Get all forthcoming board meetings.

        If ``symbol`` is specified, only board meetings for that symbol are
        returned. If ``fno`` is ``True``, only board meetings for FnO
        securities are returned. If ``from_date`` and ``to_date`` are both
        specified, only meetings within the date range are returned.

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/board_meetings.json>`__

        :param index: One of ``equities`` or ``sme``. Default ``equities``.
        :type index: str
        :param symbol: Optional stock symbol to filter board meetings.
        :type symbol: str or None
        :param fno: If ``True``, restrict results to FnO stocks. Default
            ``False``.
        :type fno: bool
        :param from_date: Optional start date of the range.
        :type from_date: datetime.datetime or None
        :param to_date: Optional end date of the range.
        :type to_date: datetime.datetime or None

        :raises ValueError: If ``from_date`` is greater than ``to_date``.

        :return: A list of corporate board meetings.
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
                dict(
                    from_date=from_date.strftime(fmt),
                    to_date=to_date.strftime(fmt),
                )
            )

        url = f"{self.base_url}/corporate-board-meetings"

        return self._transport.request(url, params=params).json()

    def annual_reports(
        self,
        symbol: str,
        segment: Literal["equities", "sme"] = "equities",
    ) -> Dict[str, List[Dict[str, str]]]:
        """Return annual reports for ``symbol``.

        The returned dictionary contains a ``data`` key holding a list of
        per-year report entries. Each entry includes a ``fileName`` pointing
        to the annual report PDF, which can be downloaded with
        :meth:`download_document`.

        .. code-block:: python

            with NSE("") as nse:
                annual_reports = nse.annual_reports(symbol="HDFCBANK")

                file = nse.download_document(annual_reports["data"][0]["fileName"])

                print(file)  # filepath of downloaded annual report

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/annual_reports.json>`__

        :param symbol: Stock symbol for which annual reports are to be
            fetched.
        :type symbol: str
        :param segment: One of ``equities`` or ``sme``. Default ``equities``.
        :type segment: str

        :return: A dictionary with a ``data`` key holding a list of
            dictionaries, each containing a link to a yearly annual report.
        :rtype: dict[str, list[dict[str, str]]]
        """
        return self._transport.request(
            f"{self.base_url}/annual-reports", params=dict(index=segment, symbol=symbol)
        ).json()

    def financial_results(
        self,
        segment: Literal["equities", "sme", "debt", "mf"] = "equities",
        period: Literal["quarterly", "annual", "half-yearly"] = "quarterly",
        symbol: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> List[Dict]:
        """Get corporate financial-results filings (metadata) for a date range.

        Returns one row per filing with broadcast/filing dates, the quarter
        covered (``fromDate`` / ``toDate``), ``relatingTo`` (e.g. "Third
        Quarter"), consolidated/audited flags, and an optional XBRL link.
        Revenue and EPS figures are **not** included here — use
        :meth:`results_comparison` for the numeric P&L summary per symbol.

        If ``from_date`` and ``to_date`` are omitted, the API returns filings
        for the current year to date.

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/financial_results.json>`__

        Reference URL:
            https://www.nseindia.com/companies-listing/corporate-filings-financial-results

        :param segment: One of ``equities``, ``sme``, ``debt`` or ``mf``.
            Default ``equities``.
        :type segment: str
        :param period: One of ``quarterly``, ``annual`` or ``half-yearly``.
            Default ``quarterly``.
        :type period: str
        :param symbol: Optional stock symbol to filter filings.
        :type symbol: str or None
        :param from_date: Optional start of the broadcast-date window
            (inclusive).
        :type from_date: datetime.datetime or None
        :param to_date: Optional end of the broadcast-date window (inclusive).
        :type to_date: datetime.datetime or None

        :raises ValueError: If ``from_date`` is greater than ``to_date``.

        :return: A list of financial-results filing records.
        :rtype: list[dict]
        """
        fmt = "%d-%m-%Y"

        params: Dict[str, Any] = dict(
            index=segment,
            period=period,
        )

        if symbol:
            params["symbol"] = symbol.upper()

        if from_date and to_date:
            if from_date > to_date:
                raise ValueError("'from_date' cannot be greater than 'to_date'")

            params.update(
                dict(
                    from_date=from_date.strftime(fmt),
                    to_date=to_date.strftime(fmt),
                )
            )

        url = f"{self.base_url}/corporates-financial-results"

        return self._transport.request(url, params=params).json()

    def results_comparison(self, symbol: str) -> Dict:
        """Get quarterly financial results comparison (P&L summary) for a symbol.

        NSE's endpoint path is spelled ``results-comparision`` (official typo).

        The response contains a ``resCmpData`` list — typically the last ~5
        quarters — with revenue, net profit and EPS fields. Monetary amounts
        are in **Rupees Lakhs** (divide by 100 for Crores).

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/results_comparison.json>`__

        Reference URL:
            https://www.nseindia.com/companies-listing/corporate-filings-financial-results

        .. code-block:: python

            with NSE("") as nse:
                data = nse.results_comparison("RELIANCE")
                for row in data["resCmpData"]:
                    print(row["re_to_dt"], row.get("re_total_inc"), row.get("re_net_profit"))

        :param symbol: Stock symbol (e.g. ``RELIANCE``, ``HDFCBANK``).
        :type symbol: str

        :return: Dictionary with ``resCmpData`` — list of quarter rows.
        :rtype: dict
        """
        return self._transport.request(
            f"{self.base_url}/results-comparision",
            params=dict(symbol=symbol.upper()),
        ).json()

    def shareholding(
        self,
        symbol: str,
        index: Literal["equities", "sme"] = "equities",
    ) -> List[dict]:
        """Fetch shareholding pattern data for the given stock ``symbol``.

        Returns quarterly shareholding details with the latest quarter first.

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/shareholding.json>`__

        Reference URL:
            https://www.nseindia.com/companies-listing/corporate-filings-shareholding-pattern?symbol=HDFCBANK&tabIndex=equity
            (company listing page)

        :param symbol: Stock symbol code.
        :type symbol: str
        :param index: Market segment, either ``"equities"`` or ``"sme"``.
        :type index: str

        :return: List of quarterly shareholding records. Each dictionary
            contains key fields including:

            - ``symbol`` – Stock symbol name
            - ``date`` – Shareholding as-on date
            - ``pr_and_prgrp`` – Shares held by Promoter and Promoter Group
            - ``public_val`` – Shares held by Public
            - ``employeeTrusts`` – Shares held by Employee Trusts

            The first item in the list corresponds to the most recent quarter.
        :rtype: list[dict[str, Any]]
        """
        return self._transport.request(
            f"{self.base_url}/corporate-share-holdings-master",
            params=dict(index=index, symbol=symbol.upper()),
        ).json()

    def equity_meta_info(self, symbol) -> Dict:
        """Return meta info for an equity symbol.

        Returns a dictionary containing the symbol, company name, ISIN, market
        type, available and suspended trading series, and flags indicating
        whether the security is listed, suspended, delisted, or belongs to
        categories such as FnO, ETF, SLB, debt, municipal bond, or hybrid
        symbol.

        The ``series`` and ``marketType`` values returned here can be passed
        directly to :meth:`quote`.

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/equity_meta_info.json>`__

        :param symbol: Equity symbol code.
        :type symbol: str

        :return: Stock meta info.
        :rtype: dict
        """
        return self._transport.request(
            self.next_api_url,
            params=dict(functionName="getMetaData", symbol=symbol.upper()),
        ).json()

    def quote(
        self,
        symbol: str,
        series: str = "EQ",
        market_type: str = "N",
    ) -> Dict:
        """Return price quotes and other data for an equity symbol.

        Returns a dictionary containing the current quote, market depth (order
        book), OHLC and price statistics, trading metrics, security
        information, and the last update timestamp.

        The ``series`` and ``market_type`` values can be obtained from
        :meth:`equity_meta_info`.

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/quote.json>`__

        :param symbol: Equity symbol code.
        :type symbol: str
        :param series: Any of the NSE equity series, e.g. ``EQ``, ``BE``,
            ``BZ``, ``SM``, ``ST``. Default ``EQ``.
        :type series: str
        :param market_type: Internal NSE market classification. Default
            ``N``.
        :type market_type: str

        :return: Price quote and other stock information.
        :rtype: dict
        """
        params = dict(
            functionName="getSymbolData",
            marketType=market_type.upper(),
            series=series.upper(),
            symbol=symbol.upper(),
        )

        result = self._transport.request(self.next_api_url, params=params).json()
        return result["equityResponse"][0]

    def equity_quote(self, symbol) -> OHLCV:
        """Extract date and OHLCV data from :meth:`quote` for ``symbol``.

        A convenience wrapper over :meth:`quote` that returns the fields typically
        needed for a daily OHLCV bar.

        :param symbol: Equity symbol code.
        :type symbol: str

        :return: OHLCV data containing ``date``, ``open``, ``high``, ``low``,
            ``close``, and ``volume``.
        :rtype: OHLCV
        """
        q = self.quote(symbol)

        return OHLCV(
            date=q["lastUpdateTime"],
            open=q["metaData"]["open"],
            high=q["metaData"]["dayHigh"],
            low=q["metaData"]["dayLow"],
            close=q["orderBook"]["lastPrice"],
            volume=q["tradeInfo"]["totalTradedVolume"],
        )

    def live_volume_gainers(self) -> dict:
        """Get live volume gainers.

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/live_volume_gainers.json>`__

        :return: A dictionary. The ``data`` key contains a list of stocks with
            volume surge metrics, price performance, and turnover data.
        :rtype: dict
        """
        return self._transport.request(
            f"{self.base_url}/live-analysis-volume-gainers"
        ).json()

    def gainers(self, data: Dict, count: Optional[int] = None) -> List[Dict]:
        """Return top gainers by percent change above zero.

        Filters the ``data`` list in ``data`` to entries with ``pChange > 0``,
        sorted descending by ``pChange``.

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/gainers.json>`__

        :param data: Output of one of :meth:`listSme` or
            :meth:`listEquityStocksByIndex`.
        :type data: dict
        :param count: Optional. Limit the number of results returned.
        :type count: int or None

        :return: List of top gainers.
        :rtype: list[dict]
        """
        return sorted(
            filter(lambda dct: dct["pChange"] > 0, data["data"]),
            key=lambda dct: dct["pChange"],
            reverse=True,
        )[:count]

    def losers(self, data: Dict, count: Optional[int] = None) -> List[Dict]:
        """Return top losers by percent change below zero.

        Filters the ``data`` list in ``data`` to entries with ``pChange < 0``,
        sorted ascending by ``pChange`` (largest loss first).

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/losers.json>`__

        :param data: Output of one of :meth:`listSme` or
            :meth:`listEquityStocksByIndex`.
        :type data: dict
        :param count: Optional. Limit the number of results returned.
        :type count: int or None

        :return: List of top losers.
        :rtype: list[dict]
        """
        return sorted(
            filter(lambda dct: dct["pChange"] < 0, data["data"]),
            key=lambda dct: dct["pChange"],
        )[:count]

    def list_equity_stocks_by_index(self, index="nifty 50") -> dict:
        """List equity stocks by their index name. Defaults to ``nifty 50``.

        :ref:`See list of acceptable values for index argument. <listEquityStocksByIndex>`

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/list_equity_stocks_by_index.json>`__

        Reference Page:
            https://www.nseindia.com/market-data/live-equity-market?symbol=NIFTY%2050

        :param index: Index name. Default ``nifty 50``.
        :type index: str

        :return: A dictionary. The ``data`` key is a list of all stocks
            represented by a dictionary with the symbol name and other
            metadata.
        :rtype: dict
        """
        endpoint = "equity-stock-indices"

        if index.upper() in ("PERMITTED TO TRADE", "SECURITIES IN F&O"):
            endpoint = "equity-stockIndex"

        return self._transport.request(
            f"{self.base_url}/{endpoint}", params=dict(index=index.upper())
        ).json()

    def list_indices(self) -> dict:
        """List all indices.

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/list_indices.json>`__

        :return: A dictionary. The ``data`` key is a list of all Indices
            represented by a dictionary with the symbol code and other
            metadata.
        :rtype: dict
        """
        url = f"{self.base_url}/allIndices"

        return self._transport.request(url).json()

    def list_etf(self) -> dict:
        """List all ETF stocks.

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/list_etf.json>`__

        :return: A dictionary. The ``data`` key is a list of all ETFs
            represented by a dictionary with the symbol code and other
            metadata.
        :rtype: dict
        """
        return self._transport.request(f"{self.base_url}/etf").json()

    def list_sme(self) -> dict:
        """List all SME stocks.

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/list_sme.json>`__

        :return: A dictionary. The ``data`` key is a list of all SMEs
            represented by a dictionary with the symbol code and other
            metadata.
        :rtype: dict
        """
        return self._transport.request(f"{self.base_url}/live-analysis-emerge").json()

    def list_sgb(self) -> dict:
        """List all Sovereign Gold Bonds.

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/list_sgb.json>`__

        :return: A dictionary. The ``data`` key is a list of all SGBs
            represented by a dictionary with the symbol code and other
            metadata.
        :rtype: dict
        """
        return self._transport.request(f"{self.base_url}/sovereign-gold-bonds").json()

    def list_current_ipo(self) -> List[Dict]:
        """List current IPOs.

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/list_current_ipo.json>`__

        :return: List of current IPOs.
        :rtype: list[dict]
        """
        return self._transport.request(f"{self.base_url}/ipo-current-issue").json()

    def list_upcoming_ipo(self) -> List[Dict]:
        """List upcoming IPOs.

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/list_upcoming_ipo.json>`__

        :return: List of upcoming IPOs.
        :rtype: list[dict]
        """
        return self._transport.request(
            f"{self.base_url}/all-upcoming-issues?category=ipo"
        ).json()

    def list_past_ipo(
        self,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> List[Dict]:
        """List past IPOs within a date range.

        If ``to_date`` is not provided, it defaults to the current date. If
        ``from_date`` is not provided, it defaults to 90 days before
        ``to_date``.

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/list_past_ipo.json>`__

        :param from_date: Optional start date. Defaults to 90 days before
            ``to_date``.
        :type from_date: datetime.datetime or None
        :param to_date: Optional end date. Defaults to the current date.
        :type to_date: datetime.datetime or None

        :raises ValueError: If ``to_date`` is earlier than ``from_date``.

        :return: List of past IPOs.
        :rtype: list[dict]
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

        return self._transport.request(
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
        """Return exchange circulars and communications by department.

        If ``to_date`` is not provided, it defaults to the current date. If
        ``from_date`` is not provided, it defaults to 7 days before
        ``to_date``.

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/circulars.json>`__

        :param subject: Optional keyword string used to filter circulars based
            on their subject.
        :type subject: str or None
        :param dept_code: Optional department code. See the list below for
            accepted values.
        :type dept_code: str or None
        :param from_date: Optional start date. Defaults to 7 days before
            ``to_date``.
        :type from_date: datetime.datetime or None
        :param to_date: Optional end date. Defaults to the current date.
        :type to_date: datetime.datetime or None

        :raises ValueError: If ``to_date`` is earlier than ``from_date``.

        Below is the list of ``dept_code`` values and their description:

        - ``CMTR`` – Capital Market (Equities) Trade
        - ``COM`` – Commodity Derivatives
        - ``CC`` – Corporate Communications
        - ``CRM`` – CRM & Marketing
        - ``CD`` – Currency Derivatives
        - ``DS`` – Debt Segment
        - ``SME`` – Emerge
        - ``SMEITP`` – Emerge-ITP
        - ``FAAC`` – Finance & Accounts
        - ``FAO`` – Futures & Options
        - ``INSP`` – Inspection & Compliance
        - ``LEGL`` – Legal, ISC & Arbitration
        - ``CMLS`` – Listing
        - ``MA`` – Market Access
        - ``MSD`` – Member Service Department
        - ``MEMB`` – Membership
        - ``MF`` – Mutual Fund
        - ``NWPR`` – New Products
        - ``NCFM`` – NSE Academy Limited
        - ``CMPT`` – NSE Clearing - Capital Market
        - ``IPO`` – Primary Market Segment
        - ``RDM`` – Retail Debt Market
        - ``SLBS`` – Securities Lending & Borrowing Scheme
        - ``SURV`` – Surveillance & Investigation
        - ``TEL`` – Systems & Telecom
        - ``UCIBD`` – UCI Business Development
        - ``WDTR`` – Wholesale Debt Market

        :return: A dictionary of circulars for the requested filters.
        :rtype: dict
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

        return self._transport.request(
            f"{self.base_url}/circulars", params=params
        ).json()

    def block_deals(self) -> Dict:
        """Return block deals.

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/block_deals.json>`__

        :return: Block deals. The ``data`` key is a list of all block deals
            (empty list if there are none).
        :rtype: dict
        """
        return self._transport.request(f"{self.base_url}/block-deal").json()

    def fno_lots(self) -> Dict[str, int]:
        """Return the lot size of FnO stocks.

        Downloads NSE's fo_mktlots.csv and parses it into a symbol → lot
        size mapping. The CSV contains two header rows, which are skipped.
        Rows where the lot size column is empty or cannot be parsed as an
        integer are skipped.

        .. note::
            A symbol with an empty lot size is omitted from the returned dictionary.
            This indicates that the symbol has been removed, or is scheduled to be
            removed, from the FnO segment.

        .. note::
            The lot size is extracted from the next-month expiry column rather than
            the current-month expiry column.

        :return: A dictionary mapping symbol codes to lot sizes.
        :rtype: dict[str, int]
        """
        url = "https://nsearchives.nseindia.com/content/fo/fo_mktlots.csv"

        res = self._transport.request(url).content

        dct = {}

        for line in res.strip().split(b"\n"):
            _, sym, _, lot, *_ = line.split(b",")

            lot_size = lot.strip().decode()

            if not lot_size:
                # empty string indicating scrip is removed or
                # will no longer be part of FnO
                continue

            decoded_sym = sym.strip().decode()
            try:
                dct[decoded_sym] = int(lot.strip().decode())
            except ValueError:
                if decoded_sym.lower() != "symbol":
                    logger.warning(
                        "NSE.fnoLots: Unable to determine lotsize for `%s` with value %s",
                        sym.strip().decode(),
                        lot_size,
                    )
                continue

        return dct

    def option_chain(
        self,
        symbol: Union[Literal["banknifty", "nifty", "finnifty", "niftyit"], str],
        expiry_date: Optional[datetime] = None,
    ) -> Dict:
        """Fetch the raw (unprocessed) option chain data for an index or F&O
        stock.

        If ``expiry_date`` is not provided, the nearest valid expiry is
        resolved automatically using the following order:

        1. Read a locally cached expiry date from
           ``<self.dir>/.opt-expiry-cache/<symbol>.txt`` (if available).
        2. Validate the cached expiry against the current date.
        3. If missing, unreadable, or expired, fetch expiry dates from NSE's
           ``option-chain-contract-info`` endpoint and select the first
           (nearest) expiry.
        4. Atomically update the local cache with the resolved expiry date.

        The final option chain data is fetched from NSE's ``option-chain-v3``
        endpoint.

        .. note::
           The cache is written atomically via a temp file and ``os.replace``,
           so concurrent readers never observe a partially written file.
           Per-symbol cache files also mean two processes resolving *different*
           symbols cannot clobber each other's entries. However, there is no
           locking: two processes resolving the *same* symbol concurrently may
           both hit NSE and race on the final rename (last writer wins, same
           value, so harmless). In multi-process deployments, consider using
           :class:`MemoryCookieStore` and passing explicit ``expiry_date``
           values to skip the cache entirely.

        Reference sample response:
        https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/option_chain.json

        :param symbol: FnO stock symbol or index futures identifier. For index
            futures, must be one of ``banknifty``, ``nifty``, ``finnifty``,
            ``niftyit``.
        :type symbol: str
        :param expiry_date: Expiry date of the instrument. If ``None``, the
            nearest valid expiry is automatically resolved and cached.
        :type expiry_date: datetime.datetime or None

        :raises ValueError: If the NSE response does not contain the
            ``expiryDates`` field.
        :raises ValueError: If NSE returns an empty list of expiry dates.

        :return: Raw JSON response from NSE containing the option chain for
            the requested symbol and expiry.
        :rtype: dict
        """
        symbol_key = symbol.lower()
        params = dict(symbol=symbol.upper())

        if expiry_date is None:
            cache_file = self.opt_cache_dir / f"{symbol_key}.txt"

            # Avoid file exists checks to avoid TOCTOU race conditions
            # in multi process environments.
            try:
                expiry_date = datetime.fromisoformat(cache_file.read_text().strip())
            except (ValueError, OSError):
                # FileNotFoundError, invalid date format etc.
                expiry_date = None

            if expiry_date is None or date.today() > expiry_date.date():
                opt_info = self._transport.request(
                    f"{self.base_url}/option-chain-contract-info", params=params
                ).json()

                if "expiryDates" not in opt_info:
                    raise ValueError(
                        "Missing `expiryDates` field in option chain contract info"
                    )

                if not opt_info["expiryDates"]:
                    raise ValueError("No expiry dates returned from NSE")

                expiry_date = datetime.strptime(opt_info["expiryDates"][0], "%d-%b-%Y")

                # Atomic file writes, prevent file corruption from
                # concurrent file writes to same file
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    dir=cache_file.parent,
                    delete=False,
                    prefix=f".{symbol_key}-",
                    suffix=".tmp",
                ) as f:
                    f.write(expiry_date.isoformat())
                    tmp_path = Path(f.name)

                try:
                    tmp_path.replace(cache_file)
                except BaseException:
                    tmp_path.unlink(missing_ok=True)
                    raise

        url = f"{self.base_url}/option-chain-v3"

        params["type"] = "Indices" if symbol_key in self._option_index else "Equity"

        params["expiry"] = expiry_date.strftime("%d-%b-%Y")

        data = self._transport.request(url, params=params).json()

        return data

    @staticmethod
    def max_pain(option_chain: Dict, expiryDate: datetime) -> float:
        """Return the max pain strike price.

        Uses prefix sums to pre-compute values and avoid nested loops, giving
        O(n) performance for the max pain calculation.

        See `Prefix sum for details <https://www.geeksforgeeks.org/dsa/prefix-sum-array-implementation-applications-competitive-programming/>`_.

        .. note::
           This method relies on NSE returning strikes in **sorted ascending
           order** within the option chain response, and does not sort them
           itself. If the ordering is ever broken, the computed max pain will
           be incorrect.

        :param option_chain: Output of :meth:`option_chain`.
        :type option_chain: dict
        :param expiryDate: Options expiry date.
        :type expiryDate: datetime.datetime

        :return: Max pain strike price.
        :rtype: float
        """
        data = option_chain["records"]["data"]
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

    def get_futures_expiry(
        self, index: Literal["nifty", "banknifty", "finnifty"] = "nifty"
    ) -> List[str]:
        """Return the current, next, and far month expiry dates for an index.

        Expiries are returned as a sorted list with order guaranteed, so the
        first item is the nearest expiry. This is a lightweight lookup that
        avoids the need to compute the last Thursday of the month and account
        for exchange holidays.

        :param index: One of ``nifty``, ``banknifty``, ``finnifty``. Default
            ``nifty``.
        :type index: str

        :return: Sorted list of current, next, and far month expiries, as
            strings in ``DD-Mon-YYYY`` format.
        :rtype: list[str]
        """
        if index == "banknifty":
            idx = "nifty_bank_fut"
        elif index == "finnifty":
            idx = "finnifty_fut"
        else:
            idx = "nse50_fut"

        res: Dict = self._transport.request(
            f"{self.base_url}/liveEquity-derivatives",
            params={"index": idx},
        ).json()

        data = tuple(i["expiryDate"] for i in res["data"])

        return sorted(data, key=lambda x: datetime.strptime(x, "%d-%b-%Y"))

    def compile_option_chain(
        self,
        symbol: Union[str, Literal["banknifty", "nifty", "finnifty", "niftyit"]],
        expiry_date: datetime,
    ) -> CompiledOptionChain:
        """
        Filter raw option chain by ``expiry_date`` and calculate various statistics
        required for analysis. This makes it easy to build an option chain for
        analysis using a simple loop.

        Statistics include:

        - Max pain
        - Strike price with max Call and Put Open Interest
        - Total Call and Put Open Interest
        - Total PCR ratio
        - PCR for every strike price
        - Every strike price has Last price, Open Interest, Change, Implied
          Volatility for both Call and Put

        Other included values: At the Money (ATM) strike price, Underlying strike
        price, Expiry date.

        The ATM strike is derived by computing the strike interval from the first
        two entries in ``data["filtered"]["data"]`` and rounding the underlying
        value to the nearest multiple of that interval.

        Only entries in ``data["records"]["data"]`` whose ``expiryDates`` field
        matches ``expiry_date`` (formatted as ``"%d-%b-%Y"``) are included. For
        each retained strike:

        - If a ``PE`` entry is present, its ``openInterest``, ``lastPrice``,
          ``chg`` and ``impliedVolatility`` are recorded; otherwise the PE side
          is populated with zeros.
        - If a ``CE`` entry is present, its ``openInterest``, ``lastPrice``,
          ``chg`` and ``impliedVolatility`` are recorded; otherwise the CE side
          is populated with zeros.
        - The per-strike PCR is ``round(pe_oi / ce_oi, 2)`` when ``ce_oi`` is
          non-zero, otherwise ``None``.

        The ``max_coi`` and ``max_poi`` strikes reported in the result default to
        ``0`` when no CE or PE data is found. Likewise, ``coi_total`` and
        ``poi_total`` remain ``0`` in that case, and ``pcr`` (overall) is ``None``
        when ``coi_total`` is ``0``.

        Max pain is delegated to :meth:`max_pain` and receives the raw response
        plus ``expiry_date``.

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/compile_option_chain.json>`__

        :param symbol: FnO stock or Index futures symbol code. If Index futures
            must be one of ``banknifty``, ``nifty``, ``finnifty``, ``niftyit``.
        :type symbol: str
        :param expiry_date: Option chain expiry date.
        :type expiry_date: datetime.datetime
        :return: Option chain filtered by ``expiry_date``. Keys include ``expiry``,
            ``timestamp``, ``underlying``, ``atm``, ``max_pain``, ``max_coi``,
            ``max_poi``, ``coi_total``, ``poi_total``, ``pcr`` and ``chain`` (a
            mapping of strike price strings to ``{"pe": {...}, "ce": {...},
            "pcr": ...}``).
        :rtype: CompiledOptionChain
        """
        data = self.option_chain(symbol, expiry_date=expiry_date)

        chain: Dict[str, StrikeRow] = {}

        expiry_date_str = expiry_date.strftime("%d-%b-%Y")

        strike_1 = data["filtered"]["data"][0]["strikePrice"]
        strike_2 = data["filtered"]["data"][1]["strikePrice"]
        multiple = strike_1 - strike_2

        underlying = data["records"]["underlyingValue"]

        max_coi = max_poi = total_coi = total_poi = max_coi_strike = max_poi_strike = 0

        data_fields = ("openInterest", "lastPrice", "chg", "impliedVolatility")

        for row in data["records"]["data"]:
            if row["expiryDates"] != expiry_date_str:
                continue

            strike = str(row["strikePrice"])

            if strike not in chain:
                chain[strike] = StrikeRow(
                    pe=OptionLeg(last=0, oi=0, chg=0, iv=0),
                    ce=OptionLeg(last=0, oi=0, chg=0, iv=0),
                    pcr=None,
                )

            poi = coi = 0

            if "PE" in row:
                poi, last, chg, iv = map(row["PE"].get, data_fields)

                chain[strike]["pe"] = OptionLeg(last=last, oi=poi, chg=chg, iv=iv)

                total_poi += poi

                if poi > max_poi:
                    max_poi = poi
                    max_poi_strike = int(strike)

            if "CE" in row:
                coi, last, chg, iv = map(row["CE"].get, data_fields)

                chain[strike]["ce"] = OptionLeg(last=last, oi=coi, chg=chg, iv=iv)

                total_coi += coi

                if coi > max_coi:
                    max_coi = coi
                    max_coi_strike = int(strike)

            if coi == 0:
                chain[strike]["pcr"] = None
            else:
                chain[strike]["pcr"] = round(poi / coi, 2)

        return CompiledOptionChain(
            expiry=expiry_date_str,
            timestamp=data["records"]["timestamp"],
            underlying=underlying,
            atm=multiple * round(underlying / multiple),
            max_pain=self.max_pain(data, expiry_date),
            max_coi=max_coi_strike,
            max_poi=max_poi_strike,
            coi_total=total_coi,
            poi_total=total_poi,
            pcr=None if total_coi == 0 else round(total_poi / total_coi, 2),
            chain=chain,
        )

    def advance_decline(self, index: str = "NIFTY 50") -> Dict:
        """Fetch advance-decline data for an NSE index.

        .. versionadded:: 3.0.0

        Reintroduced using the new NSE API endpoint. Deprecated in v1.0.9
        because the original NSE endpoint was no longer active.

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/advance_decline.json>`__

        Example::

            advanceDecline()
            advanceDecline("NIFTY BANK")

        :param index: NSE index name. Default ``NIFTY 50``.
        :type index: str

        :return: Advance-decline statistics.
        :rtype: dict
        """
        url = f"{self.base_url}/equity-stockIndices-adu"

        return self._transport.request(url, params=dict(index=index.upper())).json()

    def holidays(
        self, type: Literal["trading", "clearing"] = "trading"
    ) -> Dict[str, List[Dict]]:
        """Return the NSE holiday list.

        ``CM`` key in the dictionary stands for Capital Markets (Equity
        Market).

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/holidays.json>`__

        :param type: One of ``trading`` or ``clearing``. Default ``trading``.
        :type type: str

        :return: Market holidays for all market segments.
        :rtype: dict[str, list[dict]]
        """
        url = f"{self.base_url}/holiday-master"

        data = self._transport.request(url, params={"type": type}).json()

        return data

    def bulk_deals(
        self,
        option_type: Literal["block_deals", "bulk_deals", "short_selling"],
        from_date: datetime,
        to_date: datetime,
    ) -> List[Dict]:
        """Retrieve bulk, block, or short-selling deal data for a date range.

        Downloads historical deal data based on the selected report type. The
        requested date range must be valid and must not exceed one year.

        Sample responses:

        - Bulk deals: https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/bulk_deals-bulk_deals.json
        - Block deals: https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/bulk_deals-block_deals.json
        - Short selling: https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/bulk_deals-short_selling.json

        :param option_type: Type of deal report to fetch. Must be one of
            ``"bulk_deals"``, ``"block_deals"``, or ``"short_selling"``.
        :type option_type: str
        :param from_date: Start date of the report (inclusive).
        :type from_date: datetime.datetime
        :param to_date: End date of the report (inclusive).
        :type to_date: datetime.datetime

        :raises ValueError: If ``fromdate`` is later than ``todate``.
        :raises ValueError: If the date range exceeds one year.
        :raises RuntimeError: If no data is available for the specified date
            range and report type.

        :return: A list of dictionaries containing deal records for the
            requested report type.
        :rtype: list[dict]
        """
        if from_date > to_date:
            raise ValueError("fromdate must be earlier than or equal to todate.")

        if (to_date - from_date).days > 365:
            raise ValueError("The date range cannot exceed one year.")

        params = {
            "optionType": option_type,
            "from": from_date.strftime("%d-%m-%Y"),
            "to": to_date.strftime("%d-%m-%Y"),
        }

        url = f"{self.base_url}/historicalOR/bulk-block-short-deals"

        data = self._transport.request(url, params=params).json()

        if "data" not in data or len(data["data"]) < 1:
            raise RuntimeError(
                f"No {option_type} data available from {from_date:%d-%m-%Y} to {to_date:%d-%m-%Y}."
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
        If the downloaded file is a ``.zip`` or ``.gz`` archive, extracts its
        contents to the specified folder and returns the extracted file path.

        :param url: URL of the document to download e.g.
            ``https://archives.nseindia.com/annual_reports/AR_ULTRACEMCO_2010_2011_08082011052526.zip``
        :type url: str
        :param folder: Folder path to save file. If not specified, uses
            ``download_folder`` from class initialization.
        :type folder: pathlib.Path or str or None
        :param extract_files: A list of filenames to be extracted from a zip
            archive. If ``None``, the first file in the zip will be extracted. Must
            be non-empty if provided. Ignored for ``.gz`` archives.
        :type extract_files: List[str] or None

        :raise ValueError: If ``folder`` is not a directory, or if
            ``extract_files`` is provided as an empty list.
        :raise zipfile.BadZipFile: If the downloaded zip is not a valid archive.
        :raise KeyError: If a name in ``extract_files`` is not present in the zip.
        :raise OSError: If file I/O fails during download or extraction.

        :return: Path to the extracted file if the download was a ``.zip`` or
            ``.gz`` archive, otherwise the path to the saved file. For zip archives
            with ``extract_files`` specified, the last filepath in the list is
            returned.
        :rtype: pathlib.Path
        """
        folder = utils.prepare_path(folder, is_folder=True) if folder else self.dir
        file = self._transport.download(url, folder)

        suffix = file.suffix.lower()

        # Check if downloaded file is a zip file
        if suffix == ".zip" or suffix == ".gz":
            return utils.consume_archive(file, folder, extract_files)

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
        """Retrieve historical daily price and volume data for an equity symbol.

        Fetches historical trade data for ``symbol`` and ``series`` between
        ``from_date`` and ``to_date`` (both inclusive). If no dates are
        provided, data for the last 30 days ending today is returned.

        Data is fetched via NSE's Next API historical trade data endpoint.

        Reference URL:
            https://www.nseindia.com/get-quote/equity/HDFCBANK/HDFC-Bank-Limited
            (Historical data section)

        The response is a list of rows, where each row is a dictionary with
        column names as keys and their corresponding values. The trade date is
        available under the key ``mTIMESTAMP``.

        Requests covering more than 100 days are split into chunks and
        concatenated.

        Sample response:
            https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/fetch_equity_historical_data.json

        :param symbol: Exchange-traded symbol for which historical data is
            requested (e.g. ``HDFCBANK``, ``SGBAPR28I``, ``GOLDBEES``).
        :type symbol: str
        :param from_date: Start date of the data range. If ``None``, defaults
            to 30 days before ``to_date``.
        :type from_date: datetime.date or None
        :param to_date: End date of the data range. If ``None``, defaults to
            today's date.
        :type to_date: datetime.date or None
        :param series: Equity series for which historical data is requested.
            Must be one of ``AE``, ``AF``, ``BE``, ``BL``, ``EQ``, ``IL``,
            ``RL``, ``W3``, ``GB``, ``GS``. Default ``EQ``.
        :type series: str

        :raises TypeError: If ``from_date`` or ``to_date`` is not an instance
            of :class:`datetime.date`.
        :raises ValueError: If ``from_date`` occurs after ``to_date``.

        :return: A list of dictionaries, each representing one day of
            historical trade data. The list is ordered chronologically from
            **oldest to newest**.
        :rtype: list[dict]
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

        date_chunks = utils.split_date_range(from_date, to_date, 100)

        data = []

        for chunk in date_chunks:
            data += reversed(
                self._transport.request(
                    url=self.next_api_url,
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
        """Download historical India VIX data within a date range.

        Reference URL:
            https://www.nseindia.com/reports-indices-historical-vix

        Each row is a dictionary with column names as keys and their
        corresponding values. The date is stored under the key
        ``EOD_TIMESTAMP``.

        Requests spanning more than one year are split into chunks and
        concatenated.

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/fetch_historical_vix_data.json>`__

        :param from_date: Start date from which to fetch data. If ``None``,
            defaults to 30 days before ``to_date``.
        :type from_date: datetime.date or None
        :param to_date: End date up to which to fetch data. If ``None``,
            defaults to today's date.
        :type to_date: datetime.date or None

        :raises TypeError: If ``from_date`` or ``to_date`` is not an instance
            of :class:`datetime.date`.
        :raises ValueError: If ``from_date`` is greater than ``to_date``.

        :return: A list of rows, each row a dictionary with column names
            mapped to values. Returned in the order provided by NSE
            (newest-first).
        :rtype: list[dict]
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

        date_chunks = utils.split_date_range(from_date, to_date)

        data = []

        for chunk in date_chunks:
            data += self._transport.request(
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
        """Download historical futures and options data within a date range.

        Reference URL:
            https://www.nseindia.com/report-detail/fo_eq_security

        Each row is a dictionary with column names as keys and their
        corresponding values.

        Requests spanning more than one year are split into chunks and
        concatenated.

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/fetch_historical_fno_data.json>`__

        :param symbol: Symbol name.
        :type symbol: str
        :param instrument: Instrument name. One of ``FUTIDX``, ``FUTSTK``,
            ``OPTIDX``, ``OPTSTK``, ``FUTIVX``. Default ``FUTIDX``.
        :type instrument: str
        :param from_date: Start date from which to fetch data. If ``None``,
            defaults to 30 days before ``to_date``.
        :type from_date: datetime.date or None
        :param to_date: End date up to which to fetch data. If ``None``,
            defaults to today's date.
        :type to_date: datetime.date or None
        :param expiry: Optional expiry date of the instrument to filter
            results. When provided, the ``year`` parameter sent to NSE is
            derived from this date.
        :type expiry: datetime.date or None
        :param option_type: Optional filter for option type. Required when
            ``instrument`` is ``OPTIDX`` or ``OPTSTK``. Must be ``CE`` or
            ``PE``.
        :type option_type: str or None
        :param strike_price: Optional strike price filter.
        :type strike_price: float or None

        :raises TypeError: If ``from_date``, ``to_date``, or ``expiry`` is
            not an instance of :class:`datetime.date`.
        :raises ValueError: If ``from_date`` is greater than ``to_date``.
        :raises ValueError: If ``instrument`` is ``OPTIDX`` or ``OPTSTK`` and
            ``option_type`` is not specified.

        :return: A list of rows, each row a dictionary with column names
            mapped to values. The list is ordered chronologically from
            **oldest to newest**.
        :rtype: list[dict]
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

        date_chunks = utils.split_date_range(from_date, to_date)

        data = []

        for chunk in date_chunks:
            params["from"] = chunk[0].strftime("%d-%m-%Y")
            params["to"] = chunk[1].strftime("%d-%m-%Y")

            data += self._transport.request(
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
        """Retrieve historical index data for an NSE index within a date range.

        Downloads historical index data between ``from_date`` and ``to_date``
        (both inclusive) via NSE's ``/historicalOR/indicesHistory`` endpoint,
        returned in a flattened, row-based format.

        Reference URL:
            https://www.nseindia.com/reports-indices-historical-index-data

        The returned data is a list of dictionaries, where each dictionary
        represents a single trading day. Price and turnover values are merged
        into the same row where available.

        Requests spanning more than one year are split into chunks and
        concatenated.

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/fetch_historical_index_data.json>`__

        :param index: Name of the index for which historical data is
            requested.
        :type index: str
        :param from_date: Start date of the data range. If ``None``, defaults
            to 30 days before ``to_date``.
        :type from_date: datetime.date or None
        :param to_date: End date of the data range. If ``None``, defaults to
            today's date.
        :type to_date: datetime.date or None

        :raises TypeError: If ``from_date`` or ``to_date`` is not an instance
            of :class:`datetime.date`.
        :raises ValueError: If ``from_date`` occurs after ``to_date``.

        :return: A list of dictionaries, each representing one day of
            historical index data. The list is ordered chronologically from
            **oldest to newest**.
        :rtype: list[dict]
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

        date_chunks = utils.split_date_range(from_date, to_date)

        data = []

        for chunk in date_chunks:
            dct = self._transport.request(
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
        """Fetch the indices and stocks for which FnO contracts are available
        to trade.

        Reference URL:
            https://www.nseindia.com/market-data/securities-available-for-trading

        :return: A dictionary with keys ``IndexList`` and ``UnderlyingList``.
            The values are lists of indices and stocks, each with their names
            and tickers, in alphabetical order for stocks.
        :rtype: dict[str, list[dict[str, str]]]
        """
        url = f"{self.base_url}/underlying-information"
        data = self._transport.request(url).json()["data"]
        return data

    def fetch_index_names(self) -> Dict[str, List[Tuple[str, str]]]:
        """Return the list of index names.

        Returns a dictionary with a list of tuples. Each tuple contains the
        short index name and the full name of the index. The full name can be
        passed as the ``index`` parameter to
        :meth:`fetch_historical_index_data`.

        :return: A dictionary mapping a key to a list of ``(short_name,
            full_name)`` tuples.
        :rtype: dict[str, list[tuple[str, str]]]
        """
        return self._transport.request(f"{self.base_url}/index-names").json()

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
        """Return file metadata for daily reports in a given segment.

        The returned dictionary contains info about the current day's and
        previous day's reports, useful for checking whether a report is ready
        and updated before attempting a download.

        :param segment: The market segment to retrieve metadata for. One of
            ``CM``, ``INDEX``, ``SLBS``, ``SME``, ``FO``, ``COM``, ``CD``,
            ``NBF``, ``WDM``, ``CBM``, ``TRI-PARTY``. Default ``CM``.
        :type segment: str

        :return: A dictionary containing metadata about the daily report files
            for the specified segment.
        :rtype: dict
        """
        return self._transport.request(
            f"{self.base_url}/daily-reports", params=dict(key=segment)
        ).json()

    def get_detailed_scrip_data(
        self,
        symbol: str,
        series: Literal["EQ", "BE", "BZ", "SM", "ST", "SZ"] = "EQ",
        market_type: str = "N",
    ) -> Dict:
        """Retrieve detailed symbol data for an equity or SME symbol.

        Fetches comprehensive data including order book, metadata, trade
        information, price information, and security information for the
        given symbol and series via NSE's Next API.

        Reference URL:
            https://www.nseindia.com/get-quotes/equity?symbol=ETERNAL

        Sample response:
            https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/get_detailed_scrip_data.json

        :param symbol: Exchange-traded symbol for which data is requested
            (e.g. ``ETERNAL``, ``HDFCBANK``).
        :type symbol: str
        :param series: Equity or SME series. Must be one of ``EQ``, ``BE``,
            ``BZ``, ``SM``, ``ST``, or ``SZ``. Default ``EQ``.
            `Reference <https://www.nseindia.com/market-data/legend-of-series>`_
        :type series: str
        :param market_type: Market type for which data is requested. Default
            ``N``.
        :type market_type: str

        :return: A dictionary containing detailed symbol data.
        :rtype: dict
        """
        params = dict(
            functionName="getSymbolData",
            marketType=market_type,
            series=series.upper(),
            symbol=symbol.upper(),
        )

        return self._transport.request(self.next_api_url, params=params).json()

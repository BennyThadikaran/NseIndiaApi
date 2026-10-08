import logging
from importlib.metadata import version
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlsplit

import httpx
from pyrate_limiter import Duration, Limiter, Rate

from .cookie_store import CookieStore, FileCookieStore
from .retry import STATUS_FORCELIST, RetryableStatusError, RetryConfig, retry

logger = logging.getLogger(__name__)


class NSEFileUnavailableError(Exception):
    """Raised when the requested NSE file is unavailable or not yet updated.

    This exception is raised by :meth:`Transport.download` when the server
    responds with an HTTP ``404 Not Found`` status. It signals that the file
    either does not exist on the NSE server or has not yet been published for
    the current period.

    .. note::
        This exception is **not** in the retry trigger list, so it propagates
        immediately to the caller without any retry attempts.
    """


class Transport:
    """HTTP transport layer for interacting with the NSE website, providing
    throttled, retrying request and download methods with cookie handling.

    The transport manages an underlying :class:`httpx.Client` session, a cookie
    store, a rate limiter, and retry configuration. Cookies are loaded from the
    cookie store on session start; if the store is empty, cookies are fetched
    from the NSE option-chain page and persisted.

    :param folder: Directory used to store the default cookie file and as a
        base location for downloads.
    :type folder: Path
    :param headers: HTTP headers sent with every request (e.g. ``User-Agent``,
        ``Accept-Language``).
    :type headers: Dict[str, Any]
    :param cookie_store: Cookie storage backend. If ``None``, a
        :class:`FileCookieStore` is created using ``folder / cookie_filename``.
        Defaults to ``None``.
    :type cookie_store: Optional[CookieStore]
    :param throttle: Rate limiter instance. If ``None``, a default limiter of
        ``3 requests per second`` is created. Defaults to ``None``.
    :type throttle: Optional[Limiter]
    :param retry_config: Retry policy configuration. If ``None``, a default
        :class:`RetryConfig` is used. Defaults to ``None``.
    :type retry_config: RetryConfig | None
    :param use_http2: Whether to enable HTTP/2 for the underlying client.
        Defaults to ``False``.
    :type use_http2: bool
    :param timeout: Request timeout in seconds. Defaults to ``15``.
    :type timeout: int
    :param cookie_filename: Filename used for the default file cookie store
        when ``cookie_store`` is not provided. If ``None``, defaults to
        ``"cookies.txt"``. Defaults to ``None``.
    :type cookie_filename: Optional[str]

    .. note::
       The default rate limiter uses separate buckets named ``"api"`` (for
       :meth:`request`) and ``"file"`` (for :meth:`download`), but both share
       the same :class:`Limiter` instance and therefore the same rate budget of
       3 requests per second.

    .. note::
       A session is created immediately on instantiation via
       :meth:`_start_session`, which may trigger a network request to fetch
       cookies if the configured cookie store is empty.
    """

    def __init__(
        self,
        folder: Path,
        headers: Dict[str, Any],
        cookie_store: Optional[CookieStore] = None,
        throttle: Optional[Limiter] = None,
        retry_config: Optional[RetryConfig] = None,
        use_http2: bool = False,
        timeout: int = 15,
        cookie_filename: Optional[str] = None,
    ) -> None:

        self.timeout = timeout

        if version("pyrate_limiter") == "3.9.0":
            self.throttle = throttle or Limiter(
                Rate(3, Duration.SECOND),
                raise_when_fail=False,
                max_delay=2000,
            )
        else:
            self.throttle = throttle or Limiter(Rate(3, Duration.SECOND))

        self.retry_config = retry_config or RetryConfig()

        if cookie_filename is None:
            cookie_filename = "cookies.txt"

        self.cookie_store = cookie_store or FileCookieStore(
            path=folder / cookie_filename
        )

        self.use_http2 = use_http2
        self.headers = headers

        self._start_session()

    def _start_session(self) -> None:
        """Create a new :class:`httpx.Client` session and populate it with cookies.

        A new client is constructed using the configured headers, HTTP/2 setting,
        and timeout. Cookies are then loaded from the cookie store; if the store is
        empty, cookies are fetched from NSE via :meth:`_fetch_cookies` and saved
        back to the store.

        :return: ``None``
        :rtype: None

        .. note::
           This method is called during ``__init__`` and again by
           :meth:`_restart_session` after session failures.
        """
        self._session = httpx.Client(
            headers=self.headers,
            http2=self.use_http2,
            timeout=self.timeout,
        )

        cookies = self.cookie_store.load()

        if not cookies.jar:
            cookies = self._fetch_cookies()
            self.cookie_store.save(cookies)

        self._session.cookies.update(cookies)

    def _restart_session(self) -> None:
        """Restart the underlying HTTP session.

        Attempts to cleanly close the existing session via :meth:`exit`, then
        creates a fresh session via :meth:`_start_session`.

        :return: ``None``
        :rtype: None

        .. note::
           If closing the old session fails, the exception is logged (with
           traceback) but suppressed, and the restart proceeds regardless. This
           method is invoked automatically by the :func:`retry` decorator when an
           :class:`httpx.RemoteProtocolError` is caught.
        """
        try:
            self.exit()
        except Exception:
            logger.exception("Failed to cleanly exit old session during restart.")
        self._start_session()

    def exit(self):
        """Persist cookies and close the underlying HTTP session.

        Saves the current session cookies to the cookie store, then closes the
        :class:`httpx.Client` session.

        :return: ``None``
        :rtype: None

        .. note::
           This method is called by :meth:`_restart_session` and should typically be
           called by the user when the transport is no longer needed to ensure
           cookies are flushed to persistent storage.
        """
        self.cookie_store.save(self._session.cookies)
        self._session.close()

    def _fetch_cookies(self) -> httpx.Cookies:
        """Fetch fresh cookies from the NSE website.

        Performs a request to the NSE option-chain page and returns the cookies set
        by the server.

        :return: The cookies returned by the NSE server.
        :rtype: httpx.Cookies

        .. note::
           This method calls :meth:`request`, which is decorated with :func:`retry`
           and therefore subject to the configured retry policy and throttle.
        """
        r = self.request("https://www.nseindia.com/option-chain")
        return r.cookies

    @retry
    def request(self, url, params=None):
        """Perform a throttled, retrying HTTP GET request.

        The request is subject to the rate limiter (bucket ``"api"``) and the
        configured retry policy. Responses with a status code in
        :data:`STATUS_FORCELIST` (``429``, ``502``, ``503``, ``504``) are converted
        into :class:`RetryableStatusError` to trigger retries. Any other non-2xx
        status raises via :meth:`httpx.Response.raise_for_status`.

        :param url: The URL to request.
        :type url: str
        :param params: Optional query parameters to include in the request.
            Defaults to ``None``.
        :type params: Optional[dict]
        :return: The successful HTTP response.
        :rtype: httpx.Response

        :raises RetryableStatusError: When the response status code is in
            :data:`STATUS_FORCELIST`. This triggers a retry; if retries are
            exhausted, the exception propagates.
        :raises httpx.HTTPStatusError: For any other non-2xx status code, raised by
            :meth:`httpx.Response.raise_for_status`.
        :raises httpx.TimeoutException: If the request times out and retries are
            exhausted.
        :raises httpx.ConnectError: If a connection error occurs and retries are
            exhausted.
        :raises httpx.ReadError: If a read error occurs and retries are exhausted.
        :raises httpx.RemoteProtocolError: If a protocol error occurs and retries
            are exhausted.

        .. note::
           The ``"api"`` throttle bucket must be acquired before the request is
           sent, so callers may block waiting for rate-limit capacity.
        """
        self.throttle.try_acquire("api")

        r = self._session.get(url, params=params)

        if r.status_code in STATUS_FORCELIST:
            raise RetryableStatusError(
                f"HTTP error: {r.status_code} - {r.reason_phrase}",
                request=r.request,
                response=r,
            )

        r.raise_for_status()

        return r

    @retry
    def download(self, url: str, folder: Path):
        """Download a file from a URL to the given folder, with throttling and retries.

        The filename is derived from the last path segment of ``url``. If a file
        with that name already exists in ``folder``, it is returned immediately
        without downloading. Downloads are written to a temporary ``.part`` file
        and atomically renamed to the final path only on success.

        The download is subject to the rate limiter (bucket ``"file"``) and the
        configured retry policy.

        :param url: The URL of the file to download.
        :type url: str
        :param folder: The directory in which to save the downloaded file.
        :type folder: Path
        :return: The path to the downloaded (or already existing) file.
        :rtype: Path

        :raises RuntimeError: If no filename can be detected in the URL (i.e. the
            path is empty or ends in ``/``).
        :raises NSEFileUnavailableError: If the server responds with HTTP ``404``,
            indicating the file is unavailable or not yet updated. This exception
            is **not** retried and propagates immediately.
        :raises RetryableStatusError: When the response status code is in
            :data:`STATUS_FORCELIST`. This triggers a retry; if retries are
            exhausted, the exception propagates.
        :raises httpx.HTTPStatusError: For any other non-2xx status code, raised by
            :meth:`httpx.Response.raise_for_status`.
        :raises httpx.TimeoutException: If the request times out and retries are
            exhausted.
        :raises httpx.ConnectError: If a connection error occurs and retries are
            exhausted.
        :raises httpx.ReadError: If a read error occurs and retries are exhausted.
        :raises httpx.RemoteProtocolError: If a protocol error occurs and retries
            are exhausted.

        .. note::
           Downloads are streamed in 1 MB chunks to limit memory usage.

        .. note::
           If writing the temporary file fails for any reason, the partial
           ``.part`` file is deleted before the exception is re-raised.

        .. note::
           The ``.part`` file is atomically replaced onto the final path only after
           the full download completes successfully, so a partially downloaded file
           will never be present at the returned path.

        .. warning::
           If a file already exists at the target path, it is returned as-is
           without any freshness or integrity check. Delete the file beforehand if
           you need to force a re-download.
        """
        url_path = urlsplit(url).path

        fpath = folder / Path(url_path).name

        if not fpath.name:
            raise RuntimeError(f"Path not detected in url: {url}")

        # check if the file was already downloaded and return it
        if fpath.exists():
            return fpath

        # filename.csv -> filename.csv.part
        tmp = fpath.with_suffix(fpath.suffix + ".part")

        self.throttle.try_acquire("file")

        with self._session.stream("GET", url=url) as r:
            if r.status_code == 404:
                raise NSEFileUnavailableError(
                    "NSE file is unavailable or not yet updated."
                )

            if r.status_code in STATUS_FORCELIST:
                raise RetryableStatusError(
                    f"HTTP error: {r.status_code} - {r.reason_phrase}",
                    request=r.request,
                    response=r,
                )

            r.raise_for_status()

            try:
                with tmp.open(mode="wb") as f:
                    for chunk in r.iter_bytes(chunk_size=1000000):
                        f.write(chunk)
                tmp.replace(fpath)
            except BaseException:
                tmp.unlink(missing_ok=True)
                raise

        return fpath

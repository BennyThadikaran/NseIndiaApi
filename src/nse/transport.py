import logging
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlsplit

import httpx
from pyrate_limiter import Duration, Limiter, Rate

from .cookie_store import CookieStore, FileCookieStore
from .retry import STATUS_FORCELIST, RetryableStatusError, RetryConfig, retry

logger = logging.getLogger(__name__)


class NSEFileUnavailableError(Exception):
    """Raised when the requested NSE file is unavailable or not yet updated."""


class Transport:
    def __init__(
        self,
        folder: Path,
        headers: Dict[str, Any],
        cookie_store: Optional[CookieStore] = None,
        throttle: Optional[Limiter] = None,
        retry_config: RetryConfig | None = None,
        use_http2: bool = False,
        timeout: int = 15,
        cookie_filename: str = "cookies_httpx.txt",
    ) -> None:

        self.timeout = timeout

        self.throttle = throttle or Limiter(Rate(3, Duration.SECOND))

        self.retry_config = retry_config or RetryConfig()

        self.cookie_store = cookie_store or FileCookieStore(
            path=folder / cookie_filename,
            fetcher=self._fetch_cookies,
        )

        self.use_http2 = use_http2
        self.headers = headers

        self._start_session()

    def _start_session(self) -> None:
        self._session = httpx.Client(
            headers=self.headers,
            http2=self.use_http2,
            timeout=self.timeout,
        )
        self._session.cookies.update(self.cookie_store.load())

    def _restart_session(self) -> None:
        try:
            self.exit()
        except Exception:
            logger.exception("Failed to cleanly exit old session during restart.")
        self._start_session()

    def exit(self):
        self.cookie_store.save(self._session.cookies)
        self._session.close()

    def _fetch_cookies(self) -> httpx.Cookies:
        r = self.request("https://www.nseindia.com/option-chain")
        return r.cookies

    @retry
    def request(self, url, params=None):
        """Make a http request"""
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
        """Download a large file in chunks from the given url.
        Returns pathlib.Path object of the downloaded file
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
            except Exception:
                tmp.unlink(missing_ok=True)
                raise

        return fpath

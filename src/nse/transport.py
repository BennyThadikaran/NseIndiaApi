from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlsplit

import httpx
from pyrate_limiter import Duration, Limiter, Rate

from .cookie_store import CookieStore, FileCookieStore


class Transport:
    def __init__(
        self,
        folder: Path,
        headers: Dict[str, Any],
        cookie_store: Optional[CookieStore] = None,
        throttle: Optional[Limiter] = None,
        use_http2: bool = False,
        timeout: int = 15,
        cookie_filename: str = "cookies_httpx.txt",
    ) -> None:

        self.timeout = timeout

        self.cookie_store = cookie_store or FileCookieStore(
            path=folder / cookie_filename,
            fetcher=self._fetch_cookies,
        )

        self.throttle = throttle or Limiter(Rate(3, Duration.SECOND))

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
        self.exit()
        self._start_session()

    def exit(self):
        self.cookie_store.save(self._session.cookies)
        self._session.close()

    def _fetch_cookies(self) -> httpx.Cookies:
        r = self.request("https://www.nseindia.com/option-chain")
        return r.cookies

    def request(self, url, params=None):
        """Make a http request"""
        self.throttle.try_acquire("api")

        try:
            r = self._session.get(url, params=params)
        except httpx.ReadTimeout as e:
            raise TimeoutError("The request timed out.") from e
        except httpx.RemoteProtocolError as e:
            self.exit()
            raise ConnectionError(
                "The connection to the remote server was unexpectedly closed."
            ) from e

        if not 200 <= r.status_code < 300:
            raise ConnectionError(f"{url} {r.status_code}: {r.reason_phrase}")

        return r

    def download(self, url: str, folder: Path):
        """Download a large file in chunks from the given url.
        Returns pathlib.Path object of the downloaded file
        """
        url_path = urlsplit(url).path

        fname = folder / Path(url_path).name

        if not fname.name:
            raise RuntimeError(f"Path not detected in url: {url}")

        self.throttle.try_acquire("file")

        with self._session.stream("GET", url=url) as r:
            contentType = r.headers.get("content-type")

            if contentType and "text/html" in contentType:
                raise RuntimeError("NSE file is unavailable or not yet updated.")

            with fname.open(mode="wb") as f:
                for chunk in r.iter_bytes(chunk_size=1000000):
                    f.write(chunk)

        return fname

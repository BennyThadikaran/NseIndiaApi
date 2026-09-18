from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from mthrottle import Throttle

from .cookie_store import CookieStore, FileCookieStore

throttleConfig = {
    "default": {
        "rps": 3,
    },
}

th = Throttle(throttleConfig, 10)


class Transport:
    def __init__(
        self,
        folder: Path,
        headers: Dict[str, Any],
        cookie_store: Optional[CookieStore] = None,
        server: bool = False,
        timeout: int = 15,
        cookie_filename: str = "cookies_httpx.txt",
    ) -> None:

        self.timeout = timeout

        self.cookie_path = folder / "nse_cookies_httpx.json"

        self.cookie_store = cookie_store or FileCookieStore(
            path=folder / cookie_filename,
            fetcher=self._fetch_cookies,
        )

        self._session = httpx.Client(http2=server)
        self._session.headers.update(headers)
        self._session.cookies.update(self.cookie_store.load())

    def exit(self):
        self.cookie_store.save(self._session.cookies)
        self._session.close()

    def _fetch_cookies(self) -> httpx.Cookies:
        r = self.request("https://www.nseindia.com/option-chain")
        return r.cookies

    def request(self, url, params=None):
        """Make a http request"""
        th.check()

        try:
            r = self._session.get(url, params=params, timeout=self.timeout)
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
        fname = folder / url.split("/")[-1]

        th.check()

        with self._session.stream("GET", url=url, timeout=self.timeout) as r:
            contentType = r.headers.get("content-type")

            if contentType and "text/html" in contentType:
                raise RuntimeError("NSE file is unavailable or not yet updated.")

            with fname.open(mode="wb") as f:
                for chunk in r.iter_bytes(chunk_size=1000000):
                    f.write(chunk)

        return fname

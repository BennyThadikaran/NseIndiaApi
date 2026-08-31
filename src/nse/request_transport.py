import json
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any, Dict

import requests
from mthrottle import Throttle

throttleConfig = {
    "default": {
        "rps": 3,
    },
}

th = Throttle(throttleConfig, 10)


class RequestTransport:
    def __init__(
        self, folder: Path, headers: Dict[str, Any], timeout: int = 15
    ) -> None:
        self.timeout = timeout
        self.folder = folder

        self._session = requests.Session()
        self.cookie_path = folder / "nse_cookies_requests.json"

        self._session.headers.update(headers)
        self._session.cookies.update(self._getCookies())

    def _setCookies(self):
        r = self.request("https://www.nseindia.com/option-chain")

        cookies = r.cookies
        self.cookie_path.write_text(
            json.dumps(requests.utils.dict_from_cookiejar(cookies))
        )

        return cookies

    def _getCookies(self):
        if self.cookie_path.exists():
            cookies = requests.utils.add_dict_to_cookiejar(
                CookieJar(), json.loads(self.cookie_path.read_bytes())
            )

            if self._hasCookiesExpired(cookies):
                cookies = self._setCookies()

            return cookies

        return self._setCookies()

    @staticmethod
    def _hasCookiesExpired(cookies) -> bool:
        for cookie in cookies:
            if cookie.is_expired():
                return True
        return False

    def exit(self):
        self._session.close()
        self.cookie_path.unlink(missing_ok=True)

    def download(self, url: str, folder: Path):
        """Download a large file in chunks from the given url.
        Returns pathlib.Path object of the downloaded file
        """
        fname = folder / url.split("/")[-1]

        th.check()

        with self._session.get(url, stream=True, timeout=self.timeout) as r:
            contentType = r.headers.get("content-type")

            if contentType and "text/html" in contentType:
                raise RuntimeError("NSE file is unavailable or not yet updated.")

            with fname.open(mode="wb") as f:
                for chunk in r.iter_content(chunk_size=1000000):
                    f.write(chunk)

        return fname

    def request(self, url, params=None):
        """Make a http request"""
        th.check()

        try:
            r = self._session.get(url, params=params, timeout=self.timeout)
        except requests.ReadTimeout as e:
            raise TimeoutError("Request timed out") from e
        except requests.exceptions.ConnectionError as e:
            self.exit()
            raise ConnectionError(
                "The connection to the remote server was unexpectedly closed."
            ) from e

        if not 200 <= r.status_code < 300:
            raise ConnectionError(f"{url} {r.status_code}: {r.reason}")

        return r

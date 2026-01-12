import pickle
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from context import NSE
from httpx import Cookies
from requests.cookies import RequestsCookieJar

DIR = Path(__file__).parent
timestamp = int((datetime.now(tz=UTC) - timedelta(1)).timestamp())

requests_cookie_file = DIR / "nse_cookies_requests.pkl"
httpx_cookie_file = DIR / "nse_cookies_httpx.pkl"


class TestNseCookies(unittest.TestCase):
    """Tests NSE class cookie handling behaviour for both requests and httpx library.

    Tests check if:

    - Cookie files are namespaced to the library in use.
    - Cookie file if exists is reused.
    - Cookie files are reset if expired.
    """

    def test_h1_cookies_files_exist_on_init(self):
        """Test if cookies are saved to file when using requests library"""
        nse = NSE(download_folder=DIR, server=False)

        self.assertTrue(requests_cookie_file.exists())
        nse.exit()

    def test_h1_cookies_loaded_if_exists(self):
        """Test if cookies are loaded from file, when using requests library"""
        nse = NSE(download_folder=DIR, server=False)

        self.assertTrue(requests_cookie_file.exists())

        with patch(
            "pathlib.Path.read_bytes",
            return_value=requests_cookie_file.read_bytes(),
        ) as mock_file:
            nse2 = NSE(download_folder=DIR, server=False)

            mock_file.assert_called_once()

        nse.exit()
        nse2.exit()

    def test_h1_cookies_reset_on_expiry(self):
        """Test if cookies are reset when expired, using requests library"""
        cookie_jar = RequestsCookieJar()

        cookie_jar.set(
            name="nsit",
            value="nse",
            domain="www.nseindia.com",
            expires=timestamp,
        )

        requests_cookie_file.write_bytes(pickle.dumps(cookie_jar))

        nse = NSE(download_folder=DIR, server=False)

        cookie_jar = pickle.loads(requests_cookie_file.read_bytes())

        # Cookies not expired
        for cookie in cookie_jar:
            self.assertFalse(cookie.is_expired())

        nse.exit()

    def test_h2_cookies_files_exist_on_init(self):
        """Test if cookies are saved to file when using httpx library"""
        nse = NSE(download_folder=DIR, server=True)

        self.assertTrue(httpx_cookie_file.exists())
        nse.exit()

    def test_h2_cookies_loaded_if_exists(self):
        """Test if cookies are loaded from file, when using httpx library"""
        nse_1 = NSE(download_folder=DIR, server=True)

        self.assertTrue(httpx_cookie_file.exists())

        with patch(
            "pathlib.Path.read_bytes",
            return_value=httpx_cookie_file.read_bytes(),
        ) as mock_file:
            nse_2 = NSE(download_folder=DIR, server=True)

            mock_file.assert_called_once()

        nse_1.exit()
        nse_2.exit()

    def test_h2_cookies_reset_on_expiry(self):
        """Test if cookies are reset when expired, using httpx library"""
        cookies = dict(nsit="nse", expires=timestamp)

        httpx_cookie_file.write_bytes(pickle.dumps(cookies))

        nse = NSE(download_folder=DIR, server=True)

        cookie_jar = Cookies(pickle.loads(httpx_cookie_file.read_bytes()))

        # Cookies not expired
        for cookie in cookie_jar.jar:
            self.assertFalse(cookie.is_expired())

        nse.exit()


if __name__ == "__main__":
    unittest.main()

import logging
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import httpx

from nse import MemoryCookieStore
from nse.transport import (
    NSEFileUnavailableError,
    Transport,
)

# helpers


class FakeStreamResponse:
    """Minimal stand-in for the object returned by httpx.Client.stream(...)."""

    def __init__(self, status_code, chunks=None, url="https://x/file.csv"):
        self.status_code = status_code
        self.reason_phrase = "reason"
        self.request = httpx.Request("GET", url)
        self._chunks = chunks or []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=self.request, response=self)

    def iter_bytes(self, chunk_size):
        yield from self._chunks


class FakeCookieStore(MemoryCookieStore):
    """In-memory cookie store with controllable load/save."""

    def __init__(self, initial=None):
        self._cookies = initial or httpx.Cookies()
        self.saved = []

    def save(self, cookies):
        self.saved.append(cookies)
        self._cookies = cookies


class TransportTestCase(unittest.TestCase):
    """Base class giving each test a tmp dir and a make_transport helper."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_path = Path(self._tmp.name)

    def make_transport(self, cookies=None, **kwargs):
        """Build a Transport with a fake session, bypassing _start_session network."""
        with mock.patch.object(Transport, "_start_session", return_value=None):
            t = Transport(
                folder=self.tmp_path,
                headers={},
                cookie_store=FakeCookieStore(cookies),
                **kwargs,
            )
        t._session = mock.MagicMock(spec=httpx.Client)
        return t


# download: exception during write cleans up .part


class TestDownloadCleanupOnError(TransportTestCase):
    def test_partial_file_removed_and_exception_reraised(self):
        t = self.make_transport()
        url = "https://x/file.csv"
        final = self.tmp_path / "file.csv"
        part = self.tmp_path / "file.csv.part"

        def boom(chunk_size):
            yield b"partial data"
            raise RuntimeError("connection dropped")

        resp = FakeStreamResponse(200)
        resp.iter_bytes = boom
        t._session.stream.return_value = resp

        with self.assertRaises(RuntimeError) as ctx:
            t.download(url, self.tmp_path)

        self.assertIn("connection dropped", str(ctx.exception))
        self.assertFalse(part.exists(), ".part file should be cleaned up")
        self.assertFalse(final.exists(), "final file should not exist on failure")


# download: existing file short-circuits


class TestDownloadExistingFile(TransportTestCase):
    def test_existing_file_returns_without_network_call(self):
        t = self.make_transport()
        url = "https://x/file.csv"
        final = self.tmp_path / "file.csv"
        final.write_bytes(b"already here")

        result = t.download(url, self.tmp_path)

        self.assertEqual(result, final)
        self.assertEqual(final.read_bytes(), b"already here")
        t._session.stream.assert_not_called()


# download: 404 raises NSEFileUnavailableError, no .part


class TestDownload404(TransportTestCase):
    def test_404_raises_and_leaves_no_part_file(self):
        t = self.make_transport()
        url = "https://x/file.csv"
        part = self.tmp_path / "file.csv.part"
        final = self.tmp_path / "file.csv"

        t._session.stream.return_value = FakeStreamResponse(404, url=url)

        with self.assertRaises(NSEFileUnavailableError):
            t.download(url, self.tmp_path)

        self.assertFalse(part.exists())
        self.assertFalse(final.exists())


# _restart_session: exit() failure doesn't block restart


class TestRestartSession(TransportTestCase):
    def _build(self):
        with mock.patch.object(Transport, "_start_session", return_value=None):
            return Transport(
                folder=self.tmp_path,
                headers={},
                cookie_store=FakeCookieStore(),
            )

    def test_restart_continues_even_if_exit_raises(self):
        t = self._build()
        t.exit = mock.MagicMock(side_effect=RuntimeError("close failed"))
        t._start_session = mock.MagicMock()

        # Should not propagate the exit() exception.
        with self.assertLogs("nse.transport", level=logging.ERROR) as cm:
            t._restart_session()

        t.exit.assert_called_once()
        t._start_session.assert_called_once()

        self.assertTrue(
            any(
                "Failed to cleanly exit old session during restart" in msg
                for msg in cm.output
            ),
            cm.output,
        )


# ---------- 5. _start_session: cached cookies skip the fetch ----------


class TestStartSessionCookieFlow(TransportTestCase):
    def test_cached_cookies_skip_network_fetch(self):
        cached = httpx.Cookies()
        cached.set("sessionid", "abc")
        store = FakeCookieStore(initial=cached)

        with mock.patch("nse.transport.httpx.Client") as Client:
            client = Client.return_value
            client.cookies = httpx.Cookies()

            Transport(folder=self.tmp_path, headers={}, cookie_store=store)

        Client.assert_called_once()
        self.assertEqual(client.cookies.get("sessionid"), "abc")
        client.get.assert_not_called()
        self.assertEqual(store.saved, [])

    def test_empty_jar_fetches_and_saves(self):
        store = FakeCookieStore(initial=httpx.Cookies())  # empty

        fetched = httpx.Cookies()
        fetched.set("sessionid", "fresh")

        with mock.patch("nse.transport.httpx.Client") as Client:
            client = Client.return_value
            client.cookies = httpx.Cookies()

            with mock.patch.object(
                Transport, "_fetch_cookies", return_value=fetched
            ) as fetch:
                Transport(folder=self.tmp_path, headers={}, cookie_store=store)

        fetch.assert_called_once()
        self.assertEqual(store.saved, [fetched])
        self.assertEqual(client.cookies.get("sessionid"), "fresh")


if __name__ == "__main__":
    unittest.main()

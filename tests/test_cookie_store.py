import tempfile
import unittest
from http.cookiejar import Cookie
from pathlib import Path
from typing import Optional

import httpx
from context import FileCookieStore, MemoryCookieStore


def make_cookie(
    name: str = "session",
    value: str = "abc123",
    domain: str = "example.com",
    path: str = "/",
    secure: bool = False,
    expires: Optional[int] = None,
    discard: bool = False,
) -> Cookie:
    """Helper to build a Cookie with controllable attributes."""
    return Cookie(
        version=0,
        name=name,
        value=value,
        port=None,
        port_specified=False,
        domain=domain,
        domain_specified=bool(domain),
        domain_initial_dot=domain.startswith("."),
        path=path,
        path_specified=bool(path),
        secure=secure,
        expires=expires,
        discard=discard,
        comment=None,
        comment_url=None,
        rest={},
        rfc2109=False,
    )


def cookies_with(*cookies: Cookie) -> httpx.Cookies:
    httpx_cookies = httpx.Cookies()

    for c in cookies:
        httpx_cookies.jar.set_cookie(c)

    return httpx_cookies


class FileCookieStoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "cookies.txt"
        self.store = FileCookieStore(self.path)

    def tearDown(self):
        self._tmp.cleanup()

    def test_creates_parent_directories(self):
        nested = Path(self._tmp.name) / "a" / "b" / "cookies.txt"
        FileCookieStore(nested)
        self.assertTrue(nested.parent.is_dir())

    def test_save_creates_file(self):
        self.store.save(cookies_with(make_cookie(expires=4102444800)))
        self.assertTrue(self.path.exists())

    def test_save_then_load_preserves_important_fields(self):
        expires = 4102444800  # 2100-01-01
        cookie = make_cookie(
            name="token",
            value="xyz",
            domain="example.com",
            path="/api",
            secure=True,
            expires=expires,
            discard=False,
        )
        self.store.save(cookies_with(cookie))

        self.assertTrue(self.path.exists())

        loaded = self.store.load()
        loaded_list = list(loaded.jar)
        self.assertEqual(len(loaded_list), 1)

        c = loaded_list[0]
        self.assertEqual(c.name, "token")
        self.assertEqual(c.value, "xyz")
        self.assertEqual(c.domain, "example.com")
        self.assertEqual(c.path, "/api")
        self.assertTrue(c.secure)
        self.assertEqual(c.expires, expires)

    def test_load_missing_file_returns_empty(self):
        self.assertFalse(self.path.exists())
        loaded = self.store.load()
        self.assertEqual(list(loaded.jar), [])

    def test_load_empty_file_returns_empty(self):
        # MozillaCookieJar needs a header line to parse
        self.path.write_text("# Netscape HTTP Cookie File\n")
        loaded = self.store.load()
        self.assertEqual(list(loaded.jar), [])

    def test_load_removes_expired_cookies(self):
        valid = make_cookie(name="valid", value="1", expires=4102444800)
        expired = make_cookie(name="expired", value="2", expires=1)

        cookies = cookies_with(valid, expired)
        self.store.save(cookies)
        self.assertTrue(self.path.exists())

        loaded = self.store.load()
        names = {c.name for c in loaded.jar}
        self.assertIn("valid", names)
        self.assertNotIn("expired", names)

    def test_load_returns_empty_when_all_expired(self):
        expired = make_cookie(name="expired", value="2", expires=1)
        self.store.save(cookies_with(expired))

        loaded = self.store.load()
        self.assertEqual(list(loaded.jar), [])

    def test_clear_deletes_file(self):
        self.store.save(cookies_with(make_cookie(expires=4102444800)))
        self.assertTrue(self.path.exists())

        self.store.clear()
        self.assertFalse(self.path.exists())

    def test_clear_missing_file_is_noop(self):
        # Should not raise
        self.store.clear()
        self.assertFalse(self.path.exists())


class MemoryCookieStoreTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryCookieStore()

    def test_load_initially_empty(self):
        loaded = self.store.load()
        self.assertEqual(list(loaded.jar), [])

    def test_save_preserves_important_fields(self):
        expires = 4102444800
        cookie = make_cookie(
            name="token",
            value="xyz",
            domain="example.com",
            path="/api",
            secure=True,
            expires=expires,
            discard=False,
        )
        self.store.save(cookies_with(cookie))

        loaded = self.store.load()
        stored = list(loaded.jar)
        self.assertEqual(len(stored), 1)

        c = stored[0]
        self.assertEqual(c.name, "token")
        self.assertEqual(c.value, "xyz")
        self.assertEqual(c.domain, "example.com")
        self.assertEqual(c.path, "/api")
        self.assertTrue(c.secure)
        self.assertEqual(c.expires, expires)

    def test_save_replaces_previous_cookies(self):
        self.store.save(
            cookies_with(make_cookie(name="a", value="1", expires=4102444800))
        )
        self.store.save(
            cookies_with(make_cookie(name="b", value="2", expires=4102444800))
        )

        loaded = self.store.load()
        names = {c.name for c in loaded.jar}
        self.assertEqual(names, {"b"})

    def test_clear_empties_jar(self):
        self.store.save(cookies_with(make_cookie(expires=4102444800)))
        self.assertNotEqual(list(self.store.load().jar), [])

        self.store.clear()
        self.assertEqual(list(self.store.load().jar), [])

    def test_clear_twice_is_safe(self):
        self.store.clear()
        self.store.clear()
        self.assertEqual(list(self.store.load().jar), [])

    def test_load_does_not_auto_filter_expired_cookies(self):
        valid = make_cookie(name="valid", value="1", expires=4102444800)
        expired = make_cookie(name="expired", value="2", expires=1)
        self.store.save(cookies_with(valid, expired))

        names = {c.name for c in self.store.load().jar}
        self.assertEqual(names, {"valid", "expired"})


if __name__ == "__main__":
    unittest.main()

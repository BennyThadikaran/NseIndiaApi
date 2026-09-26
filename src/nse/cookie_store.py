import logging
from abc import ABC, abstractmethod
from http.cookiejar import MozillaCookieJar
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)


class CookieStore(ABC):
    """Abstract base class for cookie storage backends.

    Defines the interface for loading, saving, and clearing HTTP cookies
    used by an :class:`httpx` client. Concrete implementations decide
    where and how cookies are persisted (e.g. on disk or in memory).

    """

    @abstractmethod
    def load(self) -> httpx.Cookies:
        """Return the stored cookies. May trigger a fetch if empty.

        :returns: The currently stored cookies. If no cookies are
            available, an implementation may obtain a fresh set (for
            example, via a network request) before returning.
        :rtype: httpx.Cookies
        """
        ...

    @abstractmethod
    def save(self, cookies: httpx.Cookies) -> None:
        """Save cookies to the store.

        :param cookies: The cookies to persist.
        :type cookies: httpx.Cookies
        :returns: Nothing.
        :rtype: None
        """
        ...

    @abstractmethod
    def clear(self) -> None:
        """Remove all stored cookies.

        :returns: Nothing.
        :rtype: None
        """
        ...


class FileCookieStore(CookieStore):
    """Persists cookies to a Mozilla-format cookie file on disk.

    If the file is missing or empty, :meth:`load` calls ``fetcher`` to
    obtain a fresh cookie set, then writes it to disk before returning.

    .. warning::
        This implementation is **not thread-safe**. Concurrent calls to
        :meth:`load`, :meth:`save`, or :meth:`clear` from multiple threads
        may corrupt the cookie file or produce inconsistent results.

    .. note::
        Prefer :class:`MemoryCookieStore` unless persistence across
        process restarts is actually required. The in-memory store avoids
        disk I/O, file-format quirks, and the thread-safety concerns
        described above.
    """

    def __init__(self, path: Path) -> None:
        """Initialize the file-backed cookie store.

        :param path: Location of the Mozilla-format cookie file. Parent
            directories are created if they do not already exist.
        :type path: pathlib.Path
        :param fetcher: Callable invoked to obtain a fresh set of cookies
            when the file is missing or empty.
        :type fetcher: Callable[[], httpx.Cookies]
        """
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> httpx.Cookies:
        """Load cookies from disk, fetching them if necessary.

        If the cookie file exists and contains at least one cookie, those
        cookies are loaded and returned. Otherwise ``fetcher`` is called
        to obtain a fresh set, which is saved to disk before being
        returned.

        :returns: The loaded or freshly fetched cookies.
        :rtype: httpx.Cookies
        """
        if not self.path.exists():
            return httpx.Cookies()

        jar = MozillaCookieJar(self.path)

        jar.load(ignore_discard=True, ignore_expires=False)

        if any(jar):
            return httpx.Cookies(jar)

        return httpx.Cookies()

    def save(self, cookies: httpx.Cookies) -> None:
        """Write cookies to the Mozilla-format file on disk.

        Both discarded and expired cookies are written so that the full
        jar can be restored on the next :meth:`load` call.

        :param cookies: The cookies to persist.
        :type cookies: httpx.Cookies
        :returns: Nothing.
        :rtype: None
        """
        jar = MozillaCookieJar(self.path)

        for cookie in cookies.jar:
            jar.set_cookie(cookie)

        jar.save(ignore_discard=True, ignore_expires=True)

    def clear(self) -> None:
        """Delete the cookie file from disk.

        If the file does not exist, this method does nothing.

        :returns: Nothing.
        :rtype: None
        """
        self.path.unlink(missing_ok=True)


class MemoryCookieStore(CookieStore):
    """Stores cookies in memory for the lifetime of the object.

    Cookies are fetched lazily on the first call to :meth:`load` and kept
    in memory until :meth:`clear` is called or the store is garbage
    collected. Nothing is persisted to disk.

    This is the preferred store in most cases: it is simpler, has no disk
    I/O, and avoids the thread-safety concerns of
    :class:`FileCookieStore`.
    """

    def __init__(self) -> None:
        """Initialize an empty in-memory cookie store.

        :param fetcher: Callable invoked to obtain a fresh set of cookies
            the first time :meth:`load` is called (i.e. while the store
            is empty).
        :type fetcher: Callable[[], httpx.Cookies]
        """
        self._cookies = httpx.Cookies()

    def load(self) -> httpx.Cookies:
        """Return the cached cookies, fetching them if not yet loaded.

        On the first call (or after :meth:`clear`), ``fetcher`` is invoked
        and its result is cached. Subsequent calls return the cached
        cookies without invoking ``fetcher`` again.

        :returns: The cached or freshly fetched cookies.
        :rtype: httpx.Cookies

        return self._cookies

    def save(self, cookies: httpx.Cookies) -> None:
        """Replace the in-memory cookie set.

        :param cookies: The cookies to store.
        :type cookies: httpx.Cookies
        :returns: Nothing.
        :rtype: None
        """
        self._cookies = cookies

    def clear(self) -> None:
        """Discard the in-memory cookies.

        After this call, the next :meth:`load` will invoke ``fetcher``
        again to obtain a fresh set.

        :returns: Nothing.
        :rtype: None
        """
        self._cookies.clear()

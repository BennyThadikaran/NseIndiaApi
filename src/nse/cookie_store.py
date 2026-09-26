import logging
from abc import ABC, abstractmethod
from http.cookiejar import MozillaCookieJar
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)


class CookieStore(ABC):
    """Abstract base class defining the interface for cookie storage backends.

    Subclasses must implement :meth:`load`, :meth:`save`, and :meth:`clear` to
    provide a concrete persistence strategy (e.g., file-based, in-memory, or
    custom backends such as Redis or a database).

    .. note::
        Custom storage backends must subclass :class:`CookieStore` and implement
        all three abstract methods. They can then be passed to the ``NSE`` class
        via its cookie store parameter to override the default
        :class:`FileCookieStore`.
    """

    @abstractmethod
    def load(self) -> httpx.Cookies:
        """Load and return the stored cookies.

        :return: The cookies retrieved from the underlying storage. Implementations
            should return an empty :class:`httpx.Cookies` instance when no cookies
            are available, rather than ``None``.
        :rtype: httpx.Cookies
        """
        ...

    @abstractmethod
    def save(self, cookies: httpx.Cookies) -> None:
        """Persist the given cookies to the underlying storage.

        :param cookies: The cookies to store.
        :type cookies: httpx.Cookies
        :return: ``None``
        :rtype: None
        """
        ...

    @abstractmethod
    def clear(self) -> None:
        """Remove all cookies from the underlying storage.

        :return: ``None``
        :rtype: None
        """
        ...


class FileCookieStore(CookieStore):
    """File-based cookie store using a Mozilla-format cookie jar.

    This is the **default** cookie store used by the ``NSE`` class when no
    alternative store is specified.

    Cookies are persisted to ``path`` in Mozilla cookie jar format. The parent
    directory of ``path`` is created automatically on instantiation if it does
    not already exist.

    .. warning::
       This store is **not thread safe**. Concurrent access from multiple
       threads, processes, or workers may result in corrupted or lost cookies.
       For servers running with multiple workers, multi-threaded, or
       multi-process environments, prefer :class:`MemoryCookieStore` instead.

    .. note::
       Cookies marked as "discard" (session cookies) are persisted on save and
       reloaded on load (``ignore_discard=True``), but expired cookies are
       filtered out on load (``ignore_expires=False``).
    """

    def __init__(self, path: Path) -> None:
        """Initialize the file cookie store.

        Creates the parent directory of ``path`` (including any intermediate
        directories) if it does not already exist.

        :param path: Filesystem path to the cookie jar file.
        :type path: Path
        :return: ``None``
        :rtype: None
        """
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> httpx.Cookies:
        """Load cookies from the file-based cookie jar.

        If the cookie file does not exist, an empty :class:`httpx.Cookies` instance
        is returned without raising an error.

        Session cookies (those marked "discard") are preserved
        (``ignore_discard=True``), but expired cookies are **not** loaded
        (``ignore_expires=False``).

        :return: The cookies loaded from disk, or an empty :class:`httpx.Cookies`
            instance if the file does not exist or contains no valid cookies.
        :rtype: httpx.Cookies

        .. note::
            This method reads from the filesystem on every call and is therefore
            subject to I/O latency and to the thread-safety caveats described on
            :class:`FileCookieStore`.
        """
        if not self.path.exists():
            return httpx.Cookies()

        jar = MozillaCookieJar(self.path)

        jar.load(ignore_discard=True, ignore_expires=False)

        if any(jar):
            return httpx.Cookies(jar)

        return httpx.Cookies()

    def save(self, cookies: httpx.Cookies) -> None:
        """Persist the given cookies to the file-based cookie jar.

        All cookies from ``cookies`` are written to the jar and saved to disk.
        Expired cookies are written as-is (``ignore_expires=True``), and session
        cookies are retained (``ignore_discard=True``).

        :param cookies: The cookies to persist.
        :type cookies: httpx.Cookies
        :return: ``None``
        :rtype: None

        .. warning::
            This operation overwrites the existing cookie file at ``path``. It is
            not atomic and not thread safe; concurrent writes may corrupt the file.
        """
        jar = MozillaCookieJar(self.path)

        for cookie in cookies.jar:
            jar.set_cookie(cookie)

        jar.save(ignore_discard=True, ignore_expires=True)

    def clear(self) -> None:
        """Delete the cookie file from disk.

        If the file does not exist, no error is raised (equivalent to
        ``Path.unlink(missing_ok=True)``).

        :return: ``None``
        :rtype: None
        """
        self.path.unlink(missing_ok=True)


class MemoryCookieStore(CookieStore):
    """In-memory cookie store.

    Cookies are held in a single :class:`httpx.Cookies` instance for the
    lifetime of the object and are not persisted anywhere.

    This store is the recommended choice for servers running with multiple
    workers, or in multi-threaded or multi-process environments, because each
    process or worker maintains its own isolated in-memory state and avoids
    the file corruption risks of :class:`FileCookieStore`.

    :param: This class takes no constructor arguments.
    :type: None

    .. warning::
        Cookies are **not persistent**. They are lost when the process exits or
        when the instance is garbage collected.

    .. note::
        Because cookies are not persisted, every new instance starts empty and
        will incur a network request to fetch cookies from the server the first
        time they are needed. If you create many instances, this can lead to
        repeated network traffic.
    """

    def __init__(self) -> None:
        """Initialize an empty in-memory cookie store.

        :return: ``None``
        :rtype: None
        """
        self._cookies = httpx.Cookies()

    def load(self) -> httpx.Cookies:
        """Return the in-memory cookies.

        :return: The cookies currently held in memory. Returns the same
            :class:`httpx.Cookies` instance stored by the last :meth:`save` call,
            or an empty one if none has been saved.
        :rtype: httpx.Cookies

        .. note::
           The returned object is the live internal instance, not a copy. Mutating
           it will affect the store's state.
        """
        return self._cookies

    def save(self, cookies: httpx.Cookies) -> None:
        """Replace the in-memory cookies with the given cookies.

        :param cookies: The cookies to store. The reference is retained directly
        (no copy is made).
        :type cookies: httpx.Cookies
        :return: ``None``
        :rtype: None

        .. note::
            The store holds a reference to the passed object, so subsequent
            mutations to ``cookies`` by the caller will be reflected in the store.
        """
        self._cookies = cookies

    def clear(self) -> None:
        """Clear all in-memory cookies.

        :return: ``None``
        :rtype: None
        """
        self._cookies.clear()

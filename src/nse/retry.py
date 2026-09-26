import datetime
import functools
import logging
import random
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

STATUS_FORCELIST = (429, 502, 503, 504)


class RetryableStatusError(httpx.HTTPStatusError):
    """
    Exception raised for HTTP status codes that should trigger a retry.

    This exception is a subclass of :class:`httpx.HTTPStatusError` and is
    raised by the decorated method when a response with a status code in
    :data:`STATUS_FORCELIST` (``429``, ``502``, ``503``, ``504``) is received.

    .. note::
       Unlike a generic :class:`httpx.HTTPStatusError`, this exception is
       explicitly caught by the :func:`retry` decorator. Raising this exception
       (or a subclass) from a decorated method will cause the retry logic to
       engage, potentially honoring the ``Retry-After`` response header.

    :raises RetryableStatusError: When an HTTP response with a retryable status
        code is encountered and the retry policy is active.
    """

    pass


@dataclass
class RetryConfig:
    """
    Configuration for the retry behaviour applied by :func:`retry`.

    :param total: Maximum number of retry attempts before giving up. If set to
        ``0``, no retries are attempted and the original exception is raised
        immediately. Defaults to ``5``.
    :type total: int
    :param max_backoff_wait: Maximum number of seconds to wait between retries.
        This caps both the computed exponential backoff and any value derived
        from the ``Retry-After`` header. Defaults to ``8``.
    :type max_backoff_wait: float
    :param backoff_factor: Multiplier for the exponential backoff. The wait
        time is computed as ``backoff_factor * 2 ** attempts_made``. If set to
        ``0.0``, exponential backoff is disabled and a uniform wait of ``1``
        second is used instead. Defaults to ``1``.
    :type backoff_factor: float
    :param respect_retry_after_header: If ``True``, the value of the
        ``Retry-After`` HTTP response header (if present on a
        :class:`RetryableStatusError`) is parsed and used as the wait time,
        capped at ``max_backoff_wait``. Defaults to ``True``.
    :type respect_retry_after_header: bool
    :param backoff_jitter: Random jitter factor applied to the backoff to
        avoid thundering herd problems. Must be between ``0.0`` and ``1.0``
        inclusive. A value of ``0.0`` disables jitter. The actual wait is
        multiplied by ``random.uniform(1 - backoff_jitter, 1)``. Defaults to
        ``1``.
    :type backoff_jitter: float

    :raises ValueError: If ``total`` is negative.
    :raises ValueError: If ``max_backoff_wait`` is less than or equal to ``0``.
    :raises ValueError: If ``backoff_factor`` is negative.
    :raises ValueError: If ``backoff_jitter`` is not between ``0.0`` and
        ``1.0`` inclusive.

    .. note::
       Validation occurs in :meth:`__post_init__`, so invalid configurations
       raise immediately upon instantiation.
    """

    total: int = 5
    max_backoff_wait: float = 8
    backoff_factor: float = 1
    respect_retry_after_header: bool = True
    backoff_jitter: float = 1

    def __post_init__(self) -> None:
        name = "RetryConfig"
        if self.total < 0:
            raise ValueError(f"{name}: total must be non-negative")

        if self.max_backoff_wait <= 0:
            raise ValueError(f"{name}: max_backoff_wait must be greater than 0")

        if self.backoff_factor < 0:
            raise ValueError(f"{name}: backoff_factor must be non-negative")

        if not (0.0 <= self.backoff_jitter <= 1.0):
            raise ValueError(f"{name}: backoff_jitter must be between 0 and 1")


def _parse_retry_after(retry_after: str) -> float:
    """
    Parse a ``Retry-After`` HTTP header value into a number of seconds to wait.

    The ``Retry-After`` header can be specified in two formats per :rfc:`7231`:

    * A non-negative integer number of seconds (e.g. ``"120"``).
    * An HTTP-date (e.g. ``"Wed, 21 Oct 2015 07:28:00 GMT"``).

    If the header is a date without timezone information, UTC is assumed and a
    warning is logged. If the date is in the past, ``0.0`` is returned.

    :param retry_after: The raw string value of the ``Retry-After`` header.
    :type retry_after: str
    :return: The number of seconds to wait before retrying. Always
        non-negative.
    :rtype: float

    :raises ValueError: If the value is neither a valid integer number of
        seconds nor a parseable HTTP-date.

    .. note::
       Source: ``retry.py`` from ``will-ockmore/httpx-retries``.

    .. warning::
       A missing timezone on an HTTP-date is not an error; UTC is assumed and
       a warning is emitted via the module logger.
    """
    retry_after = retry_after.strip()
    if retry_after.isascii() and retry_after.isdigit():
        return float(retry_after)

    try:
        parsed_date = parsedate_to_datetime(retry_after)

        if parsed_date.tzinfo is None:
            logger.warning(
                "Retry-After date has no timezone info, assuming UTC: %s", retry_after
            )
            parsed_date = parsed_date.replace(tzinfo=datetime.timezone.utc)

        diff = (
            parsed_date - datetime.datetime.now(datetime.timezone.utc)
        ).total_seconds()
        return max(0.0, diff)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid Retry-After header: {retry_after}")


def _calculate_wait(
    attempts_made: int,
    config: RetryConfig,
    retry_after_header: Optional[str] = None,
) -> float:
    wait = 0.0
    if retry_after_header:
        try:
            retry_after_sleep = min(
                _parse_retry_after(retry_after_header),
                config.max_backoff_wait,
            )

            if retry_after_sleep > 0.0:
                wait = retry_after_sleep
        except ValueError:
            logger.warning(
                "Retry-After header is not a valid HTTP date: %s", retry_after_header
            )

    if wait == 0.0:
        if config.backoff_factor == 0.0:
            # backoff is disabled, apply a uniform wait of 1 second
            wait = 1
        else:
            backoff = config.backoff_factor * (2**attempts_made)

            if config.backoff_jitter > 0:
                backoff *= random.uniform(1 - config.backoff_jitter, 1)

            wait = min(backoff, config.max_backoff_wait)

    return wait


def retry(method):
    """
    Decorator that adds retry logic to an instance method.

    The decorated method is called repeatedly until it succeeds or the retry
    budget defined by ``self.retry_config`` is exhausted. The host class must
    expose a ``retry_config`` attribute of type :class:`RetryConfig` and a
    ``_restart_session`` method.

    Retries are triggered by the following exceptions:

    * :class:`httpx.TimeoutException`
    * :class:`httpx.ConnectError`
    * :class:`httpx.ReadError`
    * :class:`httpx.RemoteProtocolError`
    * :class:`RetryableStatusError`

    When a :class:`RetryableStatusError` is caught and
    ``respect_retry_after_header`` is enabled, the ``Retry-After`` response
    header is parsed and used to determine the wait time (capped at
    ``max_backoff_wait``). Otherwise, an exponential backoff with optional
    jitter is applied.

    On :class:`httpx.RemoteProtocolError`, the session is restarted via
    ``self._restart_session()`` before the next attempt.

    :param method: The instance method to wrap.
    :type method: callable
    :return: The wrapped method with retry behaviour.
    :rtype: callable

    :raises httpx.TimeoutException: If all retries are exhausted due to timeouts.
    :raises httpx.ConnectError: If all retries are exhausted due to connection errors.
    :raises httpx.ReadError: If all retries are exhausted due to read errors.
    :raises httpx.RemoteProtocolError: If all retries are exhausted due to
        remote protocol errors.
    :raises RetryableStatusError: If all retries are exhausted due to
        retryable HTTP status codes.

    .. note::
       The exception raised after exhausting retries is the same exception
       instance from the final attempt, preserving its original traceback.

    .. note::
       The wait time between attempts is logged at ``INFO`` level, including
       the attempt number, method name, computed wait, and exception type.

    .. note::
       ``functools.wraps`` is used to preserve the wrapped method's metadata
       (name, docstring, etc.).
    """

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        config = self.retry_config
        attempts_made = 0

        while True:
            try:
                return method(self, *args, **kwargs)
            except (
                httpx.TimeoutException,
                httpx.ConnectError,
                httpx.ReadError,
                httpx.RemoteProtocolError,
                RetryableStatusError,
            ) as e:
                if attempts_made >= config.total:
                    raise e

                retry_header = None

                if (
                    isinstance(e, RetryableStatusError)
                    and config.respect_retry_after_header
                ):
                    retry_header = e.response.headers.get("retry-after", "").strip()

                wait = _calculate_wait(attempts_made, config, retry_header)

                logger.info(
                    "Retry %d/%d for %s.%s in %.2fs due to %s",
                    attempts_made,
                    config.total,
                    type(self).__name__,
                    method.__name__,
                    wait,
                    type(e).__name__,
                )

                time.sleep(wait)

                if isinstance(e, httpx.RemoteProtocolError):
                    logger.info(
                        "Restarting session due to RemoteProtocolError in %s.%s",
                        type(self).__name__,
                        method.__name__,
                    )
                    self._restart_session()

                attempts_made += 1

    return wrapper

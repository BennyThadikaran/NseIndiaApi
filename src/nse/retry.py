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
    pass


@dataclass
class RetryConfig:
    total: int = 5
    max_backoff_wait: float = 8
    backoff_factor: float = 1
    respect_retry_after_header: bool = True
    backoff_jitter: float = 1

    def __post_init__(self) -> None:
        name = "RetryConfig"
        if self.total < 0:
            raise ValueError(f"{name}: total must be non-negative")

        if self.max_backoff_wait < 0:
            raise ValueError(f"{name}: max_backoff_wait must be non-negative")

        if self.backoff_factor < 0:
            raise ValueError(f"{name}: backoff_factor must be non-negative")

        if not (0.0 <= self.backoff_jitter <= 1.0):
            raise ValueError(f"{name}: backoff_jitter must be between 0 and 1")


def _parse_retry_after(retry_after: str) -> float:
    """
    Source: retry.py from will-ockmore/httpx-retries
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

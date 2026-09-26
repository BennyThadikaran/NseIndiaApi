import datetime
import random  # ruff: ignore[F401]
import time  # ruff: ignore[F401]
import unittest
from unittest import mock

import httpx
from context import (
    STATUS_FORCELIST,
    RetryableStatusError,
    RetryConfig,
    _calculate_wait,
    _parse_retry_after,
    retry,
)

# Helpers


def make_response(status_code: int, headers: dict | None = None) -> httpx.Response:
    request = httpx.Request("GET", "https://example.test/")

    return httpx.Response(
        status_code=status_code,
        headers=headers or {},
        request=request,
    )


def make_retryable_status_error(
    status_code: int = 503, headers: dict | None = None
) -> RetryableStatusError:
    response = make_response(status_code, headers)

    return RetryableStatusError(
        f"retryable status {status_code}",
        request=response.request,
        response=response,
    )


class Host:
    """Minimal object exposing ``retry_config`` and ``_restart_session``."""

    def __init__(self, config: RetryConfig | None = None) -> None:
        self.retry_config = config or RetryConfig()
        self.restart_count = 0

    def _restart_session(self) -> None:
        self.restart_count += 1


# STATUS_FORCELIST


class StatusForcelistTests(unittest.TestCase):
    def test_contains_expected_codes(self):
        self.assertEqual(STATUS_FORCELIST, (429, 502, 503, 504))

    def test_only_retryable_statuses(self):
        for code in STATUS_FORCELIST:
            self.assertTrue(400 <= code < 600, code)
            self.assertNotIn(code, (200, 201, 301, 401, 403, 404))


# RetryableStatusError


class RetryableStatusErrorTests(unittest.TestCase):
    def test_is_http_status_error_subclass(self):
        self.assertTrue(issubclass(RetryableStatusError, httpx.HTTPStatusError))

    def test_exposes_response(self):
        err = make_retryable_status_error(503)
        self.assertIsInstance(err.response, httpx.Response)
        self.assertEqual(err.response.status_code, 503)

    def test_response_headers_accessible(self):
        err = make_retryable_status_error(503, {"Retry-After": "5"})
        self.assertEqual(err.response.headers["Retry-After"], "5")


# _parse_retry_after


class ParseRetryAfterTests(unittest.TestCase):
    def test_numeric_string(self):
        self.assertEqual(_parse_retry_after("120"), 120.0)

    def test_numeric_string_with_whitespace(self):
        self.assertEqual(_parse_retry_after("  30  "), 30.0)

    def test_zero(self):
        self.assertEqual(_parse_retry_after("0"), 0.0)

    def test_http_date_in_future(self):
        future = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
            seconds=60
        )

        header = future.strftime("%a, %d %b %Y %H:%M:%S GMT")
        value = _parse_retry_after(header)

        self.assertGreater(value, 0)
        self.assertLessEqual(value, 61)

    def test_http_date_in_past_clamped_to_zero(self):
        past = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
            seconds=60
        )

        header = past.strftime("%a, %d %b %Y %H:%M:%S GMT")
        self.assertEqual(_parse_retry_after(header), 0.0)

    def test_http_date_without_timezone_assumes_utc_and_warns(self):
        with self.assertLogs("nse.retry", level="WARNING") as cm:
            value = _parse_retry_after("Wed, 21 Oct 2099 07:28:00")

        self.assertGreater(value, 0)
        self.assertTrue(any("timezone" in m.lower() for m in cm.output))

    def test_invalid_string_raises_value_error(self):
        with self.assertRaises(ValueError):
            _parse_retry_after("not-a-date")

    def test_empty_string_raises_value_error(self):
        with self.assertRaises(ValueError):
            _parse_retry_after("")


# _calculate_wait


class CalculateWaitTests(unittest.TestCase):
    def test_retry_after_numeric_used(self):
        config = RetryConfig(backoff_factor=1, backoff_jitter=0)
        wait = _calculate_wait(0, config, retry_after_header="7")
        self.assertEqual(wait, 7.0)

    def test_retry_after_capped_by_max_backoff(self):
        config = RetryConfig(max_backoff_wait=3, backoff_factor=1, backoff_jitter=0)
        wait = _calculate_wait(0, config, retry_after_header="100")
        self.assertEqual(wait, 3.0)

    def test_retry_after_zero_falls_through_to_backoff(self):
        config = RetryConfig(backoff_factor=1, backoff_jitter=0)
        wait = _calculate_wait(0, config, retry_after_header="0")
        self.assertEqual(wait, 1.0)

    def test_invalid_retry_after_falls_back_and_warns(self):
        config = RetryConfig(backoff_factor=1, backoff_jitter=0)

        with self.assertLogs("nse.retry", level="WARNING"):
            wait = _calculate_wait(0, config, retry_after_header="garbage")

        self.assertEqual(wait, 1.0)

    def test_exponential_backoff_growth(self):
        config = RetryConfig(backoff_factor=1, backoff_jitter=0, max_backoff_wait=10)
        self.assertEqual(_calculate_wait(0, config), 1.0)
        self.assertEqual(_calculate_wait(1, config), 2.0)
        self.assertEqual(_calculate_wait(2, config), 4.0)

    def test_backoff_capped_by_max_backoff(self):
        config = RetryConfig(backoff_factor=1, backoff_jitter=0, max_backoff_wait=3)
        self.assertEqual(_calculate_wait(5, config), 3.0)

    def test_backoff_factor_zero_gives_uniform_one_second(self):
        config = RetryConfig(backoff_factor=0, backoff_jitter=0)
        self.assertEqual(_calculate_wait(0, config), 1.0)
        self.assertEqual(_calculate_wait(5, config), 1.0)

    def test_jitter_applied_within_bounds(self):
        config = RetryConfig(
            backoff_factor=1, backoff_jitter=0.5, max_backoff_wait=1000
        )

        with mock.patch("random.uniform", return_value=0.75) as m:
            wait = _calculate_wait(2, config)

        # base for attempt 2 = 4.0; uniform(0.5, 1.0) -> 0.75 -> 3.0
        self.assertEqual(wait, 3.0)
        m.assert_called_once_with(0.5, 1.0)

    def test_jitter_zero_skips_random(self):
        config = RetryConfig(backoff_factor=1, backoff_jitter=0)

        with mock.patch("random.uniform") as m:
            _calculate_wait(0, config)

        m.assert_not_called()

    def test_jitter_one_can_reach_zero(self):
        config = RetryConfig(
            backoff_factor=1, backoff_jitter=1.0, max_backoff_wait=1000
        )

        with mock.patch("random.uniform", return_value=0.0):
            self.assertEqual(_calculate_wait(0, config), 0.0)


# RetryConfig validation


class RetryConfigTests(unittest.TestCase):
    def test_defaults(self):
        c = RetryConfig()
        self.assertEqual(c.total, 5)
        self.assertEqual(c.max_backoff_wait, 8)
        self.assertEqual(c.backoff_factor, 1)
        self.assertTrue(c.respect_retry_after_header)
        self.assertEqual(c.backoff_jitter, 1)

    def test_negative_total_rejected(self):
        with self.assertRaises(ValueError):
            RetryConfig(total=-1)

    def test_negative_max_backoff_rejected(self):
        with self.assertRaises(ValueError):
            RetryConfig(max_backoff_wait=-1)

    def test_zero_max_backoff_rejected(self):
        with self.assertRaises(ValueError):
            RetryConfig(max_backoff_wait=0)

    def test_negative_backoff_factor_rejected(self):
        with self.assertRaises(ValueError):
            RetryConfig(backoff_factor=-1)

    def test_jitter_above_one_rejected(self):
        with self.assertRaises(ValueError):
            RetryConfig(backoff_jitter=1.01)

    def test_jitter_below_zero_rejected(self):
        with self.assertRaises(ValueError):
            RetryConfig(backoff_jitter=-0.01)

    def test_boundary_values_accepted(self):
        RetryConfig(total=0, max_backoff_wait=1, backoff_factor=0, backoff_jitter=0)
        RetryConfig(backoff_jitter=1.0)


# retry decorator — happy path


class RetryHappyPathTests(unittest.TestCase):
    def test_returns_value_on_first_success(self):
        calls = []

        class C(Host):
            @retry
            def call(self, *args, **kwargs):
                calls.append((args, kwargs))
                return "ok"

        c = C()
        with mock.patch("time.sleep") as sleep:
            result = c.call(1, 2, x=3)
        self.assertEqual(result, "ok")
        self.assertEqual(calls, [((1, 2), dict(x=3))])
        sleep.assert_not_called()

    def test_reads_config_from_instance(self):
        class C(Host):
            @retry
            def call(self):
                raise httpx.TimeoutException("t")

        c = C(RetryConfig(total=1, backoff_factor=0))
        with mock.patch("time.sleep") as sleep:
            with self.assertRaises(httpx.TimeoutException):
                c.call()
        self.assertEqual(sleep.call_count, 1)


# retry decorator — retryable exceptions

RETRYABLE_EXCEPTIONS = [
    ("timeout", lambda: httpx.TimeoutException("t")),
    ("connect", lambda: httpx.ConnectError("c")),
    ("read", lambda: httpx.ReadError("r")),
    ("remote_protocol", lambda: httpx.RemoteProtocolError("p")),
    ("retryable_status", lambda: make_retryable_status_error(503)),
]


class RetryableExceptionsTests(unittest.TestCase):
    def _make_host(self, exc_factory, total=3):
        class C(Host):
            def __init__(self):
                super().__init__(RetryConfig(total=total, backoff_factor=0))

            @retry
            def call(self):
                self.attempts += 1
                raise exc_factory()

        c = C()
        c.attempts = 0
        return c

    def test_exception_matrix_retries_then_reraises(self):
        for name, factory in RETRYABLE_EXCEPTIONS:
            with self.subTest(exc=name):
                c = self._make_host(factory, total=3)

                with mock.patch("time.sleep") as sleep:
                    with self.assertRaises(Exception) as ctx:
                        c.call()

                self.assertEqual(c.attempts, 4)  # 1 initial + 3 retries
                self.assertEqual(sleep.call_count, 3)
                self.assertIsInstance(ctx.exception, factory().__class__)

    def test_reraises_last_exception_identity(self):
        raised = []

        class C(Host):
            @retry
            def call(self):
                e = httpx.TimeoutException(f"attempt {len(raised)}")
                raised.append(e)
                raise e

        c = C(RetryConfig(total=2, backoff_factor=0))

        with mock.patch("time.sleep"):
            with self.assertRaises(httpx.TimeoutException) as ctx:
                c.call()

        self.assertIs(ctx.exception, raised[-1])
        self.assertEqual(len(raised), 3)


# retry decorator — non-retryable exceptions


class NonRetryableExceptionsTests(unittest.TestCase):
    def test_plain_http_status_error_not_retried(self):
        class C(Host):
            def __init__(self):
                super().__init__(RetryConfig(total=5, backoff_factor=0))

            @retry
            def call(self):
                self.attempts += 1
                resp = make_response(401)

                raise httpx.HTTPStatusError(
                    "unauthorized", request=resp.request, response=resp
                )

        c = C()
        c.attempts = 0

        with mock.patch("time.sleep") as sleep:
            with self.assertRaises(httpx.HTTPStatusError):
                c.call()

        self.assertEqual(c.attempts, 1)
        sleep.assert_not_called()

    def test_generic_exceptions_not_retried(self):
        for exc_type in (ValueError, KeyError, RuntimeError):
            with self.subTest(exc=exc_type.__name__):

                class C(Host):
                    def __init__(self):
                        super().__init__(RetryConfig(total=5, backoff_factor=0))

                    @retry
                    def call(self):
                        self.attempts += 1
                        raise exc_type("boom")

                c = C()
                c.attempts = 0

                with mock.patch("time.sleep") as sleep:
                    with self.assertRaises(exc_type):
                        c.call()

                self.assertEqual(c.attempts, 1)
                sleep.assert_not_called()

    def test_success_after_retry_returns_value(self):
        class C(Host):
            def __init__(self):
                super().__init__(RetryConfig(total=5, backoff_factor=0))

            @retry
            def call(self):
                self.attempts += 1
                if self.attempts < 3:
                    raise httpx.TimeoutException("t")
                return "recovered"

        c = C()
        c.attempts = 0

        with mock.patch("time.sleep") as sleep:
            self.assertEqual(c.call(), "recovered")

        self.assertEqual(c.attempts, 3)
        self.assertEqual(sleep.call_count, 2)


# RemoteProtocolError special handling


class RemoteProtocolErrorTests(unittest.TestCase):
    def _make_host(self, exc_factory, total=2):
        class C(Host):
            def __init__(self):
                super().__init__(RetryConfig(total=total, backoff_factor=0))
                self.order = []

            @retry
            def call(self):
                self.order.append("call")
                raise exc_factory()

        c = C()
        return c

    def test_restart_session_called_on_remote_protocol_error(self):
        c = self._make_host(lambda: httpx.RemoteProtocolError("p"))

        with mock.patch("time.sleep"):
            with self.assertRaises(httpx.RemoteProtocolError):
                c.call()

        # restart called after each retryable failure except the last
        self.assertEqual(c.restart_count, 2)

    def test_restart_session_not_called_for_other_errors(self):
        c = self._make_host(lambda: httpx.TimeoutException("t"))

        with mock.patch("time.sleep"):
            with self.assertRaises(httpx.TimeoutException):
                c.call()

        self.assertEqual(c.restart_count, 0)

    def test_restart_called_after_sleep_before_next_attempt(self):
        events = []

        class C(Host):
            def __init__(self):
                super().__init__(RetryConfig(total=1, backoff_factor=0))

            def _restart_session(self):
                events.append("restart")
                super()._restart_session()

            @retry
            def call(self):
                events.append("call")
                raise httpx.RemoteProtocolError("p")

        c = C()

        with mock.patch(
            "time.sleep", side_effect=lambda _s: events.append("sleep")
        ), self.assertRaises(httpx.RemoteProtocolError):
            c.call()

        self.assertEqual(events, ["call", "sleep", "restart", "call"])

    def test_restart_not_called_when_retries_exhausted_for_remote_only(self):
        # With total=0 there are no retries, so no restart should happen.
        c = self._make_host(lambda: httpx.RemoteProtocolError("p"), total=0)

        with mock.patch("time.sleep") as sleep:
            with self.assertRaises(httpx.RemoteProtocolError):
                c.call()

        self.assertEqual(c.restart_count, 0)
        sleep.assert_not_called()


# Retry-After interaction with decorator


class RetryAfterInteractionTests(unittest.TestCase):
    def test_header_used_when_respected(self):
        class C(Host):
            def __init__(self):
                super().__init__(
                    RetryConfig(
                        total=1,
                        backoff_factor=1,
                        backoff_jitter=0,
                        respect_retry_after_header=True,
                        max_backoff_wait=100,
                    )
                )

            @retry
            def call(self):
                raise make_retryable_status_error(503, {"Retry-After": "5"})

        c = C()

        with mock.patch("time.sleep") as sleep:
            with self.assertRaises(RetryableStatusError):
                c.call()

        sleep.assert_called_once_with(5.0)

    def test_header_ignored_when_disabled(self):
        class C(Host):
            def __init__(self):
                super().__init__(
                    RetryConfig(
                        total=1,
                        backoff_factor=1,
                        backoff_jitter=0,
                        respect_retry_after_header=False,
                        max_backoff_wait=100,
                    )
                )

            @retry
            def call(self):
                raise make_retryable_status_error(503, {"Retry-After": "5"})

        c = C()

        with mock.patch("time.sleep") as sleep:
            with self.assertRaises(RetryableStatusError):
                c.call()

        sleep.assert_called_once_with(1.0)

    def test_header_not_read_for_non_status_errors(self):
        class C(Host):
            def __init__(self):
                super().__init__(
                    RetryConfig(
                        total=1,
                        backoff_factor=1,
                        backoff_jitter=0,
                        respect_retry_after_header=True,
                    )
                )

            @retry
            def call(self):
                raise httpx.TimeoutException("t")

        c = C()

        with mock.patch("time.sleep") as sleep:
            with self.assertRaises(httpx.TimeoutException):
                c.call()

        sleep.assert_called_once_with(1.0)

    def test_missing_header_uses_backoff(self):
        class C(Host):
            def __init__(self):
                super().__init__(
                    RetryConfig(total=1, backoff_factor=1, backoff_jitter=0)
                )

            @retry
            def call(self):
                raise make_retryable_status_error(503)

        c = C()

        with mock.patch("time.sleep") as sleep:
            with self.assertRaises(RetryableStatusError):
                c.call()

        sleep.assert_called_once_with(1.0)

    def test_invalid_header_uses_backoff_with_warning(self):
        class C(Host):
            def __init__(self):
                super().__init__(
                    RetryConfig(total=1, backoff_factor=1, backoff_jitter=0)
                )

            @retry
            def call(self):
                raise make_retryable_status_error(503, {"Retry-After": "garbage"})

        c = C()

        with mock.patch("time.sleep") as sleep:
            with self.assertLogs("nse.retry", level="WARNING"):
                with self.assertRaises(RetryableStatusError):
                    c.call()

        sleep.assert_called_once_with(1.0)


# Configuration edge cases via decorator


class ConfigEdgeCaseTests(unittest.TestCase):
    def test_total_zero_makes_single_attempt(self):
        class C(Host):
            def __init__(self):
                super().__init__(RetryConfig(total=0))

            @retry
            def call(self):
                self.attempts += 1
                raise httpx.TimeoutException("t")

        c = C()
        c.attempts = 0

        with mock.patch("time.sleep") as sleep:
            with self.assertRaises(httpx.TimeoutException):
                c.call()

        self.assertEqual(c.attempts, 1)
        sleep.assert_not_called()

    def test_backoff_factor_zero_sleeps_one_second(self):
        class C(Host):
            def __init__(self):
                super().__init__(RetryConfig(total=2, backoff_factor=0))

            @retry
            def call(self):
                raise httpx.TimeoutException("t")

        c = C()

        with mock.patch("time.sleep") as sleep:
            with self.assertRaises(httpx.TimeoutException):
                c.call()

        self.assertEqual(sleep.call_args_list, [mock.call(1.0), mock.call(1.0)])


# Timing and side-effect verification


class TimingAndSideEffectTests(unittest.TestCase):
    def test_sleep_called_once_per_retry(self):
        class C(Host):
            def __init__(self):
                super().__init__(RetryConfig(total=4, backoff_factor=0))

            @retry
            def call(self):
                raise httpx.TimeoutException("t")

        c = C()

        with mock.patch("time.sleep") as sleep:
            with self.assertRaises(httpx.TimeoutException):
                c.call()

        self.assertEqual(sleep.call_count, 4)

    def test_random_uniform_only_when_jitter_positive(self):
        class C(Host):
            def __init__(self, jitter):
                super().__init__(
                    RetryConfig(
                        total=2,
                        backoff_factor=1,
                        backoff_jitter=jitter,
                        max_backoff_wait=100,
                    )
                )

            @retry
            def call(self):
                raise httpx.TimeoutException("t")

        with mock.patch("time.sleep"), mock.patch("random.uniform") as uniform:
            with self.assertRaises(httpx.TimeoutException):
                C(jitter=0).call()

            uniform.assert_not_called()

        with mock.patch("time.sleep"), mock.patch(
            "random.uniform", return_value=1.0
        ) as uniform:
            with self.assertRaises(httpx.TimeoutException):
                C(jitter=0.5).call()

            self.assertEqual(uniform.call_count, 2)

    def test_retry_log_emitted(self):
        class C(Host):
            def __init__(self):
                super().__init__(RetryConfig(total=1, backoff_factor=0))

            @retry
            def call(self):
                raise httpx.TimeoutException("t")

        c = C()

        with mock.patch("time.sleep"):
            with self.assertLogs("nse.retry", level="INFO") as cm:
                with self.assertRaises(httpx.TimeoutException):
                    c.call()

        self.assertTrue(any("Retry 0/1" in msg for msg in cm.output))

    def test_restart_log_emitted_for_remote_protocol_error(self):
        class C(Host):
            def __init__(self):
                super().__init__(RetryConfig(total=1, backoff_factor=0))

            @retry
            def call(self):
                raise httpx.RemoteProtocolError("p")

        c = C()

        with mock.patch("time.sleep"):
            with self.assertLogs("nse.retry", level="INFO") as cm:
                with self.assertRaises(httpx.RemoteProtocolError):
                    c.call()

        self.assertTrue(any("Restarting session" in msg for msg in cm.output))


# Decorator composition / metadata


class DecoratorMetadataTests(unittest.TestCase):
    def test_multiple_methods_get_independent_state(self):
        class C(Host):
            def __init__(self):
                super().__init__(RetryConfig(total=1, backoff_factor=0))
                self.a_attempts = 0
                self.b_attempts = 0

            @retry
            def a(self):
                self.a_attempts += 1
                raise httpx.TimeoutException("a")

            @retry
            def b(self):
                self.b_attempts += 1
                if self.b_attempts < 2:
                    raise httpx.TimeoutException("b")
                return "b-ok"

        c = C()

        with mock.patch("time.sleep"):
            with self.assertRaises(httpx.TimeoutException):
                c.a()

            self.assertEqual(c.b(), "b-ok")

        self.assertEqual(c.a_attempts, 2)
        self.assertEqual(c.b_attempts, 2)


if __name__ == "__main__":
    unittest.main()

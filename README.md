# NSE — Unofficial Python API for NSE India

A lightweight Python client for the National Stock Exchange of India. Built for traders, analysts,
and quant developers who need reliable programmatic access to NSE data without having to worry about
cookie handling, rate limits, and retries under flaky network conditions.

**Python:** >= 3.8

> [!IMPORTANT]
> **NseIndiaApi 5.0.0 is a major release with breaking changes.**
>
> Before upgrading from **4.x**, please read the **[v5.0.0 Migration Guide](https://bennythadikaran.github.io/NseIndiaApi/migration.html)**.
>
> The guide explains the breaking changes and how to migrate existing code to v5.0.0.

If you ❤️ my work so far, please 🌟 this repo.

---

## 👽 Documentation

> Documentation has been rewritten for version 5 with updated examples, new code samples, and practical guidance for running the package on servers and in production environments.

[https://bennythadikaran.github.io/NseIndiaApi](https://bennythadikaran.github.io/NseIndiaApi)

## Why Use This Library?

### 🔒 Built-In Session Management

It handles the plumbing of talking to NSE so you don't have to. A dedicated `Transport` layer wraps an
`httpx.Client` session with connection pooling, sends browser-like headers on every request, loads and
persists cookies via a pluggable cookie store, and restarts the session transparently if a protocol
error occurs.

### ⚡ Automatic Throttling & Retries

Every request is rate-limited (default: **3 requests/second**) and wrapped in exponential backoff with jitter.
Retryable status codes (`429`, `502`, `503`, `504`) and network errors trigger automatic retries, and `Retry-After`
headers are respected.

### 🍪 Pluggable Cookie Storage

Choose the storage backend that fits your deployment:

- **`FileCookieStore`** (default) — Mozilla-format cookie jar on disk
- **`MemoryCookieStore`** — isolated per-process state for multi-worker servers
- **Custom** — subclass `CookieStore` for Redis, databases, or anything else

### 📊 Comprehensive Market Coverage

One consistent interface for the data you actually need:

| Category              | Methods                                                                                                                   |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| **Quotes & Depth**    | `quote`, `equity_quote`, `get_detailed_scrip_data`, `equity_meta_info`                                                    |
| **Options**           | `option_chain`, `compile_option_chain`, `max_pain`, `get_futures_expiry`                                                  |
| **Historical**        | `fetch_equity_historical_data`, `fetch_historical_fno_data`, `fetch_historical_index_data`, `fetch_historical_vix_data`   |
| **Bhavcopies**        | `equity_bhavcopy`, `fno_bhavcopy`, `delivery_bhavcopy`, `pr_bhavcopy`, `indices_bhavcopy`                                 |
| **Corporate Filings** | `actions`, `announcements`, `board_meetings`, `annual_reports`, `financial_results`, `shareholding`, `results_comparison` |
| **Market Screeners**  | `gainers`, `losers`, `live_volume_gainers`, `advance_decline`                                                             |
| **Listings**          | `list_equity_stocks_by_index`, `list_indices`, `list_etf`, `list_sme`, `list_sgb`                                         |
| **IPOs & Deals**      | `list_current_ipo`, `list_upcoming_ipo`, `list_past_ipo`, `block_deals`, `bulk_deals`                                     |
| **Misc**              | `status`, `lookup`, `holidays`, `circulars`, `fno_lots`                                                                   |

### 🛠️ Thoughtful Conveniences

- **`compile_option_chain`** — one call gives you max pain, PCR, ATM, max OI strikes, and a clean per-strike structure ready for analysis
- **Fetch Historical data for various segments** — chunk large date ranges automatically and return results in chronological order
- **Automatic archive handling** — downloads and extracts `.zip` / `.gz` bhavcopies transparently
- **Atomic file downloads** — writes to `.part` files, never leaves partial downloads behind
- **Skip-if-exists** — already-downloaded files are returned immediately

### 🧪 Flexible Configuration

Tune everything at initialization: custom `Limiter` for throttling, custom `RetryConfig` for backoff behaviour, HTTP/2 toggle, per-request timeout, etc.

---

## Quick Start

```python
from datetime import date, datetime
from nse import NSE

with NSE(download_folder=".") as nse:
    # Live quote
    print(nse.equity_quote("HDFCBANK"))

    # current, next and far month expiry
    expiry_dates = nse.get_futures_expiry(index="nifty")

    expiry = datetime.strptime(expiry_dates[0], "%d-%b-%Y")
    print(expiry)

    # Compiled option chain with max pain, PCR, ATM
    chain = nse.compile_option_chain("nifty", expiry_date=expiry)

    print(chain["max_pain"], chain["pcr"], chain["atm"])

    # Historical data with automatic chunking
    data = nse.fetch_equity_historical_data(
        "RELIANCE",
        from_date=date(2023, 1, 1),
        to_date=date(2024, 1, 1),
    )
    print(len(data), "rows")
```

## Credits

The retry mechanism in this library is heavily influenced by the excellent [`httpx-retries`](https://github.com/will-ockmore/httpx-retries) package.

In particular:

- The `RetryConfig` field names (`total`, `max_backoff_wait`, `backoff_factor`, `respect_retry_after_header`, `backoff_jitter`) follow the naming used in `httpx-retries`, so users familiar with that library will feel at home.
- The `_parse_retry_after` function is adapted from `httpx-retries`, which in turn derives its parsing logic from RFC 7231.

That said, the implementation here is not a copy — it is a from-scratch rewrite with a different design.
`httpx-retries` hooks into the `httpx` transport layer, which is elegant but does not provide full control over the
request–response lifecycle. This library needs finer-grained control (for example, to restart the session on
`RemoteProtocolError`, and to integrate with the cookie store). For that reason, the retry logic is implemented
directly as a decorator rather than as an `httpx` transport.

Credit and thanks go to the `httpx-retries` authors for the API design and for the well-tested header-parsing reference.

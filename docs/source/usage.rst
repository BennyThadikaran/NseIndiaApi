Installation & Basic Usage
==========================

Requirements
------------

- **Python** 3.8 or later (tested up to 3.14)
- **Runtime dependencies:**

  - `httpx <https://www.python-httpx.org/>`_ ``~=0.28.1`` — HTTP client
  - `pyrate-limiter <https://pyrate-limiter.readthedocs.io/>`_ ``~=4.5.0`` — request throttling

- **Optional:**

  - ``httpx[http2]`` — required only if you enable HTTP/2
  - ``sphinx`` and ``furo`` — required only for building the documentation

All runtime dependencies are installed automatically with ``pip install nse``.

Installation
------------

From PyPI
~~~~~~~~~

Install the latest stable release:

.. code-block:: bash

   pip install nse

Optional: HTTP/2 Support
~~~~~~~~~~~~~~~~~~~~~~~~

If you want the underlying HTTP client to use HTTP/2 instead of HTTP/1.1, install the ``http2`` extra:

.. code-block:: bash

   pip install "nse[http2]"

Then pass ``use_http2=True`` when constructing the client (see below). Users have reported that NSE behaves more reliably
with HTTP/2 enabled — particularly around network stability in server environments. I would encourage server users to
try both settings under your own workload and see which works better for you.

.. note::

   Keep in mind this library is synchronous, so requests are issued one at a time and HTTP/2's multiplexing benefit does not apply here.

   For desktop / local users, HTTP/2 provides no special benefit and minimal performance gains.

Basic Usage
-----------

Your First Client
~~~~~~~~~~~~~~~~~

Every interaction starts by constructing an ``NSE`` instance. You must pass a ``download_folder`` — this is where cookies are stored by default and where any downloaded files (bhavcopies, annual reports, etc.) are saved.

.. code-block:: python

   from nse import NSE

   with NSE(download_folder=".") as nse:
       print(nse.status())

**Use the context manager.** The ``with`` block guarantees that session cookies are flushed to the cookie store and the underlying HTTP session is closed cleanly when the block exits. If you prefer manual lifecycle management, call ``nse.exit()`` when you're done:

.. code-block:: python

   nse = NSE(download_folder=".")
   try:
       print(nse.status())
   finally:
       nse.exit()

On first use, the client will make a network request to NSE to fetch initial cookies. Subsequent instances reuse the cached cookies from disk until they expire.

.. note::

   All string parameters that represent symbols, indices, series, or instrument names are **case-insensitive**.

   For example, ``nse.quote("hdfcbank")`` and ``nse.quote("HDFCBANK")`` are both equivalent.

Fetching a Live Quote
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

  from nse import NSE

  with NSE(download_folder=".") as nse:
      q = nse.quote("hdfcbank")

      print(q["orderBook"]["lastPrice"])
      print(q["metaData"]["pChange"])
      print(q["metaData"]["companyName"])

If you only need the daily OHLCV bar, use the convenience wrapper:

.. code-block:: python

  with NSE(download_folder=".") as nse:
      bar = nse.equity_quote("hdfcbank")
      print(bar)
      # {'date': '...', 'open': ..., 'high': ..., 'low': ..., 'close': ..., 'volume': ...}

Looking Up a Symbol
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

  with NSE(download_folder=".") as nse:
      result = nse.lookup("HDFCBANK")

      print(result["data"][0]["symbol"])  # HDFCBANK
      print(result["data"][0]["companyName"])  # HDFC Bank Limited

Option Chain
~~~~~~~~~~~~

The ``option_chain`` method returns the raw NSE response. If you don't pass an ``expiry_date``, the nearest valid expiry is resolved automatically and cached locally per symbol.

.. code-block:: python

  from nse import NSE

  with NSE(download_folder=".") as nse:
      chain = nse.option_chain("nifty")
      print(chain["records"]["underlyingValue"])

Building a Readable Option Chain
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The raw NSE response is verbose and hard to work with for analysis. ``compile_option_chain`` reshapes it into a clean, per-strike structure that you can iterate over to build an option chain table like the ones you see on NSE's website or broker platforms.

.. code-block:: python

  from datetime import datetime
  from nse import NSE

  with NSE(download_folder=".") as nse:
      # Resolve the nearest expiry, then parse it into a datetime
      expiry_str = nse.get_futures_expiry("nifty")[0]  # e.g. "26-Oct-2026"
      expiry_date = datetime.strptime(expiry_str, "%d-%b-%Y")

      chain = nse.compile_option_chain("nifty", expiry_date=expiry_date)

      print(f"Underlying:  {chain['underlying']}")
      print(f"ATM strike:  {chain['atm']}")
      print(f"Expiry:      {chain['expiry']}")
      print(f"Max Pain:    {chain['max_pain']}")
      print(f"PCR:         {chain['pcr']}")
      print(f"Max COI:     {chain['max_coi']}  (strike with highest Call OI)")
      print(f"Max POI:     {chain['max_poi']}  (strike with highest Put OI)")
      print(f"Total CE OI: {chain['coi_total']}")
      print(f"Total PE OI: {chain['poi_total']}")

Each strike in ``chain["chain"]`` is keyed by the strike price (as a string) and holds a ``pe`` leg, a ``ce`` leg, and the per-strike PCR:

.. code-block:: python

   chain["chain"]["24000"]
   # {
   #     "pe": {"last": ..., "oi": ..., "chg": ..., "iv": ...},
   #     "ce": {"last": ..., "oi": ..., "chg": ..., "iv": ...},
   #     "pcr": ...,
   # }

Rendering a Table
^^^^^^^^^^^^^^^^^

Because the structure is ordered by strike, you can format it exactly like an option chain on a website — Calls on the left, Puts on the right, with the strike in the middle:

.. code-block:: python

  from datetime import datetime
  from nse import NSE

  with NSE(download_folder=".") as nse:
      expiry_str = nse.get_futures_expiry("nifty")[0]
      expiry_date = datetime.strptime(expiry_str, "%d-%b-%Y")

      chain = nse.compile_option_chain("nifty", expiry_date=expiry_date)

      header = (
          f"{'CE OI':>10} {'CE Chg':>10} {'CE LTP':>10} {'CE IV':>10}"
          f"{'STRIKE':>10}"
          f"{'PE IV':>8} {'PE LTP':>10} {'PE Chg':>10} {'PE OI':>10}"
      )
      print(header)
      print("-" * len(header))

      # Only show strikes near ATM to keep output readable
      atm = chain["atm"]
      window = 500

      for strike_str, row in chain["chain"].items():
          strike = int(strike_str)
          if abs(strike - atm) > window:
              continue

          ce, pe = row["ce"], row["pe"]

          # Highlight the ATM strike
          marker = "  << ATM" if strike == atm else ""

          print(
              f"{ce['oi']:>10,} {ce['chg']:>+10.2f} {ce['last']:>10.2f} {ce['iv']:>10.2f}"
              f"{strike:>10,}"
              f"{pe['iv']:>8.2f} {pe['last']:>10.2f} {pe['chg']:>+10.2f} {pe['oi']:>10,}"
              f"{marker}"
          )

The ``chain`` dict preserves insertion order, and NSE returns strikes sorted ascending — so iterating gives you a top-to-bottom table ordered from lowest to highest strike.

Highlighting Extremes
^^^^^^^^^^^^^^^^^^^^^

The compiled result also gives you the strikes with maximum Call and Put open interest, which are the levels traders watch most closely:

.. code-block:: python

   print(f"Highest Call OI at {chain['max_coi']}  (resistance)")
   print(f"Highest Put OI at {chain['max_poi']}  (support)")
   print(f"Max Pain at {chain['max_pain']}")

Historical Data
~~~~~~~~~~~~~~~

Historical methods automatically chunk large date ranges and return results in chronological order (oldest first).

.. code-block:: python

  from datetime import date
  from nse import NSE

  with NSE(download_folder=".") as nse:
      data = nse.fetch_equity_historical_data(
          symbol="reliance",
          from_date=date(2024, 1, 1),
          to_date=date(2024, 6, 30),
      )

      for row in data[:5]:
          print(row["mtimestamp"], row["chClosingPrice"])

The same pattern works for FnO and index history:

.. code-block:: python

   # Index history
   nse.fetch_historical_index_data(
       index="nifty 50",
       from_date=date(2024, 1, 1),
       to_date=date(2024, 6, 30),
   )

   # FnO history
   nse.fetch_historical_fno_data(
       symbol="nifty",
       instrument="futidx",
       from_date=date(2024, 1, 1),
       to_date=date(2024, 6, 30),
   )

   # India VIX history
   nse.fetch_historical_vix_data(
       from_date=date(2024, 1, 1),
       to_date=date(2024, 6, 30),
   )

Downloading Bhavcopies
~~~~~~~~~~~~~~~~~~~~~~

Bhavcopy methods download the report for a given date and return the path to the saved file. Archives (``.zip`` / ``.gz``) are extracted automatically.

.. code-block:: python

   from datetime import datetime
   from nse import NSE

   with NSE(download_folder="./reports") as nse:
       # Equity bhavcopy
       path = nse.equity_bhavcopy(datetime(2024, 6, 28))
       print("Saved to:", path)

       # FnO bhavcopy
       path = nse.fno_bhavcopy(datetime(2024, 6, 28))
       print("Saved to:", path)

       # Delivery report
       path = nse.delivery_bhavcopy(datetime(2024, 6, 28))
       print("Saved to:", path)

If the report isn't published for the requested date (weekend, holiday, or future date), the method raises ``NSEFileUnavailableError``.

.. code-block:: python

   from nse import NSE, NSEFileUnavailableError

   try:
       nse.equity_bhavcopy(datetime(2024, 6, 29))  # a Saturday
   except NSEFileUnavailableError:
       print("Report not available for this date")

Market Movers
~~~~~~~~~~~~~

.. code-block:: python

   with NSE(download_folder=".") as nse:
       universe = nse.list_equity_stocks_by_index("nifty 50")

       print("Top gainers:")
       for stock in nse.gainers(universe, count=5):
           print(f"  {stock['symbol']:>12} {stock['pChange']:+.2f}%")

       print("Top losers:")
       for stock in nse.losers(universe, count=5):
           print(f"  {stock['symbol']:>12} {stock['pChange']:+.2f}%")

Corporate Filings
~~~~~~~~~~~~~~~~~

.. code-block:: python

   with NSE(download_folder=".") as nse:
       # Forthcoming corporate actions
       actions = nse.actions(symbol="hdfcbank")
       print(actions)

       # Quarterly results summary for a symbol
       result = nse.results_comparison("reliance")
       for row in result["resCmpData"]:
           print(row["re_to_dt"], row.get("re_total_inc"), row.get("re_net_profit"))

       # Shareholding pattern
       holdings = nse.shareholding("hdfcbank")
       print(holdings[0])  # most recent quarter

Configuration
=============

The ``NSE`` constructor accepts several optional arguments to tune behaviour:

.. code-block:: python

   from pathlib import Path
   from pyrate_limiter import Duration, Limiter, Rate
   from nse import NSE, RetryConfig, MemoryCookieStore

   nse = NSE(
       download_folder=Path("./data"),

       # Enable HTTP/2 (requires the `http2` extra)
       use_http2=False,

       # Override the default FileCookieStore
       cookie_store=MemoryCookieStore(),

       # Custom rate limiter: 5 requests per second
       throttle=Limiter(Rate(5, Duration.SECOND)),

       # Custom retry policy
       retry_config=RetryConfig(
           total=3,
           max_backoff_wait=5,
           backoff_factor=0.5,
           respect_retry_after_header=True,
           backoff_jitter=0.5,
       ),

       # Per-request timeout in seconds
       timeout=20,

       # Only used when cookie_store is None
       cookie_filename="cookies.txt",
   )

For advanced rate-limiting strategies (multiple buckets, sliding windows, shared stores across processes), refer to the `pyrate-limiter documentation <https://pyrate-limiter.readthedocs.io/>`_ — any ``Limiter`` instance from that package is accepted.

When to Use ``MemoryCookieStore``
---------------------------------

``FileCookieStore`` (the default) is **not thread-safe**. If you're running under a multi-worker server (gunicorn, uvicorn workers, Celery, etc.), each worker should use its own ``MemoryCookieStore`` to avoid file corruption:

.. code-block:: python

   from nse import NSE, MemoryCookieStore

   nse = NSE(download_folder=".", cookie_store=MemoryCookieStore())

The trade-off: cookies are not persisted between processes, so each new instance pays the cost of an initial cookie-fetch request to NSE.

Sharing the Rate Limit Across Workers
-------------------------------------

By default, each ``NSE`` instance creates its own in-process ``Limiter``, meaning the configured rate (e.g. 3 requests/second) is enforced **per instance**, not globally. Under gunicorn with, say, 4 workers, that means up to 12 requests/second hit NSE — which can quickly trigger rate limiting or temporary blocks.

To enforce a **shared rate limit across all workers**, back the limiter with external storage (Redis is the common choice) so every instance draws from the same bucket. See the `pyrate-limiter documentation <https://pyrate-limiter.readthedocs.io/>`_ for how to configure a persistent bucket.

The recommended pattern for multi-worker deployments is therefore:

- **One shared throttle** backed by external storage, so the rate limit is enforced globally across all workers.
- **One ``MemoryCookieStore`` per worker**, so each process manages its own cookies independently without touching a shared file.

.. code-block:: python

   from pyrate_limiter import Duration, Rate, Limiter
   from pyrate_limiter.storage import RedisStorage
   from nse import NSE, MemoryCookieStore

   storage = RedisStorage(
       host="localhost",
       port=6379,
       db=0,
   )

   rate = Rate(10, Duration.MINUTE)

   # Shared limiter (e.g. Redis-backed) so all workers share the same budget
   shared_throttle = Limiter(rate, storage=storage)

   nse = NSE(
       download_folder=".",
       cookie_store=MemoryCookieStore(),   # per-worker, isolated
       throttle=shared_throttle,           # shared across all workers
   )

Exception Handling
==================

All network-touching methods can raise the following:

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Exception
     - Meaning
   * - ``httpx.TimeoutException``
     - Request timed out and retries were exhausted
   * - ``httpx.ConnectError``
     - Could not connect to NSE
   * - ``httpx.ReadError``
     - Response body could not be read
   * - ``httpx.RemoteProtocolError``
     - Protocol violation; session is restarted automatically
   * - ``RetryableStatusError``
     - NSE returned ``429``, ``502``, ``503``, or ``504`` after retries
   * - ``httpx.HTTPStatusError``
     - Any other non-2xx response
   * - ``NSEFileUnavailableError``
     - A dated report is missing (typically a ``404``)

Notice that all of these — except ``NSEFileUnavailableError`` — are subclasses of ``httpx.HTTPError`` (the base exception class for all ``httpx`` errors). This means you can catch everything network-related with a single ``except httpx.HTTPError`` clause.

(``RetryableStatusError`` is a subclass of ``httpx.HTTPStatusError``.)

.. code-block:: python

   from datetime import datetime
   from nse import NSE, NSEFileUnavailableError
   from httpx import HTTPError

   with NSE(download_folder=".") as nse:
       try:
           path = nse.equity_bhavcopy(datetime(2024, 6, 28))
       except NSEFileUnavailableError:
           # More specific — a report simply isn't available.
           # Handle this first so it isn't swallowed by the broader handler below.
           print("Report not published yet")
       except HTTPError as e:
           # Catch-all for every other httpx error:
           # timeouts, connection failures, read errors, retry exhaustion,
           # non-2xx HTTP statuses, etc.
           print(f"Network error: {e}")

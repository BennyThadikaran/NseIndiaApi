Migration Guide: 4.0.1 → 5.0.0
==============================

Version 5.0.0 is a **hard breaking release**. There are no backward-compatibility
shims, no deprecation aliases, and no automatic migration of on-disk state.

Every change below requires action from you. Please read this document before
upgrading.


Before You Upgrade
------------------

It is recommend to test the migration against a copy of your application's
environment and download directory before upgrading production.


Breaking Changes at a Glance
----------------------------

The following table summarizes the changes that are most likely to require
application changes:

+----------------------+--------------------------------------+--------------------------------------+-----------------------------+
| Area                 | 4.0.1                                | 5.0.0                                | Action                      |
+======================+======================================+======================================+=============================+
| HTTP/2               | ``server=True``                      | ``use_http2=True``                   | Rename the argument         |
+----------------------+--------------------------------------+--------------------------------------+-----------------------------+
| HTTP transport       | ``httpx`` or ``requests``            | ``httpx`` only                       | Remove requests config      |
+----------------------+--------------------------------------+--------------------------------------+-----------------------------+
| Package extras       | ``server`` / ``local``               | ``http2``                            | Update installation command |
+----------------------+--------------------------------------+--------------------------------------+-----------------------------+
| Method names         | camelCase                            | ``snake_case``                       | Rename method calls         |
+----------------------+--------------------------------------+--------------------------------------+-----------------------------+
| Exceptions           | Built-in exceptions                  | ``httpx`` + NSE exceptions           | Update ``except`` blocks    |
+----------------------+--------------------------------------+--------------------------------------+-----------------------------+
| Cookies              | JSON; deleted on exit                | Mozilla cookie jar; persistent       | Review session assumptions  |
+----------------------+--------------------------------------+--------------------------------------+-----------------------------+
| Expiry cache         | ``opt-expiry.json``                  | Per-symbol cache directory           | Delete the old cache        |
+----------------------+--------------------------------------+--------------------------------------+-----------------------------+
| Downloads            | Always re-download                   | Skip existing files                  | Delete files to refresh     |
+----------------------+--------------------------------------+--------------------------------------+-----------------------------+
| ``fno_lots()``       | Empty lot-size rows could be present | Empty lot-size rows omitted          | Handle missing symbols      |
+----------------------+--------------------------------------+--------------------------------------+-----------------------------+


1. Installation Changes
-----------------------

``nse[server]`` and ``nse[local]`` extras are gone.

They have been replaced by a single ``http2`` extra.

4.0.1::

    # HTTP/2 support
    pip install "nse[server]"

    # Plain httpx
    pip install "nse[local]"

5.0.0::

    # HTTP/2 support
    pip install "nse[http2]"

    # Plain httpx (default)
    pip install nse

Requests transport support has also been removed.

The ``use_requests_library=True`` argument and the entire ``requests``-based
transport path have been removed. If your application relied on it, switch to
the default ``httpx`` transport and remove ``requests`` from your dependencies
if it is not used elsewhere.


2. Constructor Changes
----------------------

The ``NSE(...)`` constructor has changed.

+----------------------------------+----------------------------------+
| 4.0.1                            | 5.0.0                            |
+==================================+==================================+
| ``server=False``                 | ``use_http2=False``              |
+----------------------------------+----------------------------------+
| ``use_requests_library=False``   | Removed                          |
+----------------------------------+----------------------------------+
| --                               | ``cookie_store=None``            |
+----------------------------------+----------------------------------+
| --                               | ``throttle=None``                |
+----------------------------------+----------------------------------+
| --                               | ``retry_config=None``            |
+----------------------------------+----------------------------------+
| --                               | ``cookie_filename=None``         |
+----------------------------------+----------------------------------+

For example, change::

    NSE(download_folder=".", server=True)

to::

    NSE(download_folder=".", use_http2=True)

Any code passing ``server=`` or ``use_requests_library=`` will now raise
``TypeError`` during construction.

The new ``cookie_store``, ``throttle``, ``retry_config``, and
``cookie_filename`` arguments provide explicit control over cookie storage,
rate limiting, retry behavior, and the cookie filename.


3. Public Method Renames
------------------------

Every public method has been renamed to ``snake_case``.

There are no compatibility aliases. Calling an old method name raises
``AttributeError``.

+-----------------------------+---------------------------------+
| 4.0.1                       | 5.0.0                           |
+=============================+=================================+
| ``equityBhavcopy``          | ``equity_bhavcopy``             |
+-----------------------------+---------------------------------+
| ``deliveryBhavcopy``        | ``delivery_bhavcopy``           |
+-----------------------------+---------------------------------+
| ``indicesBhavcopy``         | ``indices_bhavcopy``            |
+-----------------------------+---------------------------------+
| ``fnoBhavcopy``             | ``fno_bhavcopy``                |
+-----------------------------+---------------------------------+
| ``boardMeetings``           | ``board_meetings``              |
+-----------------------------+---------------------------------+
| ``equityMetaInfo``          | ``equity_meta_info``            |
+-----------------------------+---------------------------------+
| ``equityQuote``             | ``equity_quote``                |
+-----------------------------+---------------------------------+
| ``liveVolumeGainers``       | ``live_volume_gainers``         |
+-----------------------------+---------------------------------+
| ``listEquityStocksByIndex`` | ``list_equity_stocks_by_index`` |
+-----------------------------+---------------------------------+
| ``listIndices``             | ``list_indices``                |
+-----------------------------+---------------------------------+
| ``listEtf``                 | ``list_etf``                    |
+-----------------------------+---------------------------------+
| ``listSme``                 | ``list_sme``                    |
+-----------------------------+---------------------------------+
| ``listSgb``                 | ``list_sgb``                    |
+-----------------------------+---------------------------------+
| ``listCurrentIPO``          | ``list_current_ipo``            |
+-----------------------------+---------------------------------+
| ``listUpcomingIPO``         | ``list_upcoming_ipo``           |
+-----------------------------+---------------------------------+
| ``listPastIPO``             | ``list_past_ipo``               |
+-----------------------------+---------------------------------+
| ``blockDeals``              | ``block_deals``                 |
+-----------------------------+---------------------------------+
| ``fnoLots``                 | ``fno_lots``                    |
+-----------------------------+---------------------------------+
| ``optionChain``             | ``option_chain``                |
+-----------------------------+---------------------------------+
| ``maxpain``                 | ``max_pain``                    |
+-----------------------------+---------------------------------+
| ``getFuturesExpiry``        | ``get_futures_expiry``          |
+-----------------------------+---------------------------------+
| ``compileOptionChain``      | ``compile_option_chain``        |
+-----------------------------+---------------------------------+
| ``advanceDecline``          | ``advance_decline``             |
+-----------------------------+---------------------------------+
| ``bulkdeals``               | ``bulk_deals``                  |
+-----------------------------+---------------------------------+
| ``getDetailedScripData``    | ``get_detailed_scrip_data``     |
+-----------------------------+---------------------------------+

The ``maxpain`` rename is particularly easy to miss: an underscore was added,
rather than simply changing capitalization.

For example::

    # 4.0.1
    nse.equityBhavcopy(date)
    nse.optionChain("NIFTY")
    nse.maxpain(option_chain, expiry_date)

    # 5.0.0
    nse.equity_bhavcopy(date)
    nse.option_chain("NIFTY")
    nse.max_pain(option_chain, expiry_date)


4. Parameter Renames
--------------------

Several method parameters have also been renamed.

+--------------------------------------+----------------------+----------------------+
| Method                               | 4.0.1                | 5.0.0                |
+======================================+======================+======================+
| ``compileOptionChain``               | ``expiryDate``       | ``expiry_date``      |
+--------------------------------------+----------------------+----------------------+
| ``maxpain``                          | ``optionChain``      | ``option_chain``     |
+--------------------------------------+----------------------+----------------------+
| ``maxpain``                          | ``expiryDate``       | ``expiry_date``      |
+--------------------------------------+----------------------+----------------------+
| ``getDetailedScripData``             | ``marketType``       | ``market_type``      |
+--------------------------------------+----------------------+----------------------+
| ``bulkdeals``                        | ``fromdate``         | ``from_date``        |
+--------------------------------------+----------------------+----------------------+
| ``bulkdeals``                        | ``todate``           | ``to_date``          |
+--------------------------------------+----------------------+----------------------+

The ``bulk_deals`` change is worth calling out separately. It was the only
4.0.1 method using ``fromdate``/``todate`` without underscores. In 5.0.0 it
matches the ``from_date``/``to_date`` naming used elsewhere.


5. Option Chain Result Keys
---------------------------

``compile_option_chain`` returns the same overall structure, but five
top-level result keys have been renamed.

+-------------+---------------+
| 4.0.1       | 5.0.0         |
+=============+===============+
| ``maxpain`` | ``max_pain``  |
+-------------+---------------+
| ``maxCoi``  | ``max_coi``   |
+-------------+---------------+
| ``maxPoi``  | ``max_poi``   |
+-------------+---------------+
| ``coiTotal``| ``coi_total`` |
+-------------+---------------+
| ``poiTotal``| ``poi_total`` |
+-------------+---------------+

The per-strike ``chain`` dictionary is unchanged. Its ``pe``, ``ce``, and
``pcr`` keys remain the same.

For example, change::

    result["maxpain"]
    result["maxCoi"]
    result["maxPoi"]
    result["coiTotal"]
    result["poiTotal"]

to::

    result["max_pain"]
    result["max_coi"]
    result["max_poi"]
    result["coi_total"]
    result["poi_total"]


6. Exception Model
------------------

The exception model has been rewritten.

5.0.0 no longer raises the built-in ``TimeoutError``, ``ConnectionError``,
``FileNotFoundError``, or ``RuntimeError`` for these conditions.

Instead, network failures use ``httpx`` exceptions and unavailable NSE files
use the new ``NSEFileUnavailableError``.

+--------------------------------------+----------------------------------------------+
| 4.0.1                                | 5.0.0                                        |
+======================================+==============================================+
| ``TimeoutError``                     | ``httpx.TimeoutException``                   |
+--------------------------------------+----------------------------------------------+
| ``ConnectionError``                  | ``httpx.ConnectError``, ``httpx.ReadError``, |
|                                      | ``httpx.RemoteProtocolError``, or            |
|                                      | ``httpx.HTTPStatusError`` depending on cause |
+--------------------------------------+----------------------------------------------+
| ``FileNotFoundError``                | ``NSEFileUnavailableError``                  |
+--------------------------------------+----------------------------------------------+
| ``RuntimeError`` for HTML responses  | ``NSEFileUnavailableError`` for HTTP 404     |
+--------------------------------------+----------------------------------------------+
| 429 / 502 / 503 / 504 as             | ``RetryableStatusError`` after retries       |
| ``ConnectionError``                  | are exhausted                                |
+--------------------------------------+----------------------------------------------+

``RetryableStatusError`` subclasses ``httpx.HTTPStatusError``, which in turn
subclasses ``httpx.HTTPError``. Therefore, a single ``except HTTPError`` can
be used when the application does not need to distinguish individual network
failure types.

4.0.1::

    try:
        nse.equityBhavcopy(date)
    except TimeoutError:
        ...
    except ConnectionError:
        ...
    except FileNotFoundError:
        ...
    except RuntimeError:
        ...

5.0.0::

    from httpx import HTTPError
    from nse.transport import NSEFileUnavailableError

    try:
        nse.equity_bhavcopy(date)
    except NSEFileUnavailableError:
        # Report is not available (404)
        ...
    except HTTPError:
        # Network or HTTP failure
        ...

If your application needs different behavior for connection failures,
timeouts, HTTP status errors, or retry exhaustion, catch the appropriate
``httpx`` exception explicitly.


Missing Report Detection
~~~~~~~~~~~~~~~~~~~~~~~~

There is also an important behavioral difference in how missing reports are
detected.

In 4.0.1, the library checked whether NSE returned
``Content-Type: text/html`` and raised ``RuntimeError``.

In 5.0.0, a missing report is detected only when NSE responds with HTTP
``404``.

7. On-Disk State Changes
------------------------

5.0.0 does not read or migrate the old on-disk state automatically.

There are two affected areas: cookies and the option expiry cache.


Cookie File
~~~~~~~~~~~

4.0.1 stored cookies as JSON:

* ``nse_cookies_httpx.json``
* ``nse_cookies_requests.json``

5.0.0 stores cookies in Mozilla cookie-jar format:

* ``cookies.txt``

The old JSON files are not read. On the first run after upgrading, fresh
cookies will be fetched and a new ``cookies.txt`` file will be created.

You can safely delete the old JSON cookie files.

There is also a behavioral change:

* **4.0.1:** the cookie file was deleted on ``exit()``, so cookies did not
  persist between sessions.
* **5.0.0:** cookies persist across sessions in ``cookies.txt``.

This is intentional.

Option Expiry Cache
~~~~~~~~~~~~~~~~~~~

The option expiry cache has also changed.

4.0.1::

    <download_folder>/opt-expiry.json

5.0.0::

    <download_folder>/.opt-expiry-cache/<symbol>.txt

The old cache is not read or migrated.

You can delete ``opt-expiry.json``. The new
``.opt-expiry-cache/`` directory will be created automatically when needed.


8. Rate Limiting
----------------

5.0.0 allows the rate limiter to be shared between ``NSE`` instances.

In 4.0.1, every ``NSE`` instance created its own throttler. Creating multiple
instances could therefore cause their requests to collectively exceed NSE's
rate limit.

In 5.0.0, each ``NSE`` instance still creates its own ``Limiter`` by default,
but you can pass the same ``throttle`` to multiple instances.

Single-process example::

    from pyrate_limiter import Duration, Limiter, Rate
    from nse import NSE

    shared = Limiter(Rate(3, Duration.SECOND))

    a = NSE(download_folder=".", throttle=shared)
    b = NSE(download_folder=".", throttle=shared)

For multi-process deployments such as gunicorn or Celery, the limiter can
also be backed by external storage so that multiple workers share the same
rate-limit budget.

See the `pyrate-limiter documentation`_ for details on configuring persistent
storage.

.. _pyrate-limiter documentation:
   https://pyrate-limiter.readthedocs.io/

For server deployments, a typical configuration uses a per-worker
``MemoryCookieStore`` together with a shared throttle::

    from nse import NSE, MemoryCookieStore

    nse = NSE(
        download_folder=".",
        cookie_store=MemoryCookieStore(),
        throttle=shared_throttle,
    )

Using ``MemoryCookieStore`` keeps cookies isolated between workers while the
shared throttle coordinates their request budget.


9. Existing Downloads Are No Longer Re-downloaded
-------------------------------------------------

4.0.1 always downloaded the requested file, even if an identical file was
already present.

5.0.0 checks whether the target file already exists. If it does, the existing
path is returned immediately without making another network request.

This is intended to avoid unnecessary downloads because NSE filenames are
generally either timestamped or hash-based.

For example, a filename such as::

    BhavCopy_NSE_CM_0_0_0_20250102_F_0000.csv

identifies a specific report artifact.

.. important::

   If your application deliberately re-downloads a report to replace a
   corrupt, incomplete, or stale file, you must delete the existing file
   before calling the download method.

For example::

    from pathlib import Path

    target = Path(
        "./reports/BhavCopy_NSE_CM_0_0_0_20250102_F_0000.csv"
    )
    target.unlink(missing_ok=True)

    nse.equity_bhavcopy(report_date)


10. ``fno_lots`` Changes
------------------------

``fno_lots()`` now omits symbols whose lot size is empty.

In 4.0.1, rows with unparseable lot sizes were skipped, but rows with empty
lot sizes could still be included if the surrounding CSV parsed successfully.

In 5.0.0, empty lot sizes are explicitly omitted.

An empty lot size indicates that the symbol has been removed, or is scheduled
for removal, from the FnO segment.

If your application assumes that every requested symbol is present in the
result, update it to handle missing symbols::

    lots = nse.fno_lots()

    lot = lots.get(symbol)

    if lot is None:
        # Symbol is no longer in FnO.
        ...
    else:
        ...


11. End-to-End Migration Example
--------------------------------

A typical 4.0.1 application might look like this::

    from nse import NSE

    nse = NSE(
        download_folder="./reports",
        server=True,
        use_requests_library=False,
    )

    try:
        path = nse.equityBhavcopy(report_date)
        chain = nse.optionChain("NIFTY")

        result = nse.compileOptionChain(
            chain,
            expiryDate=expiry_date,
        )

        print(result["maxpain"])

    except TimeoutError:
        ...
    except ConnectionError:
        ...
    except FileNotFoundError:
        ...
    except RuntimeError:
        ...

The equivalent 5.0.0 code is::

    from httpx import HTTPError

    from nse import NSE, NSEFileUnavailableError

    nse = NSE(
        download_folder="./reports",
        use_http2=True,
    )

    try:
        path = nse.equity_bhavcopy(report_date)
        chain = nse.option_chain("NIFTY")

        result = nse.compile_option_chain(
            chain,
            expiry_date=expiry_date,
        )

        print(result["max_pain"])

    except NSEFileUnavailableError:
        ...
    except HTTPError:
        ...

The exact configuration of ``cookie_store``, ``throttle``, and
``retry_config`` depends on your application's deployment model.


12. Migration Checklist
-----------------------

Use the following checklist before deploying 5.0.0:

* [ ] Replace ``server=`` with ``use_http2=``.
* [ ] Remove ``use_requests_library=``.
* [ ] Remove the ``requests`` dependency if it is not used elsewhere.
* [ ] Replace ``nse[server]`` / ``nse[local]`` with ``nse[http2]`` or
      plain ``nse`` as appropriate.
* [ ] Rename all public methods to ``snake_case``.
* [ ] Pay particular attention to ``maxpain`` → ``max_pain``.
* [ ] Rename ``expiryDate`` → ``expiry_date``.
* [ ] Rename ``marketType`` → ``market_type``.
* [ ] Rename ``fromdate`` / ``todate`` → ``from_date`` / ``to_date``.
* [ ] Update option-chain result keys:
      ``maxpain`` → ``max_pain``.
* [ ] Update ``maxCoi`` → ``max_coi``.
* [ ] Update ``maxPoi`` → ``max_poi``.
* [ ] Update ``coiTotal`` → ``coi_total``.
* [ ] Update ``poiTotal`` → ``poi_total``.
* [ ] Replace built-in exception handling with ``httpx`` and
      ``NSEFileUnavailableError`` handling.
* [ ] Review any code that assumes an HTML response means a missing report.
* [ ] Delete old ``nse_cookies_httpx.json`` / ``nse_cookies_requests.json``
      files if no longer needed.
* [ ] Review whether persistent ``cookies.txt`` changes your session behavior.
* [ ] Delete the old ``opt-expiry.json`` cache.
* [ ] Review whether multiple ``NSE`` instances should share a ``throttle``.
* [ ] If using multiple processes, configure an externally backed shared
      rate limiter where appropriate.
* [ ] If your application relies on re-downloading an existing report,
      delete the target file before downloading it.
* [ ] If iterating over ``fno_lots()`` results, handle missing symbols.
* [ ] Run your application's test suite against 5.0.0 before production
      deployment.


13. Recommended Upgrade Procedure
---------------------------------

For applications with an existing production deployment, the following
sequence minimizes surprises:

#. Update the installation requirements and method/parameter names.
#. Update exception handling.
#. Review cookie and cache directories.
#. Review code that deliberately re-downloads files.
#. Review any code that creates multiple ``NSE`` instances.
#. Add handling for missing ``fno_lots()`` symbols if required.
#. Run the application's tests against 5.0.0.
#. Test report downloads against a clean download directory.
#. Test a second run using the same download directory to verify that
   skip-if-exists behavior is acceptable.
#. Test the application's session behavior across separate processes or
   runs if persistent cookies are relevant.
#. Deploy to production only after these checks pass.


Summary
-------

The 5.0.0 release requires changes in four broad areas:

* **API:** constructor arguments, method names, parameters, and option-chain
  result keys have changed.
* **Exceptions:** network and file-availability errors now use ``httpx`` and
  NSE-specific exceptions.
* **State:** cookies and the option expiry cache use new formats and
  locations, and cookies now persist between sessions.
* **Behavior:** existing downloads are skipped and ``fno_lots()`` no longer
  returns symbols with empty lot sizes.

There are no compatibility aliases or automatic state migrations, so an
application should be updated for 5.0.0 before switching its production
environment to the new release.

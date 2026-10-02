Running NSE in Server Environments
==================================

The NSE library is designed to be a thin wrapper with minimal dependencies. It
includes throttling and retries to improve network stability and help avoid NSE rate
limits.

It intentionally does not include additional features such as concurrency
management or caching, as these may not be necessary for all users and use
cases.

For server environments where these features may be useful, I've listed some
libraries below that you may want to consider.

Coordinating Concurrent NSE Downloads
--------------------------------------

When multiple processes (Gunicorn workers, Celery tasks, CLI invocations) share
a download folder, the main problem is duplicate downloads. Every process may
fetch the same file over the network, wasting bandwidth and potentially
triggering NSE's rate limits.

A related concern is partial or corrupt files, which can occur if two processes
write to the same path simultaneously. The NSE library mitigates this by writing
to a ``.part`` file and atomically renaming it on success, so the final file is
always complete even if downloads race.

There are two libraries I came across that can help with this: ``filelock`` and
``once-kernel``.

.. note::

   These are not the only libraries available, and I haven't personally used
   them. Their APIs are simple and easy to integrate. They are also not limited
   to file downloads and can be used to coordinate other NSE operations.

FileLock
~~~~~~~~

``filelock`` is a pure-Python library that works well on a single machine where
multiple processes, such as Gunicorn workers, Celery workers, or cron jobs,
share a local filesystem.

A feature of NSE file downloads is that if a file with the same name already
exists in the target folder, it is returned immediately without re-downloading.
This makes NSE work well with ``FileLock``.

You can find the project at:

https://github.com/tox-dev/filelock

An example with ``filelock``:

.. code-block:: python

   from datetime import datetime

   from filelock import FileLock
   from nse import NSE

   report_date = datetime(2025, 1, 2)

   # Any deterministic, unique-per-report name works as the lock key.
   # It does not need to match the actual filename NSE serves.
   lock = FileLock(f"bhavcopy_{report_date:%Y%m%d}.lock")

   with NSE(download_folder="./reports") as nse, lock:
       # First worker to acquire the lock downloads.
       # Every subsequent worker acquires the lock, calls the method,
       # and NSE's internal skip-if-exists check returns the
       # already-downloaded path without a network call.
       path = nse.equity_bhavcopy(report_date)
       print(path)

once-kernel
~~~~~~~~~~~

``once-kernel`` guarantees that a function or method runs exactly once for a
given key and payload, even under concurrent requests.

You provide a key (for example, ``"bhavcopy:20250102"``) and a payload. The
first caller executes the function, while subsequent callers receive the
stored result without re-executing it.

You can find the project at:

https://github.com/achyuthn/once-kernel

Example using a PostgreSQL-backed store:

.. code-block:: python

   from datetime import datetime

   from nse import NSE
   from once import Once
   from once.pg import PostgresStore

   # Shared across all workers (Gunicorn, Celery, etc.)
   store = PostgresStore("postgresql://user:pass@host/db")
   o = Once(store)

   def download_bhavcopy(report_date):
       with NSE(download_folder="./reports") as nse:
           return nse.equity_bhavcopy(report_date)

   # First caller downloads and stores the result.
   # Subsequent callers with the same key and payload
   # get the stored result without re-executing the function.
   path = o.run(
       key="bhavcopy:20250102",
       payload={"date": "20250102"},
       fn=lambda: download_bhavcopy(datetime(2025, 1, 2)),
   )

   print(path)

Caching
-------

``filelock`` and ``once-kernel`` can help coordinate concurrent operations,
ensuring that multiple instances can share a single in-flight request rather
than making duplicate requests.

Caching libraries, on the other hand, reduce repeated requests by storing and
reusing previously fetched data.

For server environments, two caching libraries worth considering are:

DiskCache
~~~~~~~~~

`DiskCache <https://github.com/grantjenks/python-diskcache>`_ is a disk-backed
caching library that uses SQLite and the filesystem to persist cached data. It
is thread- and process-safe and also provides features such as cache-stampede
prevention, locking, and throttling.

dogpile.cache
~~~~~~~~~~~~~

`dogpile.cache <https://github.com/sqlalchemy/dogpile.cache>`_ provides a
common caching interface for multiple backends, including Redis, Memcached,
DBM, and in-memory storage.

It also provides **dogpile locking**, which helps prevent multiple workers from
regenerating the same expired cache entry simultaneously.

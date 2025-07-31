=====
Usage
=====

Installation
------------

**To install on local machine or PC:**

.. code:: console

  $ pip install nse[local]

This will additionally install the requests library.

.. code-block:: python

  # server parameter set to False
  nse = NSE(download_folder='', server=False)

**To install on server like AWS or other cloud services.**

.. code:: console

  $ pip install nse[server]

This will additionally install httpx library with http2 support.

.. code-block:: python

  # Make sure to set server parameter to True.
  nse = NSE(download_folder='', server=True)

Example
-------

.. code-block:: python

   from nse import NSE
   from pathlib import Path

   # Working directory
   DIR = Path(__file__).parent

   nse = NSE(download_folder=DIR)

   status = nse.status()

   nse.exit() # close requests session

.. code-block:: python
   :caption: Using 'with' statement

   with NSE(download_folder=DIR) as nse:
       status = nse.status()

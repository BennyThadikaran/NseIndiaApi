.. NseIndiaApi documentation master file, created by
   sphinx-quickstart on Wed Oct 18 16:55:38 2023.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to NSE's documentation!
===============================

**NSE** is an Unofficial Python Api for NSE India stock exchange

Python version: >= 3.8

All network requests through NSE are rate limited or throttled to 3 requests per second. This allows making large number of requests without overloading the server or getting blocked.

GitHub Source: `BennyThadikaran/NseIndiaApi <https://github.com/BennyThadikaran/NseIndiaApi>`_

To install on local machine or PC:
----------------------------------

.. code:: console

  $ pip install nse[local]

This will additionally install the ``requests`` library.

.. code-block:: python

  # server parameter set to False
  nse = NSE(download_folder='', server=False)

To install on server like AWS or other cloud services.
------------------------------------------------------

.. code:: console

  $ pip install nse[server]

This will additionally install ``httpx`` library with http2 support.

.. code-block:: python

  # Make sure to set server parameter to True.
  nse = NSE(download_folder='', server=True)

Contents
--------

.. toctree::

   usage
   index_categories

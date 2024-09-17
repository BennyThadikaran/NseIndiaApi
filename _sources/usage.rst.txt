=====
Usage
=====

Installation
------------

To use ``nse``, first install it using pip:

.. code:: console

   $ pip install nse

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

API
___

.. autoclass:: nse.NSE

General Methods
---------------

.. automethod:: nse.NSE.exit

.. automethod:: nse.NSE.status

.. automethod:: nse.NSE.holidays

.. automethod:: nse.NSE.blockDeals

Stocks Quotes and Market info
-----------------------------

.. automethod:: nse.NSE.equityMetaInfo

.. automethod:: nse.NSE.quote

.. automethod:: nse.NSE.equityQuote

.. automethod:: nse.NSE.gainers

.. automethod:: nse.NSE.losers

.. automethod:: nse.NSE.advanceDecline

List Stocks
-----------

.. automethod:: nse.NSE.listFnoStocks

.. automethod:: nse.NSE.listIndices

.. automethod:: nse.NSE.listIndexStocks

.. automethod:: nse.NSE.listEtf

.. automethod:: nse.NSE.listSme

.. automethod:: nse.NSE.listSgb

List IPOs
---------

.. automethod:: nse.NSE.listCurrentIPO

.. automethod:: nse.NSE.listUpcomingIPO

.. automethod:: nse.NSE.listPastIPO

NSE Circulars
-------------

.. automethod:: nse.NSE.circulars

Download NSE reports
--------------------

Reports are saved to filesystem and a ``pathlib.Path`` object is returned.

By default, all methods save the file to the ``download_folder`` specified during initialization. Optionally all methods accept a ``folder`` argument if wish to save to another folder.

Zip files are automatically extracted and saved to file.

.. automethod:: nse.NSE.equityBhavcopy

.. automethod:: nse.NSE.deliveryBhavcopy

.. automethod:: nse.NSE.indicesBhavcopy

.. automethod:: nse.NSE.pr_bhavcopy

   .. code-block:: python

      from datetime import datetime
      from zipfile import ZipFile

      import pandas as pd
      from nse import NSE

      dt = datetime(2024, 9, 15)

      with NSE("") as nse:
        # Download the PR bhavcopy zip file
        zipped_file = nse.pr_bhavcopy(dt)

      # Extract all files into current folder
      with ZipFile(zipped_file) as zip:
        zip.namelist() # get the list of files
        zip.extractall()

      # OR Load a file named HL150924.csv from the zipfile into a Pandas DataFrame
      with ZipFile(zipped_file) as file:
        with zip.open(f"HL{dt:%d%m%Y}.csv") as f:
            df = pd.read_csv(f, index_col="Symbol")

.. automethod:: nse.NSE.fnoBhavcopy

.. automethod:: nse.NSE.priceband_report

Corporate Announcements and Actions
-----------------------------------

.. automethod:: nse.NSE.actions

.. automethod:: nse.NSE.announcements

.. automethod:: nse.NSE.boardMeetings

Futures and Options (FnO)
-------------------------

.. automethod:: nse.NSE.getFuturesExpiry

.. automethod:: nse.NSE.fnoLots

.. automethod:: nse.NSE.optionChain

.. automethod:: nse.NSE.compileOptionChain

.. automethod:: nse.NSE.maxpain

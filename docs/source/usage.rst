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

API
___

.. autoclass:: nse.NSE

General Methods
---------------

.. automethod:: nse.NSE.exit

.. automethod:: nse.NSE.status

.. automethod:: nse.NSE.holidays

.. automethod:: nse.NSE.blockDeals

.. automethod:: nse.NSE.bulkdeals

Stocks Quotes and Market info
------------------------------

.. automethod:: nse.NSE.equityMetaInfo

.. automethod:: nse.NSE.quote

.. automethod:: nse.NSE.equityQuote

.. automethod:: nse.NSE.gainers

.. automethod:: nse.NSE.losers

.. automethod:: nse.NSE.advanceDecline

.. automethod:: nse.NSE.fetch_index_names

.. automethod:: nse.NSE.fetch_equity_historical_data

.. automethod:: nse.NSE.fetch_historical_vix_data

.. automethod:: nse.NSE.fetch_historical_fno_data

.. automethod:: nse.NSE.fetch_historical_index_data

.. automethod:: nse.NSE.fetch_fno_underlying

List Stocks
-----------

.. automethod:: nse.NSE.listFnoStocks

.. automethod:: nse.NSE.listEquityStocksByIndex

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

.. automethod:: nse.NSE.fetch_daily_reports_file_metadata

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

.. automethod:: nse.NSE.cm_mii_security_report

.. automethod:: nse.NSE.download_document

   This method is useful for downloading attachments from announcements, actions etc. See code example below

   .. code-block:: python

      from nse import NSE

      with NSE(download_folder="") as nse:
          announcements = nse.announcements()

          for dct in announcements:
              # Only download the first pdf attachment
              if "attchmntFile" in dct and ".pdf" in dct["attchmntFile"]:
                  filepath = nse.download_document(dct["attchmntFile"])
                  print(filepath)  # saved file path
                  break

Corporate Announcements and Actions
-----------------------------------

.. automethod:: nse.NSE.actions

.. automethod:: nse.NSE.announcements

.. automethod:: nse.NSE.boardMeetings

.. automethod:: nse.NSE.annual_reports

Futures and Options (FnO)
-------------------------

.. automethod:: nse.NSE.getFuturesExpiry

.. automethod:: nse.NSE.fnoLots

.. automethod:: nse.NSE.optionChain

.. automethod:: nse.NSE.compileOptionChain

.. automethod:: nse.NSE.maxpain

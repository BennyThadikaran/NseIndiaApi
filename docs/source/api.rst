===
API
===

NSE class
=========


.. autoclass:: nse.NSE
   :special-members: __init__

General Methods
---------------

.. automethod:: nse.NSE.exit

.. automethod:: nse.NSE.status

.. automethod:: nse.NSE.lookup

.. automethod:: nse.NSE.holidays

.. automethod:: nse.NSE.block_deals

.. automethod:: nse.NSE.bulk_deals

Stocks Quotes and Market info
-----------------------------

.. automethod:: nse.NSE.equity_meta_info

.. automethod:: nse.NSE.shareholding

.. automethod:: nse.NSE.quote

.. automethod:: nse.NSE.equity_quote

.. automethod:: nse.NSE.get_detailed_scrip_data

.. automethod:: nse.NSE.live_volume_gainers

.. automethod:: nse.NSE.gainers

.. automethod:: nse.NSE.losers

.. automethod:: nse.NSE.advance_decline

.. automethod:: nse.NSE.fetch_index_names

.. automethod:: nse.NSE.fetch_equity_historical_data

.. automethod:: nse.NSE.fetch_historical_vix_data

.. automethod:: nse.NSE.fetch_historical_fno_data

.. automethod:: nse.NSE.fetch_historical_index_data

.. automethod:: nse.NSE.fetch_fno_underlying

List Stocks
-----------

.. automethod:: nse.NSE.list_equity_stocks_by_index

.. automethod:: nse.NSE.list_indices

.. automethod:: nse.NSE.list_etf

.. automethod:: nse.NSE.list_sme

.. automethod:: nse.NSE.list_sgb

List IPOs
---------

.. automethod:: nse.NSE.list_current_ipo

.. automethod:: nse.NSE.list_upcoming_ipo

.. automethod:: nse.NSE.list_past_ipo

NSE Circulars
-------------

.. automethod:: nse.NSE.circulars

Download NSE reports
--------------------

Reports are saved to filesystem and a ``pathlib.Path`` object is returned.

By default, all methods save the file to the ``download_folder`` specified during initialization. Optionally all methods accept a ``folder`` argument if wish to save to another folder.

Zip files are automatically extracted and saved to file.

.. automethod:: nse.NSE.fetch_daily_reports_file_metadata

.. automethod:: nse.NSE.equity_bhavcopy

.. automethod:: nse.NSE.delivery_bhavcopy

.. automethod:: nse.NSE.indices_bhavcopy

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

.. automethod:: nse.NSE.fno_bhavcopy

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

  The below code to downloads PR290725.zip from NSE daily reports and extract only mcap and etf files.

  .. code-block:: python
      
    dt = date(2025, 7, 29)
    BHAV_PR_URL = f"https://nsearchives.nseindia.com/archives/equities/bhavcopy/pr/PR{dt:%d%m%y}.zip"

    # Specify the file names to extract in a list
    file_list = [
      f"mcap{dt:%d%m%Y}.csv",
      f"etf{dt:%d%m%y}.csv",
    ]

    with NSE("") as nse:
        nse.download_document(BHAV_PR_URL, extract_files=file_list)

Corporate Announcements and Actions
-----------------------------------

.. automethod:: nse.NSE.actions

.. automethod:: nse.NSE.announcements

.. automethod:: nse.NSE.board_meetings

.. automethod:: nse.NSE.annual_reports

.. automethod:: nse.NSE.financial_results

.. automethod:: nse.NSE.results_comparison

Futures and Options (FnO)
-------------------------

.. automethod:: nse.NSE.get_futures_expiry

.. automethod:: nse.NSE.fno_lots

.. automethod:: nse.NSE.option_chain

.. automethod:: nse.NSE.compile_option_chain

.. automethod:: nse.NSE.max_pain

Retry Configuration
===================

.. autoclass:: nse.RetryConfig

Type Reference
==============

The library exposes some :class:`~typing.TypedDict` classes that describe
the shape of structured return values. They are primarily useful for type
checkers and editor autocomplete; at runtime they behave like ordinary
:class:`dict` objects.


OHLCV
-----

Result of :meth:`NSE.equity_quote`.

.. autoclass:: nse.NSE.OHLCV
   :members:
   :undoc-members:

CompiledOptionChain
-------------------

.. autoclass:: nse.NSE.CompiledOptionChain
   :members:
   :undoc-members:

StrikeRow
---------

.. autoclass:: nse.NSE.StrikeRow
   :members:
   :undoc-members:

OptionLeg
---------

.. autoclass:: nse.NSE.OptionLeg
   :members:
   :undoc-members:

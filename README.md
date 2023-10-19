# NseIndiaApi

An unofficial Python API for the NSE India stock exchange.

Python version: >= 3.10

## Install with PIP

```bash
pip install nse
```

## Usage

NSE class takes a single argument `download_folder`. This folder is used to store cookies and any downloaded files. It accepts a string folder path or `pathlib.Path` object.

```python
from nse import NSE
from pathlib import Path

# Working directory
DIR = Path(__file__).parent

nse = NSE(download_folder=DIR)

status = nse.status()

advDec = nse.advanceDecline()

nse.exit() # close requests session
```

Using with statement

```python
with NSE(download_folder=DIR) as nse:
    status = nse.status()

    advDec = nse.advanceDecline()
```

## More detailed documentation to follow soon

## Samples folder

The `src/samples` folder contains sample outputs of various methods. The filenames match the method names. The output has been truncated in some places but demonstrates the overall structure of responses.

## Methods signatures

```python
Help on class NSE in module nse.NSE

class NSE(builtins.object)
 |  NSE(download_folder: str | pathlib.Path)
 |
 |  Methods defined here:
 |
 |  __init__(self, download_folder: str | pathlib.Path)
 |      Initialise NSE
 |      Params:
 |      download_folder - A folder to store downloaded files and cookie files
 |
 |  actions(self,
 |          segment: Literal['equities', 'sme', 'debt', 'mf'],
 |          symbol: str | None = None,
 |          from_dt: datetime.datetime | None = None,
 |          to_dt: datetime.datetime | None = None)
 |      Get all corporate actions for specified dates or all forthcoming,
 |      Optionally specify symbol to get actions only for that symbol.
 |
 |      Params:
 |      segment - One of equities, sme, debt or mf
 |      symbol[Optional] - Stock symbol
 |      from_dt[Optional] - From Datetime
 |      to_dt[Optional] - To Datetime
 |
 |  advanceDecline(self)
 |      Advance decline for all NSE indices
 |
 |  blockDeals(self)
 |      Block deals
 |
 |  compileOptionChain(self,
 |                     symbol: Union[str, Literal['banknifty',
 |                                                'nifty',
 |                                                'finnifty',
 |                                                'niftyit']],
 |                     expiryDate: datetime.datetime)
 |      Returns a dictionary of option chain with related statistics
 |
 |      Params:
 |      symbol - FnO stock or Index futures code
 |      expiryDate - Expiry date
 |
 |  deliveryBhavcopy(self,
 |                   date: datetime.datetime,
 |                   folder: str | pathlib.Path | None = None)
 |      Download the daily report for Equity delivery data for specified
 |      date and return saved file path.
 |
 |      Params:
 |      date - Date of bhavcopy to download
 |      folder[Optional] - Save to folder. If not specified,
 |              use download_folder specified during class initializataion.
 |
 |  equityBhavcopy(self,
 |                 date: datetime.datetime,
 |                 folder: str | pathlib.Path | None = None)
 |      Download the daily report for Equity bhav copy for specified date
 |      and return the saved file path.
 |
 |      Params:
 |      date - Date of bhavcopy to download
 |      folder[Optional] - Save to folder. If not specified,
 |              use download_folder specified during class initializataion.
 |
 |  equityMetaInfo(self, symbol)
 |      Meta info for equity symbols.
 |
 |      Params:
 |      symbol - Equity symbol
 |
 |  exit(self)
 |      Close the requests session
 |
 |  fnoBhavcopy(self,
 |              date: datetime.datetime,
 |              folder: str | pathlib.Path | None = None)
 |      Download the daily report for FnO bhavcopy for specified date
 |      and return the saved file path.
 |
 |      Params:
 |      date - Date of bhavcopy to download
 |      folder[Optional] - Save to folder. If not specified,
 |              use download_folder specified during class initializataion.
 |
 |  fnoLots(self) -> dict[str, int]
 |      Return a dictionary containing lot size of FnO stocks.
 |      Keys are stock symbols and values are lot sizes
 |
 |  gainers(self, data: dict, count: int | None = None)
 |      Top gainers (percent change above zero).
 |      Returns all stocks or limit to integer count
 |
 |      Params:
 |      data - Output of one of NSE.listIndexStocks,
 |                              NSE.listSME,
 |                              NSE.listFnoStocks
 |      count - Number of results to return. If None, returns all results
 |
 |  holidays(self,
 |           type: Literal['trading', 'clearing'] = 'trading')
 |      Returns NSE holiday list
 |
 |      Params:
 |      type[Default 'trading'] - One of 'trading' or 'clearing'
 |
 |  indicesBhavcopy(self,
 |                  date: datetime.datetime,
 |                  folder: str | pathlib.Path | None = None)
 |      Download the daily report for Equity Index for specified date
 |      and return the saved file path.
 |
 |      Params:
 |      date - Date of bhavcopy to download
 |      folder[Optional] - Save to folder. If not specified,
 |              use download_folder specified during class initializataion.
 |
 |  listEtf(self)
 |      List all etf stocks
 |
 |  listFnoStocks(self)
 |      List all Futures and Options (FNO) stocks
 |
 |  listIndexStocks(self, index)
 |      List all stocks by index
 |
 |      Params:
 |      index - Market Index Name
 |
 |  listIndices(self)
 |      List all indices
 |
 |  listSME(self)
 |      List all sme stocks
 |
 |  listSgb(self)
 |      List all sovereign gold bonds
 |
 |  losers(self,
           data: dict,
           count: int | None = None)
 |      Top losers (percent change below zero).
 |      Returns all stocks or limit to integer count
 |
 |      Params:
 |      data - Output of one of NSE.listIndexStocks,
 |                              NSE.listSME,
 |                              NSE.listFnoStocks
 |      count - Number of result to return. If None, returns all result
 |
 |  optionChain(self,
 |              symbol: Union[Literal['banknifty',
 |                                    'nifty',
 |                                    'finnifty',
 |                                    'niftyit'], str])
 |      Raw option chain from api for Index futures or FNO stocks
 |
 |      Params:
 |      symbol - FnO stock or index futures code.
 |               For Index futures, must be one of 'banknifty', 'nifty',
 |               'finnifty', 'niftyit'
 |
 |  quote(self,
 |        symbol,
 |        type: Literal['equity', 'fno'] = 'equity',
 |        section: Optional[Literal['trade_info']] = None)
 |      Returns price quotes and other data for equity or derivative symbols
 |
 |      Params:
 |      symbol - Equity symbol
 |      type[Default 'equity'] - One of 'equity' or 'fno'
 |      section[Optional] - If specified must be 'trade_info'
 |
 |  status(self)
 |      Returns market status
 |
 |  stockQuote(self, symbol)
 |      Returns a formatted dictionary of OCHLV data for equity symbol
 |
 |      Params:
 |      symbol - Equity symbol
 |
 |  ----------------------------------------------------------------------
 |  Static methods defined here:
 |
 |  maxpain(optionChain, expiryDate: datetime.datetime) -> float
 |      Returns the options strike price with Max Pain
 |
 |      Params:
 |      optionChain - Output of NSE.optionChain
 |      expiryDate - Expiry date
 |
```

## Constants

Accessed as `nse.FNO_BANK`.

```python
 |  FNO_BANK = 'banknifty'
 |
 |  FNO_FINNIFTY = 'finnifty'
 |
 |  FNO_IT = 'niftyit'
 |
 |  FNO_NIFTY = 'nifty'
 |
 |  HOLIDAY_CLEARING = 'clearing'
 |
 |  HOLIDAY_TRADING = 'trading'
 |
 |  SEGMENT_DEBT = 'debt'
 |
 |  SEGMENT_EQUITY = 'equities'
 |
 |  SEGMENT_MF = 'mf'
 |
 |  SEGMENT_SME = 'sme'
```

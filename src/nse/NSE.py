import pickle
from pathlib import Path
from requests import Session
from requests.exceptions import ReadTimeout
from typing import Literal, Any
from datetime import datetime
from zipfile import ZipFile
from mthrottle import Throttle

throttleConfig = {
    'default': {
        'rps': 3,
    },
}

th = Throttle(throttleConfig, 10)


class NSE:

    '''An Unofficial Python API for the NSE India stock exchange.

    Methods will raise
        - a ``TimeoutError`` if request takes too long.
        - a ``ConnectionError`` if request failed for any reason.

    :param download_folder: A folder/dir to save downloaded files and cookie files
    :type download_folder: pathlib.Path or str
    :raise ValueError: if ``download_folder`` is not a folder/dir
    '''

    SEGMENT_EQUITY = 'equities'
    SEGMENT_SME = 'sme'
    SEGMENT_MF = 'mf'
    SEGMENT_DEBT = 'debt'

    HOLIDAY_CLEARING = 'clearing'
    HOLIDAY_TRADING = 'trading'

    FNO_BANK = 'banknifty'
    FNO_NIFTY = 'nifty'
    FNO_FINNIFTY = 'finnifty'
    FNO_IT = 'niftyit'

    __optionIndex = ('banknifty', 'nifty', 'finnifty', 'niftyit')
    base_url = 'https://www.nseindia.com/api'
    archive_url = 'https://archives.nseindia.com'

    def __init__(self, download_folder: str | Path):
        '''Initialise NSE'''

        uAgent = 'Mozilla/5.0 (Windows NT 10.0; rv:109.0) Gecko/20100101 Firefox/118.0'

        headers = {
            'User-Agent': uAgent,
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': 'https://www.nseindia.com/get-quotes/equity?symbol=HDFCBANK'
        }

        self.dir = NSE.__getPath(download_folder, isFolder=True)

        self.cookie_path = self.dir / 'nse_cookies.pkl'

        self.session = Session()
        self.session.headers.update(headers)
        self.session.cookies.update(self.__getCookies())

    def __setCookies(self):
        r = self.__req('https://www.nseindia.com/option-chain', timeout=10)

        cookies = r.cookies

        self.cookie_path.write_bytes(pickle.dumps(cookies))

        return cookies

    def __getCookies(self):

        if self.cookie_path.exists():
            cookies = pickle.loads(self.cookie_path.read_bytes())

            if self.__hasCookiesExpired(cookies):
                cookies = self.__setCookies()

            return cookies

        return self.__setCookies()

    @staticmethod
    def __hasCookiesExpired(cookies):
        for cookie in cookies:
            if cookie.is_expired():
                return True

        return False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.session.close()

        if not exc_type is None:
            exit(f'{exc_type}: {exc_value}\n{exc_traceback}')
        return True

    @staticmethod
    def __getPath(path: str | Path, isFolder: bool = False):
        path = path if isinstance(path, Path) else Path(path)

        if isFolder:
            if path.is_file():
                raise ValueError(f'{path}: must be a folder')

            if not path.exists():
                path.mkdir(parents=True)

        return path

    @staticmethod
    def __unzip(file: Path, folder: Path):
        with ZipFile(file) as zip:
            filepath = zip.extract(member=zip.namelist()[0], path=folder)

        file.unlink()
        return Path(filepath)

    def __download(self, url: str, folder: Path):
        '''Download a large file in chunks from the given url.
        Returns pathlib.Path object of the downloaded file'''

        fname = folder / url.split("/")[-1]

        th.check()

        try:
            with self.session.get(url,
                                  stream=True,
                                  timeout=15) as r:

                with fname.open(mode='wb') as f:
                    for chunk in r.iter_content(chunk_size=1000000):
                        f.write(chunk)
        except Exception as e:
            exit(f'Download error. Try again later: {e!r}')

        return fname

    def __req(self, url, params=None, timeout=10):
        '''Make a http request'''

        th.check()

        try:
            r = self.session.get(
                url,
                params=params,
                timeout=timeout
            )
        except ReadTimeout as e:
            raise TimeoutError(repr(e))

        if not r.ok:
            raise ConnectionError(f'{url} {r.status_code}: {r.reason}')

        return r

    def exit(self):
        '''Close the ``requests`` session.

        *Use at the end of script or when class is no longer required.*

        *Not required when using the ``with`` statement.*'''

        self.session.close()

    def status(self) -> list[dict]:
        '''Returns market status

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/status.json>`__

        :return: Market status of all NSE market segments
        :rtype: list[dict]
        '''

        return self.__req(f'{self.base_url}/marketStatus').json()['marketState']

    def equityBhavcopy(self, date: datetime, folder: str | Path | None = None) -> Path:
        '''Download the daily Equity bhavcopy report for specified ``date``
        and return the saved file path.

        :param date: Date of bhavcopy to download
        :type date: datetime.datetime
        :param folder: Optional folder/dir path to save file. If not specified, use ``download_folder`` specified during class initializataion.
        :type folder: pathlib.Path or str
        :raise ValueError: if ``folder`` is not a folder/dir.
        :raise FileNotFoundError: if download failed or file corrupted
        :return: Path to saved file
        :rtype: pathlib.Path
        '''

        date_str = date.strftime('%d%b%Y').upper()
        month = date_str[2:5]

        folder = NSE.__getPath(folder, isFolder=True) if folder else self.dir

        url = '{}/content/historical/EQUITIES/{}/{}/cm{}bhav.csv.zip'.format(
            self.archive_url,
            date.year,
            month,
            date_str)

        file = self.__download(url, folder)

        if not file.is_file() or file.stat().st_size < 5000:
            file.unlink()
            raise FileNotFoundError(f'Failed to download file: {file.name}')

        return NSE.__unzip(file, file.parent)

    def deliveryBhavcopy(self, date: datetime, folder: str | Path | None = None):
        '''Download the daily Equity delivery report for specified ``date`` and return saved file path.

        :param date: Date of delivery bhavcopy to download
        :type date: datetime.datetime
        :param folder: Optional folder/dir path to save file. If not specified, use ``download_folder`` specified during class initializataion.
        :type folder: pathlib.Path or str
        :raise ValueError: if ``folder`` is not a folder/dir
        :raise FileNotFoundError: if download failed or file corrupted
        :return: Path to saved file
        :rtype: pathlib.Path'''

        folder = NSE.__getPath(folder, isFolder=True) if folder else self.dir

        url = '{}/products/content/sec_bhavdata_full_{}.csv'.format(
            self.archive_url,
            date.strftime('%d%m%Y'))

        file = self.__download(url, folder)

        if not file.is_file() or file.stat().st_size < 50000:
            file.unlink()
            raise FileNotFoundError(f'Failed to download file: {file.name}')

        return file

    def indicesBhavcopy(self, date: datetime, folder: str | Path | None = None):
        '''Download the daily Equity Indices report for specified ``date``
        and return the saved file path.

        :param date: Date of Indices bhavcopy to download
        :type date: datetime.datetime
        :param folder: Optional folder/dir path to save file. If not specified, use ``download_folder`` specified during class initializataion.
        :type folder: pathlib.Path or str
        :raise ValueError: if ``folder`` is not a folder/dir
        :raise FileNotFoundError: if download failed or file corrupted
        :return: Path to saved file
        :rtype: pathlib.Path'''

        folder = NSE.__getPath(folder, isFolder=True) if folder else self.dir

        url = f'{self.archive_url}/content/indices/ind_close_all_{date:%d%m%Y}.csv'

        file = self.__download(url, folder)

        if not file.is_file() or file.stat().st_size < 5000:
            file.unlink()
            raise FileNotFoundError(f'Failed to download file: {file.name}')

        return file

    def fnoBhavcopy(self, date: datetime, folder: str | Path | None = None):
        '''Download the daily FnO bhavcopy report for specified ``date``
        and return the saved file path.

        :param date: Date of FnO bhavcopy to download
        :type date: datetime.datetime
        :param folder: Optional folder path to save file. If not specified, use ``download_folder`` specified during class initializataion.
        :type folder: pathlib.Path or str
        :raise ValueError: if ``folder`` is not a dir/folder
        :raise FileNotFoundError: if download failed or file corrupted
        :return: Path to saved file
        :rtype: pathlib.Path'''

        dt_str = date.strftime('%d%b%Y').upper()

        month = dt_str[2:5]
        year = dt_str[-4:]

        folder = NSE.__getPath(folder, isFolder=True) if folder else self.dir

        url = f'{self.archive_url}/content/historical/DERIVATIVES/{year}/{month}/fo{dt_str}bhav.csv.zip'

        file = self.__download(url, folder)

        if not file.is_file() or file.stat().st_size < 5000:
            file.unlink()
            raise FileNotFoundError(f'Failed to download file: {file.name}')

        return NSE.__unzip(file, folder=file.parent)

    def actions(self,
                segment: Literal['equities', 'sme', 'debt', 'mf'] = 'equities',
                symbol: str | None = None,
                from_date: datetime | None = None,
                to_date: datetime | None = None) -> list[dict]:
        '''Get all forthcoming corporate actions.

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/actions.json>`__

        If ``symbol`` is specified, only actions for the ``symbol`` is returned.

        If ``from_data`` and ``to_date`` are specified, actions within the date range are returned

        :param segment: One of ``equities``, ``sme``, ``debt`` or ``mf``. Default ``equities``
        :type segment: str
        :param symbol: Optional Stock symbol
        :type symbol: str or None
        :param from_date: Optional from date
        :type from_date: datetime.datetime
        :param to_date: Optional to date
        :type to_date: datetime.datetime
        :raise ValueError: if ``from_date`` is greater than ``to_date``
        :return: A list of corporate actions
        :rtype: list[dict]'''

        fmt = '%d-%m-%Y'

        params = {
            'index': segment,
        }

        if symbol:
            params['symbol'] = symbol

        if from_date and to_date:
            if from_date > to_date:
                raise ValueError(
                    "'from_date' cannot be greater than 'to_date'")

            params.update({
                'from_date': from_date.strftime(fmt),
                'to_date': to_date.strftime(fmt)
            })

        url = f'{self.base_url}/corporates-corporateActions'

        return self.__req(url, params=params).json()

    def announcements(self,
                      index: Literal['equities',
                                     'sme',
                                     'debt',
                                     'mf',
                                     'invitsreits'] = 'equities',
                      symbol: str | None = None,
                      fno=False,
                      from_date: datetime | None = None,
                      to_date: datetime | None = None) -> list[dict]:
        '''Get all corporate announcements for current date.

        If symbol is specified, only announcements for the symbol is returned.

        If from_date and to_date are specified, announcements within the date range are returned

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/announcements.json>`__

        :param index: One of `equities`, `sme`, `debt` or `mf`. Default ``equities``
        :type index: str
        :param symbol: Optional Stock symbol
        :type symbol: str or None
        :param fno: Only FnO stocks
        :type fno: bool
        :param from_date: Optional from date
        :type from_date: datetime.datetime
        :param to_date: Optional to date
        :type to_date: datetime.datetime
        :raise ValueError: if ``from_date`` is greater than ``to_date``
        :return: A list of corporate actions
        :rtype: list[dict]'''

        fmt = '%d-%m-%Y'

        params: dict[str, Any] = {
            'index': index
        }

        if symbol:
            params['symbol'] = symbol

        if fno:
            params['fo_sec'] = True

        if from_date and to_date:
            if from_date > to_date:
                raise ValueError(
                    "'from_date' cannot be greater than 'to_date'")

            params.update({
                'from_date': from_date.strftime(fmt),
                'to_date': to_date.strftime(fmt)
            })

        url = f'{self.base_url}/corporate-announcements'

        return self.__req(url, params=params).json()

    def boardMeetings(self,
                      index: Literal['equities', 'sme'] = 'equities',
                      symbol: str | None = None,
                      fno: bool = False,
                      from_date: datetime | None = None,
                      to_date: datetime | None = None) -> list[dict]:
        '''Get all forthcoming board meetings.

        If symbol is specified, only board meetings for the symbol is returned.

        If ``from_date`` and ``to_date`` are specified, board meetings within the date range are returned

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/boardMeetings.json>`__

        :param index: One of ``equities`` or ``sme``. Default ``equities``
        :type index: str
        :param symbol: Optional Stock symbol
        :type symbol: str or None
        :param fno: Only FnO stocks
        :type fno: bool
        :param from_date: Optional from date
        :type from_date: datetime.datetime
        :param to_date: Optional to date
        :type to_date: datetime.datetime
        :raise ValueError: if ``from_date`` is greater than ``to_date``
        :return: A list of corporate board meetings
        :rtype: list[dict]'''

        fmt = '%d-%m-%Y'

        params: dict[str, Any] = {
            'index': index
        }

        if symbol:
            params['symbol'] = symbol

        if fno:
            params['fo_sec'] = True

        if from_date and to_date:
            if from_date > to_date:
                raise ValueError(
                    "'from_date' cannot be greater than 'to_date'")

            params.update({
                'from_date': from_date.strftime(fmt),
                'to_date': to_date.strftime(fmt)
            })

        url = f'{self.base_url}/corporate-board-meetings'

        return self.__req(url, params=params).json()

    def equityMetaInfo(self, symbol) -> dict:
        '''Meta info for equity symbols.

        Provides useful info like stock name, code, industry, ISIN code, current status like suspended, delisted etc.

        Also has info if stock is an FnO, ETF or Debt security

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/equityMetaInfo.json>`__

        :param symbol: Equity symbol code
        :type symbol: str
        :return: Stock meta info
        :rtype: dict'''

        url = f'{self.base_url}/equity-meta-info'

        return self.__req(url, params={'symbol': symbol.upper()}).json()

    def quote(self,
              symbol,
              type: Literal['equity', 'fno'] = 'equity',
              section: Literal['trade_info'] | None = None) -> dict:
        """Price quotes and other data for equity or derivative symbols

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/quote.json>`__

        :param symbol: Equity symbol code
        :type symbol: str
        :param type: One of ``equity`` or ``fno``. Default ``equity``
        :type type: str
        :param section: Optional. If specified must be ``trade_info``
        :raise ValueError: if ``section`` does not equal ``trade_info``
        :return: Price quote and other stock meta info
        :rtype: dict"""

        if type == 'equity':
            url = f'{self.base_url}/quote-equity'
        else:
            url = f'{self.base_url}/quote-derivative'

        params = {
            'symbol': symbol.upper()
        }

        if section:
            if section != 'trade_info':
                raise ValueError("'Section' if specified must be 'trade_info'")

            params['section'] = section

        return self.__req(url, params=params).json()

    def equityQuote(self, symbol) -> dict[str, str | float]:
        '''A convenience method that extracts date and OCHLV data from ``NSE.quote`` for given stock ``symbol``

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/equityQuote.json>`__

        :param symbol: Equity symbol code
        :type symbol: str
        :return: Date and OCHLV data
        :rtype: dict[str, str | float]'''

        q = self.quote(symbol, type='equity')
        v = self.quote(symbol, type='equity', section='trade_info')

        _open, minmax, close, ltp = map(
            q['priceInfo'].get, ('open', 'intraDayHighLow', 'close', 'lastPrice'))

        return {
            'date': q['metadata']['lastUpdateTime'],
            'open': _open,
            'high': minmax['max'],
            'low': minmax['min'],
            'close': close or ltp,
            'volume': v['securityWiseDP']['quantityTraded'],
        }

    def gainers(self, data: dict, count: int | None = None) -> list[dict]:
        '''Top gainers by percent change above zero.

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/gainers.json>`__

        :param data: - Output of one of ``NSE.listIndexStocks``, ``NSE.listSME``, ``NSE.listFnoStocks``
        :type data: dict
        :param count: Optional. Limit number of result returned
        :type count: int
        :return: List of top gainers
        :rtype: list[dict]'''

        return sorted(filter(lambda dct: dct['pChange'] > 0, data['data']),
                      key=lambda dct: dct['pChange'],
                      reverse=True)[:count]

    def losers(self, data: dict, count: int | None = None) -> list[dict]:
        '''Top losers by percent change below zero.

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/losers.json>`__

        :param data: - Output of one of ``NSE.listIndexStocks``, ``NSE.listSME``, ``NSE.listFnoStocks``
        :type data: dict
        :param count: Optional. Limit number of result returned
        :type count: int
        :return: List of top losers
        :rtype: list[dict]'''

        return sorted(filter(lambda dct: dct['pChange'] < 0, data['data']),
                      key=lambda dct: dct['pChange'])[:count]

    def listFnoStocks(self):
        '''List all Futures and Options (FNO) stocks

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/listFnoStocks.json>`__

        :return: A dictionary. The ``data`` key is a list of all FnO stocks represented by a dictionary with the symbol name and other metadata.'''

        url = f'{self.base_url}/equity-stockIndices'

        return self.__req(url, params={'index': 'SECURITIES IN F&O'}).json()

    def listIndices(self):
        '''List all indices

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/listIndices.json>`__

        :return: A dictionary. The ``data`` key is a list of all Indices represented by a dictionary with the symbol code and other metadata.'''

        url = f'{self.base_url}/allIndices'

        return self.__req(url).json()

    def listIndexStocks(self, index):
        '''List all stocks by index

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/listIndexStocks.json>`__

        :param index: Market Index Name
        :type index: str
        :return: A dictionary. The ``data`` key is a list of all stocks represented by a dictionary with the symbol code and other metadata.'''

        return self.__req(f'{self.base_url}/equity-stockIndices', params={
            'index': index.upper()
        }).json()

    def listEtf(self):
        '''List all etf stocks

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/listEtf.json>`__

        :return: A dictionary. The ``data`` key is a list of all ETF's represented by a dictionary with the symbol code and other metadata.'''

        return self.__req(f'{self.base_url}/etf').json()

    def listSme(self):
        '''List all sme stocks

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/listSme.json>`__

        :return: A dictionary. The ``data`` key is a list of all SME's represented by a dictionary with the symbol code and other metadata.'''

        return self.__req(f'{self.base_url}/live-analysis-emerge').json()

    def listSgb(self):
        '''List all sovereign gold bonds

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/listSgb.json>`__

        :return: A dictionary. The ``data`` key is a list of all SGB's represented by a dictionary with the symbol code and other metadata.'''

        return self.__req(f'{self.base_url}/sovereign-gold-bonds').json()

    def blockDeals(self) -> dict:
        '''Block deals

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/blockDeals.json>`__

        :return: Block deals. ``data`` key is a list of all block deal (Empty list if no block deals).
        :rtype: dict'''

        return self.__req(f'{self.base_url}/block-deal').json()

    def fnoLots(self) -> dict[str, int]:
        '''Get the lot size of FnO stocks.

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/fnoLots.json>`__

        :return: A dictionary with symbol code as keys and lot sizes for values
        :rtype: dict[str, int]'''

        url = 'https://nsearchives.nseindia.com/content/fo/fo_mktlots.csv'

        res = self.__req(url).content

        dct = {}

        for line in res.strip().split(b'\n'):
            _, sym, _, lot, *_ = line.split(b',')

            try:
                dct[sym.strip().decode()] = int(lot.strip().decode())
            except ValueError:
                continue

        return dct

    def optionChain(self,
                    symbol: Literal['banknifty',
                                    'nifty',
                                    'finnifty',
                                    'niftyit'] | str) -> dict:
        """Unprocessed option chain from NSE for Index futures or FNO stocks

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/optionChain.json>`__

        :param symbol: FnO stock or index futures code. For Index futures, must be one of ``banknifty``, ``nifty``, ``finnifty``, ``niftyit``
        :type symbol: str
        :return: Option chain for all expiries
        :rtype: dict"""

        if symbol in self.__optionIndex:
            url = f'{self.base_url}/option-chain-indices'
        else:
            url = f'{self.base_url}/option-chain-equities'

        params = {
            'symbol': symbol.upper(),
        }

        data = self.__req(url, params=params).json()

        return data

    @staticmethod
    def maxpain(optionChain: dict, expiryDate: datetime) -> float:
        '''Get the max pain strike price

        :param optionChain: Output of NSE.optionChain
        :type optionChain: dict
        :param expiryDate: Options expiry date
        :type expiryDate: datetime.datetime
        :return: max pain strike price
        :rtype: float'''

        out = {}

        expiryDateStr = expiryDate.strftime('%d-%b-%Y')

        for x in optionChain['records']['data']:
            if x['expiryDate'] != expiryDateStr:
                continue

            expiryStrike = x['strikePrice']
            pain = 0

            for y in optionChain['records']['data']:
                if y['expiryDate'] != expiryDateStr:
                    continue

                diff = expiryStrike - y['strikePrice']

                # strike expiry above strike, loss for CE writers
                if diff > 0:
                    pain += -diff * y['CE']['openInterest']

                # strike expiry below strike, loss for PE writers
                if diff < 0:
                    pain += diff * y['PE']['openInterest']

            out[expiryStrike] = pain

        return max(out.keys(), key=(lambda k: out[k]))

    def compileOptionChain(self,
                           symbol: str | Literal['banknifty',
                                                 'nifty',
                                                 'finnifty',
                                                 'niftyit'],
                           expiryDate: datetime) -> dict[str, str | float | int]:
        '''Filter raw option chain by ``expiryDate`` and calculate various statistics required for analysis. This makes it easy to build an option chain for analysis using a simple loop.

        Statistics include:
            - Max Pain,
            - Strike price with max Call and Put Open Interest,
            - Total Call and Put Open Interest
            - Total PCR ratio
            - PCR for every strike price
            - Every strike price has Last price, Open Interest, Change, Implied Volatility for both Call and Put

        Other included values: At the Money (ATM) strike price, Underlying strike price, Expiry date.

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/compileOptionChain.json>`__

        :param symbol: FnO stock or Index futures symbol code. If Index futures must be one of ``banknifty``, ``nifty``, ``finnifty``, ``niftyit``.
        :type symbol: str
        :param expiryDate: Option chain Expiry date
        :type expiryDate: datetime.datetime
        :return: Option chain filtered by ``expiryDate``
        :rtype: dict[str, str | float | int]'''

        data = self.optionChain(symbol)

        chain = {}
        oc = {}

        expiryDateStr = expiryDate.strftime('%d-%b-%Y')

        oc['expiry'] = expiryDateStr
        oc['timestamp'] = data['records']['timestamp']
        strike1 = data['filtered']['data'][0]['strikePrice']
        strike2 = data['filtered']['data'][1]['strikePrice']
        multiple = strike1 - strike2

        underlying = data['records']['underlyingValue']

        oc['underlying'] = underlying
        oc['atm'] = multiple * round(underlying / multiple)

        maxCoi = maxPoi = totalCoi = totalPoi = maxCoiStrike = maxPoiStrike = 0

        dataFields = ('openInterest', 'lastPrice', 'chg', 'impliedVolatility')
        ocFields = ('last', 'oi', 'chg', 'iv')

        for idx in data['records']['data']:
            if idx['expiryDate'] != expiryDateStr:
                continue

            strike = str(idx['strikePrice'])

            if not strike in chain:
                chain[strike] = {'pe': {}, 'ce': {}}

            poi = coi = 0

            if 'PE' in idx:
                poi, last, chg, iv = map(idx['PE'].get, dataFields)

                chain[strike]['pe'].update(
                    {'last': last, 'oi': poi, 'chg': chg, 'iv': iv})

                totalPoi += poi

                if poi > maxPoi:
                    maxPoi = poi
                    maxPoiStrike = int(strike)
            else:
                for f in ocFields:
                    chain[strike]['pe'][f] = 0

            if 'CE' in idx:
                coi, last, chg, iv = map(idx['CE'].get, dataFields)

                chain[strike]['ce'].update(
                    {'last': last, 'oi': poi, 'chg': chg, 'iv': iv})

                totalCoi += coi

                if coi > maxCoi:
                    maxCoi = coi
                    maxCoiStrike = int(strike)
            else:
                for f in ocFields:
                    chain[strike]['ce'][f] = 0

            if poi == 0 or coi == 0:
                chain[strike]['pcr'] = None
            else:
                chain[strike]['pcr'] = round(poi / coi, 2)

        oc.update({
            'maxpain': self.maxpain(data, expiryDate),
            'maxCoi': maxCoiStrike,
            'maxPoi': maxPoiStrike,
            'coiTotal': totalCoi,
            'poiTotal': totalPoi,
            'pcr': round(totalPoi / totalCoi, 2),
            'chain': chain
        })

        return oc

    def advanceDecline(self) -> list[dict[str, str]]:
        '''Advance decline for all Market indices

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/advanceDecline.json>`__

        :return: Advance decline values for all market indices
        :rtype: list[ dict[str, str] ]'''

        url = 'https://www1.nseindia.com/common/json/indicesAdvanceDeclines.json'

        return self.__req(url).json()['data']

    def holidays(self, type: Literal['trading', 'clearing'] = 'trading') -> dict[str, list[dict]]:
        """NSE holiday list

        ``CM`` key in dictionary stands for Capital markets (Equity Market).

        `Sample response <https://github.com/BennyThadikaran/NseIndiaApi/blob/main/src/samples/holidays.json>`__

        :param type: Default ``trading``. One of ``trading`` or ``clearing``
        :type type: str
        :return: Market holidays for all market segments.
        :rtype: dict[str, list[dict]]"""

        url = f'{self.base_url}/holiday-master'

        data = self.__req(url, params={'type': type}).json()

        return data

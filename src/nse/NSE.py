from requests import Session
import pickle
from requests.exceptions import ReadTimeout
from typing import Literal
from datetime import datetime
from pathlib import Path
from zipfile import ZipFile
from mthrottle import Throttle

throttleConfig = {
    'default': {
        'rps': 3,
    },
}

th = Throttle(throttleConfig, 10)


class NSE:

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
        '''Initialise NSE
        Params:
        download_folder - A folder to store downloaded files and cookie files'''

        uAgent = 'Mozilla/5.0 (Windows NT 10.0; rv:91.0) Gecko/20100101 Firefox/91.0'

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

    def __req(self, url, params=None, timeout=30):
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
        '''Close the requests session'''

        self.session.close()

    def status(self):
        '''Returns market status'''

        return self.__req(f'{self.base_url}/marketStatus').json()['marketState']

    def equityBhavcopy(self, date: datetime, folder: str | Path | None = None):
        '''Download the daily report for Equity bhav copy for specified date
        and return the saved file path.

        Params:
        date - Date of bhavcopy to download
        folder[Optional] - Save to folder. If not specified,
                use download_folder specified during class initializataion.'''

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
        '''Download the daily report for Equity delivery data for specified
        date and return saved file path.

        Params:
        date - Date of bhavcopy to download
        folder[Optional] - Save to folder. If not specified,
                use download_folder specified during class initializataion.'''

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
        '''Download the daily report for Equity Index for specified date
        and return the saved file path.

        Params:
        date - Date of bhavcopy to download
        folder[Optional] - Save to folder. If not specified,
                use download_folder specified during class initializataion.'''

        folder = NSE.__getPath(folder, isFolder=True) if folder else self.dir

        url = f'{self.archive_url}/content/indices/ind_close_all_{date:%d%m%Y}.csv'

        file = self.__download(url, folder)

        if not file.is_file() or file.stat().st_size < 5000:
            file.unlink()
            raise FileNotFoundError(f'Failed to download file: {file.name}')

        return file

    def fnoBhavcopy(self, date: datetime, folder: str | Path | None = None):
        '''Download the daily report for FnO bhavcopy for specified date
        and return the saved file path.

        Params:
        date - Date of bhavcopy to download
        folder[Optional] - Save to folder. If not specified,
                use download_folder specified during class initializataion.'''

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
                segment: Literal['equities', 'sme', 'debt', 'mf'],
                symbol: str | None = None,
                from_dt: datetime | None = None,
                to_dt: datetime | None = None):
        '''Get all corporate actions for specified dates or all forthcoming,
        Optionally specify symbol to get actions only for that symbol.

        Params:
        segment - One of equities, sme, debt or mf
        symbol[Optional] - Stock symbol
        from_dt[Optional] - From Datetime
        to_dt[Optional] - To Datetime'''

        fmt = '%d-%m-%Y'

        params = {
            'index': segment,
        }

        if symbol:
            params['symbol'] = symbol

        if from_dt and to_dt:
            params.update({
                'from_date': from_dt.strftime(fmt),
                'to_date': to_dt.strftime(fmt)
            })

        url = f'{self.base_url}/corporates-corporateActions'

        return self.__req(url, params=params).json()

    def equityMetaInfo(self, symbol):
        '''Meta info for equity symbols.

        Params:
        symbol - Equity symbol'''

        url = f'{self.base_url}/equity-meta-info'

        return self.__req(url, params={'symbol': symbol.upper()}).json()

    def quote(self,
              symbol,
              type: Literal['equity', 'fno'] = 'equity',
              section: Literal['trade_info'] | None = None):
        """Returns price quotes and other data for equity or derivative symbols

        Params:
        symbol - Equity symbol
        type[Default 'equity'] - One of 'equity' or 'fno'
        section[Optional] - If specified must be 'trade_info'
        """

        if type == 'equity':
            url = f'{self.base_url}/quote-equity'
        else:
            url = f'{self.base_url}/quote-derivative'

        params = {
            'symbol': symbol.upper()
        }

        if section:
            if section != 'trade_info':
                raise ValueError('Section if specified must be trade_info')

            params['section'] = section

        return self.__req(url, params=params).json()

    def stockQuote(self, symbol):
        '''Returns a formatted dictionary of OCHLV data for equity symbol

        Params:
        symbol - Equity symbol'''

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

    def gainers(self, data: dict, count: int | None = None):
        '''Top gainers (percent change above zero).
        Returns all stocks or limit to integer count

        Params:
        data - Output of one of NSE.listIndexStocks,
                                NSE.listSME,
                                NSE.listFnoStocks
        count - Number of results to return. If None, returns all results'''

        return sorted(filter(lambda dct: dct['pChange'] > 0, data['data']),
                      key=lambda dct: dct['pChange'],
                      reverse=True)[:count]

    def losers(self, data: dict, count: int | None = None):
        '''Top losers (percent change below zero).
        Returns all stocks or limit to integer count

        Params:
        data - Output of one of NSE.listIndexStocks,
                                NSE.listSME,
                                NSE.listFnoStocks
        count - Number of result to return. If None, returns all result'''

        return sorted(filter(lambda dct: dct['pChange'] < 0, data['data']),
                      key=lambda dct: dct['pChange'])[:count]

    def listFnoStocks(self):
        '''List all Futures and Options (FNO) stocks'''

        url = f'{self.base_url}/equity-stockIndices'

        return self.__req(url, params={'index': 'SECURITIES IN F&O'}).json()

    def listIndices(self):
        '''List all indices'''

        url = f'{self.base_url}/allIndices'

        return self.__req(url).json()

    def listIndexStocks(self, index):
        '''List all stocks by index

        Params:
        index - Market Index Name'''

        return self.__req(f'{self.base_url}/equity-stockIndices', params={
            'index': index.upper()
        }).json()

    def listEtf(self):
        '''List all etf stocks'''

        return self.__req(f'{self.base_url}/etf').json()

    def listSME(self):
        '''List all sme stocks'''

        return self.__req(f'{self.base_url}/live-analysis-emerge').json()

    def listSgb(self):
        '''List all sovereign gold bonds'''

        return self.__req(f'{self.base_url}/sovereign-gold-bonds').json()

    def blockDeals(self):
        '''Block deals'''

        return self.__req(f'{self.base_url}/block-deal').json()

    def fnoLots(self) -> dict[str, int]:
        '''Return a dictionary containing lot size of FnO stocks.
        Keys are stock symbols and values are lot sizes'''

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
                                    'niftyit'] | str):
        """Raw option chain from api for Index futures or FNO stocks

        Params:
        symbol - FnO stock or index futures code.
                 For Index futures, must be one of 'banknifty', 'nifty',
                 'finnifty', 'niftyit'
        """

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
    def maxpain(optionChain, expiryDate: datetime) -> float:
        '''Returns the options strike price with Max Pain

        Params:
        optionChain - Output of NSE.optionChain
        expiryDate - Expiry date'''

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
                           expiryDate: datetime):
        '''Returns a dictionary of option chain with related statistics

        Params:
        symbol - FnO stock or Index futures code
        expiryDate - Expiry date'''

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

    def advanceDecline(self):
        '''Advance decline for all NSE indices'''

        url = 'https://www1.nseindia.com/common/json/indicesAdvanceDeclines.json'

        return self.__req(url).json()['data']

    def holidays(self, type: Literal['trading', 'clearing'] = 'trading'):
        """Returns NSE holiday list

        Params:
        type[Default 'trading'] - One of 'trading' or 'clearing'"""

        url = f'{self.base_url}/holiday-master'

        data = self.__req(url, params={'type': type}).json()

        return data

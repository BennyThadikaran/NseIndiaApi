# 💰 NseIndiaApi

An unofficial Python API for the NSE India stock exchange.

Python version: >= 3.8

If you ❤️ my work so far, please 🌟 this repo.

## 👽 Documentation

[https://bennythadikaran.github.io/NseIndiaApi](https://bennythadikaran.github.io/NseIndiaApi)

## API limits

All requests through NSE are rate limited or throttled to 3 requests per second. This allows making large number of requests without overloading the server or getting blocked.

- If downloading a large number of reports from NSE, please do so after-market hours (Preferably late evening).
- Add an extra 0.5 - 1 sec sleep between requests. The extra run time likely wont make a difference to your script.
- Save the file and reuse them instead of re-downloading.

## Updates

**v1.2.0** NSE package now works in server environments like AWS. [See PR #10](https://github.com/BennyThadikaran/NseIndiaApi/pull/10) for details.

## 🔥 Usage

**To install on local machine or PC**

```bash
pip install nse[local]
```

**To install in a server environment like AWS (Works on local too)**

```bash
pip install nse[server]
```

The class accepts two arguments (As of 1.2.0)

- `download_folder` - a `str` filepath, or a `pathlib object`. The folder stores cookie and any downloaded files.
- `server` - If False (default), use the requests module to make requests. Else uses the httpx module with http2 support for running on server.

Note: `server=True` works both locally and on servers. `httpx[http2]` module is required to be installed for this to work.

**Simple example**

```python
from nse import NSE
from pathlib import Path

# Working directory
DIR = Path(__file__).parent

nse = NSE(download_folder=DIR, server=False)

status = nse.status()

advDec = nse.advanceDecline()

nse.exit() # close requests session
```

**Using with statement**

```python
with NSE(download_folder=DIR, server=False) as nse:
    status = nse.status()

    advDec = nse.advanceDecline()
```

**Catching errors**

```python
from nse import NSE
from datetime import datetime

with NSE('./') as nse:
    try:
        bhavFile = nse.equityBhavcopy(date=datetime.now())
        dlvFile = nse.deliveryBhavcopy(date=datetime.now())
        raise RuntimeError('Some error')  # force an exception
    except RuntimeError as e:
        # continue execution or exit the script
        print(repr(e))

    # execution continues if handled without exit
    actions = nse.actions()

# NSE request session closed - continue processing
```

## Samples folder

The `src/samples` folder contains sample outputs of various methods. The filenames match the method names. The output has been truncated in some places but demonstrates the overall structure of responses.

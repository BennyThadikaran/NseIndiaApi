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

**v1.0.4** Added new method to download daily bhavcopy PR zip (contains a collection of various reports). [See Docs](https://bennythadikaran.github.io/NseIndiaApi/usage.html#nse.NSE.pr_bhavcopy)

## 🔥 Usage

**Install with Pip**

```bash
pip install -U nse
```

The class accepts a single argument `download_folder`, a `str` filepath, or a `pathlib object`. The folder stores cookie and any downloaded files.

**Simple example**

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

**Using with statement**

```python
with NSE(download_folder=DIR) as nse:
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

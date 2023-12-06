# 💰 NseIndiaApi

An unofficial Python API for the NSE India stock exchange.

Python version: >= 3.8

If you ❤️ my work so far, please 🌟 this repo.

## 👽 Documentation

[https://bennythadikaran.github.io/NseIndiaApi](https://bennythadikaran.github.io/NseIndiaApi)

## Updates

- Prior to v0.2.6, NSE class would exit on unhandled errors. This undesirable behavior has changed. It is left to the user to catch and handle these errors.
- Added a new method: NSE.getFuturesExpiry ([See Documentation for details](https://bennythadikaran.github.io/NseIndiaApi/usage.html#nse.NSE.getFuturesExpiry))

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

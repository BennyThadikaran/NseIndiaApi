# :moneybag: NseIndiaApi

An unofficial Python API for the NSE India stock exchange.

Python version: >= 3.10

If you ❤️ my work so far, please 🌟 this repo.

## :alien: Documentation
[https://bennythadikaran.github.io/NseIndiaApi](https://bennythadikaran.github.io/NseIndiaApi)

## :fire: Usage

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

## Samples folder

The `src/samples` folder contains sample outputs of various methods. The filenames match the method names. The output has been truncated in some places but demonstrates the overall structure of responses.

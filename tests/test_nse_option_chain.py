import json
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

from context import NSE


class TestNSEOptionChain(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        DIR = Path(__file__).parent
        cls.nse = NSE(DIR, server=False)
        cls.cache_file = cls.nse.dir / "opt-expiry.json"

    @classmethod
    def tearDownClass(cls):
        cls.nse.exit()
        cls.cache_file.unlink(missing_ok=True)

    def _mock_req(self, responses) -> MagicMock:
        """Helper to mock _NSE__req returning different .json() values
        on sequential calls.
        """
        mock = MagicMock()
        mock.side_effect = [
            MagicMock(json=MagicMock(return_value=resp)) for resp in responses
        ]
        self.nse._req = mock
        return mock

    def test_uses_cached_expiry_when_valid(self):
        expiry = datetime(2099, 1, 1)
        cache = dict(nifty=expiry.isoformat())

        self.cache_file.write_text(json.dumps(cache))

        mock = self._mock_req([dict(data="OK")])

        result = self.nse.optionChain("nifty")

        self.assertEqual(result, dict(data="OK"))
        mock.assert_called_once()

    def test_expired_cached_expiry_is_ignored(self):
        expiry = datetime(2000, 1, 1)
        cache = {"nifty": expiry.isoformat()}
        self.cache_file.write_text(json.dumps(cache))

        responses = [
            {"expiryDates": ["01-Jan-2099"]},
            {"data": "ok"},
        ]

        mock = self._mock_req(responses)

        result = self.nse.optionChain("nifty")

        self.assertEqual(result, {"data": "ok"})
        self.assertEqual(mock.call_count, 2)

    def test_missing_expiry_dates_raises(self):
        self._mock_req([{}])

        with self.assertRaises(ValueError) as ctx:
            self.nse.optionChain("nifty")

        self.assertIn("expiryDates", str(ctx.exception))

    def test_empty_expiry_dates_raises(self):
        self._mock_req([{"expiryDates": []}])

        with self.assertRaises(ValueError) as ctx:
            self.nse.optionChain("nifty")

        self.assertIn("No expiry dates", str(ctx.exception))

    def test_writes_expiry_cache_file(self):
        self._mock_req(
            [
                {"expiryDates": ["01-Jan-2099"]},
            ]
        )

        self.nse.optionChain("nifty")

        self.assertTrue(self.cache_file.exists())

        data = json.loads(self.cache_file.read_text())
        self.assertIn("nifty", data)

    def test_equity_type_for_non_index_symbol(self):
        responses = [
            {"expiryDates": ["01-Jan-2099"]},
            {"data": "ok"},
        ]
        mock = self._mock_req(responses)

        self.nse.optionChain("reliance")

        _, kwargs = mock.call_args
        self.assertEqual(kwargs["params"]["type"], "Equity")

    def test_indices_type_for_index_symbol(self):
        responses = [
            {"expiryDates": ["01-Jan-2099"]},
            {"data": "ok"},
        ]
        mock = self._mock_req(responses)

        self.nse.optionChain("nifty")

        _, kwargs = mock.call_args
        self.assertEqual(kwargs["params"]["type"], "Indices")

    def test_explicit_expiry_date_skips_cache_and_contract_info(self):
        expiry = datetime(2099, 1, 1)
        mock = self._mock_req([{"data": "ok"}])

        result = self.nse.optionChain("nifty", expiry_date=expiry)

        self.assertEqual(result, {"data": "ok"})
        mock.assert_called_once()

    def test_corrupt_cache_file_is_ignored(self):
        self.cache_file.write_text("invalid json")

        responses = [
            {"expiryDates": ["01-Jan-2099"]},
            {"data": "ok"},
        ]
        mock = self._mock_req(responses)

        result = self.nse.optionChain("nifty")

        self.assertEqual(result, {"data": "ok"})
        self.assertEqual(mock.call_count, 2)


if __name__ == "__main__":
    unittest.main()

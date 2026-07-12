import json
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

from context import NSE

DIR = Path(__file__).parent
SAMPLES = DIR.parent / "src" / "samples"


class TestNseFinancialResults(unittest.TestCase):
    """Unit tests for financial_results and results_comparison (mocked _req)."""

    @classmethod
    def setUpClass(cls):
        cls.nse = NSE(download_folder=DIR, server=False)

    @classmethod
    def tearDownClass(cls):
        cls.nse.exit()

    def _mock_req_json(self, payload):
        mock = MagicMock()
        mock.return_value.json.return_value = payload
        self.nse._req = mock
        return mock

    def test_financial_results_params(self):
        sample = json.loads((SAMPLES / "financial_results.json").read_text())
        mock = self._mock_req_json(sample)

        from_dt = datetime(2025, 1, 1)
        to_dt = datetime(2025, 3, 31)

        result = self.nse.financial_results(
            index="equities",
            period="Quarterly",
            symbol="reliance",
            from_date=from_dt,
            to_date=to_dt,
        )

        self.assertEqual(result, sample)
        mock.assert_called_once()
        _, kwargs = mock.call_args
        self.assertEqual(
            kwargs["params"],
            {
                "index": "equities",
                "period": "Quarterly",
                "symbol": "RELIANCE",
                "from_date": "01-01-2025",
                "to_date": "31-03-2025",
            },
        )

    def test_financial_results_date_validation(self):
        with self.assertRaises(ValueError):
            self.nse.financial_results(
                from_date=datetime(2025, 3, 1),
                to_date=datetime(2025, 1, 1),
            )

    def test_results_comparison(self):
        sample = json.loads((SAMPLES / "results_comparison.json").read_text())
        mock = self._mock_req_json(sample)

        result = self.nse.results_comparison("reliance")

        self.assertEqual(result, sample)
        self.assertIn("resCmpData", result)
        mock.assert_called_once()
        args, kwargs = mock.call_args
        self.assertTrue(args[0].endswith("/results-comparision"))
        self.assertEqual(kwargs["params"], {"symbol": "RELIANCE"})


if __name__ == "__main__":
    unittest.main()

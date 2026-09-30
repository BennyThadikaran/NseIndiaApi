import unittest
from pathlib import Path

from context import NSE, get_last_working_date


class TestNseApiReportsH1(unittest.TestCase):
    """Tests NSE class report method with http v1"""

    @classmethod
    def setUpClass(cls):
        DIR = Path(__file__).parent
        cls.nse = NSE(DIR, use_http2=False)
        cls.date = get_last_working_date()
        print(
            f"\nRunning tests for NSE reports using http v1 and date: {cls.date:%d %b %Y, %H:%M}.\n"
        )

    @classmethod
    def tearDownClass(cls):
        cls.nse.exit()
        cls.nse._transport.cookie_store.clear()

    def test_equityBhavcopy(self):
        file = self.nse.equity_bhavcopy(date=self.date)

        exists = file.exists()
        file.unlink(missing_ok=True)

        self.assertTrue(exists)
        self.assertTrue(file.suffix == ".csv")

    def test_deliveryBhavcopy(self):
        file = self.nse.delivery_bhavcopy(date=self.date)

        exists = file.exists()
        file.unlink(missing_ok=True)

        self.assertTrue(exists)
        self.assertTrue(file.suffix == ".csv")

    def test_indicesBhavcopy(self):
        file = self.nse.indices_bhavcopy(date=self.date)

        exists = file.exists()
        file.unlink(missing_ok=True)

        self.assertTrue(exists)
        self.assertTrue(file.suffix == ".csv")

    def test_pr_bhavcopy(self):
        file = self.nse.pr_bhavcopy(date=self.date)

        exists = file.exists()
        file.unlink(missing_ok=True)

        self.assertTrue(exists)
        self.assertTrue(file.suffix == ".zip")

    def test_fnoBhavcopy(self):
        file = self.nse.fno_bhavcopy(date=self.date)

        exists = file.exists()
        file.unlink(missing_ok=True)

        self.assertTrue(exists)
        self.assertTrue(file.suffix == ".csv")

    def test_pricebrand_report(self):
        file = self.nse.priceband_report(date=self.date)

        exists = file.exists()
        file.unlink(missing_ok=True)

        self.assertTrue(exists)
        self.assertTrue(file.suffix == ".csv")

    def test_cm_mii_security_report(self):
        file = self.nse.cm_mii_security_report(date=self.date)

        exists = file.exists()
        file.unlink(missing_ok=True)

        self.assertTrue(exists)
        self.assertTrue(file.suffix == ".csv")

    def test_download_document(self):
        url = "https://nsearchives.nseindia.com/annual_reports/AR_22445_HDFCBANK_2022_2023_19072023141052_07192023150000.zip"

        file = self.nse.download_document(url)

        exists = file.exists()
        file.unlink(missing_ok=True)

        self.assertTrue(exists)
        self.assertTrue(file.suffix == ".pdf")


if __name__ == "__main__":
    unittest.main()

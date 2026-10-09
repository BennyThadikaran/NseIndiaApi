import shutil
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from context import NSE


class TestNseApiH1(unittest.TestCase):
    """Tests NSE class with http v1"""

    @classmethod
    def setUpClass(cls):
        DIR = Path(__file__).parent
        cls.nse = NSE(DIR, use_http2=False)
        print("\nRunning tests using http v1.\n")

    @classmethod
    def tearDownClass(cls):
        cls.nse.exit()
        cls.nse._transport.cookie_store.clear()
        shutil.rmtree(cls.nse.opt_cache_dir)

    def test_status(self):
        response = self.nse.status()

        self.assertIsInstance(response, list)
        self.assertIsInstance(response[0], dict)

    def test_lookup(self):
        response = self.nse.lookup(query="hdfcbank")

        self.assertIsInstance(response, dict)
        self.assertIsInstance(response["data"], list)

    def test_holidays(self):
        response = self.nse.holidays()

        self.assertIsInstance(response, dict)
        self.assertTrue("CM" in response)

    def test_block_deals(self):
        response = self.nse.block_deals()

        self.assertIsInstance(response, dict)
        self.assertTrue("timestamp" in response)

    def test_bulk_deals(self):
        today = datetime.now()

        response = self.nse.bulk_deals(
            option_type="bulk_deals", from_date=today - timedelta(3), to_date=today
        )

        self.assertIsInstance(response, list)
        self.assertIsInstance(response[0], dict)
        self.assertTrue("BD_DT_DATE" in response[0])

    def test_equity_meta_info(self):
        response = self.nse.equity_meta_info("reliance")

        self.assertIsInstance(response, dict)
        self.assertTrue("symbol" in response)

    def test_quote(self):
        response = self.nse.quote(symbol="reliance", series="EQ")

        self.assertIsInstance(response, dict)
        self.assertTrue("priceInfo" in response)

    def test_live_volume_gainers(self):
        response = self.nse.live_volume_gainers()

        self.assertIsInstance(response, dict)
        self.assertIsInstance(response["data"], list)

        if response["data"]:
            dct = response["data"][0]
            self.assertIsInstance(dct, dict)
            self.assertTrue("symbol" in dct)
            self.assertTrue("volume" in dct)

    def test_gainers(self):
        test_data = dict(data=[dict(pChange=i) for i in range(10)])
        response = self.nse.gainers(test_data)

        self.assertIsInstance(response, list)
        self.assertIsInstance(response[0], dict)
        self.assertEqual(response[0]["pChange"], 9)
        self.assertEqual(response[-1]["pChange"], 1)
        self.assertEqual(len(response), 9)

        response = self.nse.gainers(test_data, count=3)

        self.assertEqual(len(response), 3)
        self.assertEqual(response[0]["pChange"], 9)
        self.assertEqual(response[-1]["pChange"], 7)

    def test_losers(self):
        test_data = dict(data=[dict(pChange=i) for i in range(-1, -10, -1)])
        response = self.nse.losers(test_data)

        self.assertIsInstance(response, list)
        self.assertIsInstance(response[0], dict)
        self.assertEqual(response[0]["pChange"], -9)
        self.assertEqual(response[-1]["pChange"], -1)
        self.assertEqual(len(response), 9)

        response = self.nse.losers(test_data, count=3)

        self.assertEqual(len(response), 3)
        self.assertEqual(response[0]["pChange"], -9)
        self.assertEqual(response[-1]["pChange"], -7)

    def test_list_equity_stocks_by_index(self):
        response = self.nse.list_equity_stocks_by_index(index="nifty 50")

        self.assertIsInstance(response, dict)
        self.assertTrue("data" in response)
        self.assertTrue("pChange" in response["data"][0])

    def test_list_indices(self):
        response = self.nse.list_indices()

        self.assertIsInstance(response, dict)
        self.assertTrue("data" in response)
        self.assertIsInstance(response["data"], list)

    def test_list_sme(self):
        response = self.nse.list_sme()

        self.assertIsInstance(response, dict)
        self.assertTrue("data" in response)
        self.assertTrue("pChange" in response["data"][0])

    def test_list_etf(self):
        response = self.nse.list_etf()

        self.assertIsInstance(response, dict)
        self.assertTrue("data" in response)
        self.assertTrue("symbol" in response["data"][0])

    def test_list_sgb(self):
        response = self.nse.list_sgb()

        self.assertIsInstance(response, dict)
        self.assertTrue("data" in response)
        self.assertTrue("symbol" in response["data"][0])

    def test_list_current_ipo(self):
        response = self.nse.list_current_ipo()

        self.assertIsInstance(response, list)

        if len(response):
            self.assertIsInstance(response[0], dict)
            self.assertTrue("symbol" in response[0])

    def test_list_upcoming_ipo(self):
        response = self.nse.list_upcoming_ipo()

        self.assertIsInstance(response, list)

        if len(response):
            self.assertIsInstance(response[0], dict)
            self.assertTrue("symbol" in response[0])

    def test_list_past_ipo(self):
        response = self.nse.list_past_ipo()

        self.assertIsInstance(response, list)
        self.assertIsInstance(response[0], dict)
        self.assertTrue("symbol" in response[0])

    def test_circulars(self):
        response = self.nse.circulars()

        self.assertIsInstance(response, dict)
        self.assertTrue("data" in response)
        self.assertIsInstance(response["data"], list)

        response = self.nse.circulars(subject="holidays")
        self.assertIsInstance(response, dict)

    def test_press_releases(self):
        response = self.nse.press_releases()

        self.assertIsInstance(response, list)

        if len(response):
            self.assertIsInstance(response[0], dict)

    def test_actions(self):
        response = self.nse.actions()

        self.assertIsInstance(response, list)
        self.assertIsInstance(response[0], dict)
        self.assertTrue("symbol" in response[0])

    def test_announcements(self):
        response = self.nse.announcements()

        self.assertIsInstance(response, list)
        self.assertIsInstance(response[0], dict)
        self.assertTrue("symbol" in response[0])

    def test_board_meetings(self):
        response = self.nse.board_meetings()

        self.assertIsInstance(response, list)
        self.assertIsInstance(response[0], dict)
        self.assertTrue("bm_symbol" in response[0])

    def test_get_futures_expiry(self):
        response = self.nse.get_futures_expiry()

        self.assertIsInstance(response, list)
        self.assertIsInstance(response[0], str)

    def test_fno_lots(self):
        response = self.nse.fno_lots()

        self.assertIsInstance(response, dict)

    def test_option_chain(self):
        response = self.nse.option_chain(symbol="nifty")

        self.assertIsInstance(response, dict)
        self.assertTrue("records" in response)

    def test_fetch_historical_vix_data(self):
        response = self.nse.fetch_historical_vix_data()

        self.assertIsInstance(response, list)
        self.assertTrue("VIX_PERC_CHG" in response[0])

    def test_fetch_historical_fno_data(self):
        response = self.nse.fetch_historical_fno_data(
            instrument="FUTIDX", symbol="NIFTY"
        )

        self.assertIsInstance(response, list)
        self.assertTrue("FH_TIMESTAMP" in response[0])

    def test_fetch_historical_index_data(self):
        response = self.nse.fetch_historical_index_data(index="NIFTY 50")

        self.assertIsInstance(response, list)
        self.assertIsInstance(response[0], dict)
        self.assertTrue("EOD_TIMESTAMP" in response[0])

    def test_fetch_fno_underlying(self):
        response = self.nse.fetch_fno_underlying()

        self.assertIsInstance(response, dict)
        self.assertTrue("IndexList" in response)

    def test_get_detailed_scrip_data(self):
        response = self.nse.get_detailed_scrip_data(symbol="eternal", series="eq")

        self.assertIsInstance(response, dict)
        self.assertTrue("equityResponse" in response)
        self.assertEqual(response["equityResponse"][0]["metaData"]["symbol"], "ETERNAL")


if __name__ == "__main__":
    unittest.main()

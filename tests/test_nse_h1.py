import unittest
from datetime import datetime, timedelta
from pathlib import Path

from context import NSE


class TestNseApiH1(unittest.TestCase):
    """Tests NSE class with http1 using requests library"""

    @classmethod
    def setUpClass(cls):
        DIR = Path(__file__).parent
        cls.nse = NSE(DIR, server=False)
        print("\nRunning tests using requests library.\n")

    @classmethod
    def tearDownClass(cls):
        cls.nse.exit()

    def test_status(self):
        response = self.nse.status()

        self.assertIsInstance(response, list)
        self.assertIsInstance(response[0], dict)

    def test_holidays(self):
        response = self.nse.holidays()

        self.assertIsInstance(response, dict)
        self.assertTrue("CM" in response)

    def test_blockdeals(self):
        response = self.nse.blockDeals()

        self.assertIsInstance(response, dict)
        self.assertTrue("timestamp" in response)

    def test_bulkdeals(self):
        today = datetime.now()

        response = self.nse.bulkdeals(
            fromdate=today - timedelta(3), todate=today
        )

        self.assertIsInstance(response, list)
        self.assertIsInstance(response[0], dict)
        self.assertTrue("TIMESTAMP" in response[0])

    def test_equityMetaInfo(self):
        response = self.nse.equityMetaInfo("reliance")

        self.assertIsInstance(response, dict)
        self.assertTrue("symbol" in response)

    def test_quote(self):
        response = self.nse.quote(symbol="reliance", type="equity")

        self.assertIsInstance(response, dict)
        self.assertTrue("priceInfo" in response)

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

    def test_listEquityStocksByIndex(self):
        response = self.nse.listEquityStocksByIndex(index="NIFTY 50")

        self.assertIsInstance(response, dict)
        self.assertTrue("advance" in response)
        self.assertTrue("pChange" in response["data"][0])

    def test_listIndices(self):
        response = self.nse.listIndices()

        self.assertIsInstance(response, dict)
        self.assertTrue("data" in response)
        self.assertIsInstance(response["data"], list)

    def test_listSme(self):
        response = self.nse.listSme()

        self.assertIsInstance(response, dict)
        self.assertTrue("data" in response)
        self.assertTrue("pChange" in response["data"][0])

    def test_listEtf(self):
        response = self.nse.listEtf()

        self.assertIsInstance(response, dict)
        self.assertTrue("data" in response)
        self.assertTrue("symbol" in response["data"][0])

    def test_listSgb(self):
        response = self.nse.listSgb()

        self.assertIsInstance(response, dict)
        self.assertTrue("data" in response)
        self.assertTrue("symbol" in response["data"][0])

    def test_listCurrentIPO(self):
        response = self.nse.listCurrentIPO()

        self.assertIsInstance(response, list)
        self.assertIsInstance(response[0], dict)
        self.assertTrue("symbol" in response[0])

    def test_listUpcomingIPO(self):
        response = self.nse.listUpcomingIPO()

        self.assertIsInstance(response, list)
        self.assertIsInstance(response[0], dict)
        self.assertTrue("symbol" in response[0])

    def test_listPastIPO(self):
        response = self.nse.listPastIPO()

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

    def test_boardMeetings(self):
        response = self.nse.boardMeetings()

        self.assertIsInstance(response, list)
        self.assertIsInstance(response[0], dict)
        self.assertTrue("bm_symbol" in response[0])

    def test_getFuturesExpiry(self):
        response = self.nse.getFuturesExpiry()

        self.assertIsInstance(response, list)
        self.assertIsInstance(response[0], str)

    def test_fnoLots(self):
        response = self.nse.fnoLots()

        self.assertIsInstance(response, dict)

    def test_optionChain(self):
        response = self.nse.optionChain(symbol="nifty")

        self.assertIsInstance(response, dict)
        self.assertTrue("records" in response)

    def test_fetch_historical_vix_data(self):
        response = self.nse.fetch_historical_vix_data()

        self.assertIsInstance(response, list)
        self.assertTrue("TIMESTAMP" in response[0])

    def test_fetch_historical_fno_data(self):
        response = self.nse.fetch_historical_fno_data(
            instrument="FUTIDX", symbol="NIFTY"
        )

        self.assertIsInstance(response, list)
        self.assertTrue("TIMESTAMP" in response[0])

    def test_fetch_historical_index_data(self):
        response = self.nse.fetch_historical_index_data(index="NIFTY 50")

        self.assertIsInstance(response, dict)
        self.assertTrue("TIMESTAMP" in response["price"][0])

    def test_fetch_fno_underlying(self):
        response = self.nse.fetch_fno_underlying()

        self.assertIsInstance(response, dict)
        self.assertTrue("IndexList" in response)


if __name__ == "__main__":
    unittest.main()

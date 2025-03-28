import unittest
from datetime import datetime, timedelta
from pathlib import Path

from context import NSE

DIR = Path(__file__).parent
nse = NSE(DIR)


class TestNseApi(unittest.TestCase):
    def test_status(self):
        response = nse.status()

        self.assertIsInstance(response, list)
        self.assertIsInstance(response[0], dict)

    def test_holidays(self):
        response = nse.holidays()

        self.assertIsInstance(response, dict)
        self.assertTrue("CM" in response)

    def test_blockdeals(self):
        response = nse.blockDeals()

        self.assertIsInstance(response, dict)
        self.assertTrue("timestamp" in response)

    def test_bulkdeals(self):
        today = datetime.now()

        response = nse.bulkdeals(fromdate=today - timedelta(3), todate=today)

        self.assertIsInstance(response, list)
        self.assertIsInstance(response[0], dict)
        self.assertTrue("TIMESTAMP" in response[0])

    def test_equityMetaInfo(self):
        response = nse.equityMetaInfo("reliance")

        self.assertIsInstance(response, dict)
        self.assertTrue("symbol" in response)

    def test_quote(self):
        response = nse.quote(symbol="reliance", type="equity")

        self.assertIsInstance(response, dict)
        self.assertTrue("priceInfo" in response)

    def test_gainers(self):
        test_data = dict(data=[dict(pChange=i) for i in range(10)])
        response = nse.gainers(test_data)

        self.assertIsInstance(response, list)
        self.assertIsInstance(response[0], dict)
        self.assertEqual(response[0]["pChange"], 9)
        self.assertEqual(response[-1]["pChange"], 1)
        self.assertEqual(len(response), 9)

        response = nse.gainers(test_data, count=3)

        self.assertEqual(len(response), 3)
        self.assertEqual(response[0]["pChange"], 9)
        self.assertEqual(response[-1]["pChange"], 7)

    def test_losers(self):
        test_data = dict(data=[dict(pChange=i) for i in range(-1, -10, -1)])
        response = nse.losers(test_data)

        self.assertIsInstance(response, list)
        self.assertIsInstance(response[0], dict)
        self.assertEqual(response[0]["pChange"], -9)
        self.assertEqual(response[-1]["pChange"], -1)
        self.assertEqual(len(response), 9)

        response = nse.losers(test_data, count=3)

        self.assertEqual(len(response), 3)
        self.assertEqual(response[0]["pChange"], -9)
        self.assertEqual(response[-1]["pChange"], -7)

    def test_listEquityStocksByIndex(self):
        response = nse.listEquityStocksByIndex(index="NIFTY 50")

        self.assertIsInstance(response, dict)
        self.assertTrue("advance" in response)
        self.assertTrue("pChange" in response["data"][0])

    def test_listIndices(self):
        response = nse.listIndices()

        self.assertIsInstance(response, dict)
        self.assertTrue("data" in response)
        self.assertIsInstance(response["data"], list)

    def test_listSme(self):
        response = nse.listSme()

        self.assertIsInstance(response, dict)
        self.assertTrue("data" in response)
        self.assertTrue("pChange" in response["data"][0])

    def test_listEtf(self):
        response = nse.listEtf()

        self.assertIsInstance(response, dict)
        self.assertTrue("data" in response)
        self.assertTrue("symbol" in response["data"][0])

    def test_listSgb(self):
        response = nse.listSgb()

        self.assertIsInstance(response, dict)
        self.assertTrue("data" in response)
        self.assertTrue("symbol" in response["data"][0])

    def test_listCurrentIPO(self):
        response = nse.listCurrentIPO()

        self.assertIsInstance(response, list)
        self.assertIsInstance(response[0], dict)
        self.assertTrue("symbol" in response[0])

    def test_listUpcomingIPO(self):
        response = nse.listUpcomingIPO()

        self.assertIsInstance(response, list)
        self.assertIsInstance(response[0], dict)
        self.assertTrue("symbol" in response[0])

    def test_listPastIPO(self):
        response = nse.listPastIPO()

        self.assertIsInstance(response, list)
        self.assertIsInstance(response[0], dict)
        self.assertTrue("symbol" in response[0])

    def test_circulars(self):
        response = nse.circulars()

        self.assertIsInstance(response, dict)
        self.assertTrue("data" in response)
        self.assertIsInstance(response["data"], list)

        response = nse.circulars(subject="holidays")
        self.assertIsInstance(response, dict)

    def test_actions(self):
        response = nse.actions()

        self.assertIsInstance(response, list)
        self.assertIsInstance(response[0], dict)
        self.assertTrue("symbol" in response[0])

    def test_announcements(self):
        response = nse.announcements()

        self.assertIsInstance(response, list)
        self.assertIsInstance(response[0], dict)
        self.assertTrue("symbol" in response[0])

    def test_boardMeetings(self):
        response = nse.boardMeetings()

        self.assertIsInstance(response, list)
        self.assertIsInstance(response[0], dict)
        self.assertTrue("bm_symbol" in response[0])

    def test_getFuturesExpiry(self):
        response = nse.getFuturesExpiry()

        self.assertIsInstance(response, list)
        self.assertIsInstance(response[0], str)

    def test_fnoLots(self):
        response = nse.fnoLots()

        self.assertIsInstance(response, dict)

    def test_optionChain(self):
        response = nse.optionChain(symbol="nifty")

        self.assertIsInstance(response, dict)
        self.assertTrue("records" in response)


if __name__ == "__main__":
    unittest.main()

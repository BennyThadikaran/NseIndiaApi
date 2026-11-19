"""Offline unit tests for the financial-results XBRL helpers.

Cookie bootstrap and HTTP calls are mocked, so these run without network.
"""

import copy
import json
import shutil
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from context import NSE

DIR = Path(__file__).parent
SAMPLES = DIR.parent / "src" / "samples"


def _integrated_rows():
    """Integrated Filing (Financials) rows as NSE returns them (LINDEINDIA,
    Sep-2026 C + S originals, a later C revision, and a governance filing)."""
    base = {
        "symbol": "LINDEINDIA", "audited": "Un-Audited", "qe_Date": "30-SEP-2026",
        "type": "Integrated Filing- Financials", "type_Sub": "Original",
        "revised_Date": None, "revision_Remark": None,
    }
    cons = dict(base, consolidated="Consolidated", seq_Id="208891",
                broadcast_Date="03-Nov-2026 18:27:21",
                creation_Date="03-Nov-2026 18:27:44",
                xbrl="https://nsearchives.nseindia.in/corporate/xbrl/"
                     "INTEGRATED_FILING_INDAS_1752034_03112026062743_WEB.xml")
    stand = dict(base, consolidated="Standalone", seq_Id="208890",
                 broadcast_Date="03-Nov-2026 18:26:28",
                 creation_Date="03-Nov-2026 18:26:43",
                 xbrl="https://nsearchives.nseindia.in/corporate/xbrl/"
                      "INTEGRATED_FILING_INDAS_1752031_03112026062643_WEB.xml")
    revised = dict(cons, type_Sub="Revision", seq_Id="215400", broadcast_Date=None,
                   creation_Date=None, revised_Date="18-NOV-2026 17:33:17",
                   revision_Remark="re-submitted",
                   xbrl="https://nsearchives.nseindia.in/corporate/xbrl/"
                        "INTEGRATED_FILING_INDAS_1759841_18112026053332_WEB.xml")
    governance = dict(stand, type="Integrated Filing- Governance", seq_Id="208892",
                      xbrl="https://nsearchives.nseindia.in/corporate/xbrl/GOV.xml")
    return [cons, stand, revised, governance]


def _rows():
    """Sample rows: RELIANCE Q3 FY25 consolidated + standalone, plus a revision."""
    base = json.loads((SAMPLES / "financial_results.json").read_text())
    standalone, consolidated = base[0], base[1]

    revised = copy.deepcopy(consolidated)
    revised["broadCastDate"] = "20-Jan-2025 10:00:00"
    revised["exchdisstime"] = "20-Jan-2025 10:00:30"
    revised["seqNumber"] = "1190000"
    revised["xbrl"] = "https://nsearchives.nseindia.com/corporate/xbrl/INDAS_REVISED.xml"

    no_xbrl = copy.deepcopy(standalone)
    no_xbrl["xbrl"] = "-"
    no_xbrl["fromDate"] = "01-Jul-2024"
    no_xbrl["toDate"] = "30-Sep-2024"

    return [standalone, consolidated, revised, no_xbrl]


class TestNseXbrl(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())

        with patch("nse.transport.Transport._getCookies", return_value={}):
            cls.nse = NSE(download_folder=cls.tmp, server=False)

    @classmethod
    def tearDownClass(cls):
        cls.nse.exit()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _mock_results(self, payload, integrated=None):
        """Route requests by endpoint: ``payload`` for financial results,
        ``integrated`` (a list of rows) for integrated filings."""
        integrated = integrated or []

        def _request(url, params=None):
            resp = MagicMock()
            if url.endswith("/integrated-filing-results"):
                resp.json.return_value = {
                    "data": integrated, "size": 500, "page": -1,
                    "totalCount": len(integrated),
                }
            else:
                resp.json.return_value = payload
            return resp

        mock = MagicMock(side_effect=_request)
        self.nse._transport.request = mock
        return mock

    def _results_calls(self, mock):
        return [c for c in mock.call_args_list
                if c.args[0].endswith("/corporates-financial-results")]

    # -- parsing / normalisation -------------------------------------

    def test_parse_nse_dt(self):
        self.assertEqual(
            NSE._parse_nse_dt("16-Jan-2025 20:20:21"), datetime(2025, 1, 16, 20, 20, 21)
        )
        self.assertEqual(NSE._parse_nse_dt("01-Oct-2024"), datetime(2024, 10, 1))
        self.assertIsNone(NSE._parse_nse_dt("-"))
        self.assertIsNone(NSE._parse_nse_dt(None))
        self.assertIsNone(NSE._parse_nse_dt("garbage"))

    def test_normalise_adds_fields(self):
        rec = NSE._normalise_result_filing(_rows()[1])
        self.assertEqual(rec["basis"], "C")
        self.assertEqual(rec["period_from"], date(2024, 10, 1))
        self.assertEqual(rec["period_to"], date(2024, 12, 31))
        # exchdisstime preferred over broadCastDate
        self.assertEqual(rec["broadcast_dt"], datetime(2025, 1, 16, 20, 15, 46))

    def test_normalise_drops_missing_xbrl(self):
        self.assertIsNone(NSE._normalise_result_filing(_rows()[3]))

    # -- listing -----------------------------------------------------

    def test_latest_only_collapses_revisions(self):
        self._mock_results(_rows())
        recs = self.nse.financial_results_xbrl("reliance")

        self.assertEqual(len(recs), 2)  # one S, one C (revision collapsed)
        cons = [r for r in recs if r["basis"] == "C"][0]
        self.assertTrue(cons["xbrl"].endswith("INDAS_REVISED.xml"))
        self.assertEqual(cons["revision_count"], 2)

    def test_keep_all_revisions(self):
        self._mock_results(_rows())
        recs = self.nse.financial_results_xbrl("reliance", latest_only=False)
        self.assertEqual(len(recs), 3)

    def test_basis_filter(self):
        self._mock_results(_rows())
        recs = self.nse.financial_results_xbrl("reliance", basis="standalone")
        self.assertEqual([r["basis"] for r in recs], ["S"])

    def test_date_range_chunked(self):
        mock = self._mock_results([])
        self.nse.financial_results_xbrl(
            "reliance", from_date=datetime(2022, 1, 1), to_date=datetime(2024, 12, 31)
        )
        # 1096 days (incl. leap day) -> four 365-day chunks
        calls = self._results_calls(mock)
        self.assertEqual(len(calls), 4)
        first = calls[0].kwargs["params"]
        self.assertEqual(first["from_date"], "01-01-2022")
        self.assertEqual(first["symbol"], "RELIANCE")

    def test_dict_wrapped_response(self):
        self._mock_results({"data": _rows()})
        self.assertEqual(len(self.nse.financial_results_xbrl("reliance")), 2)

    def test_one_sided_dates_rejected(self):
        with self.assertRaises(ValueError):
            self.nse.financial_results_xbrl("reliance", from_date=datetime(2024, 1, 1))

    # -- filename / download ----------------------------------------

    def test_xbrl_filename(self):
        rec = NSE._normalise_result_filing(_rows()[1])
        self.assertEqual(
            NSE.xbrl_filename(rec), "RELIANCE_20241231_C_N_20250116201546.xml"
        )

    def _fake_download(self, content: bytes):
        def _dl(url, folder):
            f = Path(folder) / url.split("/")[-1]
            f.write_bytes(content)
            return f

        return _dl

    def test_download_xbrl_renames_and_skips(self):
        rec = NSE._normalise_result_filing(_rows()[1])
        dest = self.tmp / "dl1"

        self.nse._transport.download = MagicMock(
            side_effect=self._fake_download(b'<?xml version="1.0"?><xbrli:xbrl/>')
        )
        path = self.nse.download_xbrl(rec, dest)
        self.assertEqual(path.name, NSE.xbrl_filename(rec))
        self.assertTrue(path.exists())

        # Second call skips network
        self.nse.download_xbrl(rec, dest)
        self.assertEqual(self.nse._transport.download.call_count, 1)

    def test_download_xbrl_rejects_html(self):
        rec = NSE._normalise_result_filing(_rows()[0])
        dest = self.tmp / "dl2"
        self.nse._transport.download = MagicMock(
            side_effect=self._fake_download(b"<html><body>Access Denied</body></html>")
        )
        with self.assertRaises(RuntimeError):
            self.nse.download_xbrl(rec, dest)
        self.assertEqual(list(dest.iterdir()), [])

    def test_fetch_xbrl_filings_records_errors(self):
        self._mock_results(_rows())

        def _dl(url, folder):
            if "REVISED" in url:
                raise ConnectionError("boom")
            f = Path(folder) / url.split("/")[-1]
            f.write_bytes(b"<?xml version='1.0'?><xbrl/>")
            return f

        self.nse._transport.download = MagicMock(side_effect=_dl)
        recs = self.nse.fetch_xbrl_filings("reliance", self.tmp / "raw")

        ok = [r for r in recs if r["error"] is None]
        bad = [r for r in recs if r["error"]]
        self.assertEqual(len(ok), 1)
        self.assertEqual(len(bad), 1)
        self.assertEqual(ok[0]["local_path"].parent.name, "RELIANCE")


    # -- integrated filings -----------------------------------------

    def test_normalise_integrated(self):
        rec = NSE._normalise_integrated_filing(_integrated_rows()[0])
        self.assertEqual(rec["basis"], "C")
        self.assertEqual(rec["period_from"], date(2026, 7, 1))
        self.assertEqual(rec["period_to"], date(2026, 9, 30))
        self.assertEqual(rec["broadcast_dt"], datetime(2026, 11, 3, 18, 27, 21))
        self.assertEqual(rec["source"], "integrated")
        self.assertEqual(
            NSE.xbrl_filename(rec), "LINDEINDIA_20260930_C_N_20261103182721.xml"
        )

    def test_normalise_integrated_revision_uses_revised_date(self):
        rec = NSE._normalise_integrated_filing(_integrated_rows()[2])
        self.assertEqual(rec["broadcast_dt"], datetime(2026, 11, 18, 17, 33, 17))

    def test_normalise_integrated_skips_governance(self):
        self.assertIsNone(NSE._normalise_integrated_filing(_integrated_rows()[3]))

    def test_integrated_quarter_start(self):
        row = dict(_integrated_rows()[0], qe_Date="31-MAR-2026")
        self.assertEqual(
            NSE._normalise_integrated_filing(row)["period_from"], date(2026, 1, 1)
        )

    def test_both_sources_merged(self):
        self._mock_results(_rows(), _integrated_rows())
        recs = self.nse.financial_results_xbrl("lindeindia")

        self.assertEqual([r["source"] for r in recs],
                         ["results", "results", "integrated", "integrated"])
        cons = [r for r in recs if r["source"] == "integrated" and r["basis"] == "C"][0]
        self.assertIn("1759841", cons["xbrl"])  # revision wins
        self.assertEqual(cons["revision_count"], 2)

    def test_source_filter(self):
        mock = self._mock_results(_rows(), _integrated_rows())
        recs = self.nse.financial_results_xbrl("lindeindia", source="integrated")
        self.assertEqual({r["source"] for r in recs}, {"integrated"})
        self.assertEqual(self._results_calls(mock), [])

        recs = self.nse.financial_results_xbrl("lindeindia", source="results")
        self.assertEqual({r["source"] for r in recs}, {"results"})

    def test_integrated_not_queried_for_annual(self):
        mock = self._mock_results([], _integrated_rows())
        self.assertEqual(self.nse.financial_results_xbrl("x", period="annual"), [])
        self.assertEqual(len(mock.call_args_list), len(self._results_calls(mock)))

    def test_integrated_paging(self):
        rows = [dict(_integrated_rows()[1], seq_Id=str(i)) for i in range(5)]
        pages = {1: rows[:2], 2: rows[2:4], 3: rows[4:]}
        seen = []

        def _request(url, params=None):
            seen.append(params)
            resp = MagicMock()
            resp.json.return_value = {"data": pages.get(params["page"], []),
                                      "totalCount": 5, "size": 2}
            return resp

        self.nse._transport.request = MagicMock(side_effect=_request)
        out = self.nse.integrated_filing_results(
            "lindeindia", page_size=2,
            from_date=datetime(2025, 1, 1), to_date=datetime(2026, 11, 19),
        )
        self.assertEqual(len(out), 5)
        self.assertEqual([p["page"] for p in seen], [1, 2, 3])
        self.assertEqual(seen[0]["symbol"], "LINDEINDIA")
        self.assertEqual(seen[0]["type"], "Integrated Filing- Financials")
        self.assertEqual(seen[0]["from_date"], "01-01-2025")


if __name__ == "__main__":
    unittest.main()

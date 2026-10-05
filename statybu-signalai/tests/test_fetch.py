# -*- coding: utf-8 -*-
"""Lietuvos API klientas (be tinklo: _get pakeičiamas) ir CSV importas."""
import json
import unittest
from unittest import mock

import config
import fetch
from demo import generate_demo
from tests import TempDir

BLOCKED = "<html><head><style>" + "x" * 20000 + "</style></head><body>The URL you requested has been blocked</body></html>"


def page(rows, nxt=None):
    return json.dumps({"_data": rows, "_page": {"next": nxt} if nxt else {}})


class ParseTest(unittest.TestCase):
    def test_json_page(self):
        self.assertEqual(fetch._parse(page([{"a": 1}], "abc")), ([{"a": 1}], "abc"))

    def test_blocked_html(self):
        with self.assertRaisesRegex(fetch.FetchError, "ugniasienė"):
            fetch._parse(BLOCKED)


class FetchSinceTest(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(config, "REQUEST_PAUSE_S", 0)
        p.start()
        self.addCleanup(p.stop)

    def test_server_filter_with_paging(self):
        calls = []
        responses = [(200, page([{"dokumento_reg_data": "2026-09-30"}], "p2")),
                     (200, page([{"dokumento_reg_data": "2026-10-01"}]))]

        def fake_get(url):
            calls.append(url)
            return responses[len(calls) - 1]

        with mock.patch.object(fetch, "_get", fake_get):
            rows = fetch.fetch_since("2026-09-28", verbose=False)
        self.assertEqual(len(rows), 2)
        self.assertIn('dokumento_reg_data>="2026-09-28"', calls[0])
        self.assertIn('page("p2")', calls[1])

    def test_falls_back_to_client_filter(self):
        responses = iter([(400, '{"errors": ["bad filter"]}'),
                          (200, page([{"dokumento_reg_data": "2026-09-01"}, {"dokumento_reg_data": "2026-10-01"}]))])
        with mock.patch.object(fetch, "_get", lambda url: next(responses)):
            rows = fetch.fetch_since("2026-09-28", verbose=False)
        self.assertEqual(rows, [{"dokumento_reg_data": "2026-10-01"}])

    def test_blocked_does_not_fall_back(self):
        calls = []
        with mock.patch.object(fetch, "_get", lambda url: calls.append(url) or (500, BLOCKED)):
            with self.assertRaisesRegex(fetch.FetchError, "ugniasienė"):
                fetch.fetch_since("2026-09-28", verbose=False)
        self.assertEqual(len(calls), 1)   # viso rinkinio nebandoma siųstis


class ReadCsvTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TempDir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_data_gov_lt_csv(self):
        rows = generate_demo.generate()["rows"]
        path = generate_demo.write_csv(self.tmp.file("s.csv"), rows)
        got = fetch.read_csv(path)
        self.assertEqual(len(got), len(rows))
        self.assertEqual(got[0]["adresas"], rows[0]["adresas"])           # kableliai kabutėse
        newest = max(r["dokumento_reg_data"] for r in rows)
        self.assertEqual(len(fetch.read_csv(path, newest)),
                         sum(1 for r in rows if r["dokumento_reg_data"] >= newest))

    def test_excel_semicolon_with_bom(self):
        path = self.tmp.file("e.csv")
        with open(path, "w", encoding="utf-8-sig") as fh:
            fh.write("dokumento_reg_nr;dokumento_reg_data;adresas\nA;2026-10-01;Kauno m. sav., Kauno m.\n")
        self.assertEqual(fetch.read_csv(path)[0]["adresas"], "Kauno m. sav., Kauno m.")

    def test_wrong_file(self):
        path = self.tmp.file("x.csv")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("ja_kodas;ja_pavadinimas\n1;A\n")
        with self.assertRaisesRegex(fetch.FetchError, "dokumento_reg_nr"):
            fetch.read_csv(path)


if __name__ == "__main__":
    unittest.main()

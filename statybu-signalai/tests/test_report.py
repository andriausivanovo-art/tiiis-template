# -*- coding: utf-8 -*-
"""Ataskaitų smoke testai: HTML sugeneruojamas ir jo JSON validus, CSV, statytojų eilė, pavyzdys klientui."""
import csv
import json
import re
import unittest
from datetime import date

import config
import db
import enrich
import report
import sistema
from demo import generate_demo
from tests import TempDir, quiet

TODAY = date(2026, 10, 5)


def embedded_json(html, name):
    return json.loads(re.search(r"const %s = (.*?);\n" % name, html).group(1))


class ReportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = TempDir()
        cls.con = db.connect(cls.tmp.file("t.sqlite"))
        demo = generate_demo.generate(TODAY)
        files = generate_demo.write_support_files(cls.tmp.file("demo"), demo)
        db.insert_raw(cls.con, demo["rows"], config.F)
        sistema.build_signals(cls.con)
        enrich.apply_builders(cls.con, files["builders"])
        with quiet():
            enrich.load_companies(cls.con, files["jar"])
            enrich.load_companies(cls.con, files["sodra"])
        cls.rows = report.fetch_rows(cls.con, types=config.SELLABLE_TYPES)

    @classmethod
    def tearDownClass(cls):
        cls.con.close()
        cls.tmp.cleanup()

    def test_html_is_generated_and_json_valid(self):
        path = report.write_html(self.rows, self.tmp.file("out", "a.html"), "2026-09-21", "2026-10-05",
                                 title="Testas </script>")
        with open(path, encoding="utf-8") as fh:
            html = fh.read()
        for placeholder in ("__META__", "__DATA__", "__TITLE__"):
            self.assertNotIn(placeholder, html)
        data, meta = embedded_json(html, "DATA"), embedded_json(html, "META")
        self.assertEqual(len(data), len(self.rows))
        self.assertEqual(meta["from"], "2026-09-21")
        self.assertEqual(list(meta["labels"])[:2], ["prasymas", "leidimas_nauja"])
        self.assertIn("pranesimas", meta["labels"])
        self.assertIn("<title>Testas &lt;/script&gt;</title>", html)
        self.assertNotIn("Testas </script>", html)          # pavadinimas negali uždaryti skripto
        self.assertTrue(all(d["country"] == "LT" for d in data))

    def test_sellable_types_only_by_default(self):
        types = {r["signal_type"] for r in self.rows}
        self.assertTrue(types <= set(config.SELLABLE_TYPES))
        all_rows = report.fetch_rows(self.con)
        self.assertTrue({"pritarimas", "griovimas"} <= {r["signal_type"] for r in all_rows})

    def test_builder_name_from_jar_when_only_code_given(self):
        # builders.csv įrašytas tik kodas – pavadinimas turi ateiti iš JAR (COALESCE)
        r = next(r for r in self.rows if r["builder_code"] == "990000106")
        self.assertEqual(r["builder_name"], "UAB „DEMO Namai“")
        self.assertEqual(r["c_employees"], 9)                    # naujausias Sodros mėnuo

    def test_csv(self):
        path = report.write_csv(self.rows, self.tmp.file("out", "a.csv"))
        with open(path, encoding="utf-8-sig", newline="") as fh:
            got = list(csv.reader(fh, delimiter=";"))
        self.assertEqual(got[0], [h for _, h in report.EXPORT_COLS])
        self.assertEqual(len(got) - 1, len(self.rows))

    def test_builder_queue(self):
        path = self.tmp.file("out", "eile.csv")
        n = report.write_builder_queue(self.rows, path)
        with open(path, encoding="utf-8-sig", newline="") as fh:
            got = list(csv.DictReader(fh, delimiter=";"))
        self.assertEqual(n, len(got))
        self.assertGreater(n, 0)
        self.assertTrue(all(not r["statytojo_kodas"] for r in got))
        self.assertEqual([int(r["svarba"]) for r in got], sorted((int(r["svarba"]) for r in got), reverse=True))
        self.assertEqual(list(got[0])[:4], ["dokumento_reg_nr", "statytojo_kodas", "statytojo_pavadinimas", "pastaba"])

    def test_client_sample(self):
        path = report.write_client_sample(self.rows, self.tmp.file("out", "p.html"), "Pavyzdys <b>", "2026-09-05",
                                          "2026-10-05", limit=10, contact="tel. +370 600 00000")
        with open(path, encoding="utf-8") as fh:
            html = fh.read()
        self.assertIn("Pavyzdys &lt;b&gt;", html)
        self.assertIn("10 objektų", html)
        self.assertEqual(html.count("<tr>\n<td"), 10)
        ee_rows = [dict(r, country="EE") for r in self.rows[:2]]
        path = report.write_client_sample(ee_rows, self.tmp.file("out", "ee.html"), "Estija", "a", "b")
        with open(path, encoding="utf-8") as fh:
            self.assertIn("CC BY-SA 3.0", fh.read())                      # Estijos duomenų licencija
        empty = report.write_client_sample([], self.tmp.file("out", "t.html"), "Tuščias", "a", "b")
        with open(empty, encoding="utf-8") as fh:
            self.assertIn("signalų nerasta", fh.read())

    def test_plural(self):
        forms = ("objektas", "objektai", "objektų")
        for n, expected in ((1, 0), (2, 1), (9, 1), (10, 2), (11, 2), (15, 2), (21, 0), (22, 1), (111, 2)):
            with self.subTest(n=n):
                self.assertEqual(report.plural(n, *forms), forms[expected])


if __name__ == "__main__":
    unittest.main()

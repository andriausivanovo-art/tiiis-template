# -*- coding: utf-8 -*-
"""Komandinė eilutė: demo, savaitinis paleidimas (be tinklo), importas, pavyzdys klientui."""
import glob
import io
import json
import os
import re
import sqlite3
import unittest
from datetime import date, timedelta
from unittest import mock

import config
import db
import fetch
import sistema
from demo import generate_demo
from saltiniai import ee, lv, pl
from tests import TempDir, quiet


def html_data(path):
    with open(path, encoding="utf-8") as fh:
        return json.loads(re.search(r"const DATA = (.*?);\n", fh.read()).group(1))


class CliTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = TempDir()
        p = mock.patch.object(sistema, "BASE", self.tmp.path)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)

    def run_cli(self, *argv):
        with quiet() as out:
            code = sistema.main(list(argv))
        return code, out.getvalue()

    def outputs(self, pattern):
        return sorted(glob.glob(os.path.join(self.tmp.path, "isvestis", pattern)))


class DemoTest(CliTestCase):
    def test_demo_creates_csv_and_html(self):
        code, out = self.run_cli("demo")
        self.assertEqual(code, 0, out)
        for pattern in ("demo_signalai_*.csv", "demo_ataskaita_*.html", "demo_statytoju_eile_*.csv",
                        "demo_pavyzdys_*.html"):
            self.assertEqual(len(self.outputs(pattern)), 1, pattern)
        data = html_data(self.outputs("demo_ataskaita_*.html")[0])
        self.assertEqual({d["country"] for d in data}, {"LT", "LV", "PL", "EE"})
        self.assertTrue(os.path.exists(os.path.join(self.tmp.path, "duomenys", "demo.sqlite")))
        # kartojant demonstracija pradedama iš naujo
        code, _ = self.run_cli("demo")
        self.assertEqual(code, 0)
        self.assertEqual(len(html_data(self.outputs("demo_ataskaita_*.html")[0])), len(data))

    def test_sample_and_report_on_demo_db(self):
        self.run_cli("demo")
        demo_db = os.path.join(self.tmp.path, "duomenys", "demo.sqlite")
        code, out = self.run_cli("--db", demo_db, "sample", "--paskirtis", "DAUGIABU", "--savivaldybe", "vilniaus",
                                 "--salis", "LT", "--antraste", "Vilniaus daugiabučiai")
        self.assertEqual(code, 0, out)
        sample = self.outputs("pavyzdys_lt-daugiabu-vilniaus_*.html")
        self.assertEqual(len(sample), 1)
        with open(sample[0], encoding="utf-8") as fh:
            self.assertIn("Vilniaus daugiabučiai", fh.read())
        code, out = self.run_cli("--db", demo_db, "report", "--days", "30", "--all-types", "--salis", "PL,EE")
        self.assertEqual(code, 0)
        self.assertEqual({d["country"] for d in html_data(self.outputs("ataskaita_*.html")[0])}, {"PL", "EE"})


class ResolveSinceTest(unittest.TestCase):
    def test_first_run_overlap_and_future(self):
        tmp = TempDir()
        con = db.connect(tmp.file("t.sqlite"))
        try:
            today = date(2026, 10, 5)
            self.assertEqual(sistema.resolve_since(con, today), (today - timedelta(days=config.FIRST_RUN_DAYS)).isoformat())
            db.insert_rows(con, "LT", [("k1", "A", "2026-10-01", {})])
            self.assertEqual(sistema.resolve_since(con, today), "2026-09-24")
            db.insert_rows(con, "LT", [("k2", "B", "2099-01-01", {})])       # klaidinga data ateityje
            self.assertEqual(sistema.resolve_since(con, today), "2026-09-28")
            self.assertEqual(sistema.resolve_since(con, today, "LV"), "2026-09-05")   # kiekvienai šaliai atskirai
        finally:
            con.close()
            tmp.cleanup()


class RunTest(CliTestCase):
    """Savaitinis paleidimas su pakeistais (be tinklo) šaltiniais."""

    def setUp(self):
        super().setUp()
        self.today = date.today()
        demo = generate_demo.generate(self.today)
        self.foreign = generate_demo.write_foreign_files(self.tmp.file("failai"), self.today)
        self.lt_rows = demo["rows"]
        self.lt_fail = False
        patches = [
            mock.patch.object(fetch, "fetch_since", self.fake_lt),
            mock.patch.object(lv, "fetch_items", lambda con, since, today=None:
                              lv.read_files(con, self.foreign["LV"], since, today)),
            mock.patch.object(pl, "fetch_items", lambda con, since, today=None:
                              pl.read_files(con, self.foreign["PL"], since, today)),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def fake_lt(self, since, **kw):
        if self.lt_fail:
            raise fetch.FetchError("API užklausą užblokavo data.gov.lt ugniasienė.")
        return [r for r in self.lt_rows if r["dokumento_reg_data"] >= since]

    def runs(self):
        con = sqlite3.connect(os.path.join(self.tmp.path, config.DB_PATH))
        try:
            return con.execute("SELECT note, fetched, new_signals FROM runs ORDER BY run_id").fetchall()
        finally:
            con.close()

    def test_weekly_runs(self):
        code, out = self.run_cli("run")
        self.assertEqual(code, 0, out)
        first = html_data(self.outputs("ataskaita_*.html")[0])
        self.assertEqual({d["country"] for d in first}, {"LT", "LV", "PL"})     # EE – tik per importą
        self.assertTrue(self.runs()[-1][0].startswith("run: ataskaita_"))
        self.assertGreater(len(self.outputs("statytoju_eile_*.csv")), 0)

        # antras paleidimas: tie patys duomenys -> naujų signalų nėra, ataskaita jų nekartoja
        code, out = self.run_cli("run")
        self.assertEqual(code, 0, out)
        self.assertEqual(html_data(self.outputs("ataskaita_*.html")[0]), [])

        # trečias: LT nepasiekiama, kitos šalys veikia -> ataskaita sukuriama, kodas 2, klaida žurnale
        self.lt_fail = True
        code, out = self.run_cli("run")
        self.assertEqual(code, 2)
        self.assertIn("nepavyko: LT", self.runs()[-1][0])

    def test_all_sources_fail(self):
        self.lt_fail = True
        code, _ = self.run_cli("run", "--salis", "LT")
        self.assertEqual(code, 2)
        self.assertTrue(self.runs()[-1][0].startswith("run KLAIDA"))
        self.assertEqual(self.outputs("ataskaita_*.html"), [])
        con = db.connect(os.path.join(self.tmp.path, config.DB_PATH))
        self.assertIsNone(db.last_run(con))                                    # nesėkmingas paleidimas – ne riba
        con.close()

    def test_fetch_then_build_then_report(self):
        code, out = self.run_cli("fetch", "--salis", "LT,LV")
        self.assertEqual(code, 0, out)
        code, out = self.run_cli("build")
        self.assertEqual(code, 0)
        self.assertIn("nauji", out)
        code, out = self.run_cli("report", "--days", "30")
        self.assertEqual(code, 0)
        self.assertEqual({d["country"] for d in html_data(self.outputs("ataskaita_*.html")[0])}, {"LT", "LV"})


class ImportTest(CliTestCase):
    def test_import_csv_lt_and_other_countries(self):
        rows = generate_demo.generate()["rows"]
        path = generate_demo.write_csv(self.tmp.file("statiniai.csv"), rows)
        code, out = self.run_cli("import-csv", path, "--since", "2000-01-01")
        self.assertEqual(code, 0, out)
        self.assertIn(f"Nuskaityta įrašų: {len(rows)}", out)
        files = generate_demo.write_foreign_files(self.tmp.file("f"))
        for code_, paths in files.items():
            code, out = self.run_cli("import", "--salis", code_, *paths)
            self.assertEqual(code, 0, out)
        code, out = self.run_cli("build")
        con = sqlite3.connect(os.path.join(self.tmp.path, config.DB_PATH))
        got = dict(con.execute("SELECT country, COUNT(*) FROM signals GROUP BY country").fetchall())
        con.close()
        self.assertEqual(set(got), {"LT", "LV", "PL", "EE"})

    def test_import_wrong_file(self):
        path = self.tmp.file("x.csv")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("a;b\n1;2\n")
        self.assertEqual(self.run_cli("import-csv", path)[0], 1)
        self.assertEqual(self.run_cli("import", "--salis", "PL", path)[0], 1)
        self.assertEqual(self.run_cli("import", "--salis", "LV", self.tmp.file("nera.csv"))[0], 1)
        self.assertEqual(self.run_cli("import", "--salis", "LV,PL", path)[0], 1)

    def test_enrich_needs_builders_first(self):
        code, out = self.run_cli("enrich", self.tmp.file("nera.csv"))
        self.assertEqual(code, 0)
        self.assertIn("builders.csv", out)


class ArgumentsTest(CliTestCase):
    def test_validation(self):
        for argv in (["report", "--days", "x"], ["fetch", "--since", "2026-13-01"], ["sample", "--tipas", "nera"],
                     ["run", "--salis", "FI"], ["ee-order"]):
            with self.subTest(argv=argv), quiet(), self.assertRaises(SystemExit) as cm:
                sistema.main(argv)
            self.assertEqual(cm.exception.code, 2)

    def test_no_command_prints_help(self):
        code, out = self.run_cli()
        self.assertEqual(code, 1)
        self.assertIn("komandos", out)


class EstoniaOrderTest(unittest.TestCase):
    def test_order_payload(self):
        sent = {}

        class Resp(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake_urlopen(req, timeout=None):
            sent["url"], sent["method"], sent["body"] = req.full_url, req.get_method(), json.loads(req.data)
            return Resp(b'{"status": 200, "message": "OK"}')

        with mock.patch("urllib.request.urlopen", fake_urlopen), quiet():
            code = sistema.main(["ee-order", "--email", "test@example.com", "--apskritis", "Harju,Tartu"])
        self.assertEqual(code, 0)
        self.assertEqual((sent["url"], sent["method"]), (f"{config.EE_API}/reports", "POST"))
        self.assertEqual(sent["body"]["report_code"], "eh_ehitised")
        self.assertEqual(sent["body"]["county"], ["37", "79"])
        self.assertEqual(sent["body"]["seisund"], config.EE_ORDER_STATUSES)
        self.assertEqual(ee.order_report.__module__, "saltiniai.ee")


class MigrationTest(unittest.TestCase):
    def test_old_database_gets_country_columns(self):
        tmp = TempDir()
        path = tmp.file("old.sqlite")
        con = sqlite3.connect(path)
        con.executescript("""
            CREATE TABLE raw_records (row_key TEXT PRIMARY KEY, doc_nr TEXT, doc_date TEXT,
                                      data_json TEXT NOT NULL, first_seen TEXT NOT NULL);
            CREATE TABLE signals (signal_id TEXT PRIMARY KEY, doc_date TEXT, signal_type TEXT, signal_label TEXT,
                doc_text TEXT, works_type TEXT, purposes TEXT, category TEXT, object_names TEXT, object_count INTEGER,
                address TEXT, municipality TEXT, cadastre TEXT, project_name TEXT, project_nr TEXT, lat REAL, lon REAL,
                point_lks TEXT, score INTEGER, builder_code TEXT, builder_name TEXT, first_seen TEXT NOT NULL,
                updated TEXT NOT NULL);
            INSERT INTO raw_records VALUES ('k', 'LSNS-1', '2026-10-01', '{}', '2026-10-01 10:00:00');
        """)
        con.close()
        con = db.connect(path)
        try:
            self.assertEqual(con.execute("SELECT source FROM raw_records").fetchone()[0], "LT")
            self.assertIn("country", [r[1] for r in con.execute("PRAGMA table_info(signals)")])
        finally:
            con.close()
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""Patikimumas: tinklo klaidos, rinkinio kelio pakeitimas, failų formatai, LT įrašų raktai ir taisyklės."""
import http.client
import io
import json
import os
import unittest
import zipfile
from unittest import mock

import config
import db
import fetch
import saltiniai
import signals
import sistema
from demo import generate_demo
from tests import TempDir, quiet


def page(rows, nxt=None):
    return json.dumps({"_data": rows, "_page": {"next": nxt} if nxt else {}})


class FetchModelTest(unittest.TestCase):
    def setUp(self):
        for name, value in (("REQUEST_PAUSE_S", 0),):
            p = mock.patch.object(config, name, value)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(fetch.time, "sleep", lambda s: None)
        p.start()
        self.addCleanup(p.stop)

    def test_falls_back_to_old_dataset_path(self):
        calls = []

        def fake_get(url):
            calls.append(url)
            return (404, '{"errors": [{"type": "ModelNotFound"}]}') if "/ssva/" in url else \
                (200, page([{"dokumento_reg_data": "2026-10-01"}]))

        with mock.patch.object(fetch, "_get", fake_get), quiet():
            rows = fetch.fetch_since("2026-09-28")
        self.assertEqual(len(rows), 1)
        self.assertIn("/ssva/", calls[0])
        self.assertIn("/vtpsi/", calls[1])

    def test_not_found_everywhere_is_clear_error(self):
        with mock.patch.object(fetch, "_get", lambda url: (404, "{}")):
            with self.assertRaisesRegex(fetch.FetchError, "config.MODEL"):
                fetch.fetch_since("2026-09-28", verbose=False)

    def test_temporary_error_is_retried_not_full_scan(self):
        responses = iter([(503, "Service Unavailable"), (200, page([{"dokumento_reg_data": "2026-10-01"}]))])
        calls = []
        with mock.patch.object(fetch, "_get", lambda url: calls.append(url) or next(responses)):
            rows = fetch.fetch_since("2026-09-28", verbose=False)
        self.assertEqual(len(rows), 1)
        self.assertTrue(all("dokumento_reg_data" in c for c in calls))       # filtras neprarastas

    def test_page_limit_is_an_error(self):
        with mock.patch.object(fetch, "_get", lambda url: (200, page([{"dokumento_reg_data": "2026-10-01"}], "x"))):
            with self.assertRaisesRegex(fetch.FetchError, "puslapių riba"):
                fetch.fetch_since("2026-09-28", max_pages=3, verbose=False)

    def test_broken_connection_becomes_fetch_error(self):
        def broken(req, timeout=None):
            raise http.client.IncompleteRead(b"abc", 100)

        with mock.patch("urllib.request.urlopen", broken):
            with self.assertRaisesRegex(fetch.FetchError, "nutrūko"):
                fetch._get("https://example.invalid/x")


class ArcgisTest(unittest.TestCase):
    """SSVA ArcGIS paslauga (atsarginis LT šaltinis): datos, koordinatės, puslapiai."""

    def test_rows_and_paging(self):
        def feature(i, day_ms):
            return {"attributes": {"object_id": i, "id": str(i), "dokumento_reg_nr": f"LSNS-01-261002-{i}",
                                   "dokumento_reg_data": day_ms, "iraso_data": day_ms + 3_600_000,
                                   "dok_tipo_kodas": "LSNS"},
                    "geometry": {"x": 25.2790, "y": 54.7155}}
        oct2 = 1790899200000                                              # 2026-10-02 00:00 UTC
        pages = [{"features": [feature(1, oct2), feature(2, oct2)], "exceededTransferLimit": True},
                 {"features": [feature(3, oct2)]}]
        calls = []

        def fake_get(url):
            calls.append(url)
            return 200, json.dumps(pages[len(calls) - 1])

        with mock.patch.object(fetch, "_get", fake_get), mock.patch.object(config, "REQUEST_PAUSE_S", 0):
            rows = fetch.fetch_arcgis("2026-09-28", verbose=False)
        self.assertEqual([r["id"] for r in rows], ["1", "2", "3"])
        self.assertEqual((rows[0]["dokumento_reg_data"], rows[0]["iraso_data"]), ("2026-10-02", "2026-10-02T01:00:00"))
        self.assertNotIn("object_id", rows[0])
        self.assertEqual(signals.wgs_point(rows[0]["taskas_wgs"]), (54.7155, 25.279))
        self.assertIn("resultOffset=2", calls[1])
        self.assertIn("DATE+%272026-09-28%27", calls[0])

    def test_connection_reset_is_retried(self):
        answers = [fetch.FetchError("Nepavyko prisijungti: [Errno 104] Connection reset by peer"),
                   (200, json.dumps({"features": []}))]

        def flaky(url):
            a = answers.pop(0)
            if isinstance(a, Exception):
                raise a
            return a

        with mock.patch.object(fetch, "_get", flaky), mock.patch.object(fetch.time, "sleep", lambda s: None):
            self.assertEqual(fetch.fetch_arcgis("2026-09-28", verbose=False), [])
        self.assertEqual(answers, [])

    def test_error_response(self):
        with mock.patch.object(fetch, "_get", lambda url: (200, '{"error": {"code": 400, "message": "Invalid"}}')):
            with self.assertRaisesRegex(fetch.FetchError, "ArcGIS"):
                fetch.fetch_arcgis("2026-09-28", verbose=False)


class DownloadTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TempDir()
        self.addCleanup(self.tmp.cleanup)

    def _serve(self, body, length):
        class Resp(io.BytesIO):
            headers = {"Content-Length": str(length)}

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        return mock.patch("urllib.request.urlopen", lambda req, timeout=None: Resp(body))

    def test_truncated_download_is_rejected(self):
        dest = self.tmp.file("f.csv")
        with self._serve(b"a,b\n1,2\n", 1000), self.assertRaisesRegex(saltiniai.SourceError, "nutrūko"):
            saltiniai.download("https://example.invalid/f.csv", dest)
        self.assertFalse(os.path.exists(dest))
        self.assertFalse(os.path.exists(dest + ".part"))

    def test_complete_download(self):
        dest = self.tmp.file("f.csv")
        with self._serve(b"a,b\n1,2\n", 8):
            saltiniai.download("https://example.invalid/f.csv", dest)
        with open(dest, "rb") as fh:
            self.assertEqual(fh.read(), b"a,b\n1,2\n")


class FileFormatTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TempDir()
        self.addCleanup(self.tmp.cleanup)

    def test_zip_detected_without_extension_and_cp1257(self):
        path = self.tmp.file("atsisiuntimas")              # be plėtinio, kaip iš el. laiško nuorodos
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("x.csv", "a;b\nŠiaulių;Žemė\n".encode("cp1257"))
        self.assertEqual(list(saltiniai.csv_rows(path)), [{"a": "Šiaulių", "b": "Žemė"}])

    def test_long_field(self):
        path = self.tmp.file("g.csv")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write('ehr_kood,geometry\n1,"' + "x" * 300_000 + '"\n')
        self.assertEqual(len(next(saltiniai.csv_rows(path))["geometry"]), 300_000)

    def test_lt_import_from_zip_and_excel_cp1257(self):
        rows = generate_demo.generate()["rows"]
        csv_path = generate_demo.write_csv(self.tmp.file("s.csv"), rows)
        zpath = self.tmp.file("s.zip")
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(csv_path, "Statinys.csv")
        con = db.connect(self.tmp.file("t.sqlite"))
        try:
            items = saltiniai.get("LT").read_files(con, [zpath], "2000-01-01")
            self.assertEqual(len(items), len(rows))
        finally:
            con.close()
        excel = self.tmp.file("excel.csv")
        with open(excel, "w", encoding="cp1257") as fh:
            fh.write("dokumento_reg_nr;dokumento_reg_data;dok_irasas\nA;2026-10-01;Statybos užbaigimo aktas\n")
        self.assertEqual(fetch.read_csv(excel)[0]["dok_irasas"], "Statybos užbaigimo aktas")


class LtRowKeyTest(unittest.TestCase):
    def test_buildings_sharing_document_uuid_are_all_kept(self):
        tmp = TempDir()
        con = db.connect(tmp.file("t.sqlite"))
        try:
            rows = [{"_id": f"r{i}", "id": i, "uuid": "DOKUMENTAS", "dokumento_reg_nr": "LSNS-1",
                     "dokumento_reg_data": "2026-10-01", "statinio_id": i, "dok_irasas": "Leidimas statyti naują"}
                    for i in range(4)]
            self.assertEqual(db.insert_raw(con, rows, config.F), 4)
            sistema.build_signals(con)
            self.assertEqual(con.execute("SELECT object_count FROM signals").fetchone()[0], 4)
            # ta pati eilutė su nauja būsena perrašoma ir signalas pašalinamas
            st = {}
            self.assertEqual(db.insert_raw(con, [dict(rows[0], dok_statusas="Panaikintas")], config.F, stats=st), 0)
            self.assertEqual(st["pakeisti"], 1)
            sistema.build_signals(con, db.docs_to_build(con))
            self.assertEqual(con.execute("SELECT COUNT(*) FROM signals").fetchone()[0], 0)
        finally:
            con.close()
            tmp.cleanup()


class LtRulesTest(unittest.TestCase):
    def test_municipality_list(self):
        cases = {
            "Kazlų Rūdos sav., Kazlų Rūdos m., Vytauto g. 1": "Kazlų Rūdos sav.",
            "VILNIAUS M. SAV., VILNIUS, GEDIMINO PR. 1": "Vilniaus m. sav.",
            "Vilniaus miesto savivaldybė, Vilnius": "Vilniaus m. sav.",
            "Panevėžio r. sav., Velžio sen.": "Panevėžio r. sav.",
            "Vilniaus g. 5, Kauno m. sav.": "Kauno m. sav.",
        }
        for address, expected in cases.items():
            with self.subTest(address=address):
                self.assertEqual(signals.municipality(address), expected)
        self.assertEqual(len(signals.MUNICIPALITIES), 60)

    def test_new_rules(self):
        self.assertEqual(signals.classify("Leidimas atlikti statinio (-ių) kapitalinį remontą")[0],
                         "leidimas_atnaujinimas")
        self.assertEqual(signals.classify("Prašymas išduoti rašytinį pritarimą statinio projektui")[0], "prasymas")
        s = signals.build_signal("X", [{"dokumento_reg_nr": "X", "dok_irasas": "Neatpažintas dokumentas",
                                        "dokumento_kategorija": "prasymas"}])
        self.assertEqual(s["signal_type"], "prasymas")

    def test_two_flat_house_is_not_scored_like_commerce(self):
        two = signals.score("leidimas_nauja", ["Gyvenamosios paskirties (dviejų butų) pastatai"], "", 1)
        many = signals.score("leidimas_nauja", ["Gyvenamosios paskirties (trijų ir daugiau butų) pastatai"], "", 1)
        self.assertEqual((two, many), (3, 6))


class SelectRowsTest(unittest.TestCase):
    def test_city_in_address_matches(self):
        rows = [{"municipality": "woj. mazowieckie", "address": "Warszawa, ul. Prosta 68", "purposes": ""}]
        self.assertEqual(len(sistema.select_rows(rows, savivaldybe="warszawa")), 1)
        self.assertEqual(len(sistema.select_rows(rows, savivaldybe="mazowieckie")), 1)
        self.assertEqual(len(sistema.select_rows(rows, savivaldybe="krakow")), 0)


if __name__ == "__main__":
    unittest.main()

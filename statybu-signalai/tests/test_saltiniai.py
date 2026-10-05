# -*- coding: utf-8 -*-
"""Kitų šalių šaltiniai: LV (BIS), PL (GUNB RWDZ), EE (EHR). Failai – demonstraciniai, tikrais formatais."""
import csv
import os
import unittest
from datetime import date, timedelta

import config
import db
import saltiniai
from demo import generate_demo
from saltiniai import ee, lv, pl
from tests import TempDir

TODAY = date(2026, 10, 5)
SINCE = (TODAY - timedelta(days=14)).isoformat()


class HelpersTest(unittest.TestCase):
    def test_fold_and_dates(self):
        self.assertEqual(saltiniai.fold("Ādažu ŁÓDŹ Õismäe Šiaulių"), "adazu lodz oismae siauliu")
        self.assertEqual(saltiniai.norm_date("2016-06-09 00:00:00"), "2016-06-09")
        self.assertEqual(saltiniai.norm_date("21.09.2026"), "2026-09-21")
        self.assertEqual(saltiniai.norm_date("2026.02"), "2026-02-01")
        self.assertEqual(saltiniai.norm_date("nėra"), "")

    def test_delimiter_and_duplicate_columns(self):
        tmp = TempDir()
        try:
            path = tmp.file("d.csv")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("a#cecha#cecha#b\n1#ul.#al.#2\n")   # GUNB aprašyme nurodytas „#“
            self.assertEqual(list(saltiniai.csv_rows(path)), [{"a": "1", "cecha": "ul.", "cecha_2": "al.", "b": "2"}])
        finally:
            tmp.cleanup()

    def test_unknown_country(self):
        with self.assertRaises(saltiniai.SourceError):
            saltiniai.get("FI")


class SourceTestCase(unittest.TestCase):
    code = None

    def setUp(self):
        self.tmp = TempDir()
        self.con = db.connect(self.tmp.file("t.sqlite"))
        self.files = generate_demo.write_foreign_files(self.tmp.file("demo"), TODAY)

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    def load(self, paths=None, since=SINCE, today=TODAY):
        src = saltiniai.get(self.code)
        items = src.read_files(self.con, paths or self.files[self.code], since, today)
        db.insert_rows(self.con, self.code, items)
        out = {}
        for doc, (_, rows) in db.raw_groups(self.con).items():
            if not src.is_excluded(rows):
                out[doc] = src.build_signal(doc, rows, self.con)
        return items, out


class LatviaTest(SourceTestCase):
    code = "LV"

    def test_cases_to_signals(self):
        items, sig = self.load()
        self.assertEqual(len(items), len(generate_demo.LV_CASES) - 1)        # nutraukta byla atmetama
        by_name = {s["project_name"]: s for s in sig.values()}
        flat = by_name["Daudzdzīvokļu dzīvojamā māja, Ganību dambis 40, Rīga"]
        self.assertEqual(flat["signal_type"], "prasymas")
        self.assertEqual(flat["purposes"], "daugiabučiai (3 ir daugiau butų)")
        self.assertEqual(flat["municipality"], "Rīga")
        self.assertEqual(flat["object_count"], 2)
        self.assertAlmostEqual(flat["lat"], 56.979, places=3)
        self.assertEqual(flat["score"], 3 + 3)
        self.assertTrue(flat["signal_id"].startswith("LV:BIS-BL-"))
        self.assertEqual(by_name["Loģistikas centrs DEMO, Lidosta, Mārupes nov."]["signal_type"], "leidimas_nauja")
        self.assertEqual(by_name["Viesnīcas pārbūve, Jomas iela 50, Jūrmala"]["signal_type"], "leidimas_rekonstrukcija")
        self.assertEqual(by_name["Dzīvojamā māja, Podnieku iela 7, Ādaži"]["signal_type"], "pradzia")
        renovation = by_name["Dzīvokļa vienkāršotā atjaunošana, Brīvības iela 100-12, Rīga"]
        self.assertEqual(renovation["signal_type"], "pranesimas")             # darbai pagal pranešimą
        self.assertIsNone(renovation["lat"])
        self.assertEqual(renovation["municipality"], "Rīga")                    # iš būvvaldės pavadinimo
        self.assertEqual(by_name["Biroju ēka, Graudu iela 22, Liepāja"]["signal_type"], "uzbaigimas")
        self.assertEqual(by_name["Ūdensvada pieslēgums, Ogre"]["score"], 3 - 1)  # inžinerinis statinys

    def test_stage_change_of_known_case_is_new_event(self):
        self.load()
        lietas = self.files["LV"][0]
        with open(lietas, encoding="utf-8", newline="") as fh:
            rows = list(csv.reader(fh))
        rows[1][4] = "Būvdarbi"                       # pirmoji byla pasiekė statybos darbų stadiją
        rows[1][6] = "2026-01-15"                      # sukurta seniai: imama tik todėl, kad jau žinoma
        with open(lietas, "w", encoding="utf-8", newline="") as fh:
            csv.writer(fh, quoting=csv.QUOTE_ALL).writerows(rows)
        later = TODAY + timedelta(days=7)
        items = lv.read_files(self.con, self.files["LV"], (later - timedelta(days=7)).isoformat(), later)
        new = db.insert_rows(self.con, "LV", items)
        self.assertEqual(new, 1)
        key = next(k for k, _, d, _ in items if k.endswith(":buvdarbi") and rows[1][1] in k)
        self.assertEqual(next(d for k, _, d, _ in items if k == key), later.isoformat())

    def test_known_case_older_than_tracking_window_is_skipped(self):
        self.load()
        lietas = self.files["LV"][0]
        with open(lietas, encoding="utf-8", newline="") as fh:
            rows = list(csv.reader(fh))
        rows[1][4], rows[1][6] = "Būvdarbi", (TODAY - timedelta(days=config.LV_TRACK_DAYS + 1)).isoformat()
        with open(lietas, "w", encoding="utf-8", newline="") as fh:
            csv.writer(fh, quoting=csv.QUOTE_ALL).writerows(rows)
        items = lv.read_files(self.con, self.files["LV"], SINCE, TODAY)
        self.assertFalse([k for k, _, _, _ in items if rows[1][1] in k])

    def test_old_unknown_cases_are_skipped(self):
        items = lv.read_files(self.con, self.files["LV"], TODAY.isoformat(), TODAY)
        self.assertEqual(len(items), 0)

    def test_authority_to_territory(self):
        self.assertEqual(lv.territory_from_authority("Ogres novada pašvaldības centrālās administrācijas Ogres "
                                                     "novada būvvalde"), "Ogres novads")
        self.assertEqual(lv.territory_from_authority("Rēzeknes valstspilsētas pašvaldības Būvvalde"), "Rēzekne")
        self.assertEqual(lv.territory_from_authority("Daugavpils pašvaldības Centrālā pārvalde Būvvalde"), "Daugavpils")

    def test_unknown_file(self):
        bad = self.tmp.file("x.csv")
        with open(bad, "w", encoding="utf-8") as fh:
            fh.write("a,b\n1,2\n")
        with self.assertRaises(saltiniai.SourceError):
            lv.read_files(self.con, [bad], SINCE, TODAY)


class PolandTest(SourceTestCase):
    code = "PL"

    def test_permits_and_notices(self):
        items, sig = self.load()
        # leidimai grupuojami pagal GUNB numerį (keli sklypai – vienas signalas)
        self.assertEqual(len(sig), len(generate_demo.PL_PERMITS) + len(generate_demo.PL_NOTICES))
        by_name = {s["project_name"]: s for s in sig.values()}
        flat = by_name["Budowa budynku mieszkalnego wielorodzinnego z garażem podziemnym"]
        self.assertEqual(flat["signal_type"], "leidimas_nauja")
        self.assertEqual(flat["builder_name"], "DEMO Deweloper Sp. z o.o.")
        self.assertEqual(flat["municipality"], "woj. mazowieckie")
        self.assertEqual(flat["address"], "Warszawa, ul. Kasprzaka 31")
        self.assertEqual(flat["cadastre"].count(";"), 2)                        # 3 sklypai
        self.assertIsNone(flat["lat"])
        self.assertEqual(flat["score"], 3 + 3 + 1)                              # XIII + didelė kubatūra
        self.assertEqual(by_name["Rozbiórka budynku handlowego"]["signal_type"], "griovimas")
        self.assertEqual(by_name["Nadbudowa hotelu o dwie kondygnacje"]["signal_type"], "leidimas_rekonstrukcija")
        self.assertEqual(by_name["Termomodernizacja budynku szkoły"]["signal_type"], "leidimas_atnaujinimas")
        house = by_name["Budowa budynku mieszkalnego jednorodzinnego"]
        self.assertIsNone(house["builder_name"])                                # fizinis asmuo nenurodomas
        notice = by_name["Budowa budynku mieszkalnego jednorodzinnego wolnostojącego"]
        self.assertEqual(notice["signal_type"], "pranesimas")
        self.assertTrue(notice["signal_label"].startswith("PL pranešimas"))

    def test_no_personal_data_stored(self):
        items, _ = self.load()
        for _, _, _, row in items:
            self.assertFalse([k for k in row if "projektant" in k or k in ("nazwisko", "imie")])
            self.assertNotIn("Projektant", row.values())

    def test_date_filter(self):
        items, _ = self.load(since=(TODAY - timedelta(days=3)).isoformat())
        self.assertTrue(items)
        self.assertTrue(all(d >= (TODAY - timedelta(days=3)).isoformat() for _, _, d, _ in items))

    def test_objection_is_excluded(self):
        self.assertTrue(pl.is_excluded([{"status": "Wniesiono sprzeciw"}]))
        self.assertFalse(pl.is_excluded([{"status": "Brak sprzeciwu"}]))


class EstoniaTest(SourceTestCase):
    code = "EE"

    def test_buildings_to_signals(self):
        items, sig = self.load()
        self.assertEqual(len(items), len(generate_demo.EE_BUILDINGS) - 1)     # „Realiseerimata“ atmetamas
        by_addr = {s["address"]: s for s in sig.values()}
        flat = by_addr["Harju maakond, Tallinn, Kristiine linnaosa, Tulika tn 19"]
        self.assertEqual(flat["signal_type"], "prasymas")
        self.assertEqual(flat["municipality"], "Tallinn")
        self.assertEqual(flat["purposes"], "daugiabučiai (3 ir daugiau butų) (Muu kolme või enama korteriga elamu)")
        self.assertEqual(flat["score"], 3 + 3)
        self.assertAlmostEqual(flat["lat"], 59.4250, places=4)                  # iš L-EST97 atskaitos taško
        self.assertAlmostEqual(flat["lon"], 24.7180, places=4)
        office = by_addr["Harju maakond, Tallinn, Kesklinna linnaosa, Narva mnt 7"]
        self.assertEqual(office["signal_type"], "pradzia")                       # būsena tekstu „Püstitamisel“
        self.assertEqual(by_addr["Pärnu maakond, Pärnu linn, Pärnu linn, Ranna pst 5"]["signal_type"], "uzbaigimas")
        road = by_addr["Tartu maakond, Tartu linn, Tartu linn, Riia mnt"]
        self.assertEqual(road["score"], 3 - 1)                                   # rajatis

    def test_lest97_matches_reference(self):
        # palyginta su pyproj (EPSG:4326 -> EPSG:3301)
        north, east = ee.wgs_to_lest(59.43696, 24.74535)
        self.assertAlmostEqual(north, 6589026.6, delta=0.2)
        self.assertAlmostEqual(east, 542295.3, delta=0.2)
        lat, lon = ee.lest_to_wgs(6474365.3, 659376.3)
        self.assertAlmostEqual(lat, 58.38062, places=5)
        self.assertAlmostEqual(lon, 26.72509, places=5)
        self.assertEqual(ee.point_from_lest("542295.3", "6589026.6")[0] is not None, True)   # bet kokia tvarka
        self.assertEqual(ee.point_from_lest("", "1"), (None, None))

    def test_status_mapping(self):
        self.assertEqual(ee.status("Püstitamisel")[1], "pradzia")
        self.assertIsNone(ee.status("EHITIS_SEISUND_EHITAM_LUBA_EIKEH")[1])
        self.assertEqual(ee.status("EHITIS_SEISUND_EHITAM_LUBA")[1], "leidimas_nauja")
        self.assertEqual(ee.county_codes(["Harju", "79"]), ["37", "79"])

    def test_fetch_requires_order(self):
        with self.assertRaisesRegex(saltiniai.SourceError, "ee-order"):
            ee.fetch_items(self.con, SINCE, TODAY)


class LithuaniaSourceTest(unittest.TestCase):
    def test_lt_wrapper(self):
        rows = generate_demo.generate(TODAY)["rows"]
        doc = rows[0]["dokumento_reg_nr"]
        s = saltiniai.get("LT").build_signal(doc, [r for r in rows if r["dokumento_reg_nr"] == doc])
        self.assertEqual((s["country"], s["signal_id"]), ("LT", doc))
        self.assertTrue(os.path.basename(saltiniai.get("lt").__file__).startswith("lt"))


if __name__ == "__main__":
    unittest.main()

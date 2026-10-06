# -*- coding: utf-8 -*-
"""Kitų šalių šaltiniai: LV (BIS), PL (GUNB RWDZ), EE (EHR). Failai – demonstraciniai, tikrais formatais."""
import csv
import os
import shutil
import unittest
import urllib.parse
from datetime import date, timedelta
from unittest import mock

import config
import db
import saltiniai
from demo import generate_demo
from saltiniai import ee, lv, pl
from tests import TempDir, quiet

ORIGINAL_API_GET = ee._api_get

TODAY = date(2026, 10, 5)
SINCE = (TODAY - timedelta(days=14)).isoformat()
EE_SINCE = (TODAY - timedelta(days=5)).isoformat()      # EE API ima ne daugiau kaip 7 d.


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

    def test_baseline_case_stage_change_becomes_signal(self):
        lietas = self.files["LV"][0]
        with open(lietas, encoding="utf-8", newline="") as fh:
            rows = list(csv.reader(fh))
        rows[1][6] = (TODAY - timedelta(days=200)).isoformat()      # sena byla: pirmą kartą tik įsimenama
        with open(lietas, "w", encoding="utf-8", newline="") as fh:
            csv.writer(fh, quoting=csv.QUOTE_ALL).writerows(rows)
        items, _ = self.load()
        self.assertFalse([k for k, _, _, _ in items if rows[1][1] in k])
        rows[1][4] = "Būvdarbi"
        with open(lietas, "w", encoding="utf-8", newline="") as fh:
            csv.writer(fh, quoting=csv.QUOTE_ALL).writerows(rows)
        items = lv.read_files(self.con, self.files["LV"], SINCE, TODAY)
        # žinomos bylos pateikiamos dar kartą, bet nauja tik pasikeitusi stadija
        self.assertEqual(db.insert_rows(self.con, "LV", items), 1)
        self.assertIn(f"LV:{rows[1][1]}:buvdarbi", [k for k, _, _, _ in items])

    def test_older_since_rescans_known_cases(self):
        lietas = self.files["LV"][0]
        with open(lietas, encoding="utf-8", newline="") as fh:
            rows = list(csv.reader(fh))
        rows[1][6] = (TODAY - timedelta(days=60)).isoformat()       # už numatyto laikotarpio
        with open(lietas, "w", encoding="utf-8", newline="") as fh:
            csv.writer(fh, quoting=csv.QUOTE_ALL).writerows(rows)
        items = lv.read_files(self.con, self.files["LV"], SINCE, TODAY)
        self.assertFalse([k for k, _, _, _ in items if rows[1][1] in k])
        db.insert_rows(self.con, "LV", items)
        # tas pats failas su ankstesne --since: anksčiau tik įsiminta byla dabar tampa signalu
        items = lv.read_files(self.con, self.files["LV"], "2000-01-01", TODAY)
        self.assertEqual(db.insert_rows(self.con, "LV", items), 1)

    def test_states_seeded_from_old_database(self):
        items, _ = self.load()
        self.con.execute("DELETE FROM busenos")                     # bazė iš senesnės versijos
        lietas = self.files["LV"][0]
        with open(lietas, encoding="utf-8", newline="") as fh:
            rows = list(csv.reader(fh))
        rows[1][4] = "Būvdarbi"
        rows[1][6] = (TODAY - timedelta(days=60)).isoformat()
        with open(lietas, "w", encoding="utf-8", newline="") as fh:
            csv.writer(fh, quoting=csv.QUOTE_ALL).writerows(rows)
        items = lv.read_files(self.con, self.files["LV"], SINCE, TODAY)
        self.assertIn(f"LV:{rows[1][1]}:buvdarbi", [k for k, _, _, _ in items])
        # nepasikeitusių bylų būsenos irgi įrašytos: kitą savaitę jų pokyčiai neprarandami
        self.assertGreater(len(db.get_states(self.con, "LV")), 2)
        rows[2][4] = "Būvdarbi"
        rows[2][6] = (TODAY - timedelta(days=60)).isoformat()
        with open(lietas, "w", encoding="utf-8", newline="") as fh:
            csv.writer(fh, quoting=csv.QUOTE_ALL).writerows(rows)
        items = lv.read_files(self.con, self.files["LV"], SINCE, TODAY)
        self.assertIn(f"LV:{rows[2][1]}:buvdarbi", [k for k, _, _, _ in items])

    def test_terminated_known_case_removes_signals(self):
        _, sig = self.load()
        for s in sig.values():
            db.upsert_signal(self.con, s)
        self.con.commit()
        lietas = self.files["LV"][0]
        with open(lietas, encoding="utf-8", newline="") as fh:
            rows = list(csv.reader(fh))
        rows[1][4] = "Izbeigta"
        with open(lietas, "w", encoding="utf-8", newline="") as fh:
            csv.writer(fh, quoting=csv.QUOTE_ALL).writerows(rows)
        lv.read_files(self.con, self.files["LV"], SINCE, TODAY)
        left = [r[0] for r in self.con.execute("SELECT signal_id FROM signals WHERE signal_id LIKE 'LV:%'")]
        self.assertFalse([x for x in left if rows[1][1] in x])

    def test_northern_latvia_point_kept(self):
        self.assertEqual(lv.point("57.78", "26.03"), (57.78, 26.03))             # Valka, už LT ribų
        self.assertEqual(lv.point("", "24.1"), (None, None))
        self.assertEqual(lv.point("54.0", "24.1"), (None, None))

    def test_duplicate_kind_rejected(self):
        with self.assertRaises(saltiniai.SourceError):
            lv.read_files(self.con, [self.files["LV"][0], self.files["LV"][0]], SINCE, TODAY)

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
        since = (TODAY - timedelta(days=3)).isoformat()
        items, _ = self.load(since=since)
        permits = [d for _, _, d, r in items if r["_rusis"] == "pozwolenie"]
        notices = [d for _, _, d, r in items if r["_rusis"] == "zgloszenie"]
        self.assertTrue(permits and all(d >= since for d in permits))
        # pranešimai registre atsiranda vėluodami, todėl jiems langas ne trumpesnis nei 90 d.
        self.assertEqual(len({d for d in notices}), len(generate_demo.PL_NOTICES))

    def test_one_broken_file_does_not_stop_others(self):
        good = {os.path.basename(p): p for p in self.files["PL"]}

        def fake_download(url, dest, timeout=None):
            name = url.rsplit("/", 1)[-1]
            if name not in good:
                raise saltiniai.SourceError(f"{url}: HTTP 404")
            shutil.copy(good[name], dest)
            return dest

        with mock.patch.object(config, "PL_WOJEWODZTWA", ["mazowieckie", "nera"]), \
                mock.patch.object(pl, "download", fake_download), quiet(), \
                self.assertRaisesRegex(saltiniai.PartialSourceError, "wynik_nera.zip") as cm:
            pl.fetch_items(self.con, SINCE, TODAY)
        self.assertTrue(any(r["_rusis"] == "pozwolenie" for _, _, _, r in cm.exception.items))
        self.assertEqual(db.get_states(self.con, pl.FAILED), {"wynik_nera.zip": SINCE})
        # kitą kartą praleistas failas imamas nuo tos pačios datos, nors bendra data pasislinko
        seen = []
        real_select = pl.select_file
        good["wynik_nera.zip"] = good["wynik_mazowieckie.zip"]
        with mock.patch.object(config, "PL_WOJEWODZTWA", ["mazowieckie", "nera"]), \
                mock.patch.object(pl, "download", fake_download), \
                mock.patch.object(pl, "select_file", lambda p, s, t=None: seen.append(s) or real_select(p, s, t)), quiet():
            pl.fetch_items(self.con, "2026-10-01", TODAY)
        self.assertEqual(seen[:2], ["2026-10-01", SINCE])
        self.assertEqual(db.get_states(self.con, pl.FAILED), {})
        del good["wynik_nera.zip"]
        with mock.patch.object(config, "PL_WOJEWODZTWA", ["nera"]), mock.patch.object(config, "PL_ZGLOSZENIA", None), \
                mock.patch.object(pl, "download", fake_download), quiet(), self.assertRaises(saltiniai.SourceError):
            pl.fetch_items(self.con, SINCE, TODAY)

    def test_investor_names(self):
        organizations = [
            "DEMO Deweloper Sp. z o.o.", "ABC Spółka z o.o.", "XYZ SPÓŁKA Z O. O.", "ROCON Investment Sp. z.o.o.",
            "Budimex SA", "Gmina Krapkowice", "Miasto Stołeczne Warszawa", "Zarząd Powiatu Strzeleckiego",
            "Generalna Dyrekcja Dróg Krajowych i Autostrad", "Ochotnicza Straż Pożarna w Lipnie",
            "Wojewódzkie Pogotowie Ratunkowe w Katowicach", "Narodowy Instytut Kardiologii", "Bank Spółdzielczy w Brzegu",
            "Szkoła Podstawowa nr 5 w Opolu", "Szpital Wojewódzki w Opolu", "Miejski Ośrodek Sportu i Rekreacji",
            "Parafia Rzymskokatolicka", "Wspólnota Mieszkaniowa ul. Polna 5", "Akademia Wychowania Fizycznego"]
        persons = [
            "Katarzyna Jaśkowska", "Jakub Wojewódzki", "Wojewódzki Jakub", "Jan Parafiniuk", "Anna Miastkowska",
            "Marek Komendarek", "Tomasz Szkołuda", "Jan Kowalski, Anna Nowak spółka cywilna",
            "Klimatest Trzynadlowski i Wspólnicy Sp.J.", "Zakład Usług Budowlanych Adam Ciepichał",
            "Niepubliczne Przedszkole Bajka Agnieszka Kowalska", "Sylwia, Rafał Wiczkowscy",
            "Margum Rembler Usługi Transportowe Mariusz Kot"]
        for name in organizations:
            with self.subTest(name=name):
                self.assertEqual(pl.organization(name), name)
        for name in persons:
            with self.subTest(name=name):
                self.assertIsNone(pl.organization(name))

    def test_objection_is_excluded(self):
        self.assertTrue(pl.is_excluded([{"status": "Wniesiono sprzeciw"}]))
        self.assertFalse(pl.is_excluded([{"status": "Brak sprzeciwu"}]))


class EstoniaTest(SourceTestCase):
    code = "EE"

    def test_buildings_to_signals(self):
        items, sig = self.load()
        # „Realiseerimata“ atmetamas, o seniai statomas pastatas pirmą kartą tik įsimenamas
        self.assertEqual(len(items), len(generate_demo.EE_BUILDINGS) - 2)
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

    def test_status_change_is_event_and_touch_is_not(self):
        self.load()
        path = self.files["EE"][0]
        with open(path, encoding="utf-8", newline="") as fh:
            rows = list(csv.reader(fh, delimiter=";"))
        head = rows[0]
        st, upd, addr = head.index("seisund"), head.index("date_updated"), head.index("taisaadress")
        later = TODAY + timedelta(days=7)
        for r in rows[1:]:
            if r[addr].endswith("Tulika tn 19"):
                r[st], r[upd] = "EHITIS_SEISUND_PYSTI", f"{later} 09:00:00"          # Kavandatav -> Püstitamisel
            if r[addr].endswith("Pargi tee 7"):
                r[upd] = f"{later} 09:00:00"                                         # tik atnaujintas įrašas
        with open(path, "w", encoding="utf-8", newline="") as fh:
            csv.writer(fh, delimiter=";").writerows(rows)
        items = ee.read_files(self.con, [path], (later - timedelta(days=7)).isoformat(), later)
        self.assertEqual([r["taisaadress"].rsplit(", ", 1)[-1] for _, _, _, r in items], ["Tulika tn 19"])
        self.assertTrue(items[0][0].endswith(":ehitis-seisund-pysti"))

    def test_terminated_building_removes_signals(self):
        _, sig = self.load()
        for s in sig.values():
            db.upsert_signal(self.con, s)
        self.con.commit()
        path = self.files["EE"][0]
        with open(path, encoding="utf-8", newline="") as fh:
            rows = list(csv.reader(fh, delimiter=";"))
        st, addr = rows[0].index("seisund"), rows[0].index("taisaadress")
        target = next(r for r in rows[1:] if r[addr].endswith("Tulika tn 19"))
        target[st] = "EHITIS_SEISUND_REATA"
        with open(path, "w", encoding="utf-8", newline="") as fh:
            csv.writer(fh, delimiter=";").writerows(rows)
        ee.read_files(self.con, [path], SINCE, TODAY)
        left = [r[0] for r in self.con.execute("SELECT signal_id FROM signals WHERE signal_id LIKE 'EE:%'")]
        self.assertFalse([x for x in left if x.startswith(f"EE:{target[rows[0].index('ehr_kood')]}:")])
        self.assertEqual(len(left), len(sig) - 1)

    def test_several_reports_are_merged(self):
        path = self.files["EE"][0]
        with open(path, encoding="utf-8", newline="") as fh:
            lines = fh.read().splitlines()
        a, b = self.tmp.file("a.csv"), self.tmp.file("b.csv")
        with open(a, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines[:4]) + "\n")
        with open(b, "w", encoding="utf-8") as fh:
            fh.write("\n".join([lines[0]] + lines[4:]) + "\n")
        items = ee.read_files(self.con, [a, b, self.files["EE"][1]], SINCE, TODAY)
        self.assertEqual(len(items), len(generate_demo.EE_BUILDINGS) - 2)

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



def _ee_building(code, status, kaos="11221", name="Muu kolme või enama korteriga elamu", x="6589026.6",
                 y="542295.3"):
    return {"ehitis": {
        "ehitiseAndmed": {"ehrKood": code, "seisund": status, "seisundTxt": "", "kaosIdPeamine": kaos,
                          "kaosKood": kaos, "kaosIdTxt": name, "nimetus": name, "rajatisHoone": "H",
                          "taisaadress": f"Harju maakond, Tallinn, Testi tn {code[-2:]}", "verTekkAeg": "2026-10-01"},
        "ehitisePohiandmed": {"maakond": "37", "omavalitsus": "784", "ehAlustKp": None, "kavKasutusKp": None},
        "ehitiseKujud": {"ruumikuju": [{"viitepunktX": x, "viitepunktY": y}]},
    }}


class EstoniaApiTest(unittest.TestCase):
    """Viešas EHR statinių API su netikrais atsakymais (be tinklo)."""

    def setUp(self):
        self.tmp = TempDir()
        self.addCleanup(self.tmp.cleanup)
        self.con = db.connect(self.tmp.file("t.sqlite"))
        self.addCleanup(self.con.close)
        self.calls = []
        self.feed = [[{"ehr_kood": "101", "timestamp": "2026-10-01T10:00:00"},
                      {"ehr_kood": "102", "timestamp": "2026-10-01T11:00:00"},
                      {"ehr_kood": "103", "timestamp": "2026-10-02T09:00:00"}],
                     [{"ehr_kood": "104", "timestamp": "2026-10-03T09:00:00"},
                      {"ehr_kood": "101", "timestamp": "2026-10-04T09:00:00"}]]
        self.feed_starts, self.limited = [], set()
        self.versions = {
            # statybos leidimas + senas dokumentas (iki since) + adresų pakeitimas (praleidžiamas)
            "101": [{"doku_id": "9001", "ver_nr": "2", "ver_tekk_aeg": "2026-10-01T00:00:00.000Z",
                     "doty_id": "12271", "dok_nr": "2612271/00001"},
                    {"doku_id": "8000", "ver_nr": "1", "ver_tekk_aeg": "2025-01-01T00:00:00.000Z",
                     "doty_id": "11802", "dok_nr": "PT-1"},
                    {"doku_id": "9002", "ver_nr": "3", "ver_tekk_aeg": "2026-10-04T00:00:00.000Z",
                     "doty_id": "11524", "dok_nr": ""}],
            "102": [{"doku_id": "9003", "ver_nr": "1", "ver_tekk_aeg": "2026-10-01T00:00:00.000Z",
                     "doty_id": "11524", "dok_nr": ""}],                     # tik adresas -> nieko
            "103": [{"doku_id": "9004", "ver_nr": "1", "ver_tekk_aeg": "2026-10-02T00:00:00.000Z",
                     "doty_id": "11201", "dok_nr": "2611201/7"}],              # statybos pranešimas, bet REATA
            "104": [{"doku_id": "9005", "ver_nr": "1", "ver_tekk_aeg": "2026-10-03T00:00:00.000Z",
                     "doty_id": "11581", "dok_nr": "2611581/3"}],
        }
        self.data = {"101": _ee_building("101", "EHITIS_SEISUND_KAVAN"),
                     "102": _ee_building("102", "EHITIS_SEISUND_OLEMA"),
                     "103": _ee_building("103", "EHITIS_SEISUND_REATA"),
                     "104": _ee_building("104", "EHITIS_SEISUND_PYSTI", kaos="12201", name="Büroohoone",
                                         x=None, y=None)}
        self.data["104"]["ehitis"]["ehitiseKujud"]["ruumikuju"][0]["geometry"] = {
            "type": "Polygon", "coordinates": [[[659370.0, 6474360.0], [659382.6, 6474370.6]]]}
        self.broken = set()
        p = mock.patch.object(ee, "_api_get", self.fake_get)
        p.start()
        self.addCleanup(p.stop)

    def fake_get(self, path, limiter, tries=4):
        self.calls.append(path)
        if path.startswith("find/ehrcodes/dateafter"):
            q = urllib.parse.parse_qs(path.split("?", 1)[1])
            ts, offset = q["timestamp"][0], int(q["offset"][0])
            self.feed_starts.append(ts)
            if self.feed is None:
                return None                                               # HTTP 404
            rows = [x for page in self.feed for x in page if x["timestamp"] >= ts]
            return rows[offset:offset + 2]                                # puslapiai po 2
        code = path.rsplit("=", 1)[1]
        if code in self.broken:
            raise saltiniai.SourceError(f"EHR API {path}: HTTP 503")
        if code in self.limited:
            raise ee.RateLimited("EHR riboja užklausas (HTTP 429)")
        if path.startswith("buildingVersions"):
            return self.versions.get(code)
        return self.data.get(code)

    def fetch(self, since=EE_SINCE):
        import sistema
        with quiet():
            items = ee.fetch_items(self.con, ee.resolve_since(self.con, since, TODAY), TODAY)
        db.insert_rows(self.con, "EE", items)
        sistema.build_signals(self.con)
        return items, {r["signal_id"]: dict(r) for r in self.con.execute("SELECT * FROM signals")}

    def test_documents_become_signals(self):
        items, sig = self.fetch()
        self.assertEqual(sorted(sig), ["EE:101:9001", "EE:104:9005"])
        permit, start = sig["EE:101:9001"], sig["EE:104:9005"]
        self.assertEqual((permit["signal_type"], permit["doc_date"]), ("leidimas_nauja", "2026-10-01"))
        self.assertEqual(permit["signal_label"], "EE: statybos leidimas")
        self.assertIn("2612271/00001", permit["doc_text"])
        self.assertEqual(permit["municipality"], "Tallinn")
        self.assertAlmostEqual(permit["lat"], 59.43696, places=4)
        self.assertEqual(permit["score"], 3 + 3)
        self.assertEqual(start["signal_type"], "pradzia")
        self.assertAlmostEqual(start["lat"], 58.38062, places=3)          # kontūro vidurkis
        self.assertIn("biur", start["purposes"])
        # buildingData neimamas statiniui be statybos dokumentų (102)
        self.assertNotIn("buildingData?ehr_code=102", self.calls)
        self.assertEqual(self.feed_starts, [f"{EE_SINCE}T00:00:00"] * 4)  # 3 puslapiai + tuščias
        self.assertEqual(db.get_states(self.con, ee.CURSOR), {"srautas": "2026-10-04T09:00:00"})

    def test_resolve_since_uses_cursor(self):
        self.assertEqual(ee.resolve_since(self.con, None, TODAY),
                         (TODAY - timedelta(days=config.EE_FIRST_RUN_DAYS)).isoformat())
        self.fetch()
        self.assertEqual(ee.resolve_since(self.con, None, TODAY), "2026-10-04T09:00:00")
        self.assertEqual(ee.resolve_since(self.con, "2026-09-01", TODAY), "2026-09-01")    # --since svarbiau
        # kitas paleidimas tęsia nuo žymės: naujas pokytis paimamas, senieji nekartojami
        self.feed.append([{"ehr_kood": "105", "timestamp": "2026-10-05T08:00:00"}])
        self.versions["105"] = [{"doku_id": "9100", "ver_nr": "1", "ver_tekk_aeg": "2026-10-05T00:00:00.000Z",
                                 "doty_id": "12271", "dok_nr": "LEIDIMAS-105"}]
        self.data["105"] = _ee_building("105", "EHITIS_SEISUND_KAVAN")
        self.calls.clear()
        items, _ = self.fetch(since=None)
        self.assertEqual(sorted(k for k, *_ in items), ["EE:101:9001", "EE:105:9100"])    # 101 – žymės laikas
        self.assertNotIn("buildingVersions?ehr_code=104", self.calls)

    def test_cancelled_known_building_removed(self):
        self.fetch()
        self.data["101"] = _ee_building("101", "EHITIS_SEISUND_REATA")
        self.versions["101"] = [{"doku_id": "9010", "ver_nr": "4", "ver_tekk_aeg": "2026-10-04T00:00:00.000Z",
                                 "doty_id": "11522", "dok_nr": ""}]            # registro pataisymas
        _, sig = self.fetch()
        self.assertEqual(sorted(sig), ["EE:104:9005"])
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM raw_records WHERE doc_nr LIKE 'EE:101:%'")
                         .fetchone()[0], 0)

    def test_failed_buildings_are_retried_next_time(self):
        self.broken = {"104"}
        with mock.patch.object(config, "EE_API_MAX_FAILED", 0.5):
            items, _ = self.fetch()                                       # 1 iš 4 – tęsiama
        self.assertEqual([k for k, *_ in items], ["EE:101:9001"])
        doc_since = (date.fromisoformat(EE_SINCE) - timedelta(days=3)).isoformat()
        self.assertEqual(db.get_states(self.con, ee.RETRY), {"104": f"{doc_since}|1"})
        # kitą kartą 104 pakartojamas, nors pokyčių sraute jo nebėra
        self.broken, self.feed = set(), []
        items, sig = self.fetch(since=None)
        self.assertEqual([k for k, *_ in items], ["EE:104:9005"])
        self.assertEqual(db.get_states(self.con, ee.RETRY), {})

    def test_rate_limit_saves_progress_and_resumes(self):
        self.limited = {"103"}                                            # 101, 102 apdoroti, 103 – 429
        with self.assertRaises(saltiniai.PartialSourceError) as cm:
            self.fetch()
        self.assertEqual([k for k, *_ in cm.exception.items], ["EE:101:9001"])
        self.assertEqual(db.get_states(self.con, ee.CURSOR)["srautas"], "2026-10-02T09:00:00")   # 103 laikas
        self.limited = set()
        items, sig = self.fetch(since=None)
        # 101 pasikeitė dar kartą po žymės, todėl tikrinamas iš naujo (bet naujas signalas neatsiranda)
        self.assertEqual(sorted(k for k, *_ in items), ["EE:101:9001", "EE:104:9005"])
        self.assertEqual(sorted(sig), ["EE:101:9001", "EE:104:9005"])
        self.assertIn("buildingVersions?ehr_code=103", self.calls)

    def test_outage_stops_early(self):
        self.broken = {"101", "102", "103", "104"}
        with mock.patch.object(config, "EE_API_MAX_FAILS_IN_ROW", 2), \
                self.assertRaisesRegex(saltiniai.PartialSourceError, "EHR neatsako: nepavyko 2 iš 2"):
            self.fetch()
        self.assertEqual(sum(1 for c in self.calls if c.startswith("buildingVersions")), 2)
        self.assertEqual(db.get_states(self.con, ee.CURSOR)["srautas"], "2026-10-02T09:00:00")

    def test_feed_404_is_an_error(self):
        self.feed = None
        with self.assertRaisesRegex(saltiniai.SourceError, "404"):
            self.fetch()

    def test_building_limit_per_run(self):
        with mock.patch.object(config, "EE_API_MAX_BUILDINGS", 2):
            items, _ = self.fetch()
        self.assertEqual([k for k, *_ in items], ["EE:101:9001"])         # 101, 102
        self.assertEqual(db.get_states(self.con, ee.CURSOR)["srautas"], "2026-10-02T09:00:00")
        self.assertEqual(len(self.feed_starts), 2)                      # srautas toliau neskaitomas
        items, _ = self.fetch(since=None)
        self.assertEqual(sorted(k for k, *_ in items), ["EE:101:9001", "EE:104:9005"])
        self.assertEqual(db.get_states(self.con, ee.CURSOR), {"srautas": "2026-10-04T09:00:00"})

    def test_deferred_building_keeps_wider_window(self):
        self.versions["104"][0]["ver_tekk_aeg"] = "2026-09-28T00:00:00.000Z"   # senesnis nei žymė - 3 d.
        with mock.patch.object(config, "EE_API_MAX_BUILDINGS", 3):
            items, _ = self.fetch()
        self.assertNotIn("EE:104:9005", [k for k, *_ in items])
        self.assertEqual(db.get_states(self.con, ee.CURSOR)["srautas"], "2026-10-03T09:00:00")
        items, _ = self.fetch(since=None)
        self.assertIn("EE:104:9005", [k for k, *_ in items])
        self.assertNotIn("dokumentai_nuo", db.get_states(self.con, ee.CURSOR))     # viskas apdorota

    def test_retry_window_kept_when_building_is_in_feed_again(self):
        self.versions["104"][0]["ver_tekk_aeg"] = "2026-09-28T00:00:00.000Z"
        self.broken = {"104"}
        with mock.patch.object(config, "EE_API_MAX_FAILED", 0.5):
            self.fetch()
        self.broken = set()
        self.feed.append([{"ehr_kood": "104", "timestamp": "2026-10-05T08:00:00"}])   # 104 vėl pasikeitė
        items, _ = self.fetch(since=None)
        self.assertIn("EE:104:9005", [k for k, *_ in items])

    def test_retries_come_after_feed_and_expire(self):
        self.broken = {"104"}
        with mock.patch.object(config, "EE_API_MAX_FAILED", 0.5), mock.patch.object(config, "EE_API_RETRY_TIMES", 2):
            self.fetch()
            self.feed.append([{"ehr_kood": "106", "timestamp": "2026-10-05T08:00:00"}])
            self.calls.clear()
            self.fetch(since=None)
            versions = [c for c in self.calls if c.startswith("buildingVersions")]
            self.assertEqual(versions[-1], "buildingVersions?ehr_code=104")         # pakartojimas – paskutinis
            self.assertEqual(db.get_states(self.con, ee.RETRY), {"104": f"{(date.fromisoformat(EE_SINCE) - timedelta(days=3)).isoformat()}|2"})
            with quiet():
                self.fetch(since=None)
        self.assertEqual(db.get_states(self.con, ee.RETRY), {})                     # po 2 kartų nebekartojamas

    def test_facilities_skipped_by_default(self):
        self.feed = [[{"ehr_kood": "221532379", "timestamp": "2026-10-01T10:00:00"}]]
        self.versions["221532379"] = self.versions["104"]
        self.data["221532379"] = _ee_building("221532379", "EHITIS_SEISUND_PYSTI")
        self.assertEqual(self.fetch()[0], [])
        self.assertFalse([c for c in self.calls if "221532379" in c])
        with mock.patch.object(config, "EE_RAJATISED", True):
            self.assertEqual(len(self.fetch()[0]), 1)

    def test_limiter_slows_down_and_recovers(self):
        limiter = ee._Limiter(1, max_429=2)
        limiter.too_many(0)
        limiter.too_many(0)
        self.assertEqual(limiter.gap, 4.0)                                # sulėtėjo
        for _ in range(40):
            limiter.success()
        self.assertEqual(limiter.gap, 1.0)                                # atsigavo
        with self.assertRaises(ee.RateLimited):
            limiter.too_many(0)

    def test_retry_on_429(self):
        p = mock.patch.object(ee, "_api_get", ORIGINAL_API_GET)
        p.start()
        self.addCleanup(p.stop)
        import io
        import urllib.error
        answers = [urllib.error.HTTPError("u", 429, "Too Many Requests", {}, io.BytesIO(b""))]

        class Resp(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def urlopen(req, timeout=None):
            if answers:
                raise answers.pop(0)
            return Resp(b'[{"doku_id": "1"}]')

        sleeps = []
        with mock.patch("urllib.request.urlopen", urlopen), mock.patch.object(ee.time, "sleep", sleeps.append):
            limiter = ee._Limiter(1000)
            self.assertEqual(ee._api_get("buildingVersions?ehr_code=1", limiter), [{"doku_id": "1"}])
            answers.append(urllib.error.HTTPError("u", 404, "Not Found", {}, io.BytesIO(b"")))
            self.assertIsNone(ee._api_get("buildingData?ehr_code=1", limiter))
        self.assertTrue(sleeps and max(sleeps) >= 4)                      # po 429 palaukta

    def test_doc_events(self):
        ev = ee.doc_events(self.versions["101"] + self.versions["101"][:1], "2026-09-30")
        self.assertEqual([(e[0], e[1]) for e in ev], [("9001", "leidimas_nauja")])


class LithuaniaSourceTest(unittest.TestCase):
    def test_lt_wrapper(self):
        rows = generate_demo.generate(TODAY)["rows"]
        doc = rows[0]["dokumento_reg_nr"]
        s = saltiniai.get("LT").build_signal(doc, [r for r in rows if r["dokumento_reg_nr"] == doc])
        self.assertEqual((s["country"], s["signal_id"]), ("LT", doc))
        self.assertTrue(os.path.basename(saltiniai.get("lt").__file__).startswith("lt"))


if __name__ == "__main__":
    unittest.main()

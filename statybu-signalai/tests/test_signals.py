# -*- coding: utf-8 -*-
"""Lietuvos (Infostatybos) įrašų pavertimas signalais."""
import os
import unittest

import config
import db
import signals
import sistema
from tests import TempDir


def row(doc, **kw):
    r = {
        "uuid": kw.pop("uuid", f"{doc}-{kw.get('statinio_id', 1)}"),
        "dokumento_reg_nr": doc,
        "dokumento_reg_data": "2026-09-21",
        # kaip tikruose duomenyse: pavadinimas – dokumento_kategorija, dok_irasas – tik „aktas“/„prasymas“
        "dok_tipo_kodas": "LSNS",
        "dokumento_kategorija": "Leidimas statyti naują (- us) statinį (- ius)",
        "dok_irasas": "aktas",
        "dok_statusas": "Galiojantis",
        "statinio_paskirtis": "Gyvenamoji (trijų ir daugiau butų - daugiabučiai pastatai)",
        "statinio_kategorija": "Neypatingasis",
        "statinio_pavadinimas": "Daugiabutis gyvenamasis namas",
        "adresas": "Vilnius, Ozo g. 25",
        "taskas_wgs": "POINT (54.7155 25.2790)",
    }
    r.update(kw)
    return r


class ClassifyTest(unittest.TestCase):
    def test_handoff_examples(self):
        # abu HANDOFF.md pavyzdžiai – statybos užbaigimo dokumentai
        self.assertEqual(signals.classify(
            "Deklaracija apie statybos užbaigimą / paskirties keitimą (tvirtina VTPSI)")[0], "uzbaigimas")
        self.assertEqual(signals.classify(
            "Pažyma apie statinio statybą be nukrypimų nuo esminių statinio projekto sprendinių "
            "(tvirtina ekspertas)")[0], "uzbaigimas")

    def test_all_types(self):
        cases = {
            "Prašymas išduoti statybą leidžiantį dokumentą": "prasymas",
            "Prašymas išduoti leidimą statyti naują statinį": "prasymas",
            "Leidimas statyti naują (-us) statinį (-ius) (tvirtina savivaldybė)": "leidimas_nauja",
            "Leidimas rekonstruoti statinį (-ius)": "leidimas_rekonstrukcija",
            "Leidimas atnaujinti (modernizuoti) pastatą (-us)": "leidimas_atnaujinimas",
            "Leidimas pakeisti statinio (patalpos) paskirtį (tvirtina savivaldybė)": "paskirties_keitimas",
            "Rašytinis pritarimas statinio projektui": "pritarimas",
            "Leidimas griauti statinį": "griovimas",
            "Pranešimas apie statybos pradžią": "pradzia",
            "Statybos užbaigimo aktas (tvirtina VTPSI)": "uzbaigimas",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(signals.classify(text)[0], expected)

    def test_case_insensitive_and_unknown(self):
        self.assertEqual(signals.classify("LEIDIMAS STATYTI NAUJĄ STATINĮ")[0], "leidimas_nauja")
        self.assertEqual(signals.classify("Statinio projekto ekspertizės aktas"), ("kita", "Kita"))
        self.assertEqual(signals.classify(None), ("kita", "Kita"))
        self.assertEqual(signals.classify(""), ("kita", "Kita"))

    def test_label_comes_from_config(self):
        labels = {code: label for code, label, _ in config.SIGNAL_RULES}
        self.assertEqual(signals.classify("Leidimas griauti statinį")[1], labels["griovimas"])


class DocTypeTest(unittest.TestCase):
    """Tipas pagal dokumento kodą (dok_tipo_kodas arba numerio pradžią), atsarginis – pagal pavadinimą."""

    def test_by_code(self):
        cases = {"SRA": "prasymas", "LSNS": "leidimas_nauja", "LRS": "leidimas_rekonstrukcija",
                 "LAP": "leidimas_atnaujinimas", "LSKR": "leidimas_atnaujinimas", "LPSP": "paskirties_keitimas",
                 "LGS": "griovimas", "ANN2": "pradzia", "ARCCR": "uzbaigimas", "ACUB2": "uzbaigimas",
                 "ISP": "prasymas"}
        for code, expected in cases.items():
            with self.subTest(code=code):
                self.assertEqual(signals.doc_type({"dok_tipo_kodas": code, "dok_irasas": "aktas"})[0], expected)

    def test_code_from_number_and_ignored_codes(self):
        self.assertEqual(signals.doc_code({"dokumento_reg_nr": "LSNS-21-261002-00834"}), "LSNS")
        self.assertEqual(signals.doc_type({"dokumento_reg_nr": "lrs-01-261002-00001"})[0], "leidimas_rekonstrukcija")
        for code in ("PEKA", "SRD", "PNUR", "CCA", "PKLA"):            # patikrinimai, reikalavimai, nurodymai
            with self.subTest(code=code):
                self.assertIsNone(signals.doc_type({"dok_tipo_kodas": code})[0])
                self.assertTrue(signals.is_excluded([row(f"{code}-01-261002-1", dok_tipo_kodas=code)]))

    def test_new_codes_and_inspection_acts(self):
        for code in ("DEKRP", "ACCRC", "PSTER", "CSBP", "BCPPA"):
            with self.subTest(code=code):
                self.assertIsNone(signals.doc_type({"dok_tipo_kodas": code, "dok_irasas": "prasymas"})[0])
        self.assertEqual(signals.doc_type({"dok_tipo_kodas": "ACDUB"})[0], "griovimas")
        title = "Deklaracijos apie statybos užbaigimą (tik registruojamos) patikrinimo aktas"
        self.assertIsNone(signals.doc_type({"dok_tipo_kodas": "NAUJAS", "dokumento_kategorija": title})[0])

    def test_unknown_code_uses_title(self):
        r = {"dok_tipo_kodas": "NAUJAS", "dokumento_kategorija": "Leidimas statyti naują (- us) statinį (- ius)"}
        self.assertEqual(signals.doc_type(r)[0], "leidimas_nauja")
        self.assertEqual(signals.doc_type({"dok_tipo_kodas": "NAUJAS", "dok_irasas": "prasymas"})[0], "prasymas")
        self.assertEqual(signals.doc_type({"dok_tipo_kodas": "NAUJAS", "dokumento_kategorija": "Kažkas"}),
                         ("kita", "Kažkas"))

    def test_real_statuses(self):
        for st in ("Atmestas", "Atmesta", "Nepatenkintas", "Negaliojanti", "Neišduotas", "Nutrauktas",
                   "Paslėptas/ištrintas", "Pasiūlymams nepritarta"):
            with self.subTest(st=st):
                self.assertTrue(signals.is_excluded([row("SRA-01-1", dok_tipo_kodas="SRA", dok_statusas=st)]))
        for st in ("Užregistruotas", "Tikrinamas projektas", "Priimtas", "Patenkintas", "Galiojantis", None):
            with self.subTest(st=st):
                self.assertFalse(signals.is_excluded([row("SRA-01-1", dok_tipo_kodas="SRA", dok_statusas=st)]))


class WgsPointTest(unittest.TestCase):
    def test_lat_first(self):
        self.assertEqual(signals.wgs_point("POINT (54.6750273775 25.2213355541)"), (54.6750273775, 25.2213355541))

    def test_lon_first(self):
        self.assertEqual(signals.wgs_point("POINT (25.2213355541 54.6750273775)"), (54.6750273775, 25.2213355541))

    def test_invalid(self):
        for value in (None, "", "POINT EMPTY", "POINT (40.0 10.0)", "POINT (6060527 578771)", "54.67"):
            with self.subTest(value=value):
                self.assertEqual(signals.wgs_point(value), (None, None))


class MunicipalityTest(unittest.TestCase):
    def test_forms(self):
        cases = {
            "Vilniaus m. sav., Vilniaus m., Gedimino pr. 1": "Vilniaus m. sav.",
            "Kauno r. sav., Garliavos m., Vytauto g. 5": "Kauno r. sav.",
            "Kauno rajono sav. Garliavos sen.": "Kauno r. sav.",
            "Šiaulių m. sav., Šiaulių m., Tilžės g. 1": "Šiaulių m. sav.",
            "Klaipėdos r. sav., Gargždų m.": "Klaipėdos r. sav.",
            "Birštono sav., Birštono m.": "Birštono sav.",
        }
        for address, expected in cases.items():
            with self.subTest(address=address):
                self.assertEqual(signals.municipality(address), expected)

    def test_from_document_number(self):
        self.assertEqual(signals.municipality_from_doc("LSNS-21-261002-00834"), "Kauno m. sav.")
        self.assertEqual(signals.municipality_from_doc("SRA-43-260510-00025"), "Kazlų Rūdos sav.")
        self.assertEqual(signals.municipality_from_doc("ANN2-00-260930-03872"), "")    # ne savivaldybė
        self.assertEqual(signals.municipality_from_doc("X"), "")
        self.assertEqual(len(set(config.LT_SAV_BY_DOC_CODE.values())), 60)
        # miesto adrese savivaldybės nėra – ji imama iš dokumento numerio
        s = signals.build_signal("LSNS-21-261002-1", [row("LSNS-21-261002-1", adresas="Kaunas, Laisvės al. 1")])
        self.assertEqual(s["municipality"], "Kauno m. sav.")
        s = signals.build_signal("ANN2-00-261002-1", [row("ANN2-00-261002-1", dok_tipo_kodas="ANN2",
                                                          adresas="Kauno r. sav., Garliavos m., Vytauto g. 5")])
        self.assertEqual((s["municipality"], s["signal_type"]), ("Kauno r. sav.", "pradzia"))

    def test_missing(self):
        self.assertEqual(signals.municipality(""), "")
        self.assertEqual(signals.municipality(None), "")
        self.assertEqual(signals.municipality("Gedimino pr. 1, Vilnius"), "")
        self.assertEqual(signals.municipality("Vilnius, Kaimynų g. 120"), "Vilniaus m. sav.")
        self.assertEqual(signals.municipality("KAUNAS, Laisvės al. 1"), "Kauno m. sav.")
        self.assertEqual(signals.municipality("Kaunas"), "Kauno m. sav.")
        self.assertEqual(signals.municipality("Neringa, Pervalkos g. 12"), "Neringos sav.")
        s = signals.build_signal("ACCR2-00-261001-1", [row("ACCR2-00-261001-1", dok_tipo_kodas="ACCR2",
                                                           adresas="Neringa, Pamario g. 46")])
        self.assertEqual(s["municipality"], "Neringos sav.")


class BuildSignalTest(unittest.TestCase):
    def test_groups_objects_of_one_document(self):
        rows = [
            row("LSNS-1", statinio_id=1, taskas_wgs="", statinio_kategorija="Ypatingasis statinys"),
            row("LSNS-1", statinio_id=2, taskas_wgs="POINT (25.28 54.72)"),
            row("LSNS-1", statinio_id=3, statinio_pavadinimas="Inžineriniai tinklai",
                statinio_paskirtis="Inžineriniai tinklai", statinio_kategorija="Nesudėtingasis statinys (II grupės)"),
            row("LSNS-1", statinio_id=3, uuid="dublikatas", statinio_pavadinimas="Inžineriniai tinklai",
                statinio_paskirtis="Inžineriniai tinklai"),
        ]
        s = signals.build_signal("LSNS-1", rows)
        self.assertEqual(s["signal_type"], "leidimas_nauja")
        self.assertEqual(s["object_count"], 3)                       # statinio_id 3 kartojasi
        self.assertEqual(s["category"], "Ypatingasis statinys")      # svarbiausia kategorija
        self.assertEqual(s["purposes"],
                         "Gyvenamoji (trijų ir daugiau butų - daugiabučiai pastatai); Inžineriniai tinklai")
        self.assertEqual((s["lat"], s["lon"]), (54.72, 25.28))       # pirmas turimas taškas, bet kokia tvarka
        self.assertEqual(s["municipality"], "Vilniaus m. sav.")
        # tipas 3 + daugiabutis 3 + ypatingasis 2 + >=3 statiniai 1
        self.assertEqual(s["score"], 9)

    def test_new_purpose_and_object_name_limit(self):
        rows = [row("LPP-1", statinio_id=i, statinio_pavadinimas=f"Statinys {i}",
                    statinio_pakeista_paskirtis="Administracinė") for i in range(7)]
        s = signals.build_signal("LPP-1", rows)
        self.assertEqual(s["purposes"], "Administracinė")
        self.assertTrue(s["object_names"].endswith("(+2)"))

    def test_score_parts(self):
        self.assertEqual(signals.score("prasymas", ["Sandėliavimo"], "Neypatingasis statinys", 1), 3 + 2 + 1)
        # pagalbinis pastatas su nesudėtinguoju: 1 - 1 - 1
        self.assertEqual(signals.score("uzbaigimas", ["Pagalbinio ūkio"], "Nesudėtingasis statinys (I grupės)", 1), -1)
        # tinklai prie namo balo nemažina (vertinamas vertingiausias statinys)
        house_with_networks = ["Gyvenamasis (vieno buto) pastatas", "Inžineriniai tinklai"]
        self.assertEqual(signals.score("leidimas_nauja", house_with_networks, "Neypatingasis statinys", 2), 3 + 0 + 1)
        self.assertEqual(signals.score("kita", [], "", 1), 0)

    def test_excluded(self):
        self.assertTrue(signals.is_excluded([row("X", dok_statusas="Panaikintas")]))
        self.assertTrue(signals.is_excluded([row("X"), row("X", dok_statusas="Negaliojantis")]))
        self.assertFalse(signals.is_excluded([row("X")]))


class BuildSignalsDbTest(unittest.TestCase):
    """Grupavimas per DB: build tik paveiktiems dokumentams, negaliojantys praleidžiami."""

    def setUp(self):
        self.tmp = TempDir()
        self.con = db.connect(os.path.join(self.tmp.path, "t.sqlite"))

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    def test_build_and_incremental(self):
        db.insert_raw(self.con, [row("A", statinio_id=1), row("A", statinio_id=2), row("B", statinio_id=1),
                                 row("C", statinio_id=1, dok_statusas="Panaikintas")], config.F)
        self.assertEqual(sorted(db.docs_to_build(self.con)), ["A", "B", "C"])
        st = sistema.build_signals(self.con, db.docs_to_build(self.con))
        self.assertEqual((st["nauji"], st["atmesti"]), (2, 1))
        self.assertEqual(self.con.execute("SELECT object_count FROM signals WHERE signal_id='A'").fetchone()[0], 2)
        # vėliau atsiradęs to paties dokumento statinys -> perskaičiuojamas tik A (negaliojantis C – ne)
        self.con.execute("UPDATE signals SET updated='2000-01-01 00:00:00'")
        self.con.execute("UPDATE raw_records SET first_seen='1999-01-01 00:00:00'")
        db.insert_raw(self.con, [row("A", statinio_id=3)], config.F)
        self.assertEqual(sorted(db.docs_to_build(self.con)), ["A"])
        st = sistema.build_signals(self.con, db.docs_to_build(self.con))
        self.assertEqual((st["nauji"], st["atnaujinti"]), (0, 1))
        self.assertEqual(self.con.execute("SELECT object_count FROM signals WHERE signal_id='A'").fetchone()[0], 3)

    def test_non_signal_documents_counted_separately(self):
        db.insert_raw(self.con, [row("SRD-01-261001-1", dok_tipo_kodas="SRD", statinio_id=1),
                                 row("LSNS-01-261001-2", statinio_id=1, dok_statusas="Negaliojantis")], config.F)
        st = sistema.build_signals(self.con, db.docs_to_build(self.con))
        self.assertEqual((st["ne_signalai"], st["atmesti"]), (1, 1))
        self.con.execute("UPDATE raw_records SET first_seen='1999-01-01 00:00:00'")   # vėlesnis paleidimas
        self.assertEqual(db.docs_to_build(self.con), [])                 # kitą kartą nebetikrinami

    def test_cancelled_document_removes_signal(self):
        db.insert_raw(self.con, [row("A", statinio_id=1)], config.F)
        sistema.build_signals(self.con)
        db.insert_raw(self.con, [row("A", statinio_id=2, dok_statusas="Panaikintas")], config.F)
        st = sistema.build_signals(self.con)
        self.assertEqual(st["pasalinti"], 1)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM signals").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()

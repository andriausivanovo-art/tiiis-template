# -*- coding: utf-8 -*-
"""Įmonių duomenų (JAR, Sodra) stulpelių atpažinimas ir įkėlimas, builders.csv."""
import os
import unittest
import zipfile

import db
import enrich
from tests import TempDir, quiet

JAR_HEADERS = ["ja_kodas", "ja_pavadinimas", "adresas", "ja_reg_data", "form_kodas", "form_pavadinimas",
               "stat_kodas", "stat_pavadinimas", "stat_data_nuo", "formavimo_data"]
SODRA_HEADERS = ["Draudėjo kodas (code)", "Juridinių asmenų registro kodas (jarCode)", "Pavadinimas (name)",
                 "Savivaldybė, kurioje registruota(municipality)", "Ekonominės veiklos rūšies kodas(ecoActCode)",
                 "Ekonominės veiklos rūšies pavadinimas(ecoActName)", "Mėnuo (month)",
                 "Vidutinis darbo užmokestis (avgWage)", "Apdraustųjų skaičius (numInsured)",
                 "Vidutinis darbo užmokestis II (avgWage2)", "Apdraustųjų skaičius II (numInsured2)"]


class MapColumnsTest(unittest.TestCase):
    def test_jar(self):
        m = enrich._map_columns(JAR_HEADERS)
        self.assertEqual(m, {"code": "ja_kodas", "name": "ja_pavadinimas", "legal_form": "form_pavadinimas",
                             "status": "stat_pavadinimas"})

    def test_sodra_lithuanian_headers(self):
        m = enrich._map_columns(SODRA_HEADERS)
        self.assertEqual(m["code"], "Juridinių asmenų registro kodas (jarCode)")   # ne „Draudėjo kodas“
        self.assertEqual(m["name"], "Pavadinimas (name)")
        self.assertEqual(m["nace"], "Ekonominės veiklos rūšies kodas(ecoActCode)")
        self.assertEqual(m["nace_name"], "Ekonominės veiklos rūšies pavadinimas(ecoActName)")
        self.assertEqual(m["municipality"], "Savivaldybė, kurioje registruota(municipality)")
        self.assertEqual(m["employees"], "Apdraustųjų skaičius (numInsured)")    # ne „II“ variantas
        self.assertEqual(m["avg_wage"], "Vidutinis darbo užmokestis (avgWage)")
        self.assertEqual(m["month"], "Mėnuo (month)")

    def test_sodra_english_headers(self):
        m = enrich._map_columns(["code", "jarCode", "name", "municipality", "ecoActCode", "ecoActName", "month",
                                 "avgWage", "numInsured"])
        self.assertEqual((m["code"], m["name"], m["employees"]), ("jarCode", "name", "numInsured"))

    def test_human_readable_jar(self):
        m = enrich._map_columns(["Juridinio asmens kodas", "Pavadinimas", "Teisinė forma", "Statusas"])
        self.assertEqual((m["code"], m["legal_form"], m["status"]),
                         ("Juridinio asmens kodas", "Teisinė forma", "Statusas"))


class LoadCompaniesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TempDir()
        self.con = db.connect(self.tmp.file("t.sqlite"))

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    def _sodra(self, path, encoding="utf-8"):
        lines = [";".join(SODRA_HEADERS[:9])]
        # dešimtainis kablelis ir kablelis antraštėje – csv.Sniffer čia suklystų
        lines += ["1;111111111;UAB A;Vilniaus m. sav.;412000;Statyba;202607;2100,50;10",
                  "1;111111111;UAB A;Vilniaus m. sav.;412000;Statyba;202608;2200,75;12",
                  "2;222222222;UAB B;Kauno m. sav.;681000;NT;202608;3000,00;4"]
        with open(path, "w", encoding=encoding) as fh:
            fh.write("\n".join(lines) + "\n")
        return path

    def test_sodra_keeps_latest_month(self):
        with quiet():
            n = enrich.load_companies(self.con, self._sodra(self.tmp.file("s.csv")))
        self.assertEqual(n, 2)
        r = self.con.execute("SELECT * FROM companies WHERE code='111111111'").fetchone()
        self.assertEqual((r["employees"], r["avg_wage"], r["data_month"]), (12, 2200.75, "202608"))

    def test_only_codes_cp1257_and_zip(self):
        path = self._sodra(self.tmp.file("s.csv"), encoding="cp1257")
        zpath = self.tmp.file("s.zip")
        with zipfile.ZipFile(zpath, "w") as z:
            z.write(path, "sodra.csv")
        with quiet():
            n = enrich.load_companies(self.con, zpath, only_codes={"222222222"})
        self.assertEqual(n, 1)
        self.assertEqual(self.con.execute("SELECT name FROM companies").fetchone()[0], "UAB B")

    def test_jar_and_sodra_complement(self):
        jar = self.tmp.file("jar.csv")
        with open(jar, "w", encoding="utf-8") as fh:
            fh.write("|".join(JAR_HEADERS) + "\n")
            fh.write("111111111|UAB „A“|Vilnius|2010-01-01|310|Uždaroji akcinė bendrovė|0|"
                     "Teisinis statusas neįregistruotas|2010-01-01|2026-09-01\n")
        with quiet():
            enrich.load_companies(self.con, jar)
            enrich.load_companies(self.con, self._sodra(self.tmp.file("s.csv")))
        r = self.con.execute("SELECT * FROM companies WHERE code='111111111'").fetchone()
        self.assertEqual(r["legal_form"], "Uždaroji akcinė bendrovė")   # iš JAR
        self.assertEqual(r["employees"], 12)                            # iš Sodros

    def test_latvian_and_estonian_registers(self):
        lv = self.tmp.file("register.csv")      # LV UR: kabliataškis, UTF-8 be BOM
        with open(lv, "w", encoding="utf-8") as fh:
            fh.write("regcode;sepa;name;name_before_quotes;name_in_quotes;name_after_quotes;without_quotes;regtype;"
                     "regtype_text;type;type_text;registered;terminated;closed;address;index;addressid;region;city;"
                     "atvk;reregistration_term\n"
                     '40103741893;;SIA \"DEMO Būve\";SIA;DEMO Būve;;0;K;Komercreģistrs;SIA;'
                     "Sabiedrība ar ierobežotu atbildību;2013-12-02;;;Rīga, Brīvības iela 1;LV-1010;1;;Rīga;0001000;\n")
        ee = self.tmp.file("ettevotja.zip")     # EE: ZIP, UTF-8 su BOM, kabliataškis
        with zipfile.ZipFile(ee, "w") as z:
            z.writestr("ettevotja_rekvisiidid__lihtandmed.csv", (
                "\ufeffnimi;ariregistri_kood;ettevotja_oiguslik_vorm;ettevotja_oigusliku_vormi_alaliik;kmkr_nr;"
                "ettevotja_staatus;ettevotja_staatus_tekstina;ettevotja_esmakande_kpv;ettevotja_aadress;"
                "asukoht_ettevotja_aadressis;asukoha_ehak_kood;asukoha_ehak_tekstina\n"
                "DEMO Ehitus OÜ;01834351;Osaühing;;EE100;R;Registrisse kantud;01.02.2010;;;0784;Tallinn\n"
            ).encode("utf-8"))
        with quiet():
            self.assertEqual(enrich.load_companies(self.con, lv), 1)
            self.assertEqual(enrich.load_companies(self.con, ee, only_codes={"01834351"}), 1)
        r = self.con.execute("SELECT * FROM companies WHERE code='40103741893'").fetchone()
        self.assertEqual((r["name"], r["legal_form"]), ('SIA "DEMO Būve"', "Sabiedrība ar ierobežotu atbildību"))
        r = self.con.execute("SELECT * FROM companies WHERE code='01834351'").fetchone()   # nulis priekyje
        self.assertEqual((r["name"], r["status"], r["municipality"]), ("DEMO Ehitus OÜ", "Registrisse kantud", "Tallinn"))

    def test_missing_code_column(self):
        path = self.tmp.file("bad.csv")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("a;b\n1;2\n")
        with self.assertRaises(ValueError):
            enrich.load_companies(self.con, path)


class BuildersTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TempDir()
        self.con = db.connect(self.tmp.file("t.sqlite"))
        for sid in ("LSNS-1", "LSNS-2", "LSNS-3"):
            db.upsert_signal(self.con, {"signal_id": sid, "signal_type": "leidimas_nauja", "score": 1})
        self.con.commit()

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    def test_creates_file_and_applies(self):
        path = self.tmp.file("duomenys", "builders.csv")
        self.assertEqual(enrich.apply_builders(self.con, path), 0)
        self.assertTrue(os.path.exists(path))
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("LSNS-1;111111111;UAB A;\nLSNS-2;;Fizinis asmuo;BDAR\nLSNS-9;333;UAB nėra;\nLSNS-3;;;\n")
        self.assertEqual(enrich.apply_builders(self.con, path), 2)
        got = {r[0]: (r[1], r[2]) for r in self.con.execute("SELECT signal_id, builder_code, builder_name FROM signals")}
        self.assertEqual(got["LSNS-1"], ("111111111", "UAB A"))
        self.assertEqual(got["LSNS-2"], (None, "Fizinis asmuo"))
        self.assertEqual(got["LSNS-3"], (None, None))

    def test_delimiter_from_header(self):
        self.assertEqual(enrich._delimiter(";".join(SODRA_HEADERS) + "\n1;2"), ";")
        self.assertEqual(enrich._delimiter("|".join(JAR_HEADERS)), "|")
        self.assertEqual(enrich._delimiter("a,b,c"), ",")


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""Demonstraciniai „Infostatyba“ (SSVA, buv. VTPSI; rinkinys „Statinys“) įrašai.

Laukų pavadinimai tokie pat kaip data.gov.lt rinkinyje, todėl demonstracija eina tuo pačiu
keliu kaip tikri duomenys: raw_records -> signalai -> builders.csv -> JAR/Sodra -> ataskaita.
Objektai, adresai ir įmonės išgalvoti; įmonių pavadinimuose yra žodis „DEMO“.
Rezultatas priklauso tik nuo datos ir sėklos, todėl testai gauna tuos pačius duomenis.

Kitoms šalims (write_foreign_files) kuriami failai tokiais pat formatais, kokius skelbia
Latvijos BIS (data.gov.lv), Lenkijos GUNB ir Estijos EHR, todėl demonstracija tikrina ir jų skaitymą.

Atskirai galima sugeneruoti CSV tokiu formatu, kokį duoda data.gov.lt (importui išbandyti):
    python demo/generate_demo.py --csv duomenys/demo/statiniai.csv
"""
import argparse
import csv
import io
import math
import os
import random
import sys
import uuid
import zipfile
from datetime import date, timedelta

MODEL = "datasets/gov/ssva/infostatyba/Statinys"    # tas pats kaip config.MODEL
FIELDS = [
    "id", "projekto_id", "statinio_id", "projekto_pavadinimas", "projekto_reg_nr", "projekto_metai",
    "unikalus_numeris", "statinio_paskirtis", "statinio_pakeista_paskirtis", "statinio_kategorija", "adresas",
    "statybos_rusis", "statinio_pavadinimas", "pastatymo_metai", "kadastro_nr", "ploto_reg_tipas",
    "sklypo_reg_statusas", "dokumento_reg_nr", "dokumento_reg_data", "iraso_data",
    "dok_statusas", "dok_tipo_kodas", "dokumento_kategorija", "dok_irasas", "taskas_lks", "taskas_wgs", "uuid",
]

# Savivaldybės: pavadinimas adrese, kodas dokumento numeryje (kaip tikruose duomenyse), kadastro vietovės
# kodas, miestas vardininku (miestų adresuose savivaldybė nerašoma: „Vilnius, Ozo g. 25“)
MUNIS = {
    "VLN": ("Vilniaus m. sav.", "01", "0101", "Vilnius"),
    "VLR": ("Vilniaus r. sav.", "08", "4140", None),
    "KNM": ("Kauno m. sav.", "21", "1901", "Kaunas"),
    "KNR": ("Kauno r. sav.", "24", "5240", None),
    "KLR": ("Klaipėdos r. sav.", "34", "5540", None),
    "SLM": ("Šiaulių m. sav.", "61", "9101", "Šiauliai"),
    "PNM": ("Panevėžio m. sav.", "51", "6101", "Panevėžys"),
}

# Vietos: (savivaldybė, gyvenamoji vietovė, gatvė, platuma, ilguma)
PLACES = {
    "ozo": ("VLN", "Vilniaus m.", "Ozo g.", 54.7155, 25.2790),
    "konstitucijos": ("VLN", "Vilniaus m.", "Konstitucijos pr.", 54.6965, 25.2720),
    "savanoriu_v": ("VLN", "Vilniaus m.", "Savanorių pr.", 54.6705, 25.2430),
    "zirmunai": ("VLN", "Vilniaus m.", "Žirmūnų g.", 54.7120, 25.2975),
    "pylimo": ("VLN", "Vilniaus m.", "Pylimo g.", 54.6800, 25.2805),
    "pilaites": ("VLN", "Vilniaus m.", "Pilaitės pr.", 54.7085, 25.1840),
    "antakalnio": ("VLN", "Vilniaus m.", "Antakalnio g.", 54.7010, 25.3150),
    "ukmerges": ("VLN", "Vilniaus m.", "Ukmergės g.", 54.7240, 25.2330),
    "kirtimu": ("VLN", "Vilniaus m.", "Kirtimų g.", 54.6390, 25.2560),
    "gedimino": ("VLN", "Vilniaus m.", "Gedimino pr.", 54.6870, 25.2770),
    "riese": ("VLR", "Riešės k.", "Sodų g.", 54.7760, 25.1850),
    "pagiriai": ("VLR", "Pagirių k.", "Sandėlių g.", 54.6050, 25.2120),
    "avizieniai": ("VLR", "Avižienių k.", "Liepų g.", 54.7640, 25.2650),
    "nemencine": ("VLR", "Nemenčinės m.", "Vilniaus g.", 54.8480, 25.4790),
    "maisiagala": ("VLR", "Maišiagalos mstl.", "Pramonės g.", 54.8690, 25.0600),
    "silainiai": ("KNM", "Kauno m.", "Baltų pr.", 54.9265, 23.8700),
    "laisves": ("KNM", "Kauno m.", "Laisvės al.", 54.8975, 23.9150),
    "partizanu": ("KNM", "Kauno m.", "Partizanų g.", 54.9050, 23.9550),
    "raudondvario_pl": ("KNM", "Kauno m.", "Raudondvario pl.", 54.9150, 23.8600),
    "savanoriu_k": ("KNM", "Kauno m.", "Savanorių pr.", 54.9130, 23.9380),
    "taikos": ("KNM", "Kauno m.", "Taikos pr.", 54.9080, 23.9750),
    "veiveriu": ("KNM", "Kauno m.", "Veiverių g.", 54.8820, 23.8900),
    "domeikava": ("KNR", "Domeikavos k.", "Kauno g.", 54.9600, 23.9150),
    "karmelava": ("KNR", "Karmėlavos mstl.", "Liepų g.", 54.9680, 24.0600),
    "garliava": ("KNR", "Garliavos m.", "Vytauto g.", 54.8180, 23.8700),
    "raudondvaris": ("KNR", "Raudondvario mstl.", "Instruktorių g.", 54.9430, 23.7830),
    "akademija": ("KNR", "Akademijos mstl.", "Studentų g.", 54.8950, 23.8180),
    "slengiai": ("KLR", "Slengių k.", "Medelyno g.", 55.7350, 21.1950),
    "gargzdai": ("KLR", "Gargždų m.", "Klaipėdos g.", 55.7120, 21.4000),
    "kretingale": ("KLR", "Kretingalės mstl.", "Klaipėdos g.", 55.8360, 21.2350),
    "dovilai": ("KLR", "Dovilų mstl.", "Pramonės g.", 55.6400, 21.3050),
    "priekule": ("KLR", "Priekulės m.", "Klaipėdos g.", 55.5560, 21.3180),
    "tilzes": ("SLM", "Šiaulių m.", "Tilžės g.", 55.9290, 23.3100),
    "vilniaus_s": ("SLM", "Šiaulių m.", "Vilniaus g.", 55.9330, 23.3160),
    "pramones_s": ("SLM", "Šiaulių m.", "Pramonės g.", 55.9130, 23.2600),
    "lyros": ("SLM", "Šiaulių m.", "Lyros g.", 55.9480, 23.2950),
    "aido": ("SLM", "Šiaulių m.", "Aido g.", 55.9200, 23.3300),
    "klaipedos_p": ("PNM", "Panevėžio m.", "Klaipėdos g.", 55.7330, 24.3350),
    "pramones_p": ("PNM", "Panevėžio m.", "Pramonės g.", 55.7200, 24.3800),
    "smelynes": ("PNM", "Panevėžio m.", "Smėlynės g.", 55.7330, 24.3950),
    "respublikos": ("PNM", "Panevėžio m.", "Respublikos g.", 55.7350, 24.3550),
    "tiekimo": ("PNM", "Panevėžio m.", "Tiekimo g.", 55.7250, 24.3300),
}

# Statiniai: (pavadinimas, paskirtis, kategorija) – reikšmės tokios, kokios yra tikruose duomenyse
OBJECTS = {
    "daugiabutis": ("Daugiabutis gyvenamasis namas",
                    "Gyvenamoji (trijų ir daugiau butų - daugiabučiai pastatai)", "Ypatingasis"),
    "daugiabutis_n": ("Daugiabutis gyvenamasis namas",
                      "Gyvenamoji (trijų ir daugiau butų - daugiabučiai pastatai)", "Neypatingasis"),
    "vienbutis": ("Gyvenamasis namas", "Gyvenamoji (vieno buto pastatai)", "Neypatingasis"),
    "patalpa": ("Negyvenamoji patalpa", "Administracinė", "Neypatingasis"),
    "admin": ("Administracinis pastatas", "Administracinė", "Ypatingasis"),
    "prekyba": ("Prekybos centras", "Prekybos", "Ypatingasis"),
    "parduotuve": ("Parduotuvė", "Prekybos", "Neypatingasis"),
    "sandelis": ("Sandėlis", "Sandėliavimo", "Neypatingasis"),
    "logistika": ("Logistikos centras", "Sandėliavimo", "Ypatingasis"),
    "gamyba": ("Gamybos pastatas", "Gamybos, pramonės", "Ypatingasis"),
    "viesbutis": ("Viešbutis", "Viešbučių", "Ypatingasis"),
    "klinika": ("Klinika", "Gydymo", "Neypatingasis"),
    "ligonine": ("Ligoninės korpusas", "Gydymo", "Ypatingasis"),
    "mokykla": ("Mokykla", "Mokslo", "Ypatingasis"),
    "darzelis": ("Vaikų darželis", "Mokslo", "Neypatingasis"),
    "ukinis": ("Ūkinis pastatas", "Pagalbinio ūkio", "Nesudėtingasis"),
    "garazas": ("Garažas", "Garažų", "Nesudėtingasis"),
    "tinklai": ("Vandentiekio ir nuotekų tinklai", "Vandentiekio tinklų", "Neypatingasis"),
    "aikstele": ("Automobilių stovėjimo aikštelė", "Kiti inžineriniai statiniai", "Nesudėtingasis"),
}

# Dokumentai: (dok_tipo_kodas, dokumento_kategorija, dok_irasas, statybos rūšis, būsena) – kaip tikruose
# duomenyse: dok_irasas būna tik „prasymas“ arba „aktas“, o ANN2 neturi kategorijos pavadinimo.
DOC_TYPES = {
    "prasymas": ("SRA", "Prašymas išduoti statybą leidžiantį dokumentą", "prasymas", "Naujo statinio statyba",
                 "Užregistruotas"),
    "nauja": ("LSNS", "Leidimas statyti naują (- us) statinį (- ius)", "aktas", "Naujo statinio statyba",
              "Galiojantis"),
    "rekonstrukcija": ("LRS", "Leidimas rekonstruoti statinį (- ius)", "aktas", "Statinio rekonstravimas",
                       "Galiojantis"),
    "atnaujinimas": ("LAP", "Leidimas atnaujinti (modernizuoti) pastatą (- us)", "aktas",
                     "Statinio kapitalinis remontas", "Galiojantis"),
    "paskirtis": ("LPSP", "Leidimas pakeisti statinio (-ių) / patalpos (-ų) paskirtį", "aktas",
                  "Statybos darbai neatliekami arba statinio/patalpų paskirties keitimas", "Galiojantis"),
    "pritarimas": ("RPSP", "Rašytinis pritarimas statinio projektui", "aktas", "Statinio paprastasis remontas",
                   "Galiojantis"),
    "griovimas": ("LGS", "Leidimas nugriauti statinį (-ius)", "aktas", "Statinio griovimas", "Galiojantis"),
    "pradzia": ("ANN2", None, "prasymas", "Naujo statinio statyba", "Užregistruotas"),
    "uzb_aktas": ("ACCA", "Statybos užbaigimo aktas", "aktas", "Naujo statinio statyba", "Galiojantis"),
    "uzb_deklaracija": ("ARCCR", "Deklaracija apie statybos užbaigimą / paskirties keitimą (tik registruojama)",
                        "aktas", "Naujo statinio statyba", "Galiojantis"),
    "uzb_pazyma": ("ACUB2", "Pažyma apie statinio statybą be nukrypimų nuo esminių statinio projekto sprendinių "
                            "(tvirtina ekspertas)", "aktas", "Naujo statinio statyba", "Galiojantis"),
    "ekspertize": ("PEKA", "Projekto (jo dalies) ekspertizės aktas", "aktas", "Naujo statinio statyba",
                   "Galiojantis"),
}
# Šie dokumentai liečia jau esamus statinius: jie turi unikalų numerį ir pastatymo metus
EXISTING = {"rekonstrukcija", "atnaujinimas", "paskirtis", "pritarimas", "griovimas"}

# Įmonės: (kodas, pavadinimas, teisinė forma, EVRK kodas, EVRK pavadinimas, savivaldybė,
#          apdraustųjų sk. [ankstesnis mėn., paskutinis mėn.], vidutinis atlyginimas)
COMPANIES = {
    "busta": ("990000101", "UAB „DEMO Būstas“", "Uždaroji akcinė bendrovė", "412000",
              "Gyvenamųjų ir negyvenamųjų pastatų statyba", "Vilniaus m. sav.", (46, 48), 2410.55),
    "biurai": ("990000102", "UAB „DEMO Biurai“", "Uždaroji akcinė bendrovė", "681000",
               "Nuosavo nekilnojamojo turto pirkimas ir pardavimas", "Vilniaus m. sav.", (12, 12), 3120.10),
    "logistika": ("990000103", "UAB „DEMO Logistika“", "Uždaroji akcinė bendrovė", "521000",
                  "Sandėliavimas ir saugojimas", "Vilniaus r. sav.", (85, 91), 1870.40),
    "statyba": ("990000104", "UAB „DEMO Statyba“", "Uždaroji akcinė bendrovė", "412000",
                "Gyvenamųjų ir negyvenamųjų pastatų statyba", "Kauno m. sav.", (130, 127), 2050.00),
    "klinika": ("990000105", "VšĮ „DEMO Klinika“", "Viešoji įstaiga", "862100",
                "Bendrosios praktikos gydytojų veikla", "Kauno m. sav.", (34, 35), 2290.00),
    "namai": ("990000106", "UAB „DEMO Namai“", "Uždaroji akcinė bendrovė", "411000",
              "Statybos projektų vystymas", "Kauno r. sav.", (8, 9), 2650.00),
    "gamyba": ("990000107", "UAB „DEMO Gamyba“", "Uždaroji akcinė bendrovė", "251100",
               "Metalo konstrukcijų ir jų dalių gamyba", "Kauno r. sav.", (210, 214), 1780.25),
    "pajurio": ("990000108", "UAB „DEMO Pajūrio būstas“", "Uždaroji akcinė bendrovė", "411000",
                "Statybos projektų vystymas", "Klaipėdos r. sav.", (15, 16), 2230.00),
    "prekyba": ("990000109", "UAB „DEMO Prekyba“", "Uždaroji akcinė bendrovė", "471100",
                "Mažmeninė prekyba nespecializuotose parduotuvėse, kuriose vyrauja maistas, gėrimai ir tabakas",
                "Šiaulių m. sav.", (320, 318), 1450.75),
    "bendrija": ("990000110", "DNSB „DEMO Žirmūnai“", "Daugiabučio namo savininkų bendrija", "683200",
                 "Nekilnojamojo turto valdymas už atlygį arba pagal sutartį", "Vilniaus m. sav.", (1, 1), 980.00),
    "viesbutis": ("990000111", "UAB „DEMO Viešbučiai“", "Uždaroji akcinė bendrovė", "551000",
                  "Viešbučių ir panašių laikinų buveinių veikla", "Kauno m. sav.", (54, 58), 1520.00),
    "investicijos": ("990000112", "UAB „DEMO Investicijos“", "Uždaroji akcinė bendrovė", "681000",
                     "Nuosavo nekilnojamojo turto pirkimas ir pardavimas", "Panevėžio m. sav.", (5, 5), 3400.00),
    "sandeliai": ("990000113", "UAB „DEMO Sandėliai“", "Uždaroji akcinė bendrovė", "521000",
                  "Sandėliavimas ir saugojimas", "Klaipėdos r. sav.", (22, 24), 1690.00),
    # Šios dvi nėra statytojos: JAR/Sodros faile jų yra, bet `enrich` jų neįkelia (taupoma vieta)
    "langai": ("990000114", "UAB „DEMO Langai“", "Uždaroji akcinė bendrovė", "432900",
               "Kitų statybos įrenginių įrengimas", "Kauno m. sav.", (40, 41), 1910.00),
    "sildymas": ("990000115", "MB „DEMO Šildymas“", "Mažoji bendrija", "432200",
                 "Vandentiekio, šildymo ir oro kondicionavimo įrangos įrengimas", "Vilniaus m. sav.", (6, 6), 1650.00),
}
# Statytojai, kurių builders.csv įrašytas tik kodas: pavadinimą ataskaita paima iš JAR
CODE_ONLY = {"biurai", "namai", "investicijos"}

# (dokumentas, vieta, prieš kiek dienų, statytojas, statiniai, papildomai)
# statytojas: įmonės raktas, "fizinis" arba None (dar nenustatytas – pateks į paieškos eilę);
# statinys "a>Paskirtis" reiškia, kad paskirtis keičiama į nurodytą.
DOCS = [
    ("nauja", "ozo", 2, "busta", ["daugiabutis"] * 3 + ["tinklai", "aikstele"], None),
    ("prasymas", "konstitucijos", 1, "biurai", ["admin", "aikstele"], None),
    ("rekonstrukcija", "savanoriu_v", 5, None, ["admin", "garazas"], None),
    ("atnaujinimas", "zirmunai", 7, "bendrija", ["daugiabutis_n"], None),
    ("paskirtis", "pylimo", 4, "fizinis", ["patalpa>Gyvenamoji (butų)"], None),
    ("uzb_deklaracija", "pilaites", 3, None, ["vienbutis", "garazas"], None),
    ("pradzia", "antakalnio", 6, "viesbutis", ["viesbutis"], None),
    ("nauja", "ukmerges", 9, "prekyba", ["prekyba", "aikstele", "tinklai"], None),
    ("uzb_pazyma", "kirtimu", 8, "logistika", ["sandelis"], None),
    ("pritarimas", "gedimino", 10, None, ["admin"], None),
    ("nauja", "pilaites", 12, "busta", ["daugiabutis_n"],
     {"statusas": "Negaliojantis"}),
    ("prasymas", "pilaites", 11, None, ["mokykla", "tinklai"], None),
    ("ekspertize", "zirmunai", 3, None, ["daugiabutis"], None),
    ("nauja", "riese", 4, "fizinis", ["vienbutis", "ukinis"], None),
    ("nauja", "pagiriai", 6, "logistika", ["logistika", "aikstele"], None),
    ("prasymas", "avizieniai", 2, None, ["daugiabutis_n", "daugiabutis_n", "tinklai"], None),
    ("griovimas", "nemencine", 9, None, ["ukinis"], None),
    ("uzb_aktas", "maisiagala", 13, "gamyba", ["gamyba"], None),
    ("nauja", "silainiai", 1, "statyba", ["daugiabutis", "daugiabutis", "tinklai"], None),
    ("rekonstrukcija", "laisves", 5, "biurai", ["admin"], None),
    ("prasymas", "laisves", 3, "viesbutis", ["viesbutis", "tinklai"], {"rusis": "Statinio rekonstravimas"}),
    ("atnaujinimas", "partizanu", 8, None, ["daugiabutis_n"], None),
    ("paskirtis", "raudondvario_pl", 6, "investicijos", ["gamyba>Administracinė"], None),
    ("pradzia", "savanoriu_k", 10, "klinika", ["klinika"], None),
    ("uzb_deklaracija", "taikos", 4, None, ["parduotuve"], None),
    ("nauja", "veiveriu", 12, None, ["parduotuve", "aikstele"], None),
    ("nauja", "domeikava", 2, "namai", ["vienbutis"] * 4 + ["tinklai"], None),
    ("nauja", "karmelava", 5, "gamyba", ["gamyba", "sandelis"], None),
    ("prasymas", "garliava", 7, None, ["daugiabutis_n", "daugiabutis_n", "tinklai"], None),
    ("rekonstrukcija", "raudondvaris", 11, "fizinis", ["vienbutis", "ukinis"], None),
    ("uzb_pazyma", "akademija", 9, None, ["darzelis"], None),
    ("pritarimas", "akademija", 6, None, ["ukinis"], None),
    ("nauja", "slengiai", 3, "pajurio", ["daugiabutis_n", "daugiabutis_n", "tinklai"], None),
    ("prasymas", "gargzdai", 1, "sandeliai", ["logistika", "aikstele", "tinklai"], None),
    ("nauja", "kretingale", 8, "fizinis", ["vienbutis"], None),
    ("atnaujinimas", "gargzdai", 10, None, ["daugiabutis_n", "daugiabutis_n"], None),
    ("pradzia", "dovilai", 5, "gamyba", ["gamyba"], None),
    ("uzb_aktas", "priekule", 12, None, ["parduotuve"], None),
    ("nauja", "tilzes", 4, "prekyba", ["prekyba", "aikstele"], None),
    ("rekonstrukcija", "vilniaus_s", 9, None, ["mokykla"], None),
    ("prasymas", "pramones_s", 2, None, ["gamyba", "sandelis", "tinklai"], None),
    ("atnaujinimas", "lyros", 6, None, ["daugiabutis_n"] * 3, None),
    ("paskirtis", "aido", 11, "fizinis", ["patalpa>Gyvenamoji (butų)"], None),
    ("nauja", "klaipedos_p", 3, "investicijos", ["daugiabutis_n", "daugiabutis_n"], None),
    ("prasymas", "pramones_p", 5, None, ["sandelis", "aikstele"], None),
    ("rekonstrukcija", "smelynes", 7, "klinika", ["ligonine"], None),
    ("uzb_deklaracija", "respublikos", 10, None, ["admin"], None),
    ("pradzia", "tiekimo", 13, "prekyba", ["parduotuve", "aikstele"], None),
]


def wgs_to_lks(lat, lon):
    """WGS84 -> LKS-94 (Transverse Mercator, GRS80, 24° ilguma, mastelis 0,9998). Grąžina (šiaurė, rytai)."""
    a, f, k0, lon0, fe = 6378137.0, 1 / 298.257222101, 0.9998, math.radians(24.0), 500000.0
    e2 = f * (2 - f)
    ep2 = e2 / (1 - e2)
    phi = math.radians(lat)
    n = a / math.sqrt(1 - e2 * math.sin(phi) ** 2)
    t = math.tan(phi) ** 2
    c = ep2 * math.cos(phi) ** 2
    A = (math.radians(lon) - lon0) * math.cos(phi)
    m = a * ((1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256) * phi
             - (3 * e2 / 8 + 3 * e2 ** 2 / 32 + 45 * e2 ** 3 / 1024) * math.sin(2 * phi)
             + (15 * e2 ** 2 / 256 + 45 * e2 ** 3 / 1024) * math.sin(4 * phi)
             - (35 * e2 ** 3 / 3072) * math.sin(6 * phi))
    east = fe + k0 * n * (A + (1 - t + c) * A ** 3 / 6 + (5 - 18 * t + t ** 2 + 72 * c - 58 * ep2) * A ** 5 / 120)
    north = k0 * (m + n * math.tan(phi) * (A ** 2 / 2 + (5 - t + 9 * c + 4 * c ** 2) * A ** 4 / 24
                                           + (61 - 58 * t + t ** 2 + 600 * c - 330 * ep2) * A ** 6 / 720))
    return round(north), round(east)


def _month(d, back):
    """Mėnuo YYYYMM, `back` mėnesių iki d."""
    y, m = divmod(d.year * 12 + d.month - 1 - back, 12)
    return f"{y}{m + 1:02d}"


def generate(today=None, seed=1000):
    """Sugeneruoja demonstracinius duomenis.

    Grąžina {"rows": įrašai kaip iš API, "builders": builders.csv eilutės, "months": Sodros mėnesiai}.
    """
    today = today or date.today()
    rng = random.Random(seed)

    def uid():
        return str(uuid.UUID(int=rng.getrandbits(128), version=4))

    rows, builders = [], []
    row_id, object_id = 812000, 4410000
    for n, (kind, place, days_ago, builder, objects, extra) in enumerate(DOCS, start=1):
        extra = extra or {}
        prefix, doc_cat, doc_kind, works, status = DOC_TYPES[kind]
        works = extra.get("rusis", works)
        muni_key, settlement, street, lat0, lon0 = PLACES[place]
        muni, muni_code, kv, city = MUNIS[muni_key]
        if prefix in ("ANN2", "ACUB2", "ARCCR"):
            muni_code = "00"          # šiuos dokumentus registruoja ne savivaldybė (kodas baigiasi nuliu)
        elif prefix == "ACCA":
            muni_code = "30"
        doc_date = today - timedelta(days=days_ago)
        doc_nr = f"{prefix}-{muni_code}-{doc_date:%y%m%d}-{rng.randint(100, 9999):05d}"
        house = f"{rng.randint(1, 120)}{rng.choice(['', '', '', 'A', 'B'])}"
        address = f"{city}, {street} {house}" if city else f"{muni}, {settlement}, {street} {house}"
        lat0 += rng.uniform(-0.004, 0.004)
        lon0 += rng.uniform(-0.006, 0.006)
        names = []
        for spec in objects:
            name = OBJECTS[spec.split(">")[0]][0]
            if name not in names:
                names.append(name)
        title = names[0] if len(names) == 1 else f"{names[0]} ir kiti statiniai"
        project_name = f"{title}, {street} {house}, {settlement} ({works.lower()})"
        project_id = 300000 + n * 17
        project_nr = f"P-{muni_code}-{doc_date:%y}-{rng.randint(1, 99999):05d}"
        plot = f"{kv}/{rng.randint(1, 9999):04d}:{rng.randint(1, 999)}"
        hour = rng.randint(8, 16)
        doc_uuid = uid()          # „uuid“ – dokumento ID, bendras visiems jo statiniams
        for spec in objects:
            key, _, new_purpose = spec.partition(">")
            obj_name, purpose, category = OBJECTS[key]
            row_id += 1
            object_id += rng.randint(1, 40)
            lat = lat0 + rng.uniform(-0.0004, 0.0004)
            lon = lon0 + rng.uniform(-0.0004, 0.0004)
            north, east = wgs_to_lks(lat, lon)
            existing = kind in EXISTING or kind.startswith("uzb_")
            if kind in EXISTING:
                built = rng.randint(1962, 2012)
            elif kind.startswith("uzb_"):
                built = today.year
            else:
                built = None
            unique = f"4400-{rng.randint(1000, 9999)}-{rng.randint(1000, 9999)}" if existing else None
            if unique and key == "patalpa":
                unique += f":{rng.randint(1000, 9999)}"
            rows.append({
                "_type": MODEL,
                "_id": uid(),
                "id": row_id,
                "projekto_id": project_id,
                "statinio_id": object_id,
                "projekto_pavadinimas": project_name,
                "projekto_reg_nr": project_nr,
                "projekto_metai": doc_date.year,
                "unikalus_numeris": unique,
                "statinio_paskirtis": purpose,
                "statinio_pakeista_paskirtis": new_purpose or None,
                "statinio_kategorija": category,
                "adresas": address,
                "statybos_rusis": works,
                "statinio_pavadinimas": obj_name,
                "pastatymo_metai": built,
                "kadastro_nr": plot,
                "ploto_reg_tipas": "Žemės sklypas",
                "sklypo_reg_statusas": "Įregistruotas",
                "dokumento_reg_nr": doc_nr,
                "dokumento_reg_data": doc_date.isoformat(),
                "iraso_data": f"{doc_date.isoformat()}T{hour:02d}:{rng.randint(0, 59):02d}:{rng.randint(0, 59):02d}",
                "dok_statusas": extra.get("statusas", status),
                "dok_tipo_kodas": prefix,
                "dokumento_kategorija": doc_cat,
                "dok_irasas": doc_kind,
                "taskas_lks": f"POINT ({north} {east})",
                "taskas_wgs": f"POINT ({lat:.10f} {lon:.10f})",
                "uuid": doc_uuid,
            })
        if builder == "fizinis":
            builders.append((doc_nr, "", "Fizinis asmuo", "fizinio asmens duomenų nekaupiame (BDAR)"))
        elif builder:
            code, name = COMPANIES[builder][:2]
            if builder in CODE_ONLY:
                builders.append((doc_nr, code, "", "pavadinimas bus paimtas iš JAR"))
            else:
                builders.append((doc_nr, code, name, ""))
    return {"rows": rows, "builders": builders, "months": (_month(today, 3), _month(today, 2))}


def write_csv(path, rows):
    """CSV kaip atsisiųstas iš data.gov.lt: kablelis, UTF-8, pirmi _type ir _id stulpeliai."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    cols = ["_type", "_id"] + FIELDS
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for r in rows:
            w.writerow(["" if r.get(c) is None else r.get(c) for c in cols])
    return path


def write_support_files(out_dir, demo):
    """Sukuria builders.csv, JAR ir Sodros failus tokiu formatu, kokį atpažįsta enrich.py."""
    os.makedirs(out_dir, exist_ok=True)
    paths = {k: os.path.join(out_dir, f"{k}.csv") for k in ("builders", "jar", "sodra")}

    # builders.csv: kaip duomenys/builders.csv (kabliataškis, UTF-8 su BOM – taip saugo Excel)
    with open(paths["builders"], "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["dokumento_reg_nr", "statytojo_kodas", "statytojo_pavadinimas", "pastaba"])
        w.writerows(demo["builders"])

    # JAR: atvirų duomenų stulpeliai, skirtukas „|“
    last = demo["months"][1]
    formed = f"{last[:4]}-{last[4:]}-01"
    with open(paths["jar"], "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter="|")
        w.writerow(["ja_kodas", "ja_pavadinimas", "adresas", "ja_reg_data", "form_kodas", "form_pavadinimas",
                    "stat_kodas", "stat_pavadinimas", "stat_data_nuo", "formavimo_data"])
        for i, (code, name, form, _, _, muni, _, _) in enumerate(COMPANIES.values()):
            w.writerow([code, name, f"{muni}, Demo g. {i + 1}", f"{2004 + i}-03-15", "310", form,
                        "0", "Teisinis statusas neįregistruotas", f"{2004 + i}-03-15", formed])

    # Sodra: lietuviški pavadinimai su kodu skliaustuose, du mėnesiai, dešimtainis kablelis
    with open(paths["sodra"], "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["Draudėjo kodas (code)", "Juridinių asmenų registro kodas (jarCode)", "Pavadinimas (name)",
                    "Savivaldybė, kurioje registruota(municipality)", "Ekonominės veiklos rūšies kodas(ecoActCode)",
                    "Ekonominės veiklos rūšies pavadinimas(ecoActName)", "Mėnuo (month)",
                    "Vidutinis darbo užmokestis (avgWage)", "Apdraustųjų skaičius (numInsured)"])
        for i, (code, name, _, nace, nace_name, muni, staff, wage) in enumerate(COMPANIES.values()):
            for month, insured, k in zip(demo["months"], staff, (0.97, 1.0)):
                w.writerow([f"{1200000 + i}", code, name, muni, nace, nace_name, month,
                            f"{wage * k:.2f}".replace(".", ","), insured])
    return paths


# --- Kitos šalys -------------------------------------------------------------------

# Latvija: (stadija, prašymo rūšis, statybos rūšis, bylos pavadinimas, planuojama paskirtis, statiniai,
#           savivaldybė, būvvaldė, platuma, ilguma, prieš kiek dienų sukurta)
LV_CASES = [
    ("Iecere", "Būvniecības iesniegums ēkai", "Jauna būvniecība", "Daudzdzīvokļu dzīvojamā māja, Ganību dambis 40, Rīga",
     "Triju vai vairāku dzīvokļu mājas", ["Daudzdzīvokļu dzīvojamā māja", "Ārējie inženiertīkli"], "Rīga",
     "RĪGAS VALSTSPILSĒTAS PAŠVALDĪBAS PILSĒTAS ATTĪSTĪBAS DEPARTAMENTS", 56.9790, 24.1110, 2),
    ("Projektēšanas nosacījumu izpilde", "Būvniecības iesniegums ēkai", "Jauna būvniecība",
     "Loģistikas centrs DEMO, Lidosta, Mārupes nov.", "Noliktavas, rezervuāri, bunkuri un silosi",
     ["Noliktavas ēka", "Biroju piebūve"], "Mārupes novads",
     "Mārupes novada pašvaldības Attīstības un būvniecības departaments", 56.9180, 23.9900, 5),
    ("Būvdarbu uzsākšanas nosacījumu izpilde", "Būvniecības iesniegums ēkai", "Pārbūve",
     "Viesnīcas pārbūve, Jomas iela 50, Jūrmala", None, ["Viesnīca"], "Jūrmala", "Jūrmalas Būvvalde",
     56.9690, 23.7710, 8),
    ("Būvdarbi", "Paskaidrojuma raksts ēkai (lēmums)", "Jauna būvniecība", "Dzīvojamā māja, Podnieku iela 7, Ādaži",
     "Viena dzīvokļa mājas", ["Dzīvojamā māja"], "Ādažu novads", "Ādažu novada būvvalde", 57.0740, 24.3260, 6),
    ("Būvdarbi", "Paziņojums par būvniecību", "Vienkāršota atjaunošana",
     "Dzīvokļa vienkāršotā atjaunošana, Brīvības iela 100-12, Rīga", None, [], "Rīga",
     "RĪGAS VALSTSPILSĒTAS PAŠVALDĪBAS PILSĒTAS ATTĪSTĪBAS DEPARTAMENTS", None, None, 3),
    ("Iecere", "Būvniecības iesniegums ēkai", "Jauna būvniecība", "Ražošanas ēka DEMO, Ķekavas pag.",
     "Rūpnieciskās ražošanas ēkas", ["Ražošanas ēka"], "Ķekavas novads", "Ķekavas novada pašvaldības būvvalde",
     56.8280, 24.2360, 4),
    ("Nodošana ekspluatācijā", "Būvniecības iesniegums ēkai", "Jauna būvniecība", "Biroju ēka, Graudu iela 22, Liepāja",
     "Biroju ēkas", ["Biroju ēka"], "Liepāja", "Liepājas būvvalde", 56.5050, 21.0110, 9),
    ("Izbeigta", "Būvniecības iesniegums ēkai", "Jauna būvniecība", "Atcelta ieceres lieta, Rīga", None, [], "Rīga",
     "RĪGAS VALSTSPILSĒTAS PAŠVALDĪBAS PILSĒTAS ATTĪSTĪBAS DEPARTAMENTS", None, None, 7),
    ("Projektēšanas nosacījumu izpilde", "Būvniecības iesniegums ēkai", "Atjaunošana",
     "Daudzdzīvokļu mājas atjaunošana, Ozolciema iela 20, Rīga", None, ["Daudzdzīvokļu dzīvojamā māja"], "Rīga",
     "RĪGAS VALSTSPILSĒTAS PAŠVALDĪBAS PILSĒTAS ATTĪSTĪBAS DEPARTAMENTS", 56.9480, 24.0280, 10),
    ("Iecere", "Paskaidrojuma raksts inženierbūvei (iesniegums)", "Jauna būvniecība", "Ūdensvada pieslēgums, Ogre",
     None, ["Ūdensvads"], "Ogres novads", "Ogres novada pašvaldības centrālās administrācijas Ogres novada būvvalde",
     56.8170, 24.6050, 1),
    ("Iecere", "Būvniecības iesniegums ēkai", "Jauna būvniecība", "Tirdzniecības centrs DEMO, Krasta iela 80, Rīga",
     "Vairumtirdzniecības un mazumtirdzniecības ēkas", ["Tirdzniecības centrs", "Autostāvvieta", "Ārējie inženiertīkli"],
     "Rīga", "RĪGAS VALSTSPILSĒTAS PAŠVALDĪBAS PILSĒTAS ATTĪSTĪBAS DEPARTAMENTS", 56.9330, 24.1550, 2),
    ("Būvdarbi", "Būvniecības iesniegums ēkai", "Jauna būvniecība", "Divu dzīvokļu māja, Mārupe",
     "Divu dzīvokļu mājas", ["Dzīvojamā māja"], "Mārupes novads",
     "Mārupes novada pašvaldības Attīstības un būvniecības departaments", 56.9070, 24.0570, 12),
]

# Lenkija: leidimai (vaivadija, organas, investuotojas, miestas, gatvė, nr., objekto rūšis, kategorija, darbai,
#           pavadinimas, kubatūra, sklypai, prieš kiek dienų sprendimas)
PL_PERMITS = [
    ("mazowieckie", "Prezydent m.st. Warszawy", "DEMO Deweloper Sp. z o.o.", "Warszawa", "Kasprzaka", "31",
     "Obiekt budowlany inny niż budynek mieszkalny jednorodzinny", "XIII", "budowa nowego/nowych obiektów budowlanych",
     "Budowa budynku mieszkalnego wielorodzinnego z garażem podziemnym", 24800, 3, 2),
    ("mazowieckie", "Starosta Warszawski Zachodni", "DEMO Logistyka Polska Sp. z o.o.", "Błonie", "Rokitnicka", "5",
     "Obiekt budowlany inny niż budynek mieszkalny jednorodzinny", "XVIII", "budowa nowego/nowych obiektów budowlanych",
     "Budowa hali magazynowej z częścią biurową", 61000, 2, 4),
    ("mazowieckie", "Prezydent m.st. Warszawy", "DEMO Biura S.A.", "Warszawa", "Prosta", "68",
     "Obiekt budowlany inny niż budynek mieszkalny jednorodzinny", "XVI", "rozbudowa istniejącego/istniejących obiektów budowlanych",
     "Rozbudowa budynku biurowego o część konferencyjną", 9800, 1, 6),
    ("mazowieckie", "Starosta Powiatu Pruszkowskiego", "", "Nadarzyn", "Leśna", "12",
     "Budynek mieszkalny jednorodzinny", "I", "budowa nowego/nowych obiektów budowlanych",
     "Budowa budynku mieszkalnego jednorodzinnego", 820, 1, 3),
    ("mazowieckie", "Prezydent Miasta Radomia", "Gmina Miasta DEMO", "Radom", "Szkolna", "4",
     "Obiekt budowlany inny niż budynek mieszkalny jednorodzinny", "IX",
     "wykonanie robót budowlanych innych niż wymienione powyżej", "Termomodernizacja budynku szkoły", None, 1, 9),
    ("mazowieckie", "Starosta Powiatu Płockiego", "DEMO Energia Sp. z o.o.", "Płock", "", "",
     "Obiekt budowlany inny niż budynek mieszkalny jednorodzinny", "XXVI", "budowa nowego/nowych obiektów budowlanych",
     "Budowa sieci ciepłowniczej", None, 4, 11),
    ("podlaskie", "Prezydent Miasta Białegostoku", "DEMO Hotele Sp. z o.o.", "Białystok", "Lipowa", "20",
     "Obiekt budowlany inny niż budynek mieszkalny jednorodzinny", "XIV", "nadbudowa istniejącego/istniejących obiektów budowlanych",
     "Nadbudowa hotelu o dwie kondygnacje", 7200, 1, 5),
    ("podlaskie", "Starosta Powiatu Suwalskiego", "", "Suwałki", "Kościuszki", "2",
     "Obiekt budowlany inny niż budynek mieszkalny jednorodzinny", "XVII", "rozbiórka istniejącego obiektu budowlanego",
     "Rozbiórka budynku handlowego", None, 1, 7),
]
# Lenkija: pranešimai (vaivadija, organas, miestas, pašto kodas, gatvė, nr., kategorija, pavadinimas, darbai, prieš kiek dienų)
PL_NOTICES = [
    ("mazowieckie", "Starosta Powiatu Piaseczyńskiego", "Józefosław", "05-509", "Ogrodowa", "8", "I",
     "Budowa budynku mieszkalnego jednorodzinnego wolnostojącego", "budowa nowego/nowych obiektów budowlanych", 2),
    ("pomorskie", "Starosta Powiatu Puckiego", "Władysławowo", "84-120", "Morska", "15", "I",
     "Budowa budynku mieszkalnego jednorodzinnego o pow. zabudowy do 70 m2", "budowa nowego/nowych obiektów budowlanych", 5),
    ("podlaskie", "Starosta Powiatu Białostockiego", "Wasilków", "16-010", "Polna", "3", "VIII",
     "Instalacja gazowa dla budynku mieszkalnego jednorodzinnego", "budowa nowego/nowych obiektów budowlanych", 1),
    ("malopolskie", "Starosta Powiatu Krakowskiego", "Zielonki", "32-087", "Krakowska", "40", "I",
     "Rozbudowa budynku mieszkalnego jednorodzinnego", "rozbudowa istniejącego/istniejących obiektów budowlanych", 8),
    ("slaskie", "Prezydent Miasta Katowice", "Katowice", "40-001", "Mariacka", "11", "XXVI",
     "Budowa przyłącza wodociągowego", "budowa nowego/nowych obiektów budowlanych", 4),
]
PL_PERMIT_COLS = [
    "numer_urzad", "numer_gunb", "nazwa_organu", "adres_organu", "data_wplywu_wniosku", "numer_decyzji_urzedu",
    "data_wydania_decyzji", "nazwa_inwestor", "wojewodztwo", "miasto", "terc", "cecha", "cecha", "ulica",
    "ulica_dalej", "nr_domu", "rodzaj_inwestycji", "kategoria", "nazwa_zamierzenia_bud", "nazwa_zam_budowlanego",
    "kubatura", "projektant_nazwisko", "projektant_imie", "projektant_numer_uprawnien", "jednosta_numer_ew",
    "obreb_numer", "numer_dzialki", "numer_arkusza_dzialki", "jednostka_stara_numeracja_z_wniosku",
    "stara_numeracja_obreb_z_wnioskiu", "stara_numeracja_dzialka_z_wniosku",
]
PL_NOTICE_COLS = [
    "numer_ewidencyjny_system", "numer_ewidencyjny_urzad", "data_wplywu_wniosku_do_urzedu", "nazwa_organu",
    "wojewodztwo_objekt", "obiekt_kod_pocztowy", "miasto", "terc", "cecha", "cecha", "ulica", "ulica_dalej",
    "nr_domu", "kategoria", "nazwa_zam_budowlanego", "rodzaj_zam_budowlanego", "kubatura", "stan",
    "jednostki_numer", "obreb_numer", "numer_dzialki", "numer_arkusza_dzialki", "nazwisko_projektanta",
    "imie_projektanta", "projektant_numer_uprawnien", "projektant_pozostali",
]

# Estija: (būsena, paskirties id, pavadinimas, H/R, apskritis, savivaldybė, adresas, platuma, ilguma,
#          prieš kiek dienų sukurta, prieš kiek dienų atnaujinta, pirmo naudojimo metai)
EE_BUILDINGS = [
    ("EHITIS_SEISUND_KAVAN", 11222, "", "H", "37", "784", "Harju maakond, Tallinn, Kristiine linnaosa, Tulika tn 19",
     59.4250, 24.7180, 3, 3, None),
    ("Püstitamisel", 12201, "DEMO ärihoone", "H", "37", "784", "Harju maakond, Tallinn, Kesklinna linnaosa, Narva mnt 7",
     59.4380, 24.7650, 12, 5, None),
    ("EHITIS_SEISUND_KAVAN", 12529, "Laohoone", "H", "79", "793", "Tartu maakond, Tartu linn, Tartu linn, Ringtee tn 44",
     58.3640, 26.7480, 6, 6, None),
    ("Püstitamisel", 11101, "", "H", "37", "198", "Harju maakond, Harku vald, Tabasalu alevik, Klooga mnt 30",
     59.4280, 24.5600, 10, 2, None),
    # seniai statomas: pirmą kartą tik įsimenamas, signalo nėra
    ("EHITIS_SEISUND_PYSTI", 11101, "", "H", "37", "198", "Harju maakond, Harku vald, Harku alevik, Pargi tee 7",
     59.3910, 24.6150, 900, 1, None),
    ("EHITIS_SEISUND_PYSTI", 11222, "", "H", "37", "890", "Harju maakond, Viimsi vald, Haabneeme alevik, Randvere tee 9",
     59.5100, 24.8250, 9, 9, None),
    ("EHITIS_SEISUND_OLEMA", 12111, "DEMO hotell", "H", "68", "624", "Pärnu maakond, Pärnu linn, Pärnu linn, Ranna pst 5",
     58.3780, 24.5000, 700, 4, "this_year"),
    ("EHITIS_SEISUND_KAVAN", 12519, "Tootmishoone", "H", "37", "653", "Harju maakond, Rae vald, Peetri alevik, Kesk tee 20",
     59.4040, 24.8080, 1, 1, None),
    ("EHITIS_SEISUND_REATA", 11101, "", "H", "37", "198", "Harju maakond, Harku vald, Harku alevik, Pargi tee 2",
     59.3900, 24.6200, 500, 3, None),
    ("EHITIS_SEISUND_KAVAN", 21112, "Põhimaantee lõik", "R", "79", "793", "Tartu maakond, Tartu linn, Tartu linn, Riia mnt",
     58.3500, 26.7000, 2, 2, None),
]
EE_COLS = ["id", "omandi_liik", "seisund", "ehr_kood", "kaos_id_peamine", "tahis", "nimetus", "rajatis_hoone",
           "eh_alust_kp", "kav_kasutus_kp", "ajeh_kasutalg_kp", "ajeh_kasutlopp_kp", "maakond", "omavalitsus",
           "date_created", "date_updated", "taisaadress", "lahiaadress", "esmane_kasutus", "korgus"]
EE_SHAPE_COLS = ["id", "ehit_id", "nliik_kood", "kuju_jnr", "nimetus", "ads_oid", "geometry", "date_created",
                 "date_updated", "ehr_kood", "adob_id", "ads_liik", "tyhistatud_kp", "nahtus", "taisaadress",
                 "lahiaadress", "pindala", "viitepunkt_x", "viitepunkt_y", "geom_updated"]


def _write_zip(path, member, header, rows, delimiter=";", bom=True):
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=delimiter, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(member, ("﻿" if bom else "") + buf.getvalue())
    return path


def write_foreign_files(out_dir, today=None, seed=2000):
    """Sukuria LV, PL ir EE demonstracinius failus tikrais šaltinių formatais. Grąžina {šalis: [keliai]}."""
    from saltiniai.ee import wgs_to_lest   # vėlyvas importas: modulis veikia ir paleistas atskirai
    today = today or date.today()
    rng = random.Random(seed)
    out = {}

    # --- Latvija: trys BIS failai ---
    d = os.path.join(out_dir, "lv")
    os.makedirs(d, exist_ok=True)
    cases, objects, new_builds = [], [], []
    for i, (stage, appl, works, title, use, objs, terr, authority, lat, lon, days) in enumerate(LV_CASES):
        case = f"BIS-BL-{990100 + i}-{rng.randint(1000, 99999)}"
        cases.append([authority, case, appl, title, stage, works, (today - timedelta(days=days)).isoformat()])
        for j, name in enumerate(objs):
            olat, olon = (lat + j * 0.0004, lon + j * 0.0004) if lat else ("", "")
            objects.append([case, f"0100{rng.randint(100000000, 999999999)}", "", "", olon, olat, name,
                            f"{title.split(', ', 1)[-1]}, LV-{rng.randint(1001, 5799)}", rng.randint(100000000, 199999999),
                            works, rng.randint(10000, 99999), terr])
        if use:
            new_builds.append([case, objs[0] if objs else title, use, lon, lat, "", "", "", rng.randint(100000000, 199999999),
                               title.split(", ", 1)[-1]])
    paths = {"lietas": os.path.join(d, "buvniecibas-lietu-saraksts.csv"),
             "objekti": os.path.join(d, "buvniecibas-lietu-objekti.csv"),
             "jaunbuves": os.path.join(d, "jaunbuvju-geotelpiskie-dati.csv")}
    with open(paths["lietas"], "w", encoding="utf-8", newline="") as fh:   # be BOM, visi laukai kabutėse
        w = csv.writer(fh, quoting=csv.QUOTE_ALL, lineterminator="\n")
        w.writerow(["Atbildigas_iestades_nosaukums", "Buvniecibas_lietas_numurs", "Buvniecibas_iesnieguma_veids",
                    "Objekta_nosaukums", "Aktuala_stadija", "Buvniecibas_veids", "Lietas_izveidosanas_datums"])
        w.writerows(cases)
    with open(paths["objekti"], "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["Buvniecibas_lietas_numurs", "Buves_kadastra_apzimejums", "Objekta_identifikators_inzenierbuvem",
                    "Melioracijas_kadastra_numurs", "Buves_atrasanas_vieta_geografiskais_garums",
                    "Buves_atrasanas_vieta_geografiskais_platums", "Buves_nosaukums", "Buves_objekta_adreses_teksts",
                    "Buves_objekta_adreses_kods", "Buvniecibas_veids", "Administrativas_teritorijas_kods",
                    "Administrativas_teritorijas_nosaukums"])
        w.writerows(objects)
    with open(paths["jaunbuves"], "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["Buvniecibas_lietas_numurs", "Buves_nosaukums", "Planotais_buves_galvenais_lietosanas_veids",
                    "Buves_atrasanas_vieta_geografiskais_garums", "Buves_atrasanas_vieta_geografiskais_platums",
                    "Buves_kadastra_apzimejums", "Objekta_identifikators_inzenierbuvem", "Melioracijas_kadastra_numurs",
                    "Buves_adreses_kods", "Buves_adreses_teksts"])
        w.writerows(new_builds)
    out["LV"] = list(paths.values())

    # --- Lenkija: leidimai pagal vaivadijas ir pranešimų failas ---
    d = os.path.join(out_dir, "pl")
    os.makedirs(d, exist_ok=True)
    by_voiv = {}
    for i, (voiv, organ, investor, city, street, house, kind, cat, works, name, volume, plots, days) \
            in enumerate(PL_PERMITS):
        decided = today - timedelta(days=days)
        applied = decided - timedelta(days=rng.randint(20, 60))
        office_nr = f"AB.6740.{rng.randint(1, 900)}.{decided.year}"
        system_nr = f"ST-{voiv[:2].upper()}-DM/WNIOSEK/{9000 + i}/{decided.year}"
        for k in range(plots):
            by_voiv.setdefault(voiv, []).append([
                office_nr, system_nr, organ, f"ul. Urzędowa {i + 1}, {city}", f"{applied} 00:00:00",
                f"{rng.randint(1, 900)}/{decided:%y}", f"{decided} 00:00:00", investor, voiv, city,
                f"{1400000 + rng.randint(1, 99999)}", "ul.  ", "ul.  ", street, "", house, kind, cat, works, name,
                volume or "", "Projektant", "Demo", "MAZ/0000/DEMO", f"1465{rng.randint(10, 99)}_1",
                f"{rng.randint(1, 60):04d}", f"{rng.randint(1, 400)}/{k + 1}", "", "", "", ""])
    out["PL"] = [_write_zip(os.path.join(d, f"wynik_{v}.zip"), f"wynik_{v}.csv", PL_PERMIT_COLS, rows)
                 for v, rows in by_voiv.items()]
    notices = []
    for i, (voiv, organ, city, post, street, house, cat, name, works, days) in enumerate(PL_NOTICES):
        notices.append([f"ST-{voiv[:2].upper()}-DM/ZGŁOSZENIE/{500 + i}/{today.year}", f"{rng.randint(1, 900)}/{today.year}",
                        f"{today - timedelta(days=days)} 00:00:00", organ, voiv, post, city,
                        f"{2200000 + rng.randint(1, 99999)}", "ul.  ", "ul.  ", street, "", house, cat, name, works, "",
                        "Brak sprzeciwu", f"2211{rng.randint(10, 99)}_2", f"{rng.randint(1, 40):04d}",
                        f"{rng.randint(1, 900)}", "", "Projektant", "Demo", "POM/0000/DEMO", ""])
    out["PL"].append(_write_zip(os.path.join(d, "wynik_zgloszenia_2022_up.zip"), "wynik_zgloszenia_2022_up.csv",
                                PL_NOTICE_COLS, notices, bom=False))

    # --- Estija: statinių ataskaita ir kontūrų (koordinačių) ataskaita ---
    d = os.path.join(out_dir, "ee")
    os.makedirs(d, exist_ok=True)
    buildings, shapes = [], []
    for i, (st, use, name, kind, county, muni, address, lat, lon, created, updated, first_use) in enumerate(EE_BUILDINGS):
        code = str(120900000 + i * 37) if kind == "H" else str(220900000 + i * 37)
        start = today + timedelta(days=rng.randint(10, 120))
        buildings.append([5000000 + i, "kinnisasi", st, code, use, "", name, kind, start.isoformat(),
                          (start + timedelta(days=500)).isoformat(), "", "", county, muni,
                          f"{today - timedelta(days=created)} 10:{i:02d}:00", f"{today - timedelta(days=updated)} 14:{i:02d}:00",
                          address, address.rsplit(", ", 1)[-1], today.year if first_use else "", ""])
        north, east = wgs_to_lest(lat, lon)
        shapes.append([7000000 + i, 5000000 + i, "EHITIS_KUJU", 1, "", "", "", "", "", code, "", "", "", "", address,
                       "", round(rng.uniform(80, 4000), 1), f"{north:.2f}", f"{east:.2f}", ""])
    ee_paths = [os.path.join(d, "eh_ehitised.csv"), os.path.join(d, "ehitise_ruumikuju.csv")]
    for path, cols, rows in ((ee_paths[0], EE_COLS, buildings), (ee_paths[1], EE_SHAPE_COLS, shapes)):
        with open(path, "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh, delimiter=";", lineterminator="\n")
            w.writerow(cols)
            w.writerows(rows)
    out["EE"] = ee_paths
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description="Demonstraciniai Infostatybos įrašai CSV formatu.")
    p.add_argument("--csv", required=True, help="kur įrašyti CSV, pvz. duomenys/demo/statiniai.csv")
    p.add_argument("--data", type=date.fromisoformat, help="šiandienos data YYYY-MM-DD (numatyta – šiandien)")
    args = p.parse_args(argv)
    demo = generate(args.data)
    write_csv(args.csv, demo["rows"])
    docs = len({r["dokumento_reg_nr"] for r in demo["rows"]})
    print(f"Įrašų: {len(demo['rows'])}, dokumentų: {docs} -> {args.csv}")


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    main()

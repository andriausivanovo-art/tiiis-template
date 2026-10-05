# -*- coding: utf-8 -*-
"""Statybų signalų sistemos nustatymai.

Viską, kas gali keistis (API adresai, laukų pavadinimai, klasifikavimo
taisyklės), laikome čia, kad nereikėtų liesti kodo.
"""

# --- Duomenų šaltinis: VTPSI Infostatyba atviri duomenys (data.gov.lt, rinkinys Nr. 1000) ---
API_BASE = "https://get.data.gov.lt"
MODEL = "datasets/gov/vtpsi/infostatyba/Statinys"
PAGE_LIMIT = 1000           # įrašų per užklausą
REQUEST_PAUSE_S = 1.0       # pauzė tarp užklausų (būkime mandagūs)
REQUEST_TIMEOUT_S = 90
USER_AGENT = "statybu-signalai/0.1 (+kontaktas@jusu-domenas.lt)"   # įrašykite savo kontaktą

# Kiek dienų atgal imti, jei sistema leidžiama pirmą kartą
FIRST_RUN_DAYS = 30
# Persidengimas su ankstesniu paleidimu (dienomis), kad nepraleistume vėluojančių įrašų
OVERLAP_DAYS = 7

# Laukų pavadinimai rinkinyje (jei VTPSI juos pakeistų, keičiame tik čia)
F = {
    "doc_nr": "dokumento_reg_nr",
    "doc_date": "dokumento_reg_data",
    "doc_text": "dok_irasas",
    "doc_type_code": "dok_tipo_kodas",
    "doc_category": "dokumento_kategorija",
    "doc_status": "dok_statusas",
    "works_type": "statybos_rusis",
    "purpose": "statinio_paskirtis",
    "new_purpose": "statinio_pakeista_paskirtis",
    "category": "statinio_kategorija",
    "object_name": "statinio_pavadinimas",
    "address": "adresas",
    "cadastre": "kadastro_nr",
    "project_name": "projekto_pavadinimas",
    "project_nr": "projekto_reg_nr",
    "unique_nr": "unikalus_numeris",
    "point_lks": "taskas_lks",
    "point_wgs": "taskas_wgs",
    "row_id": "uuid",
}

# Dokumentų būsenos, kurias atmetame (mažosiomis raidėmis, tikrinama "contains")
EXCLUDED_STATUSES = ["panaikint", "negalioj", "atšaukt", "atsiimt"]

# --- Signalų tipai ---
# Tikrinama eilės tvarka: pirmas atitikęs raktažodis lemia tipą.
# Raktažodžiai tikrinami dok_irasas tekste mažosiomis raidėmis.
SIGNAL_RULES = [
    ("prasymas", "Prašymas išduoti SLD", ["prašymas išduoti statybą leidžiant", "prašymas išduoti leidim"]),
    ("leidimas_nauja", "Leidimas: nauja statyba", ["leidimas statyti nauj"]),
    ("leidimas_rekonstrukcija", "Leidimas: rekonstrukcija", ["leidimas rekonstruoti"]),
    ("leidimas_atnaujinimas", "Leidimas: atnaujinimas", ["leidimas atnaujinti", "modernizuoti"]),
    ("paskirties_keitimas", "Leidimas: paskirties keitimas", ["leidimas pakeisti", "paskirties keitim"]),
    ("pritarimas", "Rašytinis pritarimas", ["rašytinis pritarimas", "rasytinis pritarimas"]),
    ("griovimas", "Leidimas griauti", ["leidimas griauti", "nugriauti"]),
    ("pradzia", "Statybos pradžia", ["statybos pradži", "pradėti statyb"]),
    ("uzbaigimas", "Statybos užbaigimas", ["užbaigim", "uzbaigim", "statybos užbaigimo akt"]),
]
# Kurie tipai įtraukiami į klientams skirtus signalus (kita lieka DB, bet neeksportuojama)
SELLABLE_TYPES = [
    "prasymas", "leidimas_nauja", "leidimas_rekonstrukcija", "leidimas_atnaujinimas",
    "paskirties_keitimas", "pradzia", "uzbaigimas",
]

# --- Svarbos balas (rūšiavimui ir "karštiems" signalams) ---
SCORE = {
    "type": {
        "prasymas": 3, "leidimas_nauja": 3, "leidimas_rekonstrukcija": 2,
        "leidimas_atnaujinimas": 2, "paskirties_keitimas": 1, "pradzia": 2, "uzbaigimas": 1,
    },
    # raktažodžiai paskirtyje -> papildomi taškai
    "purpose": {
        "daugiabu": 3, "butų": 2, "gyvenamasis (trijų ir daugiau": 3,
        "administracin": 2, "prekybos": 2, "sandėliavimo": 2, "gamybos": 2,
        "viešbuči": 2, "gydymo": 2, "mokslo": 2,
        "vienbuči": 0, "dvibuči": 0, "pagalbinio": -1, "inžinerin": -1, "tinklai": -1,
    },
    "category": {"ypatingasis": 2, "neypatingasis": 1, "nesudėtingasis": -1},
    "objects_bonus_from": 3,   # jei projekte >= tiek statinių, +1
}

# --- Infostatybos viešoji paieška (statytojui nustatyti rankiniu būdu) ---
# Įrašykite adresą, kuriuo naudojatės; jis atsiras statytojų paieškos sąraše.
INFOSTATYBA_SEARCH_URL = ""

# --- Failai ---
DB_PATH = "duomenys/signalai.sqlite"
BUILDERS_CSV = "duomenys/builders.csv"
OUTPUT_DIR = "isvestis"

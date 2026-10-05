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
    "object_id": "statinio_id",
    "point_lks": "taskas_lks",
    "point_wgs": "taskas_wgs",
    "row_id": "uuid",
}

# Dokumentų būsenos, kurias atmetame (mažosiomis raidėmis, tikrinama "contains")
EXCLUDED_STATUSES = ["panaikint", "negalioj", "atšaukt", "atsiimt"]

# --- Signalų tipai ---
# Tikrinama eilės tvarka: pirmas atitikęs raktažodis lemia tipą.
# Raktažodžiai tikrinami dok_irasas tekste mažosiomis raidėmis.
# Ataskaitoje tipai rodomi SELLABLE_TYPES tvarka, todėl šią eilę galima keisti laisvai.
SIGNAL_RULES = [
    ("prasymas", "Prašymas išduoti SLD", ["prašymas išduoti statybą leidžiant", "prašymas išduoti leidim"]),
    ("leidimas_nauja", "Leidimas: nauja statyba", ["leidimas statyti nauj"]),
    ("leidimas_rekonstrukcija", "Leidimas: rekonstrukcija", ["leidimas rekonstruoti"]),
    ("leidimas_atnaujinimas", "Leidimas: atnaujinimas", ["leidimas atnaujinti", "modernizuoti"]),
    # Užbaigimas tikrinamas prieš paskirties keitimą: „Deklaracija apie statybos užbaigimą /
    # paskirties keitimą“ yra užbaigimo dokumentas, ne leidimas. „Pažyma apie statinio statybą
    # be nukrypimų nuo esminių statinio projekto sprendinių“ irgi išduodama statybą baigus.
    ("uzbaigimas", "Statybos užbaigimas", ["užbaigim", "uzbaigim", "statybos užbaigimo akt",
                                           "be nukrypimų", "be nukrypimu", "be esminių nukrypimų"]),
    ("paskirties_keitimas", "Leidimas: paskirties keitimas", ["leidimas pakeisti", "paskirties keitim"]),
    ("pritarimas", "Rašytinis pritarimas", ["rašytinis pritarimas", "rasytinis pritarimas"]),
    ("griovimas", "Leidimas griauti", ["leidimas griauti", "nugriauti"]),
    ("pradzia", "Statybos pradžia", ["statybos pradži", "pradėti statyb"]),
]
# Kurie tipai įtraukiami į klientams skirtus signalus (kita lieka DB, bet neeksportuojama)
SELLABLE_TYPES = [
    "prasymas", "leidimas_nauja", "leidimas_rekonstrukcija", "leidimas_atnaujinimas",
    "paskirties_keitimas", "pranesimas", "pradzia", "uzbaigimas",
]
# Bendri tipų pavadinimai filtrams (visoms šalims). Kiekvienas signalas turi ir savo žymę,
# pvz. LT „Prašymas išduoti SLD“ arba „LV: sumanymas (iecere)“.
TYPE_LABELS = {
    "prasymas": "Prašymas, sumanymas",
    "leidimas_nauja": "Leidimas: nauja statyba",
    "leidimas_rekonstrukcija": "Leidimas: rekonstrukcija",
    "leidimas_atnaujinimas": "Leidimas: atnaujinimas",
    "paskirties_keitimas": "Leidimas: paskirties keitimas",
    "pranesimas": "Pranešimas (be leidimo)",
    "pradzia": "Statybos pradžia",
    "uzbaigimas": "Statybos užbaigimas",
    "pritarimas": "Rašytinis pritarimas",
    "griovimas": "Griovimas",
    "kita": "Kita",
}

# --- Svarbos balas (rūšiavimui ir "karštiems" signalams) ---
SCORE = {
    "type": {
        "prasymas": 3, "leidimas_nauja": 3, "leidimas_rekonstrukcija": 2,
        "leidimas_atnaujinimas": 2, "paskirties_keitimas": 1, "pranesimas": 1, "pradzia": 2, "uzbaigimas": 1,
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


# =====================================================================================
# Kitos šalys. Kiekviena šalis – atskiras šaltinis (saltiniai/lv.py, pl.py, ee.py).
# =====================================================================================
COUNTRY_NAMES = {"LT": "Lietuva", "LV": "Latvija", "PL": "Lenkija", "EE": "Estija"}
# Kurias šalis `run` ir `fetch` apdoroja numatytai. EE ataskaitą reikia užsisakyti el. paštu
# (python sistema.py ee-order), todėl Estija importuojama atskirai: python sistema.py import --salis EE.
RUN_COUNTRIES = ["LT", "LV", "PL"]

# Paskirties raktažodžiai kitoms šalims (tikrinama mažosiomis raidėmis be diakritikų, žr. saltiniai.fold)
SCORE_PURPOSE = {
    "LV": {
        "triju vai vairaku dzivoklu": 3, "kopdzivojamas": 2, "divu dzivoklu": 0, "viena dzivokla": 0,
        "biroju": 2, "tirdzniecibas": 2, "rupnieciskas razosanas": 2, "noliktavas": 2, "viesnicas": 2,
        "arstniecibas": 2, "skolas": 2, "sporta": 1, "plasizklaides": 1, "garazu": -1,
        "inzenierbuv": -1, "energoapgades": -1, "elektronisko sakaru": -1, "autocel": -1,
        "hidrotehnisk": -1, "dzelzcel": -1,
    },
    # EE: Ehitisregistri kasutusotstarbe kodo pradžia -> taškai (ilgiausias sutapimas laimi)
    "EE": {"1122": 3, "1121": 0, "111": 0, "113": 2, "121": 2, "122": 2, "123": 2, "124": 1,
           "125": 2, "126": 2, "127": 0, "2": -1},
}

# --- Latvija: Būvniecības informācijas sistēma (BIS), data.gov.lv, licencija CC0 ---
LV_CKAN_API = "https://data.gov.lv/dati/api/3/action/package_show?id="
LV_DATASETS = {
    "lietas": "37072983-16ac-41a0-93c0-9c9ad711279d",     # Būvniecības lietu saraksts
    "objekti": "9911ae4c-f18f-44d3-84b5-a45ae4c9b59a",    # Būvniecības lietu objekti (koordinatės, adresai)
    "jaunbuves": "9833285e-6529-49dc-b5ee-fb8de3881380",  # Jaunbūvju dati (planuojama paskirtis)
}
# Bylos stadija -> (tipas, žymė). "leidimas" – tipas pagal statybos rūšį (LV_WORKS); None – atmetama.
LV_STAGES = {
    "Iecere": ("prasymas", "sumanymas (iecere)"),
    "Būvniecības ieceres publiskā apspriešana": ("prasymas", "viešas svarstymas"),
    "Projektēšanas nosacījumu izpilde": ("leidimas", "leidimas, projektavimo sąlygos"),
    "Būvdarbu uzsākšanas nosacījumu izpilde": ("leidimas", "leidimas, darbų pradžios sąlygos"),
    "Būvdarbi": ("pradzia", "statybos darbai"),
    "Nodošana ekspluatācijā": ("uzbaigimas", "pridavimas eksploatuoti"),
    "Ekspluatācija": ("uzbaigimas", "eksploatacija"),
    "Izbeigta": (None, "byla nutraukta"),
}
LV_WORKS = {
    "Jauna būvniecība": ("leidimas_nauja", "nauja statyba"),
    "Novietošana": ("leidimas_nauja", "pastatymas"),
    "Ierīkošana": ("leidimas_nauja", "įrengimas"),
    "Pārbūve": ("leidimas_rekonstrukcija", "rekonstrukcija"),
    "Vienkāršota pārbūve": ("leidimas_rekonstrukcija", "supaprastinta rekonstrukcija"),
    "Ailes jauna būvniecība, pārbūve, nojaukšana": ("leidimas_rekonstrukcija", "angos keitimas"),
    "Atjaunošana": ("leidimas_atnaujinimas", "atnaujinimas"),
    "Vienkāršota atjaunošana": ("leidimas_atnaujinimas", "supaprastintas atnaujinimas"),
    "Vienkāršota fasādes atjaunošana": ("leidimas_atnaujinimas", "fasado atnaujinimas"),
    "Restaurācija": ("leidimas_atnaujinimas", "restauravimas"),
    "Modernizācija": ("leidimas_atnaujinimas", "modernizavimas"),
    "Remonts": ("leidimas_atnaujinimas", "remontas"),
    "Lietošanas veida maiņa bez pārbūves": ("paskirties_keitimas", "paskirties keitimas"),
    "Nojaukšana": ("griovimas", "griovimas"),
    "Demontāža": ("griovimas", "demontavimas"),
    "Konservācija": ("kita", "konservavimas"),
}
LV_WORKS_TYPES = sorted({t for t, _ in LV_WORKS.values()})
# Kiek dienų sekame jau žinomų bylų stadijų pokyčius (senesnės bylos neįtraukiamos iš naujo)
LV_TRACK_DAYS = 730

# --- Lenkija: GUNB Rejestr Wniosków, Decyzji i Zgłoszeń (RWDZ), atnaujinama kasnakt ---
PL_BASE_URL = "https://wyszukiwarka.gunb.gov.pl/pliki_pobranie/"
# Statybos leidimai (pozwolenia) – po failą vaivadijai; palikite tik reikalingas
PL_WOJEWODZTWA = [
    "dolnoslaskie", "kujawsko-pomorskie", "lubelskie", "lubuskie", "lodzkie", "mazowieckie", "malopolskie",
    "opolskie", "podkarpackie", "podlaskie", "pomorskie", "slaskie", "swietokrzyskie", "warminsko-mazurskie",
    "wielkopolskie", "zachodniopomorskie",
]
# Pranešimai apie statybą (zgłoszenia) – vienas failas visai šaliai; None – neimti
PL_ZGLOSZENIA = "wynik_zgloszenia_2022_up.zip"
PL_WORKS = {  # nazwa_zamierzenia_bud / rodzaj_zam_budowlanego pradžia -> (leidimo tipas, žymė)
    "budowa nowego": ("leidimas_nauja", "nauja statyba"),
    "rozbudowa": ("leidimas_rekonstrukcija", "išplėtimas"),
    "nadbudowa": ("leidimas_rekonstrukcija", "antstatas"),
    "odbudowa": ("leidimas_rekonstrukcija", "atstatymas"),
    "przebudowa": ("leidimas_rekonstrukcija", "rekonstrukcija"),
    "rozbiórka": ("griovimas", "griovimas"),
    "zmiana sposobu użytkowania": ("paskirties_keitimas", "paskirties keitimas"),
    "wykonanie robót budowlanych innych": ("leidimas_atnaujinimas", "kiti statybos darbai"),
}
# Statinių kategorijos (Prawo budowlane priedas): pavadinimas lietuviškai ir paskirties taškai
PL_CATEGORIES = {
    "I": ("vienbučiai gyvenamieji namai", 0), "II": ("žemės ūkio pastatai", 0),
    "III": ("nedideli pastatai (vasarnamiai, ūkiniai, garažai)", -1),
    "IV": ("viešųjų kelių ir geležinkelių elementai", -1), "V": ("sporto ir poilsio objektai", 1),
    "VI": ("kapinės", -1), "VII": ("vandens navigacijos objektai", -1), "VIII": ("kiti statiniai", -1),
    "IX": ("kultūros, mokslo ir švietimo pastatai", 2), "X": ("religiniai pastatai", 0),
    "XI": ("sveikatos ir socialinės globos pastatai", 2), "XII": ("viešojo administravimo pastatai", 2),
    "XIII": ("kiti gyvenamieji (daugiabučiai) pastatai", 3), "XIV": ("turistinio apgyvendinimo pastatai", 2),
    "XV": ("sporto ir poilsio pastatai", 1), "XVI": ("biurų ir konferencijų pastatai", 2),
    "XVII": ("prekybos, maitinimo ir paslaugų pastatai", 2), "XVIII": ("pramonės ir sandėlių pastatai", 2),
    "XIX": ("pramoniniai rezervuarai", 0), "XX": ("degalinės", 1), "XXI": ("vandens transporto objektai", -1),
    "XXII": ("aikštelės, stovėjimo aikštelės", 0), "XXIII": ("aerodromų objektai", 0),
    "XXIV": ("vandens ūkio objektai", -1), "XXV": ("keliai ir geležinkeliai", -1),
    "XXVI": ("tinklai (elektros, ryšių, dujų, šilumos, vandens, nuotekų)", -1),
    "XXVII": ("hidrotechniniai statiniai", -1), "XXVIII": ("tiltai ir viadukai", -1),
    "XXIX": ("kaminai, stiebai, vėjo elektrinės", -1), "XXX": ("vandens išteklių objektai", -1),
}
PL_KUBATURA_BONUS = 5000   # m³: didelis objektas, +1 balas

# --- Estija: Ehitisregister (EHR) atvirų duomenų API ---
EE_API = "https://livekluster.ehr.ee/api/av/v2"
EE_REPORT = "eh_ehitised"               # statiniai su būsena, adresu, datomis
EE_COORD_REPORT = "ehitise_ruumikuju"   # statinių kontūrai ir atskaitos taškas (koordinatėms)
# Užsakant ataskaitą imamos šios būsenos (statiniai, kurie dar tik planuojami arba statomi)
EE_ORDER_STATUSES = ["EHITIS_SEISUND_KAVAN", "EHITIS_SEISUND_PYSTI"]
# Būsenos kodo fragmentas -> (tipas, žymė); None – atmetama. Tikrinama eilės tvarka.
EE_STATUSES = [
    ("EIKEH", None, "leidimas negalioja"), ("KUSTU", None, "ištrintas"), ("REATA", None, "neįgyvendintas"),
    ("LAMMUT_LUBA", "griovimas", "griovimo leidimas"), ("LAMUT", "griovimas", "nugriautas"),
    ("KAVAN", "prasymas", "planuojamas statinys"), ("EHITAM_LUBA", "leidimas_nauja", "statybos leidimas"),
    ("PYSTI", "pradzia", "statomas"), ("EHITAMISEL", "pradzia", "statomas"),
    ("KASUT_OSALINE", "uzbaigimas", "iš dalies naudojamas"), ("KASUTUSEL", "uzbaigimas", "naudojamas"),
    ("OLEMA", "uzbaigimas", "pastatytas"),
]

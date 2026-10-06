# -*- coding: utf-8 -*-
"""Statybų signalų sistemos nustatymai.

Viską, kas gali keistis (API adresai, laukų pavadinimai, klasifikavimo
taisyklės), laikome čia, kad nereikėtų liesti kodo.
"""

# --- Duomenų šaltinis: Infostatyba atviri duomenys (data.gov.lt, rinkinys Nr. 1000; teikėjas SSVA, anksčiau VTPSI) ---
API_BASE = "https://get.data.gov.lt"
# 2025-07-03 duomenų teikėjo prašymu rinkinys perkeltas iš vtpsi į ssva (atviriduomenys/manifest);
# jei naujas kelias neatsako (404), bandomi MODEL_FALLBACKS
MODEL = "datasets/gov/ssva/infostatyba/Statinys"
MODEL_FALLBACKS = ["datasets/gov/vtpsi/infostatyba/Statinys"]
PAGE_LIMIT = 1000           # įrašų per užklausą
REQUEST_PAUSE_S = 1.0       # pauzė tarp užklausų (būkime mandagūs)
# Tie patys Infostatybos duomenys SSVA ArcGIS paslaugoje (data.gov.lt rinkinys Nr. 3740, geoportal.lt).
# Naudojama, kai data.gov.lt API užblokuotas ar neveikia (LT_SOURCE = "auto"), arba visada ("arcgis").
LT_ARCGIS_URL = "https://www.geoportal.lt/mapproxy/rest/services/infostatyba_duomenys/MapServer/0"
LT_SOURCE = "auto"          # "auto" – data.gov.lt, nepavykus – ArcGIS; "spinta" – tik data.gov.lt; "arcgis"
REQUEST_TIMEOUT_S = 90
USER_AGENT = "statybu-signalai/0.1 (+kontaktas@jusu-domenas.lt)"   # įrašykite savo kontaktą

# Kiek dienų atgal imti, jei sistema leidžiama pirmą kartą
FIRST_RUN_DAYS = 30
# Persidengimas su ankstesniu paleidimu (dienomis), kad nepraleistume vėluojančių įrašų
OVERLAP_DAYS = 7

# Laukų pavadinimai rinkinyje (jei teikėjas juos pakeistų, keičiame tik čia)
F = {
    "doc_nr": "dokumento_reg_nr",
    "doc_date": "dokumento_reg_data",
    "doc_text": "dokumento_kategorija",   # dokumento pavadinimas („Leidimas statyti naują (- us) statinį (- ius)“)
    "doc_type_code": "dok_tipo_kodas",     # dokumento kodas (LSNS, SRA, ...) – pagal jį nustatomas tipas
    "doc_kind": "dok_irasas",              # tik „prasymas“, „aktas“ arba „laukiama patvirtinimo“
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
    "row_id": "id",          # įrašo ID; „uuid“ – dokumento ID (bendras visiems jo statiniams), raktu netinka
}

# Dokumentų būsenos, kurias atmetame (mažosiomis raidėmis, tikrinama "contains"). Tikros reikšmės:
# Negaliojantis/Negaliojanti, Atmestas/Atmesta, Nepatenkintas, Neišduotas, Nutrauktas, Nepatvirtintas,
# „Paslėptas/ištrintas“, „Pasiūlymams nepritarta“. Prašymai, kurių būsena „Užregistruotas“, „Tikrinamas“,
# „Priimtas“ ar „Patenkintas“, paliekami.
EXCLUDED_STATUSES = ["negalioj", "atmest", "nepatenkint", "neišduot", "nutraukt", "nepatvirtint", "ištrint",
                     "nepritart", "panaikint", "atšaukt", "atsiimt"]

# Dokumento kodas (dok_tipo_kodas, jis yra ir dokumento numerio pradžioje) -> (tipas, žymė).
# Tipas None – dokumentas signalu nelaikomas (patikrinimai, privalomieji nurodymai, specialieji reikalavimai,
# prašymai, kurių galutinis dokumentas skelbiamas atskirai). Kodai be pavadinimo rinkinyje (ANN2, PTDP,
# PPVA, LNTO) atpažinti pagal jų įrašus – žymėje paliktas kodas. Kodai, kurių čia nėra, klasifikuojami pagal
# dokumento pavadinimą (SIGNAL_RULES); `diagnose` parodo dažniausius kodus.
LT_DOC_TYPES = {
    "SRA": ("prasymas", "Prašymas išduoti statybą leidžiantį dokumentą"),
    "TLDR": ("prasymas", "Prašymas išduoti leidimą (Vyriausybės lygmeniu)"),
    "ISP": ("prasymas", "Projektiniai pasiūlymai (visuomenės informavimas)"),
    "PSR": ("prasymas", "Prašymas išduoti specialiuosius reikalavimus"),
    "PPS": ("prasymas", "Prašymas išduoti prisijungimo sąlygas"),
    "PTDP": ("prasymas", "Projekto patikrinimo prašymas (PTDP)"),
    "PPVA": ("prasymas", "Prašymas (PPVA)"),
    "LSNS": ("leidimas_nauja", "Leidimas statyti naują statinį"),
    "SSIYV": ("leidimas_nauja", "Leidimas statyti (ypatingos valstybinės svarbos projektas)"),
    "LRS": ("leidimas_rekonstrukcija", "Leidimas rekonstruoti"),
    "RSIYV": ("leidimas_rekonstrukcija", "Leidimas rekonstruoti (ypatingos valstybinės svarbos projektas)"),
    "LAP": ("leidimas_atnaujinimas", "Leidimas atnaujinti (modernizuoti) pastatą"),
    "LSKR": ("leidimas_atnaujinimas", "Leidimas: kapitalinis remontas"),
    "LSPR": ("leidimas_atnaujinimas", "Leidimas: paprastasis remontas"),
    "LPSP": ("paskirties_keitimas", "Leidimas pakeisti paskirtį"),
    "LNTO": ("paskirties_keitimas", "Leidimas (LNTO): paskirties keitimas, remontas"),
    "LGS": ("griovimas", "Leidimas nugriauti"),
    "ACDC": ("griovimas", "Pažyma apie statinio nugriovimą"),
    "ACDUB": ("griovimas", "Pažyma apie nebaigto statyti statinio nugriovimą"),
    "ANN": ("pradzia", "Pranešimas apie statybos pradžią"),
    "ANN2": ("pradzia", "Pranešimas apie statybos pradžią (ANN2)"),
    "RPSP": ("pritarimas", "Rašytinis pritarimas statinio projektui"),
    "ACCA": ("uzbaigimas", "Statybos užbaigimo aktas"),
    "ARCCR": ("uzbaigimas", "Deklaracija apie statybos užbaigimą (registruojama)"),
    "ACCR": ("uzbaigimas", "Deklaracija apie statybos užbaigimą"),
    "ACCR2": ("uzbaigimas", "Deklaracija apie statybos užbaigimą (tvirtina ekspertas)"),
    "ACCE": ("uzbaigimas", "Deklaracija apie statybos užbaigimą (po ekspertizės)"),
    "ACUB": ("uzbaigimas", "Pažyma apie statybą be nukrypimų nuo projekto"),
    "ACUB2": ("uzbaigimas", "Pažyma apie statybą be nukrypimų nuo projekto (tvirtina ekspertas)"),
    # ne signalai: prašymai, kurių rezultatas – kitas dokumentas, patikrinimai, nurodymai, reikalavimai
    **{code: (None, "") for code in (
        "CCA", "CCR", "CCR2C", "RCCR", "CCE", "CUB", "CUB2C", "CDC", "ARCUB", "ANNPA", "CCPA",
        "SARD", "SRD", "SPRD", "STRD", "DSAR", "PS", "PKLA", "PEKA", "SEKA", "SPA", "SSA", "BIPA", "SLD",
        "PN", "PNUR", "PNURA", "PNSSA", "PNSD", "PNSDP", "PNSSP", "FOPPA", "PNTR", "CP", "WRI",
        "DEKRP", "ACCRC", "BCPPA", "PAPA", "SNUGA", "PSTER", "CSBP", "PBP")},
}

# Savivaldybė iš dokumento numerio („LSNS-21-261002-00834“: 21 – Kauno m. sav.). Kodai, kurie baigiasi
# nuliu (00, 20, 30), – nacionaliniai ar regioniniai išdavėjai; tada savivaldybė imama iš adreso.
LT_SAV_BY_DOC_CODE = {
    "01": "Vilniaus m. sav.", "02": "Šalčininkų r. sav.", "03": "Širvintų r. sav.", "04": "Švenčionių r. sav.",
    "05": "Trakų r. sav.", "06": "Elektrėnų sav.", "07": "Ukmergės r. sav.", "08": "Vilniaus r. sav.",
    "11": "Alytaus m. sav.", "12": "Druskininkų sav.", "13": "Alytaus r. sav.", "14": "Lazdijų r. sav.",
    "15": "Varėnos r. sav.", "21": "Kauno m. sav.", "22": "Birštono sav.", "23": "Prienų r. sav.",
    "24": "Kauno r. sav.", "25": "Jonavos r. sav.", "26": "Kaišiadorių r. sav.", "27": "Kėdainių r. sav.",
    "28": "Raseinių r. sav.", "31": "Klaipėdos m. sav.", "32": "Neringos sav.", "33": "Palangos m. sav.",
    "34": "Klaipėdos r. sav.", "35": "Kretingos r. sav.", "36": "Skuodo r. sav.", "37": "Šilutės r. sav.",
    "41": "Marijampolės sav.", "42": "Kalvarijos sav.", "43": "Kazlų Rūdos sav.", "44": "Šakių r. sav.",
    "45": "Vilkaviškio r. sav.", "51": "Panevėžio m. sav.", "52": "Biržų r. sav.", "53": "Kupiškio r. sav.",
    "54": "Panevėžio r. sav.", "55": "Pasvalio r. sav.", "56": "Rokiškio r. sav.", "61": "Šiaulių m. sav.",
    "62": "Akmenės r. sav.", "63": "Joniškio r. sav.", "64": "Pakruojo r. sav.", "65": "Kelmės r. sav.",
    "66": "Radviliškio r. sav.", "67": "Šiaulių r. sav.", "71": "Jurbarko r. sav.", "72": "Šilalės r. sav.",
    "73": "Tauragės r. sav.", "74": "Pagėgių sav.", "81": "Mažeikių r. sav.", "82": "Plungės r. sav.",
    "83": "Telšių r. sav.", "84": "Rietavo sav.", "91": "Visagino sav.", "92": "Anykščių r. sav.",
    "93": "Ignalinos r. sav.", "94": "Molėtų r. sav.", "95": "Utenos r. sav.", "96": "Zarasų r. sav.",
}

# --- Signalų tipai ---
# Atsarginės taisyklės dokumentams, kurių kodo nėra LT_DOC_TYPES (ir kitiems tekstams).
# Tikrinama eilės tvarka: pirmas atitikęs raktažodis lemia tipą.
# Raktažodžiai tikrinami dokumento pavadinime (dokumento_kategorija) mažosiomis raidėmis.
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
    ("leidimas_atnaujinimas", "Leidimas: kapitalinis remontas", ["kapitalin"]),
    ("paskirties_keitimas", "Leidimas: paskirties keitimas", ["leidimas pakeisti", "paskirties keitim"]),
    ("pritarimas", "Rašytinis pritarimas", ["rašytinis pritarimas", "rasytinis pritarimas"]),
    ("griovimas", "Leidimas griauti", ["leidimas griauti", "nugriauti"]),
    ("pradzia", "Statybos pradžia", ["statybos pradži", "pradėti statyb"]),
    # bendras prašymas (pvz., „Prašymas išduoti rašytinį pritarimą“) – po visų tikslesnių taisyklių
    ("prasymas", "Prašymas", ["prašymas", "prasymas"]),
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
        "daugiabu": 3, "trijų ir daugiau butų": 3,
        "dviejų butų": 0, "vieno buto": 0,
        "administracin": 2, "prekybos": 2, "sandėliavimo": 2, "gamybos": 2,
        "viešbuči": 2, "gydymo": 2, "mokslo": 2,
        "vienbuči": 0, "dvibuči": 0, "pagalbinio": -1, "inžinerin": -1, "tinkl": -1,
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
# Kurias šalis `run` ir `fetch` apdoroja numatytai (Estija – per viešą EHR statinių API, žr. žemiau).
RUN_COUNTRIES = ["LT", "LV", "PL", "EE"]

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
# Pranešimai į registrą patenka po kelių savaičių, todėl jie kas kartą peržiūrimi ilgesniu langu
PL_ZGLOSZENIA_LOOKBACK_DAYS = 90
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

# --- Estija: Ehitisregister (EHR) ---
# Pagrindinis kelias – viešas statinių API be registracijos: pokyčių srautas (kurie statiniai keitėsi)
# ir kiekvieno statinio dokumentų istorija bei duomenys. ~300 pakitusių statinių per dieną.
EE_BUILDING_API = "https://livekluster.ehr.ee/api/building/v2"
EE_API_RPS = 1.0            # užklausų per sekundę; dažniau Cloudflare atsako HTTP 429 ir ~20 min. riboja
EE_API_MAX_429 = 40         # tiek HTTP 429 atsakymų – gavimas sustabdomas (kitas paleidimas tęs nuo ten pat)
EE_FIRST_RUN_DAYS = 7       # pirmą kartą imama tiek dienų (~150–250 pastatų per dieną, ~2 s kiekvienam)
EE_API_MAX_BUILDINGS = 2000 # daugiausia statinių per vieną kartą (~2 s kiekvienam, ~1 val.); likusius – kitą kartą
EE_API_MAX_FAILED = 0.05    # jei negauta daugiau nei 5 % statinių, gavimas nutraukiamas (išsaugoma, kas gauta)
EE_API_MAX_FAILS_IN_ROW = 15  # tiek nesėkmių iš eilės – EHR laikomas neveikiančiu, gavimas nutraukiamas
EE_API_RETRY_TIMES = 4      # nepavykęs statinys kartojamas tiek paleidimų, paskui – praleidžiamas
# Inžineriniai statiniai (EHR kodas prasideda „2“: vamzdynai, gręžiniai, gatvės, linijos) – pusė pokyčių srauto,
# bet mažai vertės pastatų rinkai. False – tikrinami tik pastatai (kodas prasideda „1“), užklausų perpus mažiau.
EE_RAJATISED = False
# Dokumento tipas (EHR doty_id) -> (signalo tipas, žymė). Kiti tipai (adresų, savininkų, energinio
# naudingumo, registro pataisymai) – ne statybos įvykiai, praleidžiami. Visas sąrašas:
# https://livekluster.ehr.ee/api/classifier/v1/alldocumenttypes
EE_DOC_TYPES = {
    "11002": ("prasymas", "projektavimo sąlygų prašymas"),
    "11802": ("prasymas", "projektavimo sąlygos"),
    "111": ("prasymas", "rašytinio sutikimo prašymas"),
    "11119": ("prasymas", "rašytinio sutikimo prašymas (nedidelis statinys)"),
    "112": ("prasymas", "statybos leidimo prašymas"),
    "11219": ("prasymas", "statybos leidimo prašymas (naujas statinys)"),
    "11271": ("prasymas", "statybos leidimo prašymas"),
    "121": ("pritarimas", "rašytinis sutikimas"),
    "122": ("leidimas_nauja", "statybos leidimas"),
    "12219": ("leidimas_nauja", "statybos leidimas (naujas statinys)"),
    "12271": ("leidimas_nauja", "statybos leidimas"),
    "12229": ("leidimas_rekonstrukcija", "statybos leidimas (išplėtimas)"),
    "12241": ("leidimas_rekonstrukcija", "statybos leidimas (perstatymas)"),
    "12251": ("leidimas_atnaujinimas", "statybos leidimas (dalies pakeitimas)"),
    "11201": ("pranesimas", "statybos pranešimas"),
    "11202": ("pranesimas", "statybos pranešimas (naujas statinys)"),
    "11581": ("pradzia", "statybos pradžios pranešimas"),
    "113": ("uzbaigimas", "naudojimo leidimo prašymas"),
    "11371": ("uzbaigimas", "naudojimo leidimo prašymas"),
    "11301": ("uzbaigimas", "naudojimo pranešimas"),
    "1": ("uzbaigimas", "naudojimo leidimas"),
    "123": ("uzbaigimas", "naudojimo leidimas"),
    "12319": ("uzbaigimas", "naudojimo leidimas (naujas statinys)"),
    "12329": ("uzbaigimas", "naudojimo leidimas (išplėtimas)"),
    "12341": ("uzbaigimas", "naudojimo leidimas (perstatymas)"),
    "12351": ("uzbaigimas", "naudojimo leidimas (dalies pakeitimas)"),
    "12359": ("uzbaigimas", "naudojimo leidimas (dalinis)"),
    "12371": ("uzbaigimas", "naudojimo leidimas"),
    "11582": ("griovimas", "griovimo pranešimas"),
    "12291": ("griovimas", "dalinio griovimo leidimas"),
    "12299": ("griovimas", "griovimo leidimas"),
}
# Atsarginis kelias – atvirų duomenų ataskaitos, užsakomos el. paštu (python sistema.py ee-order).
EE_API = "https://livekluster.ehr.ee/api/av/v2"
EE_REPORT = "eh_ehitised"               # statiniai su būsena, adresu, datomis
EE_COORD_REPORT = "ehitise_ruumikuju"   # statinių kontūrai ir atskaitos taškas (koordinatėms)
# Užsakant ataskaitą imamos šios būsenos (statiniai, kurie dar tik planuojami arba statomi)
EE_ORDER_STATUSES = ["EHITIS_SEISUND_KAVAN", "EHITIS_SEISUND_PYSTI"]
# Būsenos kodo fragmentas -> (tipas, žymė); None – atmetama. Tikrinama eilės tvarka.
# Nuo 2022-05-30 naudojamos KAVAN, PYSTI, OLEMA, LAMEL, LAMUT, REATA, KUSTU; senesni kodai – seniems failams.
EE_STATUSES = [
    ("EIKEH", None, "leidimas negalioja"), ("KUSTU", None, "ištrintas"), ("REATA", None, "neįgyvendintas"),
    ("REG_OBJ_LOPP", None, "registro objektas panaikintas"), ("ARHIIVIS", None, "archyve"),
    ("MAARAMATA", None, "būsena nenustatyta"),
    ("LAMMUT_LUBA", "griovimas", "griovimo leidimas"), ("LAMMUTAMISEL", "griovimas", "griaunamas"),
    ("LAMEL", "griovimas", "griaunamas"), ("LAMMUTATUD", "griovimas", "nugriautas"),
    ("LAMUT", "griovimas", "nugriautas"),
    # „Kavandatav“: išduotos projektavimo sąlygos arba statybos leidimas, statyba dar nepradėta
    ("KAVAN", "prasymas", "planuojamas (projektavimo sąlygos ar statybos leidimas)"),
    ("PLANEERITAV", "prasymas", "planuojamas"), ("EHITAM_LUBA", "leidimas_nauja", "statybos leidimas"),
    ("PYSTI", "pradzia", "statomas"), ("EHITAMISEL", "pradzia", "statomas"),
    ("KASUT_OSALINE", "uzbaigimas", "iš dalies naudojamas"), ("KASUTUSEL", "uzbaigimas", "naudojamas"),
    ("OLEMA", "uzbaigimas", "pastatytas"),
]

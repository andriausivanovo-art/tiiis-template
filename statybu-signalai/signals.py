# -*- coding: utf-8 -*-
"""Žalių įrašų pavertimas signalais: grupavimas, tipas, vieta, balas."""
import re

import config
from saltiniai import fold

F = config.F

_MUNI_RE = re.compile(r"([A-ZĄČĘĖĮŠŲŪŽ][\wąčęėįšųūž\-]*(?:\s(?:r\.|rajono|m\.|miesto))?\s?sav\.)")
_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")

# 60 Lietuvos savivaldybių: (pavadinimas kilmininku, rūšis: m – miesto, r – rajono, "" – be rūšies)
MUNICIPALITIES = [
    ("Akmenės", "r"), ("Alytaus", "m"), ("Alytaus", "r"), ("Anykščių", "r"), ("Birštono", ""), ("Biržų", "r"),
    ("Druskininkų", ""), ("Elektrėnų", ""), ("Ignalinos", "r"), ("Jonavos", "r"), ("Joniškio", "r"),
    ("Jurbarko", "r"), ("Kaišiadorių", "r"), ("Kalvarijos", ""), ("Kauno", "m"), ("Kauno", "r"),
    ("Kazlų Rūdos", ""), ("Kėdainių", "r"), ("Kelmės", "r"), ("Klaipėdos", "m"), ("Klaipėdos", "r"),
    ("Kretingos", "r"), ("Kupiškio", "r"), ("Lazdijų", "r"), ("Marijampolės", ""), ("Mažeikių", "r"),
    ("Molėtų", "r"), ("Neringos", ""), ("Pagėgių", ""), ("Pakruojo", "r"), ("Palangos", "m"), ("Panevėžio", "m"),
    ("Panevėžio", "r"), ("Pasvalio", "r"), ("Plungės", "r"), ("Prienų", "r"), ("Radviliškio", "r"),
    ("Raseinių", "r"), ("Rietavo", ""), ("Rokiškio", "r"), ("Skuodo", "r"), ("Šakių", "r"), ("Šalčininkų", "r"),
    ("Šiaulių", "m"), ("Šiaulių", "r"), ("Šilalės", "r"), ("Šilutės", "r"), ("Širvintų", "r"), ("Švenčionių", "r"),
    ("Tauragės", "r"), ("Telšių", "r"), ("Trakų", "r"), ("Ukmergės", "r"), ("Utenos", "r"), ("Varėnos", "r"),
    ("Vilkaviškio", "r"), ("Vilniaus", "m"), ("Vilniaus", "r"), ("Visagino", ""), ("Zarasų", "r"),
]
# Miestų adresuose savivaldybė nerašoma („Vilnius, Ozo g. 25“): miestas vardininku -> savivaldybė
CITIES = {
    "Vilnius": "Vilniaus m. sav.", "Grigiškės": "Vilniaus m. sav.", "Kaunas": "Kauno m. sav.",
    "Klaipėda": "Klaipėdos m. sav.", "Šiauliai": "Šiaulių m. sav.", "Panevėžys": "Panevėžio m. sav.",
    "Alytus": "Alytaus m. sav.", "Palanga": "Palangos m. sav.", "Marijampolė": "Marijampolės sav.",
    "Druskininkai": "Druskininkų sav.", "Birštonas": "Birštono sav.", "Elektrėnai": "Elektrėnų sav.",
    "Visaginas": "Visagino sav.", "Kazlų Rūda": "Kazlų Rūdos sav.", "Kalvarija": "Kalvarijos sav.",
    "Pagėgiai": "Pagėgių sav.", "Rietavas": "Rietavo sav.", "Neringa": "Neringos sav.", "Nida": "Neringos sav.", "Juodkrantė": "Neringos sav.",
    # rajonų savivaldybių centrai ir didesni miestai
    "Naujoji Akmenė": "Akmenės r. sav.", "Anykščiai": "Anykščių r. sav.", "Biržai": "Biržų r. sav.",
    "Ignalina": "Ignalinos r. sav.", "Jonava": "Jonavos r. sav.", "Joniškis": "Joniškio r. sav.",
    "Jurbarkas": "Jurbarko r. sav.", "Kaišiadorys": "Kaišiadorių r. sav.", "Garliava": "Kauno r. sav.",
    "Kelmė": "Kelmės r. sav.", "Kėdainiai": "Kėdainių r. sav.", "Gargždai": "Klaipėdos r. sav.",
    "Kretinga": "Kretingos r. sav.", "Kupiškis": "Kupiškio r. sav.", "Lazdijai": "Lazdijų r. sav.",
    "Mažeikiai": "Mažeikių r. sav.", "Molėtai": "Molėtų r. sav.", "Pakruojis": "Pakruojo r. sav.",
    "Pasvalys": "Pasvalio r. sav.", "Plungė": "Plungės r. sav.", "Prienai": "Prienų r. sav.",
    "Radviliškis": "Radviliškio r. sav.", "Raseiniai": "Raseinių r. sav.", "Rokiškis": "Rokiškio r. sav.",
    "Skuodas": "Skuodo r. sav.", "Šakiai": "Šakių r. sav.", "Šalčininkai": "Šalčininkų r. sav.",
    "Kuršėnai": "Šiaulių r. sav.", "Šilalė": "Šilalės r. sav.", "Šilutė": "Šilutės r. sav.",
    "Širvintos": "Širvintų r. sav.", "Švenčionys": "Švenčionių r. sav.", "Tauragė": "Tauragės r. sav.",
    "Telšiai": "Telšių r. sav.", "Trakai": "Trakų r. sav.", "Lentvaris": "Trakų r. sav.",
    "Ukmergė": "Ukmergės r. sav.", "Utena": "Utenos r. sav.", "Varėna": "Varėnos r. sav.",
    "Vilkaviškis": "Vilkaviškio r. sav.", "Nemenčinė": "Vilniaus r. sav.", "Zarasai": "Zarasų r. sav.",
}
_CITY_BY_FOLD = {fold(k): v for k, v in CITIES.items()}
_KIND = {"m": r"(?:m\.?|miesto)\s*", "r": r"(?:r\.?|raj\.?|rajono)\s*", "": ""}
_MUNI_PATTERNS = [
    (re.compile(r"(?<![a-z])" + re.escape(fold(base)).replace(r"\ ", r"\s+") + r"\s+" + _KIND[kind] + r"sav"),
     f"{base} {kind}. sav." if kind else f"{base} sav.")
    for base, kind in MUNICIPALITIES
]


def classify(doc_text):
    """Tipas pagal dokumento pavadinimą (atsarginis būdas, kai kodo nėra LT_DOC_TYPES)."""
    t = (doc_text or "").lower()
    for code, label, keys in config.SIGNAL_RULES:
        if any(k in t for k in keys):
            return code, label
    return "kita", "Kita"


def doc_code(row):
    """Dokumento kodas: dok_tipo_kodas arba dokumento numerio pradžia („LSNS-21-261002-00834“ -> LSNS)."""
    code = (row.get(F["doc_type_code"]) or "").strip().upper()
    return code or str(row.get(F["doc_nr"]) or "").split("-", 1)[0].strip().upper()


def doc_type(row):
    """(tipas, žymė) pagal dokumento kodą, o nežinomam kodui – pagal pavadinimą. Tipas None – ne signalas."""
    hit = config.LT_DOC_TYPES.get(doc_code(row))
    if hit:
        return hit
    text = row.get(F["doc_text"]) or ""
    if "patikrinimo akt" in text.lower():          # patikrinimų aktai (nauji kodai) – ne signalai
        return None, ""
    sig_type, label = classify(text)
    if sig_type == "kita" and fold(row.get(F["doc_kind"])).startswith("prasym"):
        sig_type, label = "prasymas", "Prašymas"
    return sig_type, (text[:120] if sig_type == "kita" and text else label)


def municipality_from_doc(doc_nr):
    """Savivaldybė iš dokumento numerio („SRA-24-260915-03074“ -> Kauno r. sav.); '' – jei nežinoma."""
    parts = str(doc_nr or "").split("-")
    return config.LT_SAV_BY_DOC_CODE.get(parts[1], "") if len(parts) > 2 else ""


def municipality(address):
    """Savivaldybė iš adreso: „Kauno r. sav.“ (atpažįsta ir „Kauno rajono savivaldybė“, didžiąsias raides,
    miesto adresą be savivaldybės – „Vilnius, Ozo g. 25“)."""
    if not address:
        return ""
    text = fold(address)
    hits = [(m.start(), name) for rx, name in _MUNI_PATTERNS for m in [rx.search(text)] if m]
    if hits:
        return min(hits)[1]
    city = _CITY_BY_FOLD.get(text.split(",")[0].strip())
    if city:
        return city
    m = _MUNI_RE.search(address)
    if not m:
        return ""
    s = m.group(1)
    s = s.replace(" rajono ", " r. ").replace(" miesto ", " m. ")
    return s.strip()


def wgs_point(value):
    """'POINT (54.67 25.22)' arba 'POINT (25.22 54.67)' -> (lat, lon). Lietuvoje platuma 53–57, ilguma 20–27."""
    if not value:
        return None, None
    nums = [float(x) for x in _NUM_RE.findall(str(value))]
    if len(nums) < 2:
        return None, None
    a, b = nums[0], nums[1]
    if 53 <= a <= 57 and 20 <= b <= 27:
        return a, b
    if 53 <= b <= 57 and 20 <= a <= 27:
        return b, a
    return None, None


def _uniq(values, limit=None):
    out = []
    for v in values:
        v = (v or "").strip()
        if v and v not in out:
            out.append(v)
    return out[:limit] if limit else out


def _purpose_points(purpose):
    p = (purpose or "").lower()
    return max([w for k, w in config.SCORE["purpose"].items() if k in p] or [0])


def score(sig_type, purposes, category, object_count):
    s = config.SCORE["type"].get(sig_type, 0)
    # paskirtis vertinama pagal vertingiausią statinį: tinklai ar ūkinis pastatas prie namo balo nemažina
    s += max([_purpose_points(p) for p in purposes] or [0])
    c = (category or "").lower()
    for k, w in config.SCORE["category"].items():
        if c.startswith(k):
            s += w
            break
    if object_count >= config.SCORE["objects_bonus_from"]:
        s += 1
    return s


def is_excluded(rows):
    """Negaliojantis, atmestas ar kitaip atmestinas dokumentas arba ne signalo tipas (patikrinimas ir pan.)."""
    st = " ".join((r.get(F["doc_status"]) or "") for r in rows).lower()
    return any(x in st for x in config.EXCLUDED_STATUSES) or (bool(rows) and doc_type(rows[0])[0] is None)


def build_signal(doc_nr, rows):
    """Iš vieno dokumento įrašų (statinių) sudaro vieną signalą."""
    first = rows[0]
    sig_type, label = doc_type(first)
    sig_type = sig_type or "kita"
    purposes = _uniq([r.get(F["new_purpose"]) or r.get(F["purpose"]) for r in rows])
    cats = _uniq([r.get(F["category"]) for r in rows])
    # svarbiausia kategorija: ypatingasis > neypatingasis > nesudėtingasis
    order = {"ypatingasis": 0, "neypatingasis": 1, "nesudėtingasis": 2}
    cats.sort(key=lambda c: next((v for k, v in order.items() if c.lower().startswith(k)), 9))
    category = cats[0] if cats else ""
    names = _uniq([r.get(F["object_name"]) for r in rows])
    addr = next((r.get(F["address"]) for r in rows if r.get(F["address"])), "")
    lat = lon = None
    for r in rows:
        lat, lon = wgs_point(r.get(F["point_wgs"]))
        if lat:
            break
    # statinys atpažįstamas pagal unikalų numerį, o naujas (dar neįregistruotas) – pagal statinio_id
    n_obj = len(_uniq([str(r.get(F["unique_nr"]) or r.get(F["object_id"]) or r.get(F["object_name"]) or i)
                       for i, r in enumerate(rows)]))
    return {
        "signal_id": doc_nr,
        "doc_date": (first.get(F["doc_date"]) or "")[:10],
        "signal_type": sig_type,
        "signal_label": label,
        "doc_text": first.get(F["doc_text"]) or label,
        "works_type": "; ".join(_uniq([r.get(F["works_type"]) for r in rows])),
        "purposes": "; ".join(purposes),
        "category": category,
        "object_names": "; ".join(names[:5]) + (f" (+{len(names) - 5})" if len(names) > 5 else ""),
        "object_count": n_obj,
        "address": addr,
        "municipality": municipality_from_doc(first.get(F["doc_nr"]) or doc_nr) or municipality(addr)
        or municipality(first.get(F["project_name"])),
        "cadastre": "; ".join(_uniq([r.get(F["cadastre"]) for r in rows], 5)),
        "project_name": first.get(F["project_name"]) or "",
        "project_nr": first.get(F["project_nr"]) or "",
        "lat": lat,
        "lon": lon,
        "point_lks": next((r.get(F["point_lks"]) for r in rows if r.get(F["point_lks"])), ""),
        "score": score(sig_type, purposes, category, n_obj),
    }

# -*- coding: utf-8 -*-
"""Estija: Ehitisregister (EHR) atvirų duomenų API, https://livekluster.ehr.ee/api/av/v2.

EHR ataskaitos generuojamos pagal užsakymą: `python sistema.py ee-order --email ...` užsako
„eh_ehitised“ (ir, jei reikia, „ehitise_ruumikuju“) ataskaitą, nuoroda atsiunčiama el. paštu.
Gautą failą (ar nuorodą) įkelkite: `python sistema.py import --salis EE <failas|nuoroda>`.

Signalas = (statinys, būsena): planuojamas („Kavandatav“), statomas („Püstitamisel“),
neseniai pastatytas („Olemas“ su šių ar praėjusių metų pirmuoju naudojimo leidimu).
Koordinatės – iš „ehitise_ruumikuju“ atskaitos taško (L-EST97), perskaičiuojamos į WGS84.
Klasifikatoriai (paskirtys, savivaldybės, būsenos) – ee_klasifikatoriai.json (EHR API kopija).
"""
import contextlib
import json
import math
import os
import urllib.error
import urllib.request
from datetime import date

import config
import db
from saltiniai import SourceError, csv_rows, fold, header_of, local_file, norm_date, slug

CODE = "EE"
NAME = "Estija – Ehitisregister (EHR)"

F = {
    "status": "seisund", "code": "ehr_kood", "use": "kaos_id_peamine", "name": "nimetus",
    "kind": "rajatis_hoone", "start": "eh_alust_kp", "use_from": "kav_kasutus_kp", "county": "maakond",
    "municipality": "omavalitsus", "created": "date_created", "updated": "date_updated",
    "address": "taisaadress", "short_address": "lahiaadress", "first_use": "esmane_kasutus",
}
G = {"code": "ehr_kood", "x": "viitepunkt_x", "y": "viitepunkt_y"}   # ehitise_ruumikuju

USE_LT = {  # kasutusotstarbe kodo pradžia -> lietuviškas pavadinimas (ilgiausias sutapimas)
    "111": "vieno buto gyvenamieji namai", "1121": "dviejų butų namai", "1122": "daugiabučiai (3 ir daugiau butų)",
    "113": "bendrabučiai, globos namai", "121": "apgyvendinimo ir maitinimo pastatai", "122": "biurų pastatai",
    "123": "prekybos ir paslaugų pastatai", "124": "transporto pastatai", "125": "pramonės ir sandėlių pastatai",
    "126": "visuomeniniai pastatai (švietimas, sveikata, kultūra, sportas)", "127": "kiti negyvenamieji pastatai",
    "21": "transporto statiniai", "22": "vamzdynai, ryšių ir elektros linijos", "23": "pramonės statiniai",
    "24": "kiti statiniai",
}

_CLASS = None


def classifiers():
    global _CLASS
    if _CLASS is None:
        with open(os.path.join(os.path.dirname(__file__), "ee_klasifikatoriai.json"), encoding="utf-8") as fh:
            _CLASS = json.load(fh)
    return _CLASS


def _prefix_match(code, table):
    hits = [k for k in table if str(code).startswith(k)]
    return table[max(hits, key=len)] if hits else None


# --- L-EST97 (EPSG:3301, Lamberto konforminė kūginė projekcija, GRS80) ---
_A, _FL = 6378137.0, 1 / 298.257222101
_E2 = _FL * (2 - _FL)
_E = math.sqrt(_E2)
_LAT1, _LAT2, _LAT0, _LON0 = (math.radians(v) for v in (59 + 20 / 60, 58.0, 57.51755393055556, 24.0))
_FE, _FN = 500000.0, 6375000.0


def _m(phi):
    return math.cos(phi) / math.sqrt(1 - _E2 * math.sin(phi) ** 2)


def _t(phi):
    es = _E * math.sin(phi)
    return math.tan(math.pi / 4 - phi / 2) / ((1 - es) / (1 + es)) ** (_E / 2)


_N = (math.log(_m(_LAT1)) - math.log(_m(_LAT2))) / (math.log(_t(_LAT1)) - math.log(_t(_LAT2)))
_AF = _A * _m(_LAT1) / (_N * _t(_LAT1) ** _N)
_RHO0 = _AF * _t(_LAT0) ** _N


def wgs_to_lest(lat, lon):
    """WGS84 -> L-EST97 (šiaurė x, rytai y)."""
    rho = _AF * _t(math.radians(lat)) ** _N
    theta = _N * (math.radians(lon) - _LON0)
    return _FN + _RHO0 - rho * math.cos(theta), _FE + rho * math.sin(theta)


def lest_to_wgs(north, east):
    """L-EST97 (šiaurė x, rytai y) -> WGS84 (platuma, ilguma)."""
    dx, dy = east - _FE, _RHO0 - (north - _FN)
    t = (math.hypot(dx, dy) / _AF) ** (1 / _N)
    lon = math.atan2(dx, dy) / _N + _LON0
    phi = math.pi / 2 - 2 * math.atan(t)
    for _ in range(8):
        es = _E * math.sin(phi)
        phi = math.pi / 2 - 2 * math.atan(t * ((1 - es) / (1 + es)) ** (_E / 2))
    return math.degrees(phi), math.degrees(lon)


def point_from_lest(x, y):
    """EHR atskaitos taškas -> (lat, lon). Estijoje šiaurės koordinatė ~6,3–6,7 mln., rytų ~0,3–0,8 mln."""
    try:
        a, b = float(str(x).replace(",", ".")), float(str(y).replace(",", "."))
    except (TypeError, ValueError):
        return None, None
    north, east = (a, b) if a > b else (b, a)
    if not (6.2e6 < north < 6.7e6 and 3e5 < east < 8e5):
        return None, None
    return lest_to_wgs(north, east)


# --- Būsenos ---

def status(value):
    """EHR būsena (kodas arba tekstas) -> (kodas, tipas, žymė); tipas None – atmetama."""
    v = (value or "").strip()
    by_text = {fold(t): k for k, t in classifiers()["seisund"].items()}
    code = by_text.get(fold(v), v).upper()
    for fragment, typ, label in config.EE_STATUSES:
        if fragment in code:
            return code, typ, label
    return code, "kita", v.lower()


def _kind(path):
    head = header_of(path)
    if G["x"] in head:
        return "ruumikuju"
    if F["status"] in head and F["code"] in head:
        return "ehitised"
    raise SourceError(f"{os.path.basename(path)}: neatpažintas EHR failas (stulpeliai: {', '.join(head[:6])}…)")


def select(con, files, since, today=None):
    today = today or date.today()
    if files.get("ruumikuju"):
        points = []
        for r in csv_rows(files["ruumikuju"]):
            lat, lon = point_from_lest(r.get(G["x"]), r.get(G["y"]))
            if lat and r.get(G["code"]):
                points.append((r[G["code"]].strip(), lat, lon))
        db.set_points(con, CODE, points)
    if not files.get("ehitised"):
        return []
    items = []
    for r in csv_rows(files["ehitised"]):
        code = (r.get(F["code"]) or "").strip()
        st_code, typ, _ = status(r.get(F["status"]))
        if not code or typ is None:
            continue
        if typ == "uzbaigimas":
            try:
                if int(float(r.get(F["first_use"]) or 0)) < today.year - 1:
                    continue   # seniai stovintis statinys, kurio įrašas tiesiog atnaujintas
            except ValueError:
                continue
        created, updated = norm_date(r.get(F["created"])), norm_date(r.get(F["updated"]))
        event = created if typ == "prasymas" and created else (updated or created)
        if not event or event < since:
            continue
        r["_ivykio_data"] = event
        key = f"{CODE}:{code}:{slug(st_code)}"
        items.append((key, key, event, r))
    return items


def read_files(con, paths, since, today=None):
    with contextlib.ExitStack() as stack:
        files = {}
        for p in paths:
            local = stack.enter_context(local_file(p))
            files[_kind(local)] = local
        return select(con, files, since, today)


def fetch_items(con, since, today=None):
    raise SourceError("Estijos EHR ataskaitą reikia užsisakyti: python sistema.py ee-order --email <adresas>; "
                      "gautą failą įkelkite: python sistema.py import --salis EE <failas arba nuoroda>")


def order_report(email, report_code=None, statuses=None, counties=None):
    """Užsako EHR ataskaitą (POST /reports); nuoroda atsiunčiama nurodytu el. paštu."""
    payload = {"report_code": report_code or config.EE_REPORT, "email_address": email, "report_format": "csv",
               "seisund": statuses if statuses is not None else config.EE_ORDER_STATUSES}
    if counties:
        payload["county"] = counties
    req = urllib.request.Request(f"{config.EE_API}/reports", data=json.dumps(payload).encode("utf-8"),
                                 method="POST", headers={"Content-Type": "application/json",
                                                         "User-Agent": config.USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=config.REQUEST_TIMEOUT_S) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        raise SourceError(f"EHR atsakė HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}") from e
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise SourceError(f"EHR nepasiekiamas: {e}") from e


def county_codes(names):
    """Apskričių pavadinimai arba kodai -> EHAK kodai („Harju“ -> „37“)."""
    table = classifiers()["maakond"]
    out = []
    for n in names:
        n = n.strip()
        hit = n if n in table else next((k for k, v in table.items() if fold(v).startswith(fold(n))), None)
        if not hit:
            raise SourceError(f"nežinoma apskritis „{n}“; galimos: {', '.join(table.values())}")
        out.append(hit)
    return out


def build_signal(doc_nr, rows, con=None):
    r = rows[0]
    code = (r.get(F["code"]) or "").strip()
    st_code, typ, label = status(r.get(F["status"]))
    cls = classifiers()
    use_id = str(r.get(F["use"]) or "").split(".")[0]
    use_code, use_et = cls["kaos"].get(use_id, [use_id, ""])
    use_lt = _prefix_match(use_code, USE_LT) or ""
    purposes = f"{use_lt} ({use_et})" if use_lt and use_et else (use_lt or use_et)
    points = _prefix_match(use_code, config.SCORE_PURPOSE["EE"])
    if points is None:
        points = -1 if (r.get(F["kind"]) or "").upper() == "R" else 0
    municipality = cls["omavalitsus"].get(str(r.get(F["municipality"]) or "").strip()) \
        or cls["maakond"].get(str(r.get(F["county"]) or "").strip(), "")
    lat, lon = db.get_point(con, CODE, code) if con is not None else (None, None)
    when = [f"planuojama pradžia {norm_date(r.get(F['start']))}" if norm_date(r.get(F["start"])) else "",
            f"naudojimas nuo {norm_date(r.get(F['use_from']))}" if norm_date(r.get(F["use_from"])) else ""]
    return {
        "signal_id": doc_nr,
        "country": CODE,
        "doc_date": r.get("_ivykio_data") or norm_date(r.get(F["updated"])),
        "signal_type": typ or "kita",
        "signal_label": f"EE: {label}",
        "doc_text": f"EHR {code} · {cls['seisund'].get(st_code, st_code)}",
        "works_type": "; ".join(w for w in when if w),
        "purposes": purposes,
        "category": "statinys (rajatis)" if (r.get(F["kind"]) or "").upper() == "R" else "pastatas (hoone)",
        "object_names": r.get(F["name"]) or use_et or "",
        "object_count": 1,
        "address": r.get(F["address"]) or r.get(F["short_address"]) or "",
        "municipality": municipality,
        "cadastre": "",
        "project_name": r.get(F["name"]) or "",
        "project_nr": code,
        "lat": lat,
        "lon": lon,
        "point_lks": "",
        "score": config.SCORE["type"].get(typ, 0) + points,
    }


def is_excluded(rows):
    return any(status(r.get(F["status"]))[1] is None for r in rows)


def diagnose():
    try:
        req = urllib.request.Request(f"{config.EE_API}/reports/{config.EE_REPORT}",
                                     headers={"User-Agent": config.USER_AGENT})
        with urllib.request.urlopen(req, timeout=config.REQUEST_TIMEOUT_S) as resp:
            cols = [c["column_name"] for c in json.load(resp)["data"]["description"]]
    except (OSError, ValueError, KeyError, TypeError) as e:
        print(f"  EE: KLAIDA {e}")
        return False
    missing = [c for c in F.values() if c not in cols]
    print(f"  EE {config.EE_REPORT}: {len(cols)} stulpeliai" +
          (f", TRŪKSTA: {', '.join(missing)}" if missing else ", laukai OK"))
    return not missing

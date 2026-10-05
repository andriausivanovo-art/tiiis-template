# -*- coding: utf-8 -*-
"""Latvija: Būvniecības informācijas sistēma (BIS) atviri duomenys, data.gov.lv (CC0, kasdien).

Naudojami trys rinkiniai:
  „Būvniecības lietu saraksts“   – byla, institucija, prašymo rūšis, dabartinė stadija, sukūrimo data;
  „Būvniecības lietu objekti“    – bylos statiniai: adresas, savivaldybė, kadastro žymuo, WGS koordinatės;
  „Jaunbūvju ģeotelpiskie dati“  – naujų pastatų planuojama pagrindinė paskirtis.
Rinkiniuose yra tik dabartinė bylos stadija, todėl signalas = (byla, stadija): nauja byla arba
jau žinomos bylos stadijos pasikeitimas (pvz., „Iecere“ -> „Būvdarbi“) tampa nauju įvykiu.
"""
import contextlib
import json
import os
import shutil
import tempfile
import urllib.request
from datetime import date, timedelta

import config
import db
import signals
from saltiniai import SourceError, csv_rows, download, fold, header_of, local_file, norm_date, slug

CODE = "LV"
NAME = "Latvija – BIS (data.gov.lv)"

F = {
    "case": "Buvniecibas_lietas_numurs",
    "authority": "Atbildigas_iestades_nosaukums",
    "application": "Buvniecibas_iesnieguma_veids",
    "name": "Objekta_nosaukums",
    "stage": "Aktuala_stadija",
    "works": "Buvniecibas_veids",
    "created": "Lietas_izveidosanas_datums",
    "cadastre": "Buves_kadastra_apzimejums",
    "lon": "Buves_atrasanas_vieta_geografiskais_garums",
    "lat": "Buves_atrasanas_vieta_geografiskais_platums",
    "object": "Buves_nosaukums",
    "address": "Buves_objekta_adreses_teksts",
    "address_new": "Buves_adreses_teksts",
    "territory": "Administrativas_teritorijas_nosaukums",
    "use": "Planotais_buves_galvenais_lietosanas_veids",
}
# Pagal kurį stulpelį atpažįstame failą
KINDS = {"lietas": F["stage"], "objekti": F["address"], "jaunbuves": F["use"]}
MAX_OBJECTS = 30

USES_LT = {
    "Viena dzīvokļa mājas": "vieno buto namai",
    "Divu dzīvokļu mājas": "dviejų butų namai",
    "Triju vai vairāku dzīvokļu mājas": "daugiabučiai (3 ir daugiau butų)",
    "Dažādu sociālo grupu kopdzīvojamās mājas": "bendrabučiai, globos namai",
    "Viesnīcas un sabiedriskās ēdināšanas ēkas": "viešbučiai ir maitinimo pastatai",
    "Citas īslaicīgas apmešanās ēkas": "kiti trumpalaikio apgyvendinimo pastatai",
    "Biroju ēkas": "biurų pastatai",
    "Vairumtirdzniecības un mazumtirdzniecības ēkas": "prekybos pastatai",
    "Sakaru ēkas, stacijas, termināļi un ar tiem saistītās ēkas": "ryšių ir transporto pastatai",
    "Garāžu ēkas": "garažai",
    "Rūpnieciskās ražošanas ēkas": "pramonės pastatai",
    "Noliktavas, rezervuāri, bunkuri un silosi": "sandėliai, rezervuarai",
    "Ēkas plašizklaides pasākumiem": "pramogų pastatai",
    "Muzeji un bibliotēkas": "muziejai ir bibliotekos",
    "Skolas, universitātes un zinātniskajai pētniecībai paredzētās ēkas": "mokyklos ir mokslo pastatai",
    "Ārstniecības vai veselības aprūpes iestāžu ēkas": "gydymo įstaigų pastatai",
    "Sporta ēkas": "sporto pastatai",
    "Lauksaimniecības nedzīvojamās ēkas": "žemės ūkio pastatai",
    "Kulta ēkas": "religiniai pastatai",
    "Kultūrvēsturiskie objekti": "kultūros paveldo objektai",
    "Citas, iepriekš neklasificētas, ēkas": "kiti pastatai",
    "Koplietošanas telpu grupa": "bendrojo naudojimo patalpos",
}
# Prašymo rūšies (procedūros) vertimas dalimis: ko neišverčiame, lieka latviškai
APPLICATION_LT = [
    ("Būvniecības iesniegums", "statybos prašymas"), ("Paskaidrojuma raksts", "aiškinamasis raštas"),
    ("Ēkas fasādes apliecinājuma karte", "fasado patvirtinimo kortelė"),
    ("Apliecinājuma karte", "patvirtinimo kortelė"), ("Paziņojums par būvniecību", "pranešimas apie statybą"),
    ("ēkas vai tās daļas lietošanas veida maiņai bez pārbūves", "paskirties keitimui be rekonstrukcijos"),
    ("ēkas nojaukšanai", "pastato griovimui"), ("inženierbūvei", "inžineriniam statiniui"), ("ēkai", "pastatui"),
    ("energoapgādes objektam", "energetikos objektui"), ("autoceļu objektam", "kelių objektui"),
    ("autoceļam un ielai", "keliui ir gatvei"), ("elektronisko sakaru tīklam", "elektroninių ryšių tinklui"),
    ("hidrotehniskai un meliorācijas būvei", "hidrotechniniam ir melioracijos statiniui"),
    ("dzelzceļa infrastruktūras objektam", "geležinkelio objektui"),
    ("dzelzceļa objekta būvniecībai", "geležinkelio objekto statybai"),
    ("(lēmums)", "(sprendimas)"), ("(iesniegums)", "(prašymas)"),
]


def territory_from_authority(name):
    """Būvvaldės pavadinimas -> savivaldybė, kaip objektų faile („Ogres novada būvvalde“ -> „Ogres novads“)."""
    words = (name or "").replace(",", " ").split()
    low = [w.lower() for w in words]
    if "novada" in low:
        i = low.index("novada")
        return " ".join(w.capitalize() for w in words[:i]) + " novads" if i else name
    if words and any(k in (name or "").lower() for k in ("valstspilsētas", "būvvalde", "pašvaldības", "būvinspekcija")):
        w = words[0].capitalize()
        return w if w.endswith("pils") else w[:-1] if w.endswith(("as", "es")) else w
    return name or ""


def translate_application(text):
    out = text or ""
    for lv, lt in APPLICATION_LT:
        out = out.replace(lv, lt)
    return out


def _kind(path):
    head = header_of(path)
    for kind, col in KINDS.items():
        if col in head:
            return kind
    raise SourceError(f"{os.path.basename(path)}: neatpažintas BIS failas (stulpeliai: {', '.join(head[:8])}…)")


def _float(v):
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def select(con, files, since, today=None):
    """Atrenka įvykius iš BIS failų: files – {"lietas": kelias, "objekti": kelias, "jaunbuves": kelias}."""
    if "lietas" not in files:
        raise SourceError("reikia bylų sąrašo failo („Būvniecības lietu saraksts“)")
    today = today or date.today()
    track_from = (today - timedelta(days=config.LV_TRACK_DAYS)).isoformat()
    known = {d.split(":")[1] for d in db.known_docs(con, CODE) if d.count(":") >= 2}
    chosen = {}
    for r in csv_rows(files["lietas"]):
        case = (r.get(F["case"]) or "").strip()
        created = norm_date(r.get(F["created"]))
        if not case or not r.get(F["stage"]) or config.LV_STAGES.get(r[F["stage"]], ("kita",))[0] is None:
            continue   # be numerio, be stadijos arba nutraukta byla
        if case in known:
            if created and created < track_from:
                continue
            event = today.isoformat()        # žinomos bylos nauja stadija: pastebėta šiandien
        elif created and created >= since:
            event = created                  # nauja byla
        else:
            continue
        r["_ivykio_data"] = event
        r["_objektai"], r["_paskirtys"] = [], []
        chosen[case] = r
    if not chosen:
        return []
    if files.get("objekti"):
        for o in csv_rows(files["objekti"]):
            r = chosen.get((o.get(F["case"]) or "").strip())
            if r is not None and len(r["_objektai"]) < MAX_OBJECTS:
                r["_objektai"].append({k: o.get(F[k]) for k in ("object", "address", "territory", "cadastre",
                                                                "lat", "lon", "works")})
    if files.get("jaunbuves"):
        for o in csv_rows(files["jaunbuves"]):
            r = chosen.get((o.get(F["case"]) or "").strip())
            if r is not None and len(r["_paskirtys"]) < MAX_OBJECTS:
                r["_paskirtys"].append({"use": o.get(F["use"]), "object": o.get(F["object"]),
                                        "address": o.get(F["address_new"]), "lat": o.get(F["lat"]),
                                        "lon": o.get(F["lon"])})
    items = []
    for case, r in chosen.items():
        key = f"{CODE}:{case}:{slug(r[F['stage']])}"
        items.append((key, key, r["_ivykio_data"], r))
    return items


def read_files(con, paths, since, today=None):
    with contextlib.ExitStack() as stack:
        files = {}
        for p in paths:
            local = stack.enter_context(local_file(p))
            files[_kind(local)] = local
        return select(con, files, since, today)


def resource_url(dataset_id):
    """Naujausio CSV ištekliaus adresas CKAN rinkinyje (failo pavadinime – data, todėl kinta kasdien)."""
    url = config.LV_CKAN_API + dataset_id
    req = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=config.REQUEST_TIMEOUT_S) as resp:
            meta = json.load(resp)["result"]
    except Exception as e:  # tinklas, JSON, struktūra
        raise SourceError(f"data.gov.lv rinkinio {dataset_id} aprašas nepasiekiamas: {e}") from e
    csvs = [r for r in meta.get("resources", []) if (r.get("format") or "").upper() == "CSV" and r.get("url")]
    if not csvs:
        raise SourceError(f"data.gov.lv rinkinyje {dataset_id} nėra CSV failo")
    best = max(csvs, key=lambda r: r.get("last_modified") or r.get("created") or "")
    return best["url"], best.get("last_modified") or best.get("created") or ""


def fetch_items(con, since, today=None):
    tmp = tempfile.mkdtemp(prefix="bis_")
    try:
        files = {}
        for kind, dataset_id in config.LV_DATASETS.items():
            url, _ = resource_url(dataset_id)
            print(f"  LV: atsisiunčiamas {kind}: {url.rsplit('/', 1)[-1]}", flush=True)
            files[kind] = download(url, os.path.join(tmp, f"{kind}.csv"))
        return select(con, files, since, today)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def build_signal(doc_nr, rows, con=None):
    r = rows[0]
    stage = r.get(F["stage"]) or ""
    works = (r.get(F["works"]) or next((o.get("works") for o in r.get("_objektai", []) if o.get("works")), "")
             or "").strip()
    application = r.get(F["application"]) or ""
    typ, stage_lt = config.LV_STAGES.get(stage, ("kita", stage.lower()))
    works_type, works_lt = config.LV_WORKS.get(works, ("kita", works.lower()))
    if typ == "leidimas":
        typ = works_type
    if "paziņojums" in application.lower() and typ in ("prasymas", "pradzia") + tuple(config.LV_WORKS_TYPES):
        typ = "pranesimas"   # darbai pagal pranešimą (pvz., buto atnaujinimas) – be statybos leidimo
    label = f"LV: {stage_lt}" + (f" – {works_lt}" if works_lt and typ not in ("prasymas",) else "")
    objects = r.get("_objektai") or []
    uses_lv = signals._uniq([u.get("use") for u in r.get("_paskirtys", []) if u.get("use") not in (None, "", "-")])
    purposes = [USES_LT.get(u, u) for u in uses_lv]
    names = signals._uniq([o.get("object") for o in objects] or [r.get(F["name"])])
    lat = lon = None
    for o in objects + (r.get("_paskirtys") or []):
        lat, lon = signals.wgs_point(f"{o.get('lat')} {o.get('lon')}")
        if lat:
            break
    # be objekto adreso paliekame tuščią: bylos pavadinimas (dažnai su adresu) jau rodomas kaip objektas
    address = next((o.get("address") for o in objects + r.get("_paskirtys", []) if o.get("address")), "")
    territory = next((o.get("territory") for o in objects if o.get("territory")), "") \
        or territory_from_authority(r.get(F["authority"]))
    n_obj = max(1, len(objects))
    points = config.SCORE_PURPOSE["LV"]
    score_terms = [fold(u) for u in uses_lv] or [fold(application)]
    score = config.SCORE["type"].get(typ, 0) \
        + max([max([w for k, w in points.items() if k in t] or [0]) for t in score_terms] or [0]) \
        + (1 if n_obj >= config.SCORE["objects_bonus_from"] else 0)
    return {
        "signal_id": doc_nr,
        "country": CODE,
        "doc_date": r.get("_ivykio_data") or norm_date(r.get(F["created"])),
        "signal_type": typ,
        "signal_label": label,
        "doc_text": f"{application or 'Būvniecības lieta'} · {stage}",
        "works_type": works_lt or works,
        "purposes": "; ".join(purposes),
        "category": translate_application(application),
        "object_names": "; ".join(names[:5]) + (f" (+{len(names) - 5})" if len(names) > 5 else ""),
        "object_count": n_obj,
        "address": address,
        "municipality": territory,
        "cadastre": "; ".join(signals._uniq([o.get("cadastre") for o in objects], 5)),
        "project_name": r.get(F["name"]) or "",
        "project_nr": r.get(F["case"]) or "",
        "lat": lat,
        "lon": lon,
        "point_lks": "",
        "score": score,
    }


def is_excluded(rows):
    return any(config.LV_STAGES.get(r.get(F["stage"]), ("kita",))[0] is None for r in rows)


def diagnose():
    ok = True
    for kind, dataset_id in config.LV_DATASETS.items():
        try:
            url, modified = resource_url(dataset_id)
            req = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT, "Range": "bytes=0-4095"})
            with urllib.request.urlopen(req, timeout=config.REQUEST_TIMEOUT_S) as resp:
                head = resp.read(4096).decode("utf-8-sig", errors="replace").splitlines()[0]
            missing = KINDS[kind] not in head
            state = f"TRŪKSTA stulpelio {KINDS[kind]}" if missing else "laukai OK"
            print(f"  LV {kind}: atnaujinta {modified[:16]}, {state}")
            ok = ok and not missing
        except (SourceError, OSError, IndexError) as e:
            print(f"  LV {kind}: KLAIDA {e}")
            ok = False
    return ok

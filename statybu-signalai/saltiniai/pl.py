# -*- coding: utf-8 -*-
"""Lenkija: GUNB „Rejestr Wniosków, Decyzji i Zgłoszeń“ (RWDZ), wyszukiwarka.gunb.gov.pl.

Failai atnaujinami kasnakt, duomenys nuo 2016 m., UTF-8, skirtukas „;“ (aprašyme nurodytas „#“ –
skirtuką atpažįstame automatiškai):
  wynik_<vaivadija>.zip          – statybos leidimai (pozwolenia na budowę) su investuotoju;
  wynik_zgloszenia_2022_up.zip   – pranešimai apie statybą (zgłoszenia) visai šaliai.
Koordinačių registre nėra, todėl Lenkijos signalai rodomi sąraše, bet ne žemėlapyje.
Projektuotojų vardai ir pavardės (asmens duomenys) į bazę neįrašomi.
"""
import contextlib
import os
import shutil
import tempfile
import urllib.request

import config
from saltiniai import SourceError, csv_rows, download, fold, header_of, local_file, norm_date

CODE = "PL"
NAME = "Lenkija – GUNB RWDZ (wyszukiwarka.gunb.gov.pl)"

# Leidimų (pozwolenia) stulpeliai
P = {
    "id": "numer_gunb", "office_nr": "numer_urzad", "organ": "nazwa_organu", "applied": "data_wplywu_wniosku",
    "decision_nr": "numer_decyzji_urzedu", "decided": "data_wydania_decyzji", "investor": "nazwa_inwestor",
    "voiv": "wojewodztwo", "city": "miasto", "terc": "terc", "cecha": "cecha", "street": "ulica",
    "street2": "ulica_dalej", "house": "nr_domu", "kind": "rodzaj_inwestycji", "category": "kategoria",
    "works": "nazwa_zamierzenia_bud", "name": "nazwa_zam_budowlanego", "volume": "kubatura",
    "unit": "jednosta_numer_ew", "precinct": "obreb_numer", "plot": "numer_dzialki",
}
# Pranešimų (zgłoszenia) stulpeliai
Z = {
    "id": "numer_ewidencyjny_system", "office_nr": "numer_ewidencyjny_urzad",
    "applied": "data_wplywu_wniosku_do_urzedu", "organ": "nazwa_organu", "voiv": "wojewodztwo_objekt",
    "postcode": "obiekt_kod_pocztowy", "city": "miasto", "terc": "terc", "cecha": "cecha", "street": "ulica",
    "street2": "ulica_dalej", "house": "nr_domu", "category": "kategoria", "name": "nazwa_zam_budowlanego",
    "works": "rodzaj_zam_budowlanego", "volume": "kubatura", "status": "stan",
    "unit": "jednostki_numer", "precinct": "obreb_numer", "plot": "numer_dzialki",
}
KIND_LT = {
    "Budynek mieszkalny jednorodzinny": "vienbutis gyvenamasis namas",
    "Obiekt budowlany inny niż budynek mieszkalny jednorodzinny": "kitas statinys (ne vienbutis namas)",
}


def _kind(path):
    head = header_of(path)
    if P["id"] in head:
        return "pozwolenie"
    if Z["id"] in head:
        return "zgloszenie"
    raise SourceError(f"{os.path.basename(path)}: neatpažintas GUNB failas (stulpeliai: {', '.join(head[:6])}…)")


def select_file(path, since, today=None):
    """Vieno failo (CSV ar ZIP) įvykiai nuo since: leidimai – pagal sprendimo datą, pranešimai – pagal pateikimo."""
    kind = _kind(path)
    cols = P if kind == "pozwolenie" else Z
    date_col = cols["decided"] if kind == "pozwolenie" else cols["applied"]
    items = []
    for r in csv_rows(path):
        event = norm_date(r.get(date_col))
        doc_id = (r.get(cols["id"]) or "").strip()
        if not doc_id or not event or event < since or is_excluded([{"status": r.get(cols.get("status", ""), "")}]):
            continue
        # saugome tik reikalingus laukus: be projektuotojų vardų ir pavardžių
        row = {k: (r.get(c) or "").strip() for k, c in cols.items()}
        row["_rusis"], row["_ivykio_data"] = kind, event
        doc = f"{CODE}:{doc_id}"
        items.append((f"{doc}|{row['unit']}|{row['precinct']}|{row['plot']}", doc, event, row))
    return items


def read_files(con, paths, since, today=None):
    items = []
    with contextlib.ExitStack() as stack:
        for p in paths:
            items.extend(select_file(stack.enter_context(local_file(p)), since, today))
    return items


def files_to_fetch():
    names = [f"wynik_{w}.zip" for w in config.PL_WOJEWODZTWA]
    return names + ([config.PL_ZGLOSZENIA] if config.PL_ZGLOSZENIA else [])


def fetch_items(con, since, today=None):
    items = []
    tmp = tempfile.mkdtemp(prefix="gunb_")
    try:
        for name in files_to_fetch():
            print(f"  PL: atsisiunčiamas {name}", flush=True)
            path = download(config.PL_BASE_URL + name, os.path.join(tmp, name), timeout=600)
            items.extend(select_file(path, since, today))
            os.remove(path)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return items


def _works(text):
    t = fold(text)
    for key, (typ, label) in config.PL_WORKS.items():
        if t.startswith(fold(key)):
            return typ, label
    return "kita", (text or "").strip()


def _int(v):
    try:
        return int(float(str(v).replace(",", ".").replace(" ", "")))
    except (TypeError, ValueError):
        return None


def build_signal(doc_nr, rows, con=None):
    r = rows[0]
    permit = r.get("_rusis") == "pozwolenie"
    typ, works_lt = _works(r.get("works"))
    if not permit and typ != "griovimas":
        typ = "pranesimas"
    cat = (r.get("category") or "").strip().upper()
    cat_lt, cat_points = config.PL_CATEGORIES.get(cat, ("", 0))
    volume = _int(r.get("volume"))
    purposes = cat_lt or KIND_LT.get(r.get("kind"), r.get("kind") or "")
    street = " ".join(" ".join(filter(None, [r.get("cecha"), r.get("street2"), r.get("street")])).split())
    street = "" if street in ("ul.", "") else street
    address = ", ".join(filter(None, [r.get("city"), " ".join(filter(None, [street, r.get("house")]))]))
    plots = []
    for x in rows:
        p = "/".join(filter(None, [x.get("unit"), x.get("precinct"), x.get("plot")]))
        if p and p not in plots:
            plots.append(p)
    investor = (r.get("investor") or "").strip() if permit else ""
    score = config.SCORE["type"].get(typ, 0) + cat_points \
        + (1 if volume and volume >= config.PL_KUBATURA_BONUS else 0)
    return {
        "signal_id": doc_nr,
        "country": CODE,
        "doc_date": r.get("_ivykio_data") or "",
        "signal_type": typ,
        "signal_label": f"PL {'leidimas' if permit else 'pranešimas'}: {works_lt}",
        "doc_text": " · ".join(filter(None, [r.get("decision_nr") or r.get("office_nr"), r.get("organ")])),
        "works_type": works_lt,
        "purposes": purposes + (f"; {volume} m³" if volume else ""),
        "category": f"{cat} – {cat_lt}" if cat_lt else cat,
        "object_names": (r.get("name") or "")[:300],
        "object_count": 1,
        "address": address,
        "municipality": f"woj. {r.get('voiv')}" if r.get("voiv") else "",
        "cadastre": "; ".join(plots[:5]) + (f" (+{len(plots) - 5})" if len(plots) > 5 else ""),
        "project_name": (r.get("name") or "")[:300],
        "project_nr": doc_nr.split(":", 1)[1],
        "lat": None,
        "lon": None,
        "point_lks": "",
        "score": score,
        "builder_name": investor or None,
    }


def is_excluded(rows):
    st = fold(" ".join(r.get("status") or "" for r in rows))
    return "sprzeciw" in st and "brak sprzeciwu" not in st


def diagnose():
    ok = True
    for name in files_to_fetch():
        req = urllib.request.Request(config.PL_BASE_URL + name, method="HEAD",
                                     headers={"User-Agent": config.USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=config.REQUEST_TIMEOUT_S) as resp:
                size = int(resp.headers.get("Content-Length") or 0) / 1e6
                print(f"  PL {name}: {size:.1f} MB, atnaujinta {resp.headers.get('Last-Modified', '?')}")
        except OSError as e:
            print(f"  PL {name}: KLAIDA {e}")
            ok = False
    return ok

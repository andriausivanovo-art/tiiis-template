# -*- coding: utf-8 -*-
"""Lenkija: GUNB „Rejestr Wniosków, Decyzji i Zgłoszeń“ (RWDZ), wyszukiwarka.gunb.gov.pl.

Failai atnaujinami kasnakt, duomenys nuo 2016 m., UTF-8, skirtukas „;“ (aprašyme nurodytas „#“ –
skirtuką atpažįstame automatiškai):
  wynik_<vaivadija>.zip          – statybos leidimai (pozwolenia na budowę) su investuotoju;
  wynik_zgloszenia_2022_up.zip   – pranešimai apie statybą (zgłoszenia) visai šaliai.
Koordinačių registre nėra, todėl Lenkijos signalai rodomi sąraše, bet ne žemėlapyje.
Projektuotojų vardai ir pavardės (asmens duomenys) į bazę neįrašomi. Investuotojas rodomas tik tada, kai
tai organizacija (bendrovė, savivaldybė, įstaiga); fizinių asmenų ir verslininkų vardai paslepiami.
"""
import contextlib
import csv
import os
import re
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from datetime import date, timedelta

import config
import db
from saltiniai import PartialSourceError, SourceError, csv_rows, download, fold, header_of, local_file, norm_date

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
# Organizacijos požymiai investuotojo pavadinime: teisinė forma arba viešasis subjektas (visais atvejais –
# ištisi žodžiai, kad nesutaptų su pavardėmis: Wojewódzki, Parafiniuk, Szkołuda). Kiti – fiziniai asmenys ar
# verslininkai (pvz., „Katarzyna Kowalska“, „PHU Jan Nowak“, civilinė bendrija) – jų vardų nerodome (BDAR).
_PERSONAL = re.compile(r"spółk\w*\s+cywiln|\bs\.\s?c\.|\bwspólnicy\b", re.I)
_ORG = re.compile(
    # teisinės formos
    r"\bsp\.?\s*z\s*\.?\s*o\.?\s*o\b|sp\.\s*z\s*\.?\s*o\.\s*o|\bspółk\w*\s+z\s*\.?\s*o\.?\s*o\b|"
    r"\bspółk[aiąe]\s+(?:akcyjn|komandytow|jawn|partnersk|z\s+ograniczon)|\bs\.\s?a\.?(?!\w)|\bsa\b|"
    r"\bsp\.\s?[jkp]\.?(?!\w)|\bsp\.?\s?k\.?\s?a\b|\bspółdzielni\w*|\bbank\w*\s+spółdzielcz|"
    # samorządas ir valstybė
    r"\bgmin(?:a|y|ie|ą|ę)\b|\bmiast(?:o|a|u)\b|\bm\.\s?st\.|\bpowiat(?:u|em|owi)?\b|\bwojewódz(?:two|twa|twu)\b|"
    r"\bwojewódzk\w*\s+(?:szpital|ośrod|bibliotek|centrum|zarząd|fundusz|inspektorat|urząd|komend|sąd)|"
    r"skarb\s+państwa|\bpaństwow\w*|\burz(?:ąd|ędu)\b|\bzarząd\b|\bsamorząd\w*|\bdyrekcj\w*|"
    r"\bgeneralny\s+dyrektor|\bministerstw\w*|\bkomend(?:a|y)\b|\bjednostk\w*\s+wojskow|\bstraż\w*\s+pożarn|"
    r"\bagencj\w*\s+(?:mienia|restrukturyzacji|rozwoju)|\bkrajow\w*\s+ośrod|\bgddkia\b|"
    # įstaigos (tik su viešojo subjekto požymiu, kad nesutaptų su verslininkų pavadinimais)
    r"\bfundacj(?:a|i|ę)\b|\bstowarzyszeni(?:e|a)\b|\bparafi(?:a|i|ę)\b|\bkości(?:ół|oła)\b|"
    r"\bzgromadzeni(?:e|a)\b|diecezj(?:a|i)\b|\bwspólnot\w*\s+mieszkaniow|\buniwersytet\w*|\bpolitechnik\w*|"
    r"\bakademi\w*\s+(?:wychowania|medyczn|górniczo|sztuk|muzyczn|ekonomiczn|rolnicz|morsk|wojsk|pedagogiczn)|"
    r"\bszkoł\w*\s+(?:podstawow|ponadpodstawow|specjaln|muzyczn|policealn|branżow|nr)|\bzespół\s+szkół|"
    r"\b(?:publiczn|samorządow|miejsk|gminn)\w*\s+przedszkol|\bprzedszkol\w*\s+(?:nr|publiczn|samorządow|miejsk)|"
    r"\bszpital\w*\s+(?:wojewódzk|miejsk|powiatow|kliniczn|uniwersyteck|specjalistyczn)|\bsamodzieln\w*\s+publiczn|"
    r"\bzespół\s+opieki|\b(?:sp)?zoz\b|\bnadleśnictw\w*|\blasy\s+państwowe|\bmuzeum\b|"
    r"\b(?:gminn|miejsk|powiatow|wojewódzk)\w*\s+ośrod\w*|\bośrod\w*\s+(?:sportu|pomocy\s+społecznej)|"
    r"\bzakład\w*\s+(?:wodociąg|gospodarki\s+komunalnej|karny|ubezpieczeń)|\bprzedsiębiorstw\w*\s+wodociąg|"
    r"\b(?:mpwik|pwik|mpk|zgk)\b|\bpkp\b|\bpolskie\s+sieci|\btauron\b|\benea\b|\benerga\b|\bpge\b|\borlen\b|"
    r"\bgaz-system\b|"
    # viešojo lygmens būdvardis + įstaigos daiktavardis („Wojewódzkie Pogotowie Ratunkowe“, „Narodowy Instytut“,
    # „Powiatowe Centrum“, „Gminne Przedsiębiorstwo Komunalne“); pavardė vien ja nepasižymi
    r"\b(?:gminn|miejsk|powiatow|wojewódzk|narodow|państwow|krajow|regionaln|samorządow|publiczn)\w*\s+"
    r"(?:\w+\s+){0,2}(?:przedsiębiorstw|centrum|centr|inspektor|pogotowi|instytut|zarząd|ośrod|klub|szpital|"
    r"bibliotek|fundusz|urząd|zakład|związ|dom|teatr|muzeum|port|zespół|sąd|komend|biur|archiwum|stadion|"
    r"cmentarz|wodociąg|spółk|towarzystw|filharmoni|oper|szkoł|przedszkol|żłob|agencj|instytucj)\w*|"
    r"\b\w+\s+szpital\w*\b|\binstytut\w*\s+(?:matki|badawcz|naukow|techniki|technologii|transportu|"
    r"meteorologii|geologiczn|ochrony|medycyny|onkologii|kardiologii)|\bakademi\w*\s+nauk|\bspółdziel\w*|"
    r"\bspółk\w*\s+europejsk|\bwspólnot\w*\s+(?:mieszk|właścic)|\bklub\w*\s+sportow|"
    r"\b(?:uczniowsk|ludow)\w*\s+klub|\bzwiąz\w*\s+(?:\w+\s+){0,3}gmin", re.I)


def organization(name):
    """Investuotojo pavadinimas, jei tai organizacija; kitaip None (fizinis asmuo ar verslininkas)."""
    name = " ".join((name or "").split())
    if not name or _PERSONAL.search(name):
        return None
    return name if _ORG.search(name) else None


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
    """Vieno failo (CSV ar ZIP) įvykiai nuo since: leidimai – pagal sprendimo datą, pranešimai – pagal pateikimo.

    Pranešimai registre atsiranda tik pasibaigus prieštaravimo terminui (po kelių savaičių), todėl jiems
    langas ne trumpesnis nei PL_ZGLOSZENIA_LOOKBACK_DAYS; pasikartojimų neatsiranda (raktai unikalūs).
    """
    kind = _kind(path)
    cols = P if kind == "pozwolenie" else Z
    date_col = cols["decided"] if kind == "pozwolenie" else cols["applied"]
    if kind == "zgloszenie":
        today = today or date.today()
        since = min(since, (today - timedelta(days=config.PL_ZGLOSZENIA_LOOKBACK_DAYS)).isoformat())
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


FAILED = "PL_FAILAS"        # busenos.source: failas -> data, nuo kurios jį reikia paimti (nepavyko praeitą kartą)


def fetch_items(con, since, today=None):
    """Visi PL failai. Nepavykęs failas praleidžiamas, bet įsimenama, nuo kada jį reikės paimti kitą kartą,
    o šalis pažymima gauta tik iš dalies (PartialSourceError) – kitų failų įvykiai išsaugomi."""
    items, failed = [], []
    names = files_to_fetch()
    behind = db.get_states(con, FAILED)
    tmp = tempfile.mkdtemp(prefix="gunb_")
    try:
        for name in names:
            print(f"  PL: atsisiunčiamas {name}", flush=True)
            file_since = min(since, behind.get(name, since))
            try:
                path = download(config.PL_BASE_URL + name, os.path.join(tmp, name), timeout=600)
                items.extend(select_file(path, file_since, today))
                os.remove(path)
            except (SourceError, OSError, ValueError, csv.Error, zipfile.BadZipFile) as e:
                print(f"  PL: {name} praleistas: {e}", file=sys.stderr, flush=True)
                failed.append((name, file_since, str(e)[:120]))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    con.execute("DELETE FROM busenos WHERE source=?", (FAILED,))
    db.set_states(con, FAILED, [(name, s) for name, s, _ in failed])
    if names and len(failed) == len(names):
        raise SourceError(f"nepavyko gauti nė vieno GUNB failo ({', '.join(n for n, _, _ in failed)})")
    if failed:
        raise PartialSourceError("nepavyko: " + "; ".join(f"{n} ({e})" for n, _, e in failed)
                                 + " – kitą kartą jie bus paimti nuo praleistos datos", items)
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
    investor = organization(r.get("investor")) if permit else None
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

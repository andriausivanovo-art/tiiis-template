# -*- coding: utf-8 -*-
"""Lietuva: „Infostatyba“ (data.gov.lt rinkinys Nr. 1000, Spinta API; teikėjas SSVA, anksčiau VTPSI).

Kai data.gov.lt nepasiekiamas (pvz., ugniasienė blokuoja užsienio IP), tie patys duomenys imami iš SSVA
ArcGIS paslaugos geoportal.lt (data.gov.lt rinkinys Nr. 3740) – žr. config.LT_SOURCE.
Logika gyvena fetch.py ir signals.py; čia ji pritaikyta bendrai šaltinių sąsajai.
"""
import sys

import config
import db
import fetch
import signals

CODE = "LT"
NAME = "Lietuva – Infostatyba (data.gov.lt)"


STATUS = "LT_BUSENOS"   # busenos.source: nuo kada dar nepatikrinti dokumentų būsenų pokyčiai (jei nepavyko)


def fetch_items(con, since, today=None):
    """Nauji dokumentai nuo since ir anksčiau gautų dokumentų pasikeitimai (pvz., prašymas atmestas).

    Pasikeitimai imami pagal įrašo datą (iraso_data): seni dokumentai, kurių bazėje dar nėra,
    nauju įvykiu nelaikomi – atnaujinami tik jau žinomi įrašai. Jei pasikeitimų gauti nepavyko,
    nauji dokumentai išsaugomi, šalis pažymima gauta iš dalies, o kitą kartą pasikeitimai imami nuo ten pat.
    """
    from saltiniai import PartialSourceError, SourceError
    mode = getattr(config, "LT_SOURCE", "spinta")
    status_since = min(since, db.get_states(con, STATUS).get("nuo") or since)
    status_error = None
    try:
        if mode == "arcgis":
            rows = fetch.fetch_arcgis(since, status_since=status_since)
        else:
            try:
                rows = fetch.fetch_since(since)
                try:
                    rows += fetch.fetch_since(status_since, field="iraso_data", allow_client=False, verbose=False)
                except fetch.FetchError as e:
                    status_error = e
            except fetch.FetchError as e:
                if mode != "auto":
                    raise
                print(f"  LT: data.gov.lt nepavyko ({e}); imama iš SSVA ArcGIS paslaugos", file=sys.stderr,
                      flush=True)
                rows = fetch.fetch_arcgis(since, status_since=status_since)
    except fetch.FetchError as e:
        raise SourceError(f"{e} Jei neveikia nė vienas kelias: atsisiųskite CSV iš data.gov.lt (rinkinys "
                          "Nr. 1000) ir įkelkite – python sistema.py import-csv <failas>") from e
    items, old = {}, {}
    for key, doc, day, r in db.lt_items(rows, config.F):
        ((items if (day or "")[:10] >= since else old))[str(key)] = (key, doc, day, r)
    known = db.existing_keys(con, CODE, list(old))
    result = list(items.values()) + [v for k, v in old.items() if k in known and k not in items]
    if status_error:
        db.set_states(con, STATUS, [("nuo", status_since)])
        raise PartialSourceError(f"dokumentų būsenų pokyčių gauti nepavyko ({str(status_error)[:150]}); "
                                 f"kitą kartą jie bus imami nuo {status_since}", result)
    con.execute("DELETE FROM busenos WHERE source=?", (STATUS,))
    con.commit()
    return result


def read_files(con, paths, since, today=None):
    from saltiniai import local_file
    items = []
    for path in paths:
        with local_file(path) as local:      # CSV, ZIP arba nuoroda
            items.extend(db.lt_items(fetch.read_csv(local, since), config.F))
    return items


def build_signal(doc_nr, rows, con=None):
    s = signals.build_signal(doc_nr, rows)
    s["country"] = CODE
    return s


def is_excluded(rows):
    return signals.is_excluded(rows)


def not_signal(rows):
    """Dokumento tipas – ne signalas (patikrinimo aktas, specialieji reikalavimai ir pan.)."""
    return bool(rows) and signals.doc_type(rows[0])[0] is None


def diagnose():
    ok = fetch.diagnose()
    if getattr(config, "LT_SOURCE", "spinta") in ("auto", "arcgis"):
        ok = fetch.diagnose_arcgis() or (ok and config.LT_SOURCE == "auto")
    return ok

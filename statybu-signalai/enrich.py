# -*- coding: utf-8 -*-
"""Įmonių praturtinimas: JAR ir Sodros CSV, statytojų susiejimas per builders.csv.

Stulpelių pavadinimai šaltiniuose kartais keičiasi, todėl juos atpažįstame
pagal kelis galimus variantus.
"""
import csv
import io
import os
import re
import zipfile

from db import now_iso

CANDIDATES = {
    "code": ["ja_kodas", "jarcode", "juridiniuasmenuregistrokodas", "imoneskodas", "kodas", "code"],
    "name": ["ja_pavadinimas", "pavadinimas", "name"],
    "legal_form": ["form_pavadinimas", "teisineforma", "form_kodas"],
    "status": ["stat_pavadinimas", "statusas", "stat_kodas"],
    "nace": ["ecoactcode", "evrk_kodas", "evrk", "veiklosrusieskodas"],
    "nace_name": ["ecoactname", "evrk_pavadinimas", "veiklosrusiespavadinimas"],
    "municipality": ["municipality", "savivaldybe", "savivaldybekurojeregistruota"],
    "employees": ["numinsured", "apdraustujuskaicius"],
    "avg_wage": ["avgwage", "vidutinisdarbouzmokestis"],
    "month": ["month", "menuo"],
}


def _norm(h):
    h = h.lower()
    for a, b in zip("ąčęėįšųūž", "aceeisuuz"):
        h = h.replace(a, b)
    return re.sub(r"[^a-z0-9_]", "", h)


def _map_columns(headers):
    normed = {h: _norm(h) for h in headers}
    out = {}
    for field, cands in CANDIDATES.items():
        for c in cands:  # pirmenybė tikslesniems variantams
            hit = next((h for h, n in normed.items() if n == c), None) or \
                  next((h for h, n in normed.items() if c in n), None)
            if hit and hit not in out.values():
                out[field] = hit
                break
    # "code" neturi sutapti su "Draudėjo kodas" Sodros faile, jei yra JAR kodas
    return out


def _delimiter(text, candidates=",;|\t"):
    """Skirtukas – dažniausias antraštės eilutės simbolis iš galimų.

    csv.Sniffer čia nepatikimas: Sodros antraštėje yra kablelis („Savivaldybė, kurioje
    registruota“), o sumos rašomos su dešimtainiu kableliu, todėl jis „atspėja“ kablelį.
    """
    header = text.split("\n", 1)[0]
    return max(candidates, key=header.count)


def _read_any(path):
    if path.lower().endswith(".zip"):
        with zipfile.ZipFile(path) as z:
            name = next((n for n in z.namelist() if n.lower().endswith(".csv")), None)
            if name is None:
                raise ValueError(f"ZIP archyve nėra CSV failo: {path}")
            raw = z.read(name)
    else:
        with open(path, "rb") as fh:
            raw = fh.read()
    for enc in ("utf-8-sig", "cp1257"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", errors="replace")
    return csv.DictReader(io.StringIO(text), delimiter=_delimiter(text))


def _int(v):
    try:
        return int(float(str(v).replace(",", ".").replace(" ", "")))
    except (TypeError, ValueError):
        return None


def _float(v):
    try:
        return float(str(v).replace(",", ".").replace(" ", ""))
    except (TypeError, ValueError):
        return None


def load_companies(con, path, only_codes=None):
    """Įkelia įmonių duomenis iš JAR arba Sodros CSV/ZIP. Grąžina įkeltų įrašų skaičių.

    only_codes: jei nurodyta, įkeliamos tik šios įmonės (taupome vietą).
    Sodros faile yra keli mėnesiai – paliekame naujausią.
    """
    reader = _read_any(path)
    cols = _map_columns(reader.fieldnames or [])
    if "code" not in cols:
        raise ValueError(f"Nerastas įmonės kodo stulpelis. Stulpeliai: {reader.fieldnames}")
    print("  Atpažinti stulpeliai:", {k: v for k, v in cols.items()})
    latest = {}
    for r in reader:
        code = (r.get(cols["code"]) or "").strip()
        if not code or (only_codes is not None and code not in only_codes):
            continue
        month = r.get(cols.get("month", ""), "") or ""
        if code in latest and latest[code]["data_month"] >= month:
            continue
        latest[code] = {
            "code": code,
            "name": r.get(cols.get("name", ""), "") or None,
            "legal_form": r.get(cols.get("legal_form", ""), "") or None,
            "status": r.get(cols.get("status", ""), "") or None,
            "nace": r.get(cols.get("nace", ""), "") or None,
            "nace_name": r.get(cols.get("nace_name", ""), "") or None,
            "municipality": r.get(cols.get("municipality", ""), "") or None,
            "employees": _int(r.get(cols.get("employees", ""))),
            "avg_wage": _float(r.get(cols.get("avg_wage", ""))),
            "data_month": month,
        }
    ts = now_iso()
    for c in latest.values():
        # COALESCE: JAR ir Sodros duomenys papildo vieni kitus, neištrina
        con.execute(
            """INSERT INTO companies(code, name, legal_form, status, nace, nace_name, municipality,
                                     employees, avg_wage, data_month, updated)
               VALUES (:code, :name, :legal_form, :status, :nace, :nace_name, :municipality,
                       :employees, :avg_wage, :data_month, :updated)
               ON CONFLICT(code) DO UPDATE SET
                 name=COALESCE(excluded.name, name), legal_form=COALESCE(excluded.legal_form, legal_form),
                 status=COALESCE(excluded.status, status), nace=COALESCE(excluded.nace, nace),
                 nace_name=COALESCE(excluded.nace_name, nace_name),
                 municipality=COALESCE(excluded.municipality, municipality),
                 employees=COALESCE(excluded.employees, employees), avg_wage=COALESCE(excluded.avg_wage, avg_wage),
                 data_month=COALESCE(NULLIF(excluded.data_month, ''), data_month), updated=excluded.updated""",
            {**c, "updated": ts},
        )
    con.commit()
    return len(latest)


def ensure_builders_file(path):
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh, delimiter=";")
            w.writerow(["dokumento_reg_nr", "statytojo_kodas", "statytojo_pavadinimas", "pastaba"])


def apply_builders(con, path):
    """Perkelia rankiniu būdu nustatytus statytojus iš builders.csv į signalus."""
    ensure_builders_file(path)
    n = 0
    for r in _read_any(path):
        doc = (r.get("dokumento_reg_nr") or "").strip()
        code = (r.get("statytojo_kodas") or "").strip()
        name = (r.get("statytojo_pavadinimas") or "").strip()
        if doc and (code or name):
            n += con.execute("UPDATE signals SET builder_code=?, builder_name=? WHERE signal_id=?",
                             (code or None, name or None, doc)).rowcount
    con.commit()
    return n

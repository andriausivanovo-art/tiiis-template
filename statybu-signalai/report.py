# -*- coding: utf-8 -*-
"""Išvestys: CSV, interaktyvi HTML ataskaita sau ir statinis pavyzdys klientui."""
import csv
import html
import json
import os

import config

EXPORT_COLS = [
    ("signal_id", "Dokumento nr."), ("doc_date", "Data"), ("signal_label", "Signalas"),
    ("works_type", "Statybos rūšis"), ("purposes", "Paskirtis"), ("category", "Kategorija"),
    ("object_names", "Statiniai"), ("object_count", "Statinių sk."), ("address", "Adresas"),
    ("municipality", "Savivaldybė"), ("cadastre", "Kadastro nr."), ("lat", "Platuma"), ("lon", "Ilguma"),
    ("score", "Svarba"), ("builder_code", "Statytojo kodas"), ("builder_name", "Statytojas"),
    ("c_employees", "Darbuotojai"), ("c_nace", "EVRK"), ("c_status", "Įmonės statusas"),
    ("doc_text", "Dokumentas"), ("project_name", "Projektas"),
]


def fetch_rows(con, since=None, until=None, types=None, by="doc_date"):
    q = """SELECT s.*, c.employees AS c_employees, c.nace AS c_nace, c.status AS c_status,
                  COALESCE(s.builder_name, c.name) AS builder_name
           FROM signals s LEFT JOIN companies c ON c.code = s.builder_code WHERE 1=1"""
    args = []
    if since:
        q += f" AND s.{by} >= ?"
        args.append(since)
    if until:
        q += f" AND s.{by} <= ?"
        args.append(until)
    if types:
        q += " AND s.signal_type IN (%s)" % ",".join("?" * len(types))
        args += list(types)
    q += " ORDER BY s.score DESC, s.doc_date DESC"
    return [dict(r) for r in con.execute(q, args).fetchall()]


def write_csv(rows, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow([h for _, h in EXPORT_COLS])
        for r in rows:
            w.writerow(["" if r.get(k) is None else r.get(k) for k, _ in EXPORT_COLS])
    return path


def write_builder_queue(rows, path):
    """Leidimai su juridiniu statytoju dar nenustatytu – sąrašas rankinei paieškai."""
    todo = [r for r in rows if not r.get("builder_code") and not r.get("builder_name")
            and r["signal_type"] in ("prasymas", "leidimas_nauja", "leidimas_rekonstrukcija", "paskirties_keitimas")]
    todo.sort(key=lambda r: -r["score"])
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["dokumento_reg_nr", "statytojo_kodas", "statytojo_pavadinimas", "pastaba",
                    "svarba", "data", "signalas", "paskirtis", "adresas", "paieska"])
        for r in todo:
            w.writerow([r["signal_id"], "", "", "", r["score"], r["doc_date"], r["signal_label"],
                        r["purposes"], r["address"], config.INFOSTATYBA_SEARCH_URL])
    return len(todo)


def _json_rows(rows):
    keep = ["signal_id", "doc_date", "signal_type", "signal_label", "works_type", "purposes", "category",
            "object_names", "object_count", "address", "municipality", "cadastre", "lat", "lon", "score",
            "builder_code", "builder_name", "c_employees", "project_name"]
    return [{k: r.get(k) for k in keep} for r in rows]


def write_html(rows, path, period_from, period_to, title="Statybų signalai"):
    tpl_path = os.path.join(os.path.dirname(__file__), "templates", "ataskaita.html")
    with open(tpl_path, encoding="utf-8") as fh:
        tpl = fh.read()
    labels = {code: label for code, label, _ in config.SIGNAL_RULES}
    labels["kita"] = "Kita"
    meta = {"from": period_from, "to": period_to, "title": title, "labels": labels}
    data = json.dumps(_json_rows(rows), ensure_ascii=False).replace("</", "<\\/")
    out = tpl.replace("__META__", json.dumps(meta, ensure_ascii=False)).replace("__DATA__", data)
    out = out.replace("__TITLE__", html.escape(title))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(out)
    return path


def write_client_sample(rows, path, heading, period_from, period_to, limit=10, contact=""):
    """Statinis HTML (tinka el. laiškui): geriausi N signalų konkrečiai įmonei ar segmentui."""
    rows = rows[:limit]
    e = html.escape
    tr = []
    for r in rows:
        builder = r.get("builder_name") or "nenustatytas"
        tr.append(f"""<tr>
<td style="padding:10px 12px;border-bottom:1px solid #D5DBDC;white-space:nowrap;color:#5E6B70;font-size:13px">{e(r['doc_date'])}</td>
<td style="padding:10px 12px;border-bottom:1px solid #D5DBDC;font-size:14px;color:#1E2A2F">
<div style="font-weight:600">{e(r['purposes'] or r['object_names'] or '-')}</div>
<div style="color:#5E6B70;font-size:13px">{e(r['address'] or '')}</div></td>
<td style="padding:10px 12px;border-bottom:1px solid #D5DBDC;font-size:13px;color:#1E2A2F">{e(r['signal_label'])}<br>
<span style="color:#5E6B70">{e(r.get('category') or '')}</span></td>
<td style="padding:10px 12px;border-bottom:1px solid #D5DBDC;font-size:13px;color:#1E2A2F">{e(builder)}</td>
</tr>""")
    body = "\n".join(tr) or '<tr><td colspan="4" style="padding:12px">Šiuo laikotarpiu signalų nerasta.</td></tr>'
    doc = f"""<!DOCTYPE html><html lang="lt"><head><meta charset="utf-8"><title>{e(heading)}</title></head>
<body style="margin:0;padding:24px;background:#F6F7F5;font-family:Arial,Helvetica,sans-serif">
<table role="presentation" width="100%" style="max-width:760px;margin:0 auto;background:#FFFFFF;border:1px solid #D5DBDC;border-collapse:collapse">
<tr><td style="padding:20px 20px 4px;font-size:20px;font-weight:700;color:#1E2A2F">{e(heading)}</td></tr>
<tr><td style="padding:0 20px 16px;font-size:14px;color:#5E6B70">{e(period_from)} – {e(period_to)} · {len(rows)} objektai · šaltinis: Infostatyba (VTPSI atviri duomenys)</td></tr>
<tr><td style="padding:0 8px 8px"><table width="100%" style="border-collapse:collapse">
<tr><th align="left" style="padding:8px 12px;font-size:12px;color:#5E6B70;border-bottom:2px solid #1E2A2F">Data</th>
<th align="left" style="padding:8px 12px;font-size:12px;color:#5E6B70;border-bottom:2px solid #1E2A2F">Objektas</th>
<th align="left" style="padding:8px 12px;font-size:12px;color:#5E6B70;border-bottom:2px solid #1E2A2F">Etapas</th>
<th align="left" style="padding:8px 12px;font-size:12px;color:#5E6B70;border-bottom:2px solid #1E2A2F">Statytojas</th></tr>
{body}</table></td></tr>
<tr><td style="padding:16px 20px 20px;font-size:13px;color:#5E6B70">{e(contact)}</td></tr>
</table></body></html>"""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(doc)
    return path

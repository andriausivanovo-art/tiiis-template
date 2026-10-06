# -*- coding: utf-8 -*-
"""SQLite saugykla: žali įrašai, signalai, įmonės, paleidimų žurnalas."""
import json
import os
import re
import sqlite3
from datetime import datetime

SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_records (
    row_key      TEXT PRIMARY KEY,
    doc_nr       TEXT,
    doc_date     TEXT,
    data_json    TEXT NOT NULL,
    first_seen   TEXT NOT NULL,
    source       TEXT NOT NULL DEFAULT 'LT'   -- šalis: LT, LV, PL, EE
);
CREATE INDEX IF NOT EXISTS ix_raw_doc ON raw_records(doc_nr);

CREATE TABLE IF NOT EXISTS signals (
    signal_id     TEXT PRIMARY KEY,      -- LT: dokumento_reg_nr; kitos šalys: "LV:..." ir pan.
    doc_date      TEXT,
    signal_type   TEXT,
    signal_label  TEXT,
    doc_text      TEXT,
    works_type    TEXT,
    purposes      TEXT,
    category      TEXT,
    object_names  TEXT,
    object_count  INTEGER,
    address       TEXT,
    municipality  TEXT,
    cadastre      TEXT,
    project_name  TEXT,
    project_nr    TEXT,
    lat           REAL,
    lon           REAL,
    point_lks     TEXT,
    score         INTEGER,
    builder_code  TEXT,
    builder_name  TEXT,
    first_seen    TEXT NOT NULL,
    updated       TEXT NOT NULL,
    country       TEXT NOT NULL DEFAULT 'LT'
);
CREATE INDEX IF NOT EXISTS ix_sig_date ON signals(doc_date);
CREATE INDEX IF NOT EXISTS ix_sig_first ON signals(first_seen);

CREATE TABLE IF NOT EXISTS companies (
    code          TEXT PRIMARY KEY,
    name          TEXT,
    legal_form    TEXT,
    status        TEXT,
    nace          TEXT,
    nace_name     TEXT,
    municipality  TEXT,
    employees     INTEGER,
    avg_wage      REAL,
    data_month    TEXT,
    updated       TEXT
);

-- Koordinatės, gaunamos atskiru failu (pvz., Estijos statinių kontūrų ataskaita)
CREATE TABLE IF NOT EXISTS taskai (
    source        TEXT NOT NULL,
    key           TEXT NOT NULL,
    lat           REAL,
    lon           REAL,
    PRIMARY KEY (source, key)
);

-- Paskutinė žinoma objekto būsena (LV bylos stadija, EE statinio būsena): pokytis = naujas įvykis
CREATE TABLE IF NOT EXISTS busenos (
    source        TEXT NOT NULL,
    key           TEXT NOT NULL,
    value         TEXT,
    updated       TEXT,
    PRIMARY KEY (source, key)
);

CREATE TABLE IF NOT EXISTS runs (
    run_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    started       TEXT,
    since_date    TEXT,
    fetched       INTEGER,
    new_raw       INTEGER,
    new_signals   INTEGER,
    note          TEXT
);
"""


def now_iso():
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


def connect(path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    _migrate(con)
    return con


def _migrate(con):
    """Senose bazėse (tik LT) prideda šalies stulpelius ir indeksus."""
    for table, col in (("raw_records", "source"), ("signals", "country")):
        cols = {r["name"] for r in con.execute(f"PRAGMA table_info({table})")}
        if col not in cols:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {col} TEXT NOT NULL DEFAULT 'LT'")
    con.execute("CREATE INDEX IF NOT EXISTS ix_raw_source ON raw_records(source, doc_date)")
    con.execute("CREATE INDEX IF NOT EXISTS ix_sig_country ON signals(country)")
    con.commit()


def insert_rows(con, source, items, update=False, stats=None):
    """Įrašo žalius įrašus: items – (raktas, dokumentas, data, įrašas). Grąžina naujų skaičių.

    update=True: jei to paties rakto įrašas pasikeitė (pvz., dokumentas panaikintas), jis perrašomas ir
    first_seen atnaujinamas, kad `build` perskaičiuotų signalą. stats (žodynas) gauna „pakeisti“ skaičių.
    """
    new = changed = 0
    ts = now_iso()
    for key, doc_nr, doc_date, row in items:
        data = json.dumps(row, ensure_ascii=False, sort_keys=True)
        args = (str(key), doc_nr, (doc_date or "")[:10], data, ts, source)
        cur = con.execute("INSERT OR IGNORE INTO raw_records(row_key, doc_nr, doc_date, data_json, first_seen, source) "
                          "VALUES (?,?,?,?,?,?)", args)
        if cur.rowcount:
            new += 1
        elif update:
            changed += con.execute("UPDATE raw_records SET doc_nr=?, doc_date=?, data_json=?, first_seen=? "
                                   "WHERE row_key=? AND data_json != ?",
                                   (doc_nr, (doc_date or "")[:10], data, ts, str(key), data)).rowcount
    con.commit()
    if stats is not None:
        stats["pakeisti"] = stats.get("pakeisti", 0) + changed
    return new


def lt_items(rows, fields):
    """Infostatybos įrašai -> (raktas, dokumentas, data, įrašas).

    Raktas – įrašo (statinys × dokumentas) ID: rinkinio „id“ (toks pat data.gov.lt ir ArcGIS paslaugoje),
    jei jo nėra – Spinta _id. Laukas „uuid“ yra
    dokumento ID (bendras visiems dokumento statiniams), todėl raktu netinka.
    """
    for r in rows:
        key = r.get(fields["row_id"]) or r.get("_id")
        if not key:
            # be ID: sudarome iš dokumento ir statinio
            key = "|".join(str(r.get(fields[k]) or "") for k in ("doc_nr", "object_id", "unique_nr", "object_name"))
        yield key, r.get(fields["doc_nr"]), r.get(fields["doc_date"]), r


def existing_keys(con, source, keys):
    """Kurie iš raktų jau yra raw_records (šaltinio)."""
    found = set()
    keys = [str(k) for k in keys]
    for i in range(0, len(keys), 500):
        chunk = keys[i:i + 500]
        found.update(r[0] for r in con.execute(
            "SELECT row_key FROM raw_records WHERE source=? AND row_key IN (%s)" % ",".join("?" * len(chunk)),
            [source] + chunk))
    return found


def insert_raw(con, rows, fields, stats=None):
    """Įrašo Lietuvos (Infostatybos) žalius įrašus; pasikeitę įrašai perrašomi. Grąžina naujų skaičių."""
    return insert_rows(con, "LT", lt_items(rows, fields), update=True, stats=stats)


def raw_groups(con, doc_nrs=None):
    """Grąžina {doc_nr: (šaltinis, [įrašai])} – visiems arba nurodytiems dokumentams."""
    out = {}
    q = "SELECT doc_nr, source, data_json FROM raw_records WHERE doc_nr IS NOT NULL"
    if doc_nrs is None:
        cur = con.execute(q)
    else:
        doc_nrs = list(doc_nrs)
        cur = []
        for i in range(0, len(doc_nrs), 500):
            chunk = doc_nrs[i:i + 500]
            cur.extend(con.execute(q + " AND doc_nr IN (%s)" % ",".join("?" * len(chunk)), chunk).fetchall())
    for row in cur:
        out.setdefault(row["doc_nr"], (row["source"], []))[1].append(json.loads(row["data_json"]))
    return out


def raw_by_doc(con, doc_nrs=None):
    """Grąžina {doc_nr: [įrašai]} – visiems arba nurodytiems dokumentams."""
    out = {d: [] for d in doc_nrs} if doc_nrs is not None else {}
    for doc, (_, rows) in raw_groups(con, doc_nrs).items():
        out[doc] = rows
    return out


def known_docs(con, source):
    """Šaltinio dokumentų numeriai, kuriuos jau turime (stadijų pokyčiams atpažinti)."""
    return {r[0] for r in con.execute("SELECT DISTINCT doc_nr FROM raw_records WHERE source=?", (source,))}


def set_points(con, source, points):
    """Įrašo koordinates: points – (raktas, platuma, ilguma). Grąžina įrašytų skaičių."""
    n = 0
    for key, lat, lon in points:
        con.execute("INSERT OR REPLACE INTO taskai(source, key, lat, lon) VALUES (?,?,?,?)", (source, key, lat, lon))
        n += 1
    con.commit()
    return n


def get_point(con, source, key):
    row = con.execute("SELECT lat, lon FROM taskai WHERE source=? AND key=?", (source, key)).fetchone()
    return (row["lat"], row["lon"]) if row else (None, None)


def upsert_signal(con, s):
    """Įrašo arba atnaujina signalą. Grąžina True, jei signalas naujas."""
    ts = now_iso()
    existing = con.execute("SELECT first_seen, builder_code, builder_name FROM signals WHERE signal_id=?",
                           (s["signal_id"],)).fetchone()
    cols = ["signal_id", "doc_date", "signal_type", "signal_label", "doc_text", "works_type", "purposes",
            "category", "object_names", "object_count", "address", "municipality", "cadastre",
            "project_name", "project_nr", "lat", "lon", "point_lks", "score"]
    country = s.get("country") or "LT"
    # statytoją kartais pateikia pats šaltinis (pvz., Lenkijos investuotojas); builders.csv įrašas svarbesnis
    b_code, b_name = s.get("builder_code") or None, s.get("builder_name") or None
    if existing is None:
        con.execute(
            "INSERT INTO signals(%s, country, builder_code, builder_name, first_seen, updated) "
            "VALUES (%s, ?, ?, ?, ?, ?)" % (",".join(cols), ",".join("?" * len(cols))),
            [s.get(c) for c in cols] + [country, b_code, b_name, ts, ts],
        )
        return True
    sets = ",".join(f"{c}=?" for c in cols[1:])
    # jei statytoją pateikia šaltinis, jo reikšmė atnaujinama (pvz., pagal naują filtrą paslėptas asmens
    # vardas), nebent įrašytas rankinis kodas; builders.csv įrašai po to pritaikomi iš naujo
    name_sql = "CASE WHEN builder_code IS NULL THEN ? ELSE builder_name END" if "builder_name" in s \
        else "COALESCE(builder_name, ?)"
    con.execute(f"UPDATE signals SET {sets}, country=?, builder_code=COALESCE(builder_code, ?), "
                f"builder_name={name_sql}, updated=? WHERE signal_id=?",
                [s.get(c) for c in cols[1:]] + [country, b_code, b_name, ts, s["signal_id"]])
    return False


def docs_to_build(con):
    """Dokumentai, kurių įrašai atsirado ar pasikeitė po paskutinio perskaičiavimo (žymė lentelėje „busenos“).

    Be žymės (nauja arba senesnės versijos bazė) – visi dokumentai, kad nauji tipai, savivaldybės ir
    filtrai būtų pritaikyti ir anksčiau gautiems signalams.
    """
    mark = get_states(con, "BUILD").get("paskutinis")
    cur = con.execute("SELECT DISTINCT doc_nr FROM raw_records WHERE doc_nr IS NOT NULL AND doc_nr != ''"
                      + (" AND first_seen >= ?" if mark else ""), (mark,) if mark else ())
    return [row["doc_nr"] for row in cur]


def delete_signal(con, signal_id):
    """Pašalina signalą (pvz., dokumentas panaikintas). Grąžina True, jei toks buvo."""
    return con.execute("DELETE FROM signals WHERE signal_id=?", (signal_id,)).rowcount > 0


def delete_signals_with_prefix(con, prefix):
    """Pašalina visus objekto signalus ir jų žalius įrašus (pvz., „LV:BIS-...:“ – nutraukta byla).

    Žali įrašai šalinami, kad `build --all` signalų neatkurtų. Grąžina pašalintų signalų skaičių.
    """
    pattern = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    n = con.execute("DELETE FROM signals WHERE signal_id LIKE ? ESCAPE '\\'", (pattern,)).rowcount
    con.execute("DELETE FROM raw_records WHERE doc_nr LIKE ? ESCAPE '\\'", (pattern,))
    con.commit()
    return n


def get_states(con, source):
    """{raktas: būsena} – paskutinės žinomos šaltinio objektų būsenos."""
    return {r["key"]: r["value"] for r in con.execute("SELECT key, value FROM busenos WHERE source=?", (source,))}


def set_states(con, source, pairs):
    """Įrašo pasikeitusias būsenas: pairs – (raktas, būsena)."""
    ts = now_iso()
    con.executemany("INSERT INTO busenos(source, key, value, updated) VALUES (?,?,?,?) "
                    "ON CONFLICT(source, key) DO UPDATE SET value=excluded.value, updated=excluded.updated",
                    [(source, k, v, ts) for k, v in pairs])
    con.commit()


def log_run(con, since_date, fetched, new_raw, new_signals, note=""):
    # started įrašomas, kai paleidimas baigtas: nuo šio laiko kitas `run` skaičiuoja naujus signalus
    con.execute("INSERT INTO runs(started, since_date, fetched, new_raw, new_signals, note) VALUES (?,?,?,?,?,?)",
                (now_iso(), since_date, fetched, new_raw, new_signals, note))
    con.commit()


def last_run(con, kind="run"):
    """Paskutinio sėkmingo nurodyto tipo paleidimo laikas arba None."""
    row = con.execute("SELECT MAX(started) AS t FROM runs WHERE note LIKE ? AND note NOT LIKE '%KLAIDA%'",
                      (kind + "%",)).fetchone()
    return row["t"] if row and row["t"] else None


def run_times(con, n=2):
    """Paskutinių n sėkmingų savaitinių paleidimų laikai (naujausias pirmas)."""
    cur = con.execute("SELECT started FROM runs WHERE note LIKE 'run%' AND note NOT LIKE '%KLAIDA%' "
                      "ORDER BY started DESC LIMIT ?", (n,))
    return [r["started"] for r in cur]


def first_run_since(con):
    """Ankstyviausia „nuo“ data iš paskutinio sėkmingo `run` (pvz., „LT 2026-09-06; LV 2026-09-06“)."""
    row = con.execute("SELECT since_date FROM runs WHERE note LIKE 'run%' AND note NOT LIKE '%KLAIDA%' "
                      "ORDER BY started DESC LIMIT 1").fetchone()
    dates = re.findall(r"\d{4}-\d{2}-\d{2}", (row["since_date"] or "") if row else "")
    return min(dates) if dates else None


def last_since(con, source="LT"):
    """Naujausia turima šaltinio dokumento data."""
    row = con.execute("SELECT MAX(doc_date) AS d FROM raw_records WHERE source=?", (source,)).fetchone()
    return row["d"] if row and row["d"] else None

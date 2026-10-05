# -*- coding: utf-8 -*-
"""SQLite saugykla: žali įrašai, signalai, įmonės, paleidimų žurnalas."""
import json
import os
import sqlite3
from datetime import datetime

SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_records (
    row_key      TEXT PRIMARY KEY,
    doc_nr       TEXT,
    doc_date     TEXT,
    data_json    TEXT NOT NULL,
    first_seen   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_raw_doc ON raw_records(doc_nr);

CREATE TABLE IF NOT EXISTS signals (
    signal_id     TEXT PRIMARY KEY,      -- dokumento_reg_nr
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
    updated       TEXT NOT NULL
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
    return con


def insert_raw(con, rows, fields):
    """Įrašo naujus žalius įrašus. Grąžina, kiek buvo naujų."""
    new = 0
    ts = now_iso()
    for r in rows:
        key = r.get(fields["row_id"]) or r.get("_id") or r.get("id")
        if not key:
            # be ID: sudarome iš dokumento ir statinio
            key = f'{r.get(fields["doc_nr"])}|{r.get(fields["unique_nr"])}|{r.get(fields["object_name"])}'
        cur = con.execute(
            "INSERT OR IGNORE INTO raw_records(row_key, doc_nr, doc_date, data_json, first_seen) VALUES (?,?,?,?,?)",
            (str(key), r.get(fields["doc_nr"]), (r.get(fields["doc_date"]) or "")[:10],
             json.dumps(r, ensure_ascii=False), ts),
        )
        new += cur.rowcount
    con.commit()
    return new


def raw_by_doc(con, doc_nrs=None):
    """Grąžina {doc_nr: [įrašai]} – visiems arba nurodytiems dokumentams."""
    out = {}
    if doc_nrs is None:
        cur = con.execute("SELECT doc_nr, data_json FROM raw_records WHERE doc_nr IS NOT NULL")
    else:
        doc_nrs = list(doc_nrs)
        out = {d: [] for d in doc_nrs}
        cur = []
        for i in range(0, len(doc_nrs), 500):
            chunk = doc_nrs[i:i + 500]
            q = "SELECT doc_nr, data_json FROM raw_records WHERE doc_nr IN (%s)" % ",".join("?" * len(chunk))
            cur.extend(con.execute(q, chunk).fetchall())
    for row in cur:
        out.setdefault(row["doc_nr"], []).append(json.loads(row["data_json"]))
    return out


def upsert_signal(con, s):
    """Įrašo arba atnaujina signalą. Grąžina True, jei signalas naujas."""
    ts = now_iso()
    existing = con.execute("SELECT first_seen, builder_code, builder_name FROM signals WHERE signal_id=?",
                           (s["signal_id"],)).fetchone()
    cols = ["signal_id", "doc_date", "signal_type", "signal_label", "doc_text", "works_type", "purposes",
            "category", "object_names", "object_count", "address", "municipality", "cadastre",
            "project_name", "project_nr", "lat", "lon", "point_lks", "score"]
    if existing is None:
        con.execute(
            "INSERT INTO signals(%s, first_seen, updated) VALUES (%s, ?, ?)" % (",".join(cols), ",".join("?" * len(cols))),
            [s.get(c) for c in cols] + [ts, ts],
        )
        return True
    sets = ",".join(f"{c}=?" for c in cols[1:])
    con.execute(f"UPDATE signals SET {sets}, updated=? WHERE signal_id=?",
                [s.get(c) for c in cols[1:]] + [ts, s["signal_id"]])
    return False


def log_run(con, since_date, fetched, new_raw, new_signals, note=""):
    con.execute("INSERT INTO runs(started, since_date, fetched, new_raw, new_signals, note) VALUES (?,?,?,?,?,?)",
                (now_iso(), since_date, fetched, new_raw, new_signals, note))
    con.commit()


def last_since(con):
    row = con.execute("SELECT MAX(doc_date) AS d FROM raw_records").fetchone()
    return row["d"] if row and row["d"] else None

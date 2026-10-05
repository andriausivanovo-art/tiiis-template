# -*- coding: utf-8 -*-
"""Lietuva: VTPSI „Infostatyba“ (data.gov.lt rinkinys Nr. 1000, Spinta API).

Logika gyvena fetch.py ir signals.py; čia ji pritaikyta bendrai šaltinių sąsajai.
"""
import config
import db
import fetch
import signals

CODE = "LT"
NAME = "Lietuva – Infostatyba (data.gov.lt)"


def fetch_items(con, since, today=None):
    try:
        rows = fetch.fetch_since(since)
    except fetch.FetchError as e:
        from saltiniai import SourceError
        raise SourceError(str(e)) from e
    return list(db.lt_items(rows, config.F))


def read_files(con, paths, since, today=None):
    items = []
    for path in paths:
        items.extend(db.lt_items(fetch.read_csv(path, since), config.F))
    return items


def build_signal(doc_nr, rows, con=None):
    s = signals.build_signal(doc_nr, rows)
    s["country"] = CODE
    return s


def is_excluded(rows):
    return signals.is_excluded(rows)


def diagnose():
    return fetch.diagnose()

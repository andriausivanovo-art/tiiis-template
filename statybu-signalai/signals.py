# -*- coding: utf-8 -*-
"""Žalių įrašų pavertimas signalais: grupavimas, tipas, vieta, balas."""
import re

import config

F = config.F

_MUNI_RE = re.compile(r"([A-ZĄČĘĖĮŠŲŪŽ][\wąčęėįšųūž\-]*(?:\s(?:r\.|rajono|m\.|miesto))?\s?sav\.)")
_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def classify(doc_text):
    t = (doc_text or "").lower()
    for code, label, keys in config.SIGNAL_RULES:
        if any(k in t for k in keys):
            return code, label
    return "kita", "Kita"


def municipality(address):
    if not address:
        return ""
    m = _MUNI_RE.search(address)
    if not m:
        return ""
    s = m.group(1)
    s = s.replace(" rajono ", " r. ").replace(" miesto ", " m. ")
    return s.strip()


def wgs_point(value):
    """'POINT (54.67 25.22)' arba 'POINT (25.22 54.67)' -> (lat, lon). Lietuvoje platuma 53–57, ilguma 20–27."""
    if not value:
        return None, None
    nums = [float(x) for x in _NUM_RE.findall(str(value))]
    if len(nums) < 2:
        return None, None
    a, b = nums[0], nums[1]
    if 53 <= a <= 57 and 20 <= b <= 27:
        return a, b
    if 53 <= b <= 57 and 20 <= a <= 27:
        return b, a
    return None, None


def _uniq(values, limit=None):
    out = []
    for v in values:
        v = (v or "").strip()
        if v and v not in out:
            out.append(v)
    return out[:limit] if limit else out


def _purpose_points(purpose):
    p = (purpose or "").lower()
    return max([w for k, w in config.SCORE["purpose"].items() if k in p] or [0])


def score(sig_type, purposes, category, object_count):
    s = config.SCORE["type"].get(sig_type, 0)
    # paskirtis vertinama pagal vertingiausią statinį: tinklai ar ūkinis pastatas prie namo balo nemažina
    s += max([_purpose_points(p) for p in purposes] or [0])
    c = (category or "").lower()
    for k, w in config.SCORE["category"].items():
        if c.startswith(k):
            s += w
            break
    if object_count >= config.SCORE["objects_bonus_from"]:
        s += 1
    return s


def is_excluded(rows):
    st = " ".join((r.get(F["doc_status"]) or "") for r in rows).lower()
    return any(x in st for x in config.EXCLUDED_STATUSES)


def build_signal(doc_nr, rows):
    """Iš vieno dokumento įrašų (statinių) sudaro vieną signalą."""
    first = rows[0]
    sig_type, label = classify(first.get(F["doc_text"]))
    purposes = _uniq([r.get(F["new_purpose"]) or r.get(F["purpose"]) for r in rows])
    cats = _uniq([r.get(F["category"]) for r in rows])
    # svarbiausia kategorija: ypatingasis > neypatingasis > nesudėtingasis
    order = {"ypatingasis": 0, "neypatingasis": 1, "nesudėtingasis": 2}
    cats.sort(key=lambda c: next((v for k, v in order.items() if c.lower().startswith(k)), 9))
    category = cats[0] if cats else ""
    names = _uniq([r.get(F["object_name"]) for r in rows])
    addr = next((r.get(F["address"]) for r in rows if r.get(F["address"])), "")
    lat = lon = None
    for r in rows:
        lat, lon = wgs_point(r.get(F["point_wgs"]))
        if lat:
            break
    # statinys atpažįstamas pagal unikalų numerį, o naujas (dar neįregistruotas) – pagal statinio_id
    n_obj = len(_uniq([str(r.get(F["unique_nr"]) or r.get(F["object_id"]) or r.get(F["object_name"]) or i)
                       for i, r in enumerate(rows)]))
    return {
        "signal_id": doc_nr,
        "doc_date": (first.get(F["doc_date"]) or "")[:10],
        "signal_type": sig_type,
        "signal_label": label,
        "doc_text": first.get(F["doc_text"]) or "",
        "works_type": "; ".join(_uniq([r.get(F["works_type"]) for r in rows])),
        "purposes": "; ".join(purposes),
        "category": category,
        "object_names": "; ".join(names[:5]) + (f" (+{len(names) - 5})" if len(names) > 5 else ""),
        "object_count": n_obj,
        "address": addr,
        "municipality": municipality(addr) or municipality(first.get(F["project_name"])),
        "cadastre": "; ".join(_uniq([r.get(F["cadastre"]) for r in rows], 5)),
        "project_name": first.get(F["project_name"]) or "",
        "project_nr": first.get(F["project_nr"]) or "",
        "lat": lat,
        "lon": lon,
        "point_lks": next((r.get(F["point_lks"]) for r in rows if r.get(F["point_lks"])), ""),
        "score": score(sig_type, purposes, category, n_obj),
    }

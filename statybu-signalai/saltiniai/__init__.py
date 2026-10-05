# -*- coding: utf-8 -*-
"""Duomenų šaltiniai pagal šalis: LT (Infostatyba), LV (BIS), PL (GUNB RWDZ), EE (EHR).

Kiekvienas šaltinis (modulis) turi tą pačią sąsają:
    CODE, NAME                     šalies kodas ir pavadinimas
    fetch(con, since, today)       parsisiunčia ir atrenka naujus įvykius -> [(raktas, dok., data, įrašas)]
    read_files(con, paths, since, today)   tas pats iš rankiniu būdu atsisiųstų failų
    build_signal(doc_nr, rows, con)        vieno dokumento įrašai -> bendro formato signalas
    is_excluded(rows)              ar dokumentas negaliojantis
    diagnose()                     ryšio ir laukų patikra
Bendro formato signalą įrašo db.upsert_signal, o ataskaitos jau nebeskiria šalių.
"""
import contextlib
import csv
import io
import os
import re
import shutil
import tempfile
import urllib.error
import urllib.request
import zipfile

import config


class SourceError(Exception):
    """Šaltinio klaida, kurią rodome naudotojui be techninių detalių."""


_FOLD = str.maketrans({  # LT, LV, EE, PL raidės be diakritikų
    "ą": "a", "č": "c", "ę": "e", "ė": "e", "į": "i", "š": "s", "ų": "u", "ū": "u", "ž": "z",
    "ā": "a", "ē": "e", "ī": "i", "ļ": "l", "ķ": "k", "ņ": "n", "ģ": "g",
    "õ": "o", "ä": "a", "ö": "o", "ü": "u",
    "ł": "l", "ń": "n", "ó": "o", "ś": "s", "ź": "z", "ż": "z", "ć": "c",
})


def fold(s):
    """Mažosios raidės be diakritikų: paieškai ir raktažodžiams, nepriklausomai nuo kalbos."""
    return (s or "").lower().translate(_FOLD)


def slug(s, limit=40):
    return re.sub(r"[^a-z0-9]+", "-", fold(s)).strip("-")[:limit] or "x"


def norm_date(value):
    """Įvairių formatų data -> 'YYYY-MM-DD' ('' jei neatpažinta).

    Pvz.: '2026-09-21', '2026-09-21 00:00:00', '2026-09-21T10:15:00', '21.09.2026', '2026.09'.
    """
    v = (value or "").strip()
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", v)
    if m:
        return m.group(0)
    m = re.match(r"(\d{2})\.(\d{2})\.(\d{4})", v)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    m = re.match(r"(\d{4})\.(\d{2})$", v)
    if m:
        return f"{m.group(1)}-{m.group(2)}-01"
    return ""


def delimiter(header, candidates=",;|\t#"):
    """Skirtukas – dažniausias antraštės simbolis (Sniffer klysta, kai antraštėje yra kablelių)."""
    return max(candidates, key=header.count)


def download(url, dest, timeout=None):
    """Atsisiunčia failą srautu (dideli failai neužima atminties). Grąžina dest."""
    req = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout or config.REQUEST_TIMEOUT_S) as resp, \
                open(dest, "wb") as fh:
            shutil.copyfileobj(resp, fh, 1 << 20)
    except urllib.error.HTTPError as e:
        raise SourceError(f"{url}: HTTP {e.code}") from e
    except (urllib.error.URLError, OSError) as e:
        raise SourceError(f"{url}: nepavyko atsisiųsti ({getattr(e, 'reason', e)})") from e
    return dest


@contextlib.contextmanager
def local_file(path_or_url):
    """Leidžia vienodai naudoti vietinį failą ir URL (URL atsisiunčiamas į laikiną failą)."""
    if re.match(r"https?://", path_or_url or ""):
        suffix = os.path.splitext(path_or_url.split("?")[0])[1][:8]
        fd, tmp = tempfile.mkstemp(suffix=suffix or ".csv")
        os.close(fd)
        try:
            yield download(path_or_url, tmp)
        finally:
            with contextlib.suppress(OSError):
                os.remove(tmp)
    else:
        if not os.path.exists(path_or_url):
            raise SourceError(f"failas nerastas: {path_or_url}")
        yield path_or_url


@contextlib.contextmanager
def open_text(path, member=None):
    """Atidaro CSV tekstą: paprastą failą arba CSV iš ZIP (pirmą arba nurodytą `member`)."""
    if path.lower().endswith(".zip"):
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist() if n.lower().endswith(".csv")]
            name = member if member in z.namelist() else (names[0] if names else None)
            if not name:
                raise SourceError(f"ZIP archyve nėra CSV failo: {path}")
            with z.open(name) as raw:
                yield io.TextIOWrapper(raw, encoding="utf-8-sig", errors="replace", newline="")
    else:
        with open(path, encoding="utf-8-sig", errors="replace", newline="") as fh:
            yield fh


def header_of(path):
    """Pirmoji CSV eilutė (stulpelių pavadinimai) – failo tipui atpažinti."""
    with open_text(path) as fh:
        line = fh.readline()
    return [h.strip().strip('"') for h in next(csv.reader([line], delimiter=delimiter(line)), [])]


def csv_rows(path):
    """CSV eilutės kaip žodynai (srautu). Pasikartojantis stulpelio pavadinimas gauna priesagą _2."""
    with open_text(path) as fh:
        first = fh.readline()
        reader = csv.reader(fh, delimiter=delimiter(first))
        names, seen = [], {}
        for h in next(csv.reader([first], delimiter=delimiter(first)), []):
            h = h.strip()
            seen[h] = seen.get(h, 0) + 1
            names.append(h if seen[h] == 1 else f"{h}_{seen[h]}")
        for row in reader:
            if row:
                yield dict(zip(names, row))


def get(code):
    """Šaltinio modulis pagal šalies kodą."""
    from saltiniai import ee, lt, lv, pl  # vėlyvas importas: moduliai patys naudoja šį paketą
    sources = {"LT": lt, "LV": lv, "PL": pl, "EE": ee}
    try:
        return sources[code.upper()]
    except KeyError:
        raise SourceError(f"nežinoma šalis „{code}“; galimos: {', '.join(sources)}") from None


def codes():
    return list(config.COUNTRY_NAMES)

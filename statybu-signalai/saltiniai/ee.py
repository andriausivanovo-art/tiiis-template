# -*- coding: utf-8 -*-
"""Estija: Ehitisregister (EHR).

Pagrindinis kelias (`fetch`, `run`) – viešas statinių API be registracijos ir el. pašto:
  1) pokyčių srautas https://livekluster.ehr.ee/api/building/v2/find/ehrcodes/dateafter – kurie statiniai
     keitėsi nuo datos;
  2) kiekvieno statinio dokumentų istorija (buildingVersions): signalas = naujas statybos dokumentas
     (projektavimo sąlygos, statybos leidimo prašymas, leidimas, statybos pranešimas, pradžia, naudojimo
     leidimas, griovimas – žr. config.EE_DOC_TYPES); adresų, savininkų ir pan. pakeitimai praleidžiami;
  3) statinio duomenys (buildingData): paskirtis, adresas, savivaldybė, būsena, koordinatės (L-EST97).
EHR (Cloudflare) riboja užklausų dažnį, todėl jos siunčiamos nuosekliai, ne dažniau kaip
config.EE_API_RPS per sekundę, o gavus HTTP 429 – dar rečiau.

Atsarginis kelias – atvirų duomenų ataskaitos: `python sistema.py ee-order --email ...` užsako
„eh_ehitised“ (ir, jei reikia, „ehitise_ruumikuju“) ataskaitą, nuoroda atsiunčiama el. paštu.
Gautą failą (ar nuorodą) įkelkite: `python sistema.py import --salis EE <failas|nuoroda>`.
Tada signalas = (statinys, būsena): planuojamas („Kavandatav“), statomas („Püstitamisel“),
neseniai pastatytas („Olemas“ su šių ar praėjusių metų pirmuoju naudojimo leidimu).
Klasifikatoriai (paskirtys, savivaldybės, būsenos) – ee_klasifikatoriai.json (EHR API kopija).
"""
import contextlib
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

import config
import db
from saltiniai import NETWORK_ERRORS, PartialSourceError, SourceError, csv_rows, fold, header_of, local_file, norm_date, slug

CODE = "EE"
NAME = "Estija – Ehitisregister (EHR)"

F = {
    "status": "seisund", "code": "ehr_kood", "use": "kaos_id_peamine", "name": "nimetus",
    "kind": "rajatis_hoone", "start": "eh_alust_kp", "use_from": "kav_kasutus_kp", "county": "maakond",
    "municipality": "omavalitsus", "created": "date_created", "updated": "date_updated",
    "address": "taisaadress", "short_address": "lahiaadress", "first_use": "esmane_kasutus",
}
G = {"code": "ehr_kood", "x": "viitepunkt_x", "y": "viitepunkt_y"}   # ehitise_ruumikuju

USE_LT = {  # kasutusotstarbe kodo pradžia -> lietuviškas pavadinimas (ilgiausias sutapimas)
    "111": "vieno buto gyvenamieji namai", "1121": "dviejų butų namai", "1122": "daugiabučiai (3 ir daugiau butų)",
    "113": "bendrabučiai, globos namai", "121": "apgyvendinimo ir maitinimo pastatai", "122": "biurų pastatai",
    "123": "prekybos ir paslaugų pastatai", "124": "transporto pastatai", "125": "pramonės ir sandėlių pastatai",
    "126": "visuomeniniai pastatai (švietimas, sveikata, kultūra, sportas)", "127": "kiti negyvenamieji pastatai",
    "21": "transporto statiniai", "22": "vamzdynai, ryšių ir elektros linijos", "23": "pramonės statiniai",
    "24": "kiti statiniai",
}

_CLASS = None


def classifiers():
    global _CLASS
    if _CLASS is None:
        with open(os.path.join(os.path.dirname(__file__), "ee_klasifikatoriai.json"), encoding="utf-8") as fh:
            _CLASS = json.load(fh)
    return _CLASS


def _prefix_match(code, table):
    hits = [k for k in table if str(code).startswith(k)]
    return table[max(hits, key=len)] if hits else None


# --- L-EST97 (EPSG:3301, Lamberto konforminė kūginė projekcija, GRS80) ---
_A, _FL = 6378137.0, 1 / 298.257222101
_E2 = _FL * (2 - _FL)
_E = math.sqrt(_E2)
_LAT1, _LAT2, _LAT0, _LON0 = (math.radians(v) for v in (59 + 20 / 60, 58.0, 57.51755393055556, 24.0))
_FE, _FN = 500000.0, 6375000.0


def _m(phi):
    return math.cos(phi) / math.sqrt(1 - _E2 * math.sin(phi) ** 2)


def _t(phi):
    es = _E * math.sin(phi)
    return math.tan(math.pi / 4 - phi / 2) / ((1 - es) / (1 + es)) ** (_E / 2)


_N = (math.log(_m(_LAT1)) - math.log(_m(_LAT2))) / (math.log(_t(_LAT1)) - math.log(_t(_LAT2)))
_AF = _A * _m(_LAT1) / (_N * _t(_LAT1) ** _N)
_RHO0 = _AF * _t(_LAT0) ** _N


def wgs_to_lest(lat, lon):
    """WGS84 -> L-EST97 (šiaurė x, rytai y)."""
    rho = _AF * _t(math.radians(lat)) ** _N
    theta = _N * (math.radians(lon) - _LON0)
    return _FN + _RHO0 - rho * math.cos(theta), _FE + rho * math.sin(theta)


def lest_to_wgs(north, east):
    """L-EST97 (šiaurė x, rytai y) -> WGS84 (platuma, ilguma)."""
    dx, dy = east - _FE, _RHO0 - (north - _FN)
    t = (math.hypot(dx, dy) / _AF) ** (1 / _N)
    lon = math.atan2(dx, dy) / _N + _LON0
    phi = math.pi / 2 - 2 * math.atan(t)
    for _ in range(8):
        es = _E * math.sin(phi)
        phi = math.pi / 2 - 2 * math.atan(t * ((1 - es) / (1 + es)) ** (_E / 2))
    return math.degrees(phi), math.degrees(lon)


def point_from_lest(x, y):
    """EHR atskaitos taškas -> (lat, lon). Estijoje šiaurės koordinatė ~6,3–6,7 mln., rytų ~0,3–0,8 mln."""
    try:
        a, b = float(str(x).replace(",", ".")), float(str(y).replace(",", "."))
    except (TypeError, ValueError):
        return None, None
    north, east = (a, b) if a > b else (b, a)
    if not (6.2e6 < north < 6.7e6 and 3e5 < east < 8e5):
        return None, None
    return lest_to_wgs(north, east)


# --- Būsenos ---

def status(value):
    """EHR būsena (kodas arba tekstas) -> (kodas, tipas, žymė); tipas None – atmetama."""
    v = (value or "").strip()
    by_text = {fold(t): k for k, t in classifiers()["seisund"].items()}
    code = by_text.get(fold(v), v).upper()
    for fragment, typ, label in config.EE_STATUSES:
        if fragment in code:
            return code, typ, label
    return code, "kita", v.lower()


def _kind(path):
    head = header_of(path)
    if G["x"] in head:
        return "ruumikuju"
    if F["status"] in head and F["code"] in head:
        return "ehitised"
    raise SourceError(f"{os.path.basename(path)}: neatpažintas EHR failas (stulpeliai: {', '.join(head[:6])}…)")


def _year(v):
    try:
        return int(float(v or 0))
    except ValueError:
        return 0


def select(con, files, since, today=None):
    """Atrenka įvykius iš EHR ataskaitų: files – {"ehitised": [keliai], "ruumikuju": [keliai]}.

    Kiekvieno statinio būsena saugoma lentelėje „busenos“. Įvykis – naujas statinio įrašas
    (sukurtas nuo since) arba žinomo statinio būsenos pasikeitimas (pvz., „Kavandatav“ -> „Püstitamisel“).
    Vien atnaujintas įrašas (date_updated) įvykiu nelaikomas: Estijoje daug statinių metų metus lieka
    „Püstitamisel“. Pirmą kartą senesni statiniai tik įsimenami. Pastatyti („Olemas“) statiniai, kurių
    pirmasis naudojimo leidimas šių ar praėjusių metų, įtraukiami ir pirmą kartą.
    """
    today = today or date.today()
    for path in files.get("ruumikuju", []):
        points = []
        for r in csv_rows(path):
            lat, lon = point_from_lest(r.get(G["x"]), r.get(G["y"]))
            if lat and r.get(G["code"]):
                points.append((r[G["code"]].strip(), lat, lon))
        db.set_points(con, CODE, points)
    states = db.get_states(con, CODE)
    if not states:                       # bazė iš senesnės versijos: būsenos atkuriamos ir įrašomos
        states = _states_from_raw(con)
        db.set_states(con, CODE, states.items())
    changed, terminated, items = {}, [], []
    for path in files.get("ehitised", []):
        for r in csv_rows(path):
            code = (r.get(F["code"]) or "").strip()
            st_code, typ, _ = status(r.get(F["status"]))
            prev = states.get(code)
            if not code or changed.get(code) == st_code:
                continue
            if prev == st_code:
                # jau žinoma būsena; laikotarpyje naujas statinys (pvz., pakartotinai su ankstesne --since)
                # pateikiamas tomis pačiomis taisyklėmis kaip pirmą kartą – jau įrašytas įvykis nesidubliuos
                created, updated = norm_date(r.get(F["created"])), norm_date(r.get(F["updated"]))
                if typ == "uzbaigimas":
                    event = updated if (_year(r.get(F["first_use"])) >= today.year - 1 and updated
                                        and updated >= since) else None
                else:
                    event = created if typ and created and created >= since else None
                if event:
                    r["_ivykio_data"] = event
                    key = f"{CODE}:{code}:{slug(st_code)}"
                    items.append((key, key, event, r))
                continue
            changed[code] = st_code
            if typ is None:                       # ištrintas, neįgyvendintas, leidimas negalioja
                if prev is not None:
                    terminated.append(code)
                continue
            created, updated = norm_date(r.get(F["created"])), norm_date(r.get(F["updated"]))
            if prev is not None:
                event = max(updated, since) if updated else today.isoformat()   # būsena pasikeitė
            elif typ == "uzbaigimas":
                if _year(r.get(F["first_use"])) < today.year - 1 or not updated or updated < since:
                    continue                          # seniai pastatytas statinys
                event = updated
            elif created and created >= since:
                event = created                       # naujas statinio įrašas
            else:
                continue                              # senesnis statinys: tik įsimenama būsena
            r["_ivykio_data"] = event
            key = f"{CODE}:{code}:{slug(st_code)}"
            items.append((key, key, event, r))
    db.set_states(con, CODE, changed.items())
    for code in terminated:
        db.delete_signals_with_prefix(con, f"{CODE}:{code}:")
    return items


def _states_from_raw(con):
    """Būsenos iš jau įrašytų ataskaitų įvykių (bazei, sukurtai senesne versija be lentelės „busenos“)."""
    states = {}
    for data, in con.execute("SELECT data_json FROM raw_records WHERE source=? ORDER BY doc_date", (CODE,)):
        r = json.loads(data)
        if r.get(F["code"]) and not r.get("_dok_tipas"):          # tik ataskaitų (ne API) įvykiai
            states[str(r[F["code"]]).strip()] = status(r.get(F["status"]))[0]
    return states


def read_files(con, paths, since, today=None):
    with contextlib.ExitStack() as stack:
        files = {"ehitised": [], "ruumikuju": []}
        for p in paths:
            local = stack.enter_context(local_file(p))
            files[_kind(local)].append(local)    # kelios ataskaitos (pvz., pagal apskritis) sujungiamos
        return select(con, files, since, today)


# --- Viešas statinių API ---

class RateLimited(SourceError):
    """EHR (Cloudflare) per daug kartų atsakė HTTP 429 – gavimą reikia kartoti vėliau."""


class _Limiter:
    """Užklausų greičio ribotuvas: ne dažniau kaip rps per sekundę; po HTTP 429 lėtėja, po sėkmių atsigauna."""

    def __init__(self, rps, max_429=None):
        self.base = self.gap = 1.0 / rps if rps else 0.0
        self.next = 0.0
        self.limited = self.ok = 0
        self.max_429 = config.EE_API_MAX_429 if max_429 is None else max_429

    def wait(self):
        now = time.monotonic()
        at = max(now, self.next)
        self.next = at + self.gap
        if at > now:
            time.sleep(at - now)

    def success(self):
        """Po 20 sėkmingų užklausų iš eilės greitis vėl didinamas (iki config.EE_API_RPS)."""
        self.ok += 1
        if self.ok >= 20 and self.gap > self.base:
            self.gap, self.ok = max(self.base, self.gap / 2), 0

    def too_many(self, seconds):
        """HTTP 429: pauzė ir dvigubai retesnės užklausos (iki vienos per 8 s); per daug – RateLimited."""
        self.limited += 1
        self.ok = 0
        if self.limited > self.max_429:
            raise RateLimited(f"EHR riboja užklausas (HTTP 429 jau {self.limited} kartus). Kitas paleidimas tęs "
                              "nuo ten, kur sustota; jei kartojasi, sumažinkite config.EE_API_RPS.")
        self.gap = min(max(self.gap * 2, 1.0), 8.0)
        self.next = max(self.next, time.monotonic() + seconds)


def _api_get(path, limiter, tries=4):
    """GET į statinių API. Grąžina JSON arba None (404). Laikinos klaidos (429, 5xx, ryšys) kartojamos.

    Į Cloudflare „Retry-After“ (būna 20 min.) neatsižvelgiama: ribojimo metu retesnės užklausos praeina.
    """
    url = f"{config.EE_BUILDING_API}/{path}"
    req = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT, "Accept": "application/json"})
    for attempt in range(tries):
        limiter.wait()
        try:
            with urllib.request.urlopen(req, timeout=config.REQUEST_TIMEOUT_S) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            limiter.success()
            return data
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code == 429:
                limiter.too_many(30 * (attempt + 1))
                continue
            if e.code < 500 or attempt == tries - 1:
                raise SourceError(f"EHR API {path}: HTTP {e.code}") from e
        except (ValueError,) + NETWORK_ERRORS as e:          # ValueError – sugadintas JSON
            if attempt == tries - 1:
                raise SourceError(f"EHR API {path}: {e!r}") from e
        time.sleep(5 * 2 ** attempt)
    raise SourceError(f"EHR API {path}: nepavyko po {tries} bandymų")


def changed_codes(start, limiter, keep=None, limit=None, max_pages=200):
    """Pokyčių srautas nuo start (Estijos laiku, „YYYY-MM-DD“ arba „YYYY-MM-DDTHH:MM:SS.sss“).

    Kiekvienas kodas imamas vieną kartą (pirmas pokytis), tik tie, kuriems keep(kodas) teisinga.
    Surinkus limit kodų, skaitymas stabdomas (srautas surikiuotas pagal laiką).
    Grąžina ([(kodas, laikas)], paskutinio pokyčio laikas, laikas, nuo kurio tęsti (jei sustota) arba None,
    praleistų (ne keep) kodų skaičius).
    """
    ts = start if "T" in start else f"{start}T00:00:00"
    out, seen, offset, last, skipped = [], set(), 0, ts, 0
    for _ in range(max_pages):
        page = _api_get(f"find/ehrcodes/dateafter?timestamp={urllib.parse.quote(ts)}&offset={offset}", limiter)
        if page is None and offset == 0:
            raise SourceError("EHR pokyčių srautas nerastas (HTTP 404) – pasikeitė API adresas? "
                              "Patikrinkite config.EE_BUILDING_API ir `python sistema.py diagnose --salis EE`.")
        if page is not None and not isinstance(page, list):
            raise SourceError(f"EHR pokyčių srautas grąžino ne sąrašą: {str(page)[:200]}")
        if not page:
            return out, last, None, skipped
        for x in page:
            code, when = str(x.get("ehr_kood") or ""), str(x.get("timestamp") or ts)
            if not code or code in seen:
                last = max(last, when)
                continue
            seen.add(code)
            if keep and not keep(code):
                skipped += 1
            elif limit is not None and len(out) >= limit:
                return out, last, when, skipped                  # likusius paims kitas paleidimas
            else:
                out.append((code, when))
            last = max(last, when)
        offset += len(page)
    raise SourceError(f"EHR pokyčių sraute daugiau nei {max_pages} puslapių – nurodykite vėlesnę --since datą")


def doc_events(versions, since):
    """Statinio dokumentų istorija -> statybos dokumentai nuo since: [(doku_id, tipas, žymė, data, nr)]."""
    out, seen = [], set()
    for v in versions or []:
        kind = config.EE_DOC_TYPES.get(str(v.get("doty_id") or ""))
        day = norm_date(v.get("ver_tekk_aeg"))
        doc_id = str(v.get("doku_id") or v.get("dok_nr") or "")
        if kind and day and day >= since and doc_id and doc_id not in seen:
            seen.add(doc_id)
            out.append((doc_id, kind[0], kind[1], day, v.get("dok_nr") or ""))
    return out


def _point_from_building(e):
    """Atskaitos taškas, įėjimo taškas arba kontūro vidurkis (L-EST97) -> (lat, lon)."""
    for k in ((e.get("ehitiseKujud") or {}).get("ruumikuju") or []):
        lat, lon = point_from_lest(k.get("viitepunktX"), k.get("viitepunktY"))
        if lat:
            return lat, lon
        for sp in ((k.get("sissepaasupunktid") or {}).get("sissepaasupunkt") or []):
            lat, lon = point_from_lest(sp.get("viitepunkt_x"), sp.get("viitepunkt_y"))
            if lat:
                return lat, lon
        coords, stack = [], [(k.get("geometry") or {}).get("coordinates")]
        while stack:
            c = stack.pop()
            if isinstance(c, list) and len(c) >= 2 and all(isinstance(v, (int, float)) for v in c[:2]):
                coords.append(c[:2])
            elif isinstance(c, list):
                stack.extend(c)
        if coords:
            lat, lon = point_from_lest(sum(c[0] for c in coords) / len(coords),
                                       sum(c[1] for c in coords) / len(coords))
            if lat:
                return lat, lon
    return None, None


def building_row(e):
    """buildingData „ehitis“ -> įrašas su tais pačiais laukais kaip eh_ehitised ataskaitoje."""
    a, p = e.get("ehitiseAndmed") or {}, e.get("ehitisePohiandmed") or {}
    return {
        F["status"]: a.get("seisund") or "", F["code"]: str(a.get("ehrKood") or ""),
        F["use"]: a.get("kaosIdPeamine") or "", F["name"]: a.get("nimetus") or "",
        F["kind"]: a.get("rajatisHoone") or "", F["start"]: p.get("ehAlustKp") or "",
        F["use_from"]: p.get("kavKasutusKp") or "", F["county"]: p.get("maakond") or "",
        F["municipality"]: p.get("omavalitsus") or "", F["updated"]: a.get("verTekkAeg") or "",
        F["address"]: a.get("taisaadress") or "", F["first_use"]: a.get("esmaneKasutus") or "",
        "_kaos_kood": a.get("kaosKood") or "", "_kaos_tekstas": a.get("kaosIdTxt") or "",
        "_busena_tekstas": a.get("seisundTxt") or "",
    }


def _one_building(code, since, known, limiter):
    """(statinio duomenys arba None, įvykiai). Duomenys imami tik kai yra įvykių ar statinys jau žinomas."""
    events = doc_events(_api_get(f"buildingVersions?ehr_code={urllib.parse.quote(code)}", limiter), since)
    if not events and code not in known:
        return None, []
    data = _api_get(f"buildingData?ehr_code={urllib.parse.quote(code)}", limiter)
    return (data or {}).get("ehitis"), events


RETRY = "EE_PAKARTOTI"      # busenos.source: statiniai, kurių praėjusį kartą nepavyko gauti (kodas -> nuo)
CURSOR = "EE_ZYMA"          # busenos.source: pokyčių srauto vieta, iki kurios viskas apdorota


def resolve_since(con, since=None, today=None):
    """Nuo kur imti: nurodyta --since; kitaip – kur baigėsi paskutinis gavimas (žymė), pirmą kartą –
    config.EE_FIRST_RUN_DAYS dienų atgal. Taip nepavykęs ar pavėlavęs paleidimas nieko nepraranda."""
    if since:
        return since
    mark = db.get_states(con, CURSOR).get("srautas")
    if mark:
        return mark
    return ((today or date.today()) - timedelta(days=config.EE_FIRST_RUN_DAYS)).isoformat()


def _retry_entry(value):
    """busenos RETRY reikšmė „data|bandymai“ -> (data, bandymai)."""
    day, _, tries = str(value or "").partition("|")
    return day, int(tries or 1)


def fetch_items(con, since, today=None, verbose=True):
    """Statybos dokumentai iš viešo EHR statinių API nuo since (data ar srauto žymė).

    Užklausos nuoseklios ir ribojamo greičio. Per vieną kartą apdorojama ne daugiau kaip
    EE_API_MAX_BUILDINGS statinių – likusius paims kitas paleidimas (žymė lentelėje „busenos“).
    Nutrūkus (HTTP 429, EHR neatsako) išsaugoma tai, kas gauta, ir žymė, iki kur apdorota; atidėtiems
    statiniams kitą kartą taikomas tas pats (platesnis) dokumentų laikotarpis.
    """
    limiter = _Limiter(config.EE_API_RPS)
    start = since if "T" in since else f"{since}T00:00:00"
    mark = db.get_states(con, CURSOR)
    feed, last, cut, skipped = changed_codes(
        start, limiter, keep=None if config.EE_RAJATISED else (lambda c: not c.startswith("2")),
        limit=config.EE_API_MAX_BUILDINGS)
    if verbose and skipped:
        print(f"  EE: praleista inžinerinių statinių {skipped} (config.EE_RAJATISED)", file=sys.stderr)
    if verbose and cut:
        print(f"  EE: šį kartą {len(feed)} statinių, likusius paims kitas paleidimas (nuo {cut})", file=sys.stderr)
    # dokumentai su keliomis dienomis atsargos: jų data gali būti ankstesnė nei įrašymo į registrą laikas;
    # jei praeitą kartą sustota anksčiau, tęsiama su tuo pačiu laikotarpiu
    doc_since = (date.fromisoformat(start[:10]) - timedelta(days=3)).isoformat()
    if mark.get("dokumentai_nuo") and "T" in since and since == mark.get("srautas"):
        doc_since = min(doc_since, mark["dokumentai_nuo"])
    retry = {c: _retry_entry(v) for c, v in db.get_states(con, RETRY).items()}
    in_feed = {c for c, _ in feed}
    work = [(c, t, min(doc_since, retry[c][0]) if c in retry else doc_since) for c, t in feed] + \
           [(c, None, d) for c, (d, _) in retry.items() if c not in in_feed]     # pakartojami – po srauto
    known = {sid.split(":")[1] for (sid,) in con.execute("SELECT signal_id FROM signals WHERE country=?", (CODE,))
             if sid.count(":") >= 2}
    if verbose:
        minutes = len(work) * 2.0 / max(config.EE_API_RPS, 0.1) / 60
        print(f"  EE: tikrinama statinių {len(work)}" + (f" (iš jų pakartojami {len(retry)})" if retry else "") +
              f", ~{minutes:.0f} min.", file=sys.stderr, flush=True)
    items, failed, points, abort, in_row = [], [], [], None, 0
    for n, (code, ts, code_since) in enumerate(work):
        if verbose and n and n % 250 == 0:
            print(f"  EE: {n}/{len(work)} (įvykių {len(items)})", file=sys.stderr, flush=True)
        try:
            data, events = _one_building(code, code_since, known, limiter)
            in_row = 0
        except RateLimited as e:
            abort = (n, str(e))
            break
        except SourceError as e:
            failed.append((code, code_since, e))
            in_row += 1
            if in_row >= config.EE_API_MAX_FAILS_IN_ROW or \
                    (n >= 50 and len(failed) > config.EE_API_MAX_FAILED * (n + 1)):
                abort = (n + 1, f"EHR neatsako: nepavyko {len(failed)} iš {n + 1} statinių (pvz., {code}: {e})")
                break
            continue
        if not data:
            continue
        row = building_row(data)
        if status(row[F["status"]])[1] is None:          # neįgyvendintas, ištrintas
            if code in known:
                db.delete_signals_with_prefix(con, f"{CODE}:{code}:")
            continue
        lat, lon = _point_from_building(data)
        if lat:
            points.append((code, lat, lon))
        for doc_id, typ, label, day, nr in events:
            r = dict(row, _ivykio_data=day, _dok_tipas=typ, _dok_zyme=label, _dok_nr=nr)
            key = f"{CODE}:{code}:{doc_id}"
            items.append((key, key, day, r))
    db.set_points(con, CODE, points)
    cursor, pending = cut or last, []
    if abort:                                            # neapdoroti: pakartojami arba paims žymė
        rest = work[abort[0]:]
        pending = [(c, s) for c, t, s in rest if t is None]
        cursor = next((t for _, t, _ in rest if t is not None), cursor)
    # nepavykę statiniai pakartojami kitą kartą, bet ne daugiau kaip EE_API_RETRY_TIMES kartų
    new_retry, dropped = [], []
    for c, s, _ in failed:
        tries = retry.get(c, ("", 0))[1] + 1
        (new_retry if tries <= config.EE_API_RETRY_TIMES else dropped).append((c, f"{s}|{tries}"))
    new_retry += [(c, f"{s}|{retry.get(c, ('', 1))[1]}") for c, s in pending]
    con.execute("DELETE FROM busenos WHERE source=?", (RETRY,))
    db.set_states(con, RETRY, new_retry)
    db.set_states(con, CURSOR, [("srautas", cursor)])
    if abort or cut:
        db.set_states(con, CURSOR, [("dokumentai_nuo", doc_since)])
    else:
        con.execute("DELETE FROM busenos WHERE source=? AND key='dokumentai_nuo'", (CURSOR,))
        con.commit()
    if dropped:
        print(f"  EE: {len(dropped)} statinių nepavyko gauti {config.EE_API_RETRY_TIMES} kartus iš eilės – "
              f"nebekartojami (pvz., {dropped[0][0]})", file=sys.stderr)
    if verbose and limiter.limited:
        print(f"  EE: EHR ribojo užklausas {limiter.limited} k.", file=sys.stderr)
    if abort:
        raise PartialSourceError(f"{abort[1]} Išsaugota {len(items)} įvykių; kitas paleidimas tęs nuo {cursor}.",
                                 items)
    if failed:
        print(f"  EE: nepavyko gauti {len(failed)} iš {len(work)} statinių (pvz., {failed[0][0]}: {failed[0][2]}); "
              "jie bus pakartoti kitą kartą", file=sys.stderr)
    return items


def order_report(email, report_code=None, statuses=None, counties=None, changed_since=None):
    """Užsako EHR ataskaitą (POST /reports); nuoroda atsiunčiama nurodytu el. paštu.

    changed_since (YYYY-MM-DD) – tik nuo tos datos pasikeitę įrašai (EHR „Muutunud kirjed alates“);
    be jo ataskaitoje – visi kada nors užregistruoti statiniai su nurodytomis būsenomis.
    """
    payload = {"report_code": report_code or config.EE_REPORT, "email_address": email, "report_format": "csv",
               "seisund": statuses if statuses is not None else config.EE_ORDER_STATUSES}
    if changed_since:
        payload["point_kdate"] = changed_since
    if counties:
        payload["county"] = counties
    req = urllib.request.Request(f"{config.EE_API}/reports", data=json.dumps(payload).encode("utf-8"),
                                 method="POST", headers={"Content-Type": "application/json",
                                                         "User-Agent": config.USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=config.REQUEST_TIMEOUT_S) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        raise SourceError(f"EHR atsakė HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}") from e
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise SourceError(f"EHR nepasiekiamas: {e}") from e


def county_codes(names):
    """Apskričių pavadinimai arba kodai -> EHAK kodai („Harju“ -> „37“)."""
    table = classifiers()["maakond"]
    out = []
    for n in names:
        n = n.strip()
        hit = n if n in table else next((k for k, v in table.items() if fold(v).startswith(fold(n))), None)
        if not hit:
            raise SourceError(f"nežinoma apskritis „{n}“; galimos: {', '.join(table.values())}")
        out.append(hit)
    return out


def build_signal(doc_nr, rows, con=None):
    r = rows[0]
    code = (r.get(F["code"]) or "").strip()
    st_code, typ, label = status(r.get(F["status"]))
    if r.get("_dok_tipas"):                 # API: signalas – konkretus dokumentas
        typ, label = r["_dok_tipas"], r.get("_dok_zyme") or label
    cls = classifiers()
    use_id = str(r.get(F["use"]) or "").split(".")[0]
    use_code, use_et = cls["kaos"].get(use_id) or [r.get("_kaos_kood") or use_id, r.get("_kaos_tekstas") or ""]
    use_lt = _prefix_match(use_code, USE_LT) or ""
    purposes = f"{use_lt} ({use_et})" if use_lt and use_et else (use_lt or use_et)
    points = _prefix_match(use_code, config.SCORE_PURPOSE["EE"])
    if points is None:
        points = -1 if (r.get(F["kind"]) or "").upper() == "R" else 0
    municipality = cls["omavalitsus"].get(str(r.get(F["municipality"]) or "").strip()) \
        or cls["maakond"].get(str(r.get(F["county"]) or "").strip(), "")
    lat, lon = db.get_point(con, CODE, code) if con is not None else (None, None)
    when = [f"planuojama pradžia {norm_date(r.get(F['start']))}" if norm_date(r.get(F["start"])) else "",
            f"naudojimas nuo {norm_date(r.get(F['use_from']))}" if norm_date(r.get(F["use_from"])) else ""]
    return {
        "signal_id": doc_nr,
        "country": CODE,
        "doc_date": r.get("_ivykio_data") or norm_date(r.get(F["updated"])),
        "signal_type": typ or "kita",
        "signal_label": f"EE: {label}",
        "doc_text": " · ".join(x for x in (f"EHR {code}", r.get("_dok_nr") or "",
                                           cls["seisund"].get(st_code) or r.get("_busena_tekstas") or st_code) if x),
        "works_type": "; ".join(w for w in when if w),
        "purposes": purposes,
        "category": "statinys (rajatis)" if (r.get(F["kind"]) or "").upper() == "R" else "pastatas (hoone)",
        "object_names": r.get(F["name"]) or use_et or "",
        "object_count": 1,
        "address": r.get(F["address"]) or r.get(F["short_address"]) or "",
        "municipality": municipality,
        "cadastre": "",
        "project_name": r.get(F["name"]) or "",
        "project_nr": code,
        "lat": lat,
        "lon": lon,
        "point_lks": "",
        "score": config.SCORE["type"].get(typ, 0) + points,
    }


def is_excluded(rows):
    return any(status(r.get(F["status"]))[1] is None for r in rows)


def diagnose():
    ok = True
    limiter = _Limiter(config.EE_API_RPS)
    since = (date.today() - timedelta(days=1)).isoformat()
    try:
        feed = _api_get(f"find/ehrcodes/dateafter?timestamp={since}T00:00:00&offset=0", limiter)
        if feed is None:
            raise SourceError("pokyčių srautas nerastas (HTTP 404)")
        print(f"  EE statinių API: pokyčių nuo {since} – {len(feed)}{'+' if len(feed) >= 1000 else ''}")
        if not feed:
            print("  EE: DĖMESIO, per parą nė vieno pokyčio – srautas neveikia?")
            ok = False
        if feed:
            code = str(feed[-1]["ehr_kood"])
            versions = _api_get(f"buildingVersions?ehr_code={code}", limiter) or []
            data = (_api_get(f"buildingData?ehr_code={code}", limiter) or {}).get("ehitis") or {}
            row = building_row(data)
            last = max(versions, key=lambda v: int(v.get("ver_nr") or 0), default={})
            print(f"  EE pavyzdys {code}: {row[F['name']] or '?'}, {row[F['status']] or '?'}, "
                  f"dokumentas {last.get('doty_id')} {last.get('dok_nr') or ''}, "
                  f"koordinatės {'yra' if _point_from_building(data)[0] else 'nėra'}")
            if not row[F["status"]] or not row[F["code"]]:
                print("  EE: DĖMESIO, buildingData atsakyme nėra laukų seisund/ehrKood – API pasikeitė?")
                ok = False
    except (SourceError, KeyError, TypeError, AttributeError) as e:
        print(f"  EE statinių API: KLAIDA {e}")
        ok = False
    try:
        req = urllib.request.Request(f"{config.EE_API}/reports/{config.EE_REPORT}",
                                     headers={"User-Agent": config.USER_AGENT})
        with urllib.request.urlopen(req, timeout=config.REQUEST_TIMEOUT_S) as resp:
            cols = [c["column_name"] for c in json.load(resp)["data"]["description"]]
    except (OSError, ValueError, KeyError, TypeError) as e:
        print(f"  EE ataskaitos ({config.EE_REPORT}): KLAIDA {e}")
        return ok
    missing = [c for c in F.values() if c not in cols]
    print(f"  EE ataskaita {config.EE_REPORT}: {len(cols)} stulpeliai" +
          (f", TRŪKSTA: {', '.join(missing)}" if missing else ", laukai OK"))
    return ok

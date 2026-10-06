# -*- coding: utf-8 -*-
"""Duomenų gavimas iš data.gov.lt (Spinta API) ir atsarginis CSV importas."""
import csv
import datetime
import http.client
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter

import config

# Spinta užklausos sintaksė nėra įprastas key=value, todėl šių simbolių nekoduojame
_SAFE = "()=<>\"',&_-.:/*"


class FetchError(Exception):
    pass


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=config.REQUEST_TIMEOUT_S) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status, body
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        return e.code, body
    except urllib.error.URLError as e:
        raise FetchError(f"Nepavyko prisijungti: {e.reason}") from e
    except (http.client.HTTPException, OSError) as e:   # nutrūkęs atsakymas, laiko limitas
        raise FetchError(f"Ryšys nutrūko: {e!r}") from e


def _blocked(body):
    return "blocked" in (body or "")[:300000].lower()


def _http_error(status, body, what="API grąžino"):
    if _blocked(body):
        return FetchError("API užklausą užblokavo data.gov.lt ugniasienė. Leiskite iš Lietuvos IP adreso "
                          "arba įkelkite CSV: python sistema.py import-csv <failas>.")
    if status == 404:
        return FetchError(f"Rinkinys nerastas (HTTP 404): {', '.join(_models())}. Patikrinkite config.MODEL "
                          "su `python sistema.py diagnose --salis LT` ir data.gov.lt rinkinio Nr. 1000 puslapiu.")
    return FetchError(f"{what} HTTP {status}: {' '.join(body.split())[:300]}")


def _models():
    """Dabartinis modelio kelias ir senesni (rinkinys 2025-07 perkeltas iš vtpsi į ssva)."""
    return [config.MODEL] + [m for m in getattr(config, "MODEL_FALLBACKS", []) if m != config.MODEL]


def _url(query_parts, model=None):
    q = "&".join(p for p in query_parts if p)
    return f"{config.API_BASE}/{model or config.MODEL}" + ("?" + urllib.parse.quote(q, safe=_SAFE) if q else "")


def _first(query_parts):
    """Pirmoji užklausa: bandomi visi žinomi modelio keliai, kol kuris nors neatsako 404."""
    for model in _models():
        status, body = _get(_url(query_parts, model))
        if status != 404 or _blocked(body):
            break
    return model, status, body


def _retry(url, tries=3):
    """Laikinoms klaidoms (429, 5xx, nutrūkęs ryšys) – pakartojimai po vis ilgesnės pauzės."""
    for attempt in range(tries):
        try:
            status, body = _get(url)
        except FetchError:
            if attempt == tries - 1:
                raise
        else:
            if not (status == 429 or status >= 500 and not _blocked(body)) or attempt == tries - 1:
                return status, body
        time.sleep(max(config.REQUEST_PAUSE_S, 1) * 5 * (attempt + 1))


def _parse(body):
    """Grąžina (įrašai, kito puslapio žymė)."""
    if body.lstrip().startswith("<"):
        if _blocked(body):
            raise _http_error(200, body)
        raise FetchError("Vietoj JSON gautas HTML: " + " ".join(body.split())[:300])
    d = json.loads(body)
    rows = d.get("_data", d if isinstance(d, list) else [])
    page = d.get("_page") or {}
    nxt = page.get("next") if isinstance(page, dict) else None
    return rows, nxt


def fetch_since(since_date, max_pages=500, verbose=True, field=None, allow_client=True):
    """Parsiunčia įrašus, kurių dokumento_reg_data (arba field) >= since_date (YYYY-MM-DD).

    Pirmiausia bando filtruoti serveryje. Tik jei serveris atmeta patį filtrą (HTTP 400),
    pereina prie viso rinkinio puslapiavimo ir filtruoja vietoje (lėčiau). 404 – neteisingas
    rinkinio kelias, 429/5xx – laikina klaida: tada stabdoma, kad nebūtų tylių spragų.
    """
    date_field = field or config.F["doc_date"]
    server_filter = f'{date_field}>="{since_date}"'
    rows_all, mode = [], "server"

    model, status, body = _first([server_filter, f"limit({config.PAGE_LIMIT})"])
    if status >= 400 and _blocked(body):
        raise _http_error(status, body)
    if status == 429 or status >= 500:
        status, body = _retry(_url([server_filter, f"limit({config.PAGE_LIMIT})"], model))
    if status == 400 and not allow_client:
        raise _http_error(status, body, f"Filtras pagal {date_field} nepriimtas:")
    if status == 400:
        if verbose:
            print("  Serveris nepriėmė datos filtro (HTTP 400), imu visą rinkinį ir filtruoju vietoje.",
                  file=sys.stderr)
        mode = "client"
        status, body = _retry(_url([f"limit({config.PAGE_LIMIT})"], model))
    if status >= 400:
        raise _http_error(status, body)
    if verbose and model != config.MODEL:
        print(f"  Naudojamas senesnis rinkinio kelias {model} (pakeiskite config.MODEL).", file=sys.stderr)

    pages = 0
    while True:
        rows, nxt = _parse(body)
        if mode == "client":
            rows = [r for r in rows if (r.get(date_field) or "")[:10] >= since_date]
        rows_all.extend(rows)
        pages += 1
        if verbose:
            print(f"  puslapis {pages}: +{len(rows)} (iš viso {len(rows_all)})", file=sys.stderr)
        if not nxt:
            break
        if pages >= max_pages:
            raise FetchError(f"Pasiekta {max_pages} puslapių riba, o duomenų dar yra – rezultatas būtų nepilnas. "
                             "Sumažinkite laikotarpį (--since) arba padidinkite max_pages.")
        time.sleep(config.REQUEST_PAUSE_S)
        parts = [server_filter] if mode == "server" else []
        parts += [f"limit({config.PAGE_LIMIT})", f'page("{nxt}")']
        status, body = _retry(_url(parts, model))
        if status >= 400:
            raise _http_error(status, body, "Puslapiavimas nutrūko:")
    return rows_all


SAMPLE_FIELDS = ("dok_tipo_kodas", "dok_irasas", "dok_statusas", "dokumento_kategorija", "statybos_rusis",
                 "statinio_kategorija", "statinio_paskirtis")


def diagnose():
    """Patikrina ryšį, rinkinio kelią ir laukus, parodo dažniausias reikšmes taisyklėms derinti."""
    recent = f'{config.F["doc_date"]}>="{(datetime.date.today() - datetime.timedelta(days=30)).isoformat()}"'
    model, status, body = _first([recent, "limit(500)"])
    print("Užklausa:", _url([recent, "limit(500)"], model))
    print("HTTP:", status)
    if status >= 400:
        print("KLAIDA:", _http_error(status, body))
        return False
    if model != config.MODEL:
        print(f"DĖMESIO: veikia senesnis kelias {model}; įrašykite jį į config.MODEL.")
    try:
        rows, nxt = _parse(body)
    except FetchError as e:
        print("KLAIDA:", e)
        return False
    except json.JSONDecodeError:
        print("Atsakymas ne JSON. Pradžia:", body[:500])
        return False
    if not rows:
        print("Įrašų negauta. Atsakymo pradžia:", body[:500])
        return False
    print(f"Gauta {len(rows)} įr., kitas puslapis: {'yra' if nxt else 'nėra'}")
    print("Laukai:", ", ".join(rows[0].keys()))
    missing = [v for v in config.F.values() if v not in rows[0]]
    if missing:
        print("DĖMESIO, config.F laukų nėra atsakyme:", ", ".join(missing))
    print("Pavyzdys:")
    for k, v in rows[0].items():
        print(f"  {k}: {str(v)[:100]}")
    # dažniausios reikšmės: pagal jas tikslinamos SIGNAL_RULES ir SCORE taisyklės
    import signals   # vėlyvas importas (signals importuoja config)
    for field in SAMPLE_FIELDS:
        counts = Counter(str(r.get(field) or "")[:80] for r in rows)
        print(f"{field}: " + "; ".join(f"{v or '(tuščia)'} ×{n}" for v, n in counts.most_common(8)))
    unknown = Counter(signals.doc_code(r) for r in rows if signals.doc_code(r) not in config.LT_DOC_TYPES)
    kita = sum(1 for r in rows if signals.doc_type(r)[0] == "kita")
    print(f"Neatpažinti dokumentai („Kita“): {kita} iš {len(rows)}")
    if unknown:
        print("Kodai, kurių nėra config.LT_DOC_TYPES (tipas pagal pavadinimą): "
              + "; ".join(f"{c or '(be kodo)'} ×{n}" for c, n in unknown.most_common(10)))
    # datos filtro patikra
    status, body = _get(_url([f'{config.F["doc_date"]}>="2026-01-01"', "limit(1)"], model))
    print("Datos filtras serveryje:", "veikia" if status < 400 else f"neveikia (HTTP {status})")
    return True


# --- Atsarginis šaltinis: tie patys duomenys SSVA ArcGIS paslaugoje (geoportal.lt) ---

ARCGIS_DATE_FIELDS = ("dokumento_reg_data", "iraso_data")
ARCGIS_PAGE = 2000          # paslaugos maxRecordCount


def _arcgis_date(value, with_time=False):
    """ArcGIS data (milisekundės nuo 1970-01-01 UTC) -> 'YYYY-MM-DD' (arba su laiku)."""
    if value in (None, ""):
        return None
    try:
        dt = datetime.datetime.fromtimestamp(int(value) / 1000, tz=datetime.timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return str(value)
    return dt.strftime("%Y-%m-%dT%H:%M:%S") if with_time else dt.date().isoformat()


def arcgis_row(feature):
    """ArcGIS objektas -> įrašas su tais pačiais laukais kaip data.gov.lt „Statinys“."""
    r = dict(feature.get("attributes") or {})
    r.pop("object_id", None)
    r["dokumento_reg_data"] = _arcgis_date(r.get("dokumento_reg_data"))
    r["iraso_data"] = _arcgis_date(r.get("iraso_data"), with_time=True)
    g = feature.get("geometry") or {}
    if g.get("x") is not None and g.get("y") is not None:
        r["taskas_wgs"] = f"POINT ({g['y']} {g['x']})"
    return r


def _arcgis_query(params):
    url = f"{config.LT_ARCGIS_URL}/query?" + urllib.parse.urlencode(params)
    status, body = _retry(url)
    if status >= 400:
        raise FetchError(f"SSVA ArcGIS paslauga grąžino HTTP {status}: {' '.join(body.split())[:300]}")
    try:
        d = json.loads(body)
    except json.JSONDecodeError as e:
        raise FetchError("SSVA ArcGIS paslauga grąžino ne JSON: " + " ".join(body.split())[:300]) from e
    if "error" in d:
        raise FetchError(f"SSVA ArcGIS paslaugos klaida: {d['error']}")
    return d


def fetch_arcgis(since_date, max_pages=500, verbose=True, status_since=None):
    """Įrašai iš SSVA ArcGIS paslaugos (puslapiais po 2000), kurių dokumento_reg_data >= since_date arba
    kurie keitėsi nuo status_since (iraso_data – pvz., prašymas vėliau atmestas; numatyta – since_date)."""
    rows, offset = [], 0
    status_since = status_since or since_date
    where = f"(dokumento_reg_data >= DATE '{since_date}' OR iraso_data >= DATE '{status_since}')"
    for page in range(1, max_pages + 1):
        d = _arcgis_query({
            "where": where, "outFields": "*", "returnGeometry": "true",
            "outSR": "4326", "orderByFields": "object_id", "resultOffset": offset,
            "resultRecordCount": ARCGIS_PAGE, "f": "json"})
        feats = d.get("features") or []
        rows.extend(r for r in map(arcgis_row, feats)
                    if (r.get("dokumento_reg_data") or "") >= since_date
                    or (r.get("iraso_data") or "")[:10] >= status_since)
        offset += len(feats)
        if verbose:
            print(f"  ArcGIS puslapis {page}: +{len(feats)} (iš viso {len(rows)})", file=sys.stderr)
        if not feats or not d.get("exceededTransferLimit"):
            return rows
        time.sleep(config.REQUEST_PAUSE_S)
    raise FetchError(f"Pasiekta {max_pages} puslapių riba, o duomenų dar yra – sumažinkite laikotarpį (--since).")


def diagnose_arcgis():
    """Patikrina SSVA ArcGIS paslaugą: laukai, paskutinė data, įrašų skaičius per savaitę."""
    try:
        cols = [c["name"] for c in json.loads(_get(config.LT_ARCGIS_URL + "?f=json")[1]).get("fields", [])]
        week = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
        n = _arcgis_query({"where": f"dokumento_reg_data >= DATE '{week}'", "returnCountOnly": "true",
                           "f": "json"}).get("count")
        last = _arcgis_query({"where": "1=1", "outStatistics": json.dumps([{
            "statisticType": "max", "onStatisticField": "dokumento_reg_data", "outStatisticFieldName": "d"}]),
            "f": "json"})["features"][0]["attributes"]["d"]
    except (FetchError, ValueError, KeyError, IndexError, TypeError) as e:
        print("ArcGIS: KLAIDA", e)
        return False
    missing = [v for k, v in config.F.items() if v not in cols and k not in ("point_lks", "point_wgs")]
    print(f"ArcGIS ({config.LT_ARCGIS_URL}): įrašų per 7 d. {n}, naujausia dokumento data {_arcgis_date(last)}"
          + (f", TRŪKSTA laukų: {', '.join(missing)}" if missing else ", laukai OK"))
    _print_unknown_codes()
    return not missing


def _print_unknown_codes(days=30):
    """Per paskutines dienas pasitaikę dokumentų kodai, kurių nėra config.LT_DOC_TYPES (su pavadinimu)."""
    since = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    try:
        d = _arcgis_query({
            "where": f"dokumento_reg_data >= DATE '{since}'", "groupByFieldsForStatistics": "dok_tipo_kodas,dokumento_kategorija",
            "outStatistics": json.dumps([{"statisticType": "count", "onStatisticField": "object_id",
                                          "outStatisticFieldName": "n"}]), "f": "json"})
    except FetchError as e:
        print("Kodų statistikos gauti nepavyko:", e)
        return
    rows = sorted((f["attributes"] for f in d.get("features") or []), key=lambda a: -(a.get("n") or 0))
    unknown = [a for a in rows if (a.get("dok_tipo_kodas") or "").upper() not in config.LT_DOC_TYPES]
    if unknown:
        print(f"Kodai per {days} d., kurių nėra config.LT_DOC_TYPES (tipas nustatomas pagal pavadinimą):")
        for a in unknown[:15]:
            print(f"  {a.get('dok_tipo_kodas') or '(be kodo)'} ×{a.get('n')}: {(a.get('dokumento_kategorija') or '')[:90]}")
    else:
        print(f"Visi per {days} d. pasitaikę dokumentų kodai yra config.LT_DOC_TYPES.")


def read_csv(path, since_date=None):
    """Nuskaito rankiniu būdu iš data.gov.lt atsisiųstą CSV (taip pat ZIP; UTF-8 arba Windows-1257).

    Failas skaitomas eilutė po eilutės, todėl tinka ir viso rinkinio CSV: senesni nei
    since_date įrašai atmetami neužimdami atminties.
    """
    import saltiniai   # vėlyvas importas: saltiniai paketas naudoja šį modulį per saltiniai.lt
    f = config.F["doc_date"]
    with saltiniai.open_text(path) as fh:
        header = fh.readline()
        names = next(csv.reader([header], delimiter=saltiniai.delimiter(header, ",;\t")), [])
        missing = [c for c in (config.F["doc_nr"], f) if c not in names]
        if missing:
            raise FetchError(f"CSV faile nėra stulpelių: {', '.join(missing)}. "
                             f"Ar tai Infostatybos „Statinys“ rinkinys? Stulpeliai: {names}")
        reader = csv.DictReader(fh, fieldnames=names, delimiter=saltiniai.delimiter(header, ",;\t"))
        return [r for r in reader if not since_date or (r.get(f) or "")[:10] >= since_date]

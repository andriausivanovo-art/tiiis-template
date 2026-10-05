# -*- coding: utf-8 -*-
"""Duomenų gavimas iš data.gov.lt (Spinta API) ir atsarginis CSV importas."""
import csv
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

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


def _blocked(body):
    return "blocked" in (body or "")[:300000].lower()


def _http_error(status, body, what="API grąžino"):
    if _blocked(body):
        return FetchError("API užklausą užblokavo data.gov.lt ugniasienė. Leiskite iš Lietuvos IP adreso "
                          "arba įkelkite CSV: python sistema.py import-csv <failas>.")
    return FetchError(f"{what} HTTP {status}: {' '.join(body.split())[:300]}")


def _url(query_parts):
    q = "&".join(p for p in query_parts if p)
    return f"{config.API_BASE}/{config.MODEL}" + ("?" + urllib.parse.quote(q, safe=_SAFE) if q else "")


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


def fetch_since(since_date, max_pages=500, verbose=True):
    """Parsiunčia įrašus, kurių dokumento_reg_data >= since_date (YYYY-MM-DD).

    Pirmiausia bando filtruoti serveryje. Jei serveris filtro nepriima,
    pereina prie viso rinkinio puslapiavimo ir filtruoja vietoje (lėčiau).
    """
    date_field = config.F["doc_date"]
    server_filter = f'{date_field}>="{since_date}"'
    rows_all, mode = [], "server"

    status, body = _get(_url([server_filter, f"limit({config.PAGE_LIMIT})"]))
    if status >= 400 and _blocked(body):
        raise _http_error(status, body)
    if status >= 400:
        if verbose:
            print(f"  Serveris nepriėmė datos filtro (HTTP {status}), imu visą rinkinį ir filtruoju vietoje.",
                  file=sys.stderr)
        mode = "client"
        status, body = _get(_url([f"limit({config.PAGE_LIMIT})"]))
        if status >= 400:
            raise _http_error(status, body)

    pages = 0
    while True:
        rows, nxt = _parse(body)
        if mode == "client":
            rows = [r for r in rows if (r.get(date_field) or "")[:10] >= since_date]
        rows_all.extend(rows)
        pages += 1
        if verbose:
            print(f"  puslapis {pages}: +{len(rows)} (iš viso {len(rows_all)})", file=sys.stderr)
        if not nxt or pages >= max_pages:
            break
        time.sleep(config.REQUEST_PAUSE_S)
        parts = [server_filter] if mode == "server" else []
        parts += [f"limit({config.PAGE_LIMIT})", f'page("{nxt}")']
        status, body = _get(_url(parts))
        if status >= 400:
            raise _http_error(status, body, "Puslapiavimas nutrūko:")
    return rows_all


def diagnose():
    """Patikrina ryšį ir parodo pirmo įrašo laukus – naudinga, jei VTPSI ką nors pakeitė."""
    url = _url(["limit(3)"])
    print("Užklausa:", url)
    status, body = _get(url)
    print("HTTP:", status)
    if status >= 400:
        print("KLAIDA:", _http_error(status, body))
        return False
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
    # datos filtro patikra
    status, body = _get(_url([f'{config.F["doc_date"]}>="2026-01-01"', "limit(1)"]))
    print("Datos filtras serveryje:", "veikia" if status < 400 else f"neveikia (HTTP {status})")
    return True


def read_csv(path, since_date=None):
    """Nuskaito rankiniu būdu iš data.gov.lt atsisiųstą CSV (atsarginis variantas).

    Failas skaitomas eilutė po eilutės, todėl tinka ir viso rinkinio CSV: senesni nei
    since_date įrašai atmetami neužimdami atminties.
    """
    f = config.F["doc_date"]
    with open(path, encoding="utf-8-sig", errors="replace", newline="") as fh:
        header = fh.readline()
        fh.seek(0)
        # skirtukas – dažniausias antraštės simbolis (data.gov.lt – kablelis, Excel – kabliataškis)
        reader = csv.DictReader(fh, delimiter=max(",;\t", key=header.count))
        missing = [c for c in (config.F["doc_nr"], f) if c not in (reader.fieldnames or [])]
        if missing:
            raise FetchError(f"CSV faile nėra stulpelių: {', '.join(missing)}. "
                             f"Ar tai Infostatybos „Statinys“ rinkinys? Stulpeliai: {reader.fieldnames}")
        return [r for r in reader if not since_date or (r.get(f) or "")[:10] >= since_date]

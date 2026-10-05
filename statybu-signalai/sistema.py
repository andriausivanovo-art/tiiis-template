# -*- coding: utf-8 -*-
"""Statybų signalų sistemos komandinė eilutė (Lietuva, Latvija, Lenkija, Estija).

    python sistema.py demo        išbandyti be interneto su demonstraciniais duomenimis
    python sistema.py diagnose    patikrinti ryšį su šaltiniais ir laukų pavadinimus
    python sistema.py run         savaitinis paleidimas: fetch + build + builders + report

Visos komandos: python sistema.py -h; komandos parinktys: python sistema.py <komanda> -h
"""
import argparse
import csv
import os
import re
import sys
import zipfile
from contextlib import closing
from datetime import date, datetime, timedelta

import config
import db
import enrich
import fetch
import report
import saltiniai

# Santykiniai config.py keliai skaičiuojami nuo programos aplanko, kad veiktų ir iš planuoklio
BASE = os.path.dirname(os.path.abspath(__file__))
DEMO_DB = "duomenys/demo.sqlite"
DEMO_DIR = "duomenys/demo"

# Ko tikimės iš šaltinių: ryšio klaida, ugniasienė, sugadintas ar ne tas failas
SOURCE_ERRORS = (saltiniai.SourceError, fetch.FetchError, OSError, ValueError, csv.Error, zipfile.BadZipFile)
FILE_ERRORS = (OSError, ValueError, csv.Error, zipfile.BadZipFile)


def _path(p):
    return p if os.path.isabs(p) else os.path.join(BASE, p)


def _rel(p):
    """Kelias pranešimams: santykinis nuo programos aplanko, jei failas jame."""
    try:
        r = os.path.relpath(p, BASE)
    except ValueError:  # kitas diskas (Windows)
        return p
    return p if r.startswith("..") else r


def _connect(args):
    return closing(db.connect(os.path.abspath(args.db) if args.db else _path(config.DB_PATH)))


def _today():
    return date.today()


def _err(msg):
    print(f"KLAIDA: {msg}", file=sys.stderr)


# --- Bendri žingsniai (naudoja kelios komandos ir testai) ---

def resolve_since(con, today=None, source="LT"):
    """Nuo kurios datos imti šaltinio įvykius, kai --since nenurodytas.

    Paskutinė turima šaltinio data minus OVERLAP_DAYS (vėluojantiems įrašams),
    pirmą kartą – FIRST_RUN_DAYS atgal nuo šiandien.
    """
    today = today or _today()
    last = db.last_since(con, source)
    if last:
        try:
            last_d = min(date.fromisoformat(last[:10]), today)
            return (last_d - timedelta(days=config.OVERLAP_DAYS)).isoformat()
        except ValueError:
            pass
    return (today - timedelta(days=config.FIRST_RUN_DAYS)).isoformat()


def build_signals(con, doc_nrs=None):
    """Perskaičiuoja signalus iš raw_records: doc_nrs=None – visiems dokumentams.

    Negaliojantys dokumentai praleidžiami, o jei signalas jau buvo – pašalinamas.
    """
    st = {"nauji": 0, "atnaujinti": 0, "atmesti": 0, "pasalinti": 0}
    for doc_nr, (source, rows) in db.raw_groups(con, doc_nrs).items():
        if not doc_nr or not rows:
            continue
        src = saltiniai.get(source)
        if src.is_excluded(rows):
            st["atmesti"] += 1
            st["pasalinti"] += db.delete_signal(con, doc_nr)
            continue
        st["nauji" if db.upsert_signal(con, src.build_signal(doc_nr, rows, con)) else "atnaujinti"] += 1
    con.commit()
    return st


def fetch_country(con, code, since=None, today=None):
    """Parsisiunčia vienos šalies naujus įvykius į raw_records. Grąžina (nuo, gauta, nauji)."""
    since = since or resolve_since(con, today, code)
    print(f"{code}: imami įvykiai nuo {since}", flush=True)
    items = saltiniai.get(code).fetch_items(con, since, today or _today())
    return since, len(items), db.insert_rows(con, code, items)


def builder_codes(con):
    """Statytojų kodai, jau priskirti signalams (jiems ir įkeliami JAR/Sodros duomenys)."""
    cur = con.execute("SELECT DISTINCT builder_code FROM signals WHERE TRIM(COALESCE(builder_code, '')) != ''")
    return {r[0].strip() for r in cur}


def make_report(con, since=None, until=None, by="doc_date", period=None, all_types=False,
                prefix="", title="Statybų signalai", stamp=None, countries=None):
    """Sukuria CSV, statytojų paieškos eilę ir HTML ataskaitą aplanke isvestis/.

    since/until – filtro ribos stulpeliui `by` (doc_date arba first_seen),
    period – (nuo, iki) datos ataskaitos antraštei. Grąžina eilutes ir failų kelius.
    """
    rows = report.fetch_rows(con, since=since, until=until, by=by, countries=countries,
                             types=None if all_types else config.SELLABLE_TYPES)
    stamp = stamp or _today().isoformat()
    p_from, p_to = period or ((since or "")[:10], (until or stamp)[:10])
    out = _path(config.OUTPUT_DIR)
    res = {"rows": rows, "from": p_from, "to": p_to,
           "queue_path": os.path.join(out, f"{prefix}statytoju_eile_{stamp}.csv")}
    res["csv"] = report.write_csv(rows, os.path.join(out, f"{prefix}signalai_{stamp}.csv"))
    res["queue"] = report.write_builder_queue(rows, res["queue_path"])
    res["html"] = report.write_html(rows, os.path.join(out, f"{prefix}ataskaita_{stamp}.html"), p_from, p_to, title)
    return res


def print_report(res):
    rows = res["rows"]
    print(f"Ataskaita {res['from']} – {res['to']}: {len(rows)} "
          f"{report.plural(len(rows), 'signalas', 'signalai', 'signalų')}")
    for title, key in (("Šalys", "country"), ("Tipai", "signal_type")):
        counts = {}
        for r in rows:
            counts[r[key]] = counts.get(r[key], 0) + 1
        names = config.COUNTRY_NAMES if key == "country" else config.TYPE_LABELS
        if counts:
            ordered = sorted(counts.items(), key=lambda x: -x[1])
            print(f"  {title}: " + ", ".join(f"{names.get(k, k)} {n}" for k, n in ordered))
    print(f"  CSV:            {_rel(res['csv'])}")
    print(f"  Statytojų eilė: {_rel(res['queue_path'])} (be statytojo: {res['queue']})")
    print(f"  HTML:           {_rel(res['html'])}")


def select_rows(rows, paskirtis=None, savivaldybe=None):
    """Atrenka signalus pagal paskirties ir savivaldybės fragmentus (nesvarbu raidžių dydis ir diakritikai)."""
    p, m = saltiniai.fold(paskirtis), saltiniai.fold(savivaldybe)
    out = []
    for r in rows:
        what = " ".join(filter(None, [r.get("purposes"), r.get("object_names"), r.get("project_name")]))
        if p and p not in saltiniai.fold(what):
            continue
        if m and m not in saltiniai.fold(r.get("municipality") or r.get("address")):
            continue
        out.append(r)
    return out


def _slug(*parts):
    s = re.sub(r"[^a-z0-9]+", "-", saltiniai.fold(" ".join(p for p in parts if p))).strip("-")
    return s[:50].strip("-") or "visi"


def _source_failed(code, e):
    _err(f"{code}: {e}")
    if code == "LT":
        print("Jei data.gov.lt blokuoja užklausas, paleiskite iš Lietuvos IP adreso arba atsisiųskite CSV\n"
              "iš data.gov.lt ir įkelkite: python sistema.py import-csv <failas.csv>", file=sys.stderr)


# --- Komandos ---

def cmd_diagnose(args):
    ok = True
    for code in args.salis or saltiniai.codes():
        print(f"== {code}: {saltiniai.get(code).NAME}")
        try:
            ok = saltiniai.get(code).diagnose() and ok
        except SOURCE_ERRORS as e:
            _err(f"{code}: {e}")
            ok = False
    return 0 if ok else 2


def cmd_fetch(args):
    failed = []
    with _connect(args) as con:
        for code in args.salis or config.RUN_COUNTRIES:
            try:
                since, got, new = fetch_country(con, code, args.since)
            except SOURCE_ERRORS as e:
                _source_failed(code, e)
                db.log_run(con, args.since, 0, 0, 0, f"fetch {code} KLAIDA: {e}")
                failed.append(code)
                continue
            db.log_run(con, since, got, new, 0, f"fetch {code}")
            print(f"{code}: gauta {got}, naujų {new}.")
    print("Toliau: python sistema.py build")
    return 2 if failed else 0


def cmd_import(args):
    if args.salis and len(args.salis) > 1:
        _err("importuojant nurodykite vieną šalį, pvz. --salis LV")
        return 1
    code = args.salis[0] if args.salis else "LT"
    with _connect(args) as con:
        since = args.since or resolve_since(con, source=code)
        print(f"{code}: skaitomi {', '.join(args.failai)} (įvykiai nuo {since}; visiems – --since 2000-01-01)")
        try:
            items = saltiniai.get(code).read_files(con, args.failai, since, _today())
        except SOURCE_ERRORS as e:
            _err(e)
            return 1
        new = db.insert_rows(con, code, items)
        db.log_run(con, since, len(items), new, 0, f"import {code} {', '.join(os.path.basename(f) for f in args.failai)}")
    print(f"Nuskaityta įrašų: {len(items)}, naujų: {new}. Toliau: python sistema.py build")
    if code == "EE":
        print("Jei įkėlėte koordinačių ataskaitą (ehitise_ruumikuju), paleiskite: python sistema.py build --all")
    return 0


def cmd_import_csv(args):
    args.salis, args.failai = ["LT"], [args.failas]
    return cmd_import(args)


def cmd_build(args):
    with _connect(args) as con:
        st = build_signals(con, None if args.all else db.docs_to_build(con))
    print(f"Signalai: nauji {st['nauji']}, atnaujinti {st['atnaujinti']}, "
          f"atmesti negaliojantys {st['atmesti']} (iš jų pašalinti anksčiau buvę: {st['pasalinti']}).")
    return 0


def cmd_enrich(args):
    with _connect(args) as con:
        only = None
        if not args.all:
            only = builder_codes(con)
            if not only:
                print("Signaluose dar nėra statytojų kodų: užpildykite duomenys/builders.csv ir paleiskite\n"
                      "„python sistema.py builders“, arba įkelkite visas įmones su --all.")
                return 0
        try:
            n = enrich.load_companies(con, args.failas, only)
        except FILE_ERRORS as e:
            _err(e)
            return 1
    print(f"Įkelta įmonių: {n}" + (f" (ieškota statytojų: {len(only)})" if only is not None else "") + ".")
    return 0


def cmd_builders(args):
    path = _path(config.BUILDERS_CSV)
    with _connect(args) as con:
        try:
            n = enrich.apply_builders(con, path)
        except FILE_ERRORS as e:
            _err(e)
            return 1
    print(f"Statytojai priskirti signalams: {n} (failas {_rel(path)}).")
    if not n:
        print("Statytojus įrašykite pagal isvestis/statytoju_eile_*.csv (žr. README.md).")
    return 0


def cmd_report(args):
    today = _today()
    since = (today - timedelta(days=args.days)).isoformat()
    suffix = " (visi tipai)" if args.all_types else ""
    with _connect(args) as con:
        if args.gauti:
            res = make_report(con, since=since, by="first_seen", period=(since, today.isoformat()),
                              all_types=args.all_types, countries=args.salis,
                              title=f"Statybų signalai, gauti per {args.days} d.{suffix}")
        else:
            res = make_report(con, since=since, until=today.isoformat(), by="doc_date", countries=args.salis,
                              all_types=args.all_types, title=f"Statybų signalai{suffix}")
    print_report(res)
    return 0


def cmd_sample(args):
    today = _today()
    since = (today - timedelta(days=args.days)).isoformat()
    with _connect(args) as con:
        rows = report.fetch_rows(con, since=since, until=today.isoformat(), by="doc_date", countries=args.salis,
                                 types=args.tipas or config.SELLABLE_TYPES)
    rows = select_rows(rows, args.paskirtis, args.savivaldybe)
    heading = args.antraste or "Statybų signalai" + (f": {args.savivaldybe}" if args.savivaldybe else "")
    slug = _slug(",".join(args.salis or []), args.paskirtis, args.savivaldybe, ",".join(args.tipas or []))
    path = os.path.abspath(args.failas) if args.failas else os.path.join(
        _path(config.OUTPUT_DIR), f"pavyzdys_{slug}_{today.isoformat()}.html")
    report.write_client_sample(rows, path, heading, since, today.isoformat(), limit=args.limit, contact=args.kontaktas)
    print(f"Pavyzdys klientui: {min(len(rows), args.limit)} iš {len(rows)} tinkamų signalų -> {_rel(path)}")
    if not rows:
        print(f"Per {args.days} d. pagal filtrus signalų nerasta: padidinkite --days arba praplėskite filtrus.")
    return 0


def cmd_run(args):
    today = _today()
    countries = args.salis or config.RUN_COUNTRIES
    done, failed, since_note, fetched, new_raw = [], [], [], 0, 0
    with _connect(args) as con:
        prev = db.last_run(con)
        print(f"Savaitinis paleidimas {db.now_iso()}: {', '.join(countries)}")
        for code in countries:
            try:
                since, got, new = fetch_country(con, code, args.since, today)
            except SOURCE_ERRORS as e:
                _source_failed(code, e)
                failed.append(f"{code} ({str(e)[:80]})")
                continue
            done.append(code)
            since_note.append(f"{code} {since}")
            fetched, new_raw = fetched + got, new_raw + new
            print(f"{code}: gauta {got}, naujų {new}.")
        if not done:
            db.log_run(con, None, 0, 0, 0, "run KLAIDA: " + "; ".join(failed))
            return 2
        st = build_signals(con, db.docs_to_build(con))
        n_builders = enrich.apply_builders(con, _path(config.BUILDERS_CSV))
        print(f"Signalai: nauji {st['nauji']}, atnaujinti {st['atnaujinti']}, atmesti {st['atmesti']}. "
              f"Statytojai priskirti: {n_builders}.")
        # Ataskaitoje – signalai, atsiradę po ankstesnio paleidimo (pirmą kartą – visi).
        # Taip vėluojantys įrašai nepradingsta, o tas pats signalas dviejose savaitėse nesikartoja.
        if prev:
            since_ts = (datetime.fromisoformat(prev) + timedelta(seconds=1)).isoformat(sep=" ")
            period = (prev[:10], today.isoformat())
        else:
            first = min(s.split()[1] for s in since_note)
            since_ts, period = None, (first, today.isoformat())
        res = make_report(con, since=since_ts, by="first_seen", period=period, title="Nauji statybų signalai")
        note = f"run: {os.path.basename(res['html'])}" + (f"; nepavyko: {'; '.join(failed)}" if failed else "")
        db.log_run(con, "; ".join(since_note), fetched, new_raw, st["nauji"], note)
    print_report(res)
    if failed:
        print("Nepavyko: " + "; ".join(failed), file=sys.stderr)
    return 2 if failed else 0


def cmd_ee_order(args):
    try:
        counties = saltiniai.get("EE").county_codes(args.apskritis.split(",")) if args.apskritis else None
        res = saltiniai.get("EE").order_report(args.email, args.ataskaita, counties=counties,
                                               statuses=args.busenos.split(",") if args.busenos else None)
    except SOURCE_ERRORS as e:
        _err(e)
        return 2
    print(f"EHR ataskaita „{args.ataskaita}“ užsakyta, nuoroda bus atsiųsta {args.email}. Atsakymas: "
          f"{str(res.get('message') if isinstance(res, dict) else res)[:200]}")
    print("Gavę failą: python sistema.py import --salis EE <failas arba nuoroda>")
    return 0


def cmd_demo(args):
    from demo import generate_demo

    db_path, demo_dir = _path(DEMO_DB), _path(DEMO_DIR)
    try:
        if os.path.exists(db_path):
            os.remove(db_path)  # demonstracija kaskart pradedama iš naujo
    except OSError as e:
        _err(f"nepavyko ištrinti {_rel(db_path)} ({e}). Uždarykite programas, kurios jį naudoja.")
        return 1
    today = _today()
    demo = generate_demo.generate(today)
    files = generate_demo.write_support_files(demo_dir, demo)
    foreign = generate_demo.write_foreign_files(demo_dir, today)
    period_from = (today - timedelta(days=14)).isoformat()
    counts = {}
    with closing(db.connect(db_path)) as con:
        counts["LT"] = db.insert_raw(con, demo["rows"], config.F)
        # kitų šalių failai eina tuo pačiu keliu kaip tikri atsisiųsti failai
        for code, paths in foreign.items():
            items = saltiniai.get(code).read_files(con, paths, period_from, today)
            counts[code] = db.insert_rows(con, code, items)
        st = build_signals(con)
        n_builders = enrich.apply_builders(con, files["builders"])
        codes = builder_codes(con)
        n_jar = enrich.load_companies(con, files["jar"], codes)
        n_sodra = enrich.load_companies(con, files["sodra"], codes)
        res = make_report(con, since=period_from, until=today.isoformat(), by="doc_date",
                          prefix="demo_", title="Statybų signalai · DEMO duomenys")
        sample_rows = select_rows(report.fetch_rows(con, since=period_from, types=config.SELLABLE_TYPES),
                                  paskirtis="daugiabu")
        sample = report.write_client_sample(
            sample_rows, os.path.join(_path(config.OUTPUT_DIR), f"demo_pavyzdys_daugiabuciai_{today.isoformat()}.html"),
            "Daugiabučių statybos signalai (DEMO)", period_from, today.isoformat(), limit=10,
            contact="Tokį sąrašą kas savaitę gautumėte el. paštu. DEMO duomenys – objektai ir įmonės išgalvoti.")
        db.log_run(con, period_from, sum(counts.values()), sum(counts.values()), st["nauji"], "demo")
    print("Demonstraciniai įrašai: " + ", ".join(f"{config.COUNTRY_NAMES[c]} {n}" for c, n in counts.items())
          + f" -> {_rel(db_path)}")
    print(f"Signalai: nauji {st['nauji']}, atmesti negaliojantys {st['atmesti']}.")
    print(f"Statytojai iš {_rel(files['builders'])}: {n_builders}; įmonės iš JAR: {n_jar}, iš Sodros: {n_sodra}.")
    print_report(res)
    print(f"Pavyzdys klientui: {_rel(sample)} ({min(len(sample_rows), 10)} signalų)")
    print(f"Atidarykite naršyklėje: {res['html']}")
    return 0


# --- Argumentai ---

class _Formatter(argparse.HelpFormatter):
    def add_usage(self, usage, actions, groups, prefix=None):
        return super().add_usage(usage, actions, groups, prefix or "naudojimas: ")


class _Parser(argparse.ArgumentParser):
    """argparse su lietuviškomis antraštėmis (sub-komandos paveldi šią klasę)."""

    def __init__(self, *a, **kw):
        kw.setdefault("add_help", False)
        kw.setdefault("formatter_class", _Formatter)
        super().__init__(*a, **kw)
        self._positionals.title = "argumentai"
        self._optionals.title = "parinktys"
        self.add_argument("-h", "--help", action="help", help="parodyti šią pagalbą")

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: klaida: {message}\n")


def _date_arg(s):
    try:
        return date.fromisoformat(s).isoformat()
    except ValueError:
        raise argparse.ArgumentTypeError(f"neteisinga data „{s}“, reikia YYYY-MM-DD") from None


def _int_arg(minimum):
    def parse(s):
        try:
            v = int(s)
        except ValueError:
            raise argparse.ArgumentTypeError(f"„{s}“ nėra sveikasis skaičius") from None
        if v < minimum:
            raise argparse.ArgumentTypeError(f"turi būti ne mažiau kaip {minimum}")
        return v
    return parse


def _types_arg(s):
    known = list(config.TYPE_LABELS)
    types = [t.strip() for t in s.split(",") if t.strip()]
    bad = [t for t in types if t not in known]
    if bad or not types:
        raise argparse.ArgumentTypeError(f"nežinomas tipas {', '.join(bad) or s}; galimi: {', '.join(known)}")
    return types


def _countries_arg(s):
    codes = [c.strip().upper() for c in s.split(",") if c.strip()]
    bad = [c for c in codes if c not in config.COUNTRY_NAMES]
    if bad or not codes:
        raise argparse.ArgumentTypeError(f"nežinoma šalis {', '.join(bad) or s}; galimos: "
                                         f"{', '.join(config.COUNTRY_NAMES)}")
    return codes


def build_parser():
    p = _Parser(prog="sistema.py", description="Statybų signalai iš Lietuvos, Latvijos, Lenkijos ir Estijos "
                                               "statybų registrų atvirų duomenų.")
    p.add_argument("--db", metavar="FAILAS",
                   help=f"SQLite duomenų bazė (numatyta {config.DB_PATH} programos aplanke)")
    sub = p.add_subparsers(dest="cmd", title="komandos", metavar="KOMANDA")
    since_help = ("nuo kurios datos imti įvykius (numatyta: paskutinė turima data minus "
                  f"{config.OVERLAP_DAYS} d., pirmą kartą – {config.FIRST_RUN_DAYS} d. atgal)")
    countries = ", ".join(f"{k} – {v}" for k, v in config.COUNTRY_NAMES.items())

    def salis(parser, default_note):
        parser.add_argument("--salis", type=_countries_arg, metavar="LT,LV,PL,EE",
                            help=f"šalys per kablelį ({countries}); numatyta: {default_note}")

    s = sub.add_parser("diagnose", help="patikrinti ryšį su šaltiniais ir laukų pavadinimus")
    salis(s, "visos")
    s.set_defaults(func=cmd_diagnose)

    s = sub.add_parser("fetch", help="parsisiųsti naujus įvykius iš šaltinių")
    s.add_argument("--since", type=_date_arg, metavar="YYYY-MM-DD", help=since_help)
    salis(s, ", ".join(config.RUN_COUNTRIES))
    s.set_defaults(func=cmd_fetch)

    s = sub.add_parser("import", help="įkelti rankiniu būdu atsisiųstus failus (CSV, ZIP arba nuorodą)")
    s.add_argument("failai", nargs="+", help="failai arba nuorodos (LV – iki trijų BIS failų, EE – ataskaitos)")
    s.add_argument("--salis", type=_countries_arg, metavar="XX", default=["LT"], help="šalis (numatyta LT)")
    s.add_argument("--since", type=_date_arg, metavar="YYYY-MM-DD",
                   help=since_help + "; visiems įrašams nurodykite 2000-01-01")
    s.set_defaults(func=cmd_import)

    s = sub.add_parser("import-csv", help="įkelti iš data.gov.lt atsisiųstą Infostatybos CSV (= import --salis LT)")
    s.add_argument("failas", help="CSV failas (Infostatybos rinkinys „Statinys“)")
    s.add_argument("--since", type=_date_arg, metavar="YYYY-MM-DD",
                   help=since_help + "; visiems įrašams nurodykite 2000-01-01")
    s.set_defaults(func=cmd_import_csv)

    s = sub.add_parser("build", help="perskaičiuoti signalus iš žalių įrašų (tik paveiktiems dokumentams)")
    s.add_argument("--all", action="store_true", help="perskaičiuoti visus dokumentus (pvz., pakeitus config.py)")
    s.set_defaults(func=cmd_build)

    s = sub.add_parser("enrich", help="įkelti įmonių duomenis iš JAR arba Sodros CSV/ZIP")
    s.add_argument("failas", help="JAR arba Sodros CSV ar ZIP failas")
    s.add_argument("--all", action="store_true", help="įkelti visas faile esančias įmones, ne tik statytojus")
    s.set_defaults(func=cmd_enrich)

    s = sub.add_parser("builders", help=f"priskirti statytojus iš {config.BUILDERS_CSV}")
    s.set_defaults(func=cmd_builders)

    s = sub.add_parser("report", help="sukurti CSV, statytojų paieškos eilę ir HTML ataskaitą")
    s.add_argument("--days", type=_int_arg(0), default=7, help="kiek dienų atgal (numatyta 7)")
    s.add_argument("--all-types", action="store_true", help="įtraukti ir neparduodamus tipus (pritarimai, griovimas, kita)")
    s.add_argument("--gauti", action="store_true",
                   help="laikotarpį taikyti gavimo datai (kada signalas atsirado DB), ne dokumento datai")
    salis(s, "visos")
    s.set_defaults(func=cmd_report)

    s = sub.add_parser("sample", help="statinis HTML pavyzdys klientui (tinka el. laiškui)")
    s.add_argument("--paskirtis", help="paskirties ar statinio fragmentas, pvz. daugiabu, sandėliav")
    s.add_argument("--savivaldybe", help="savivaldybės fragmentas, pvz. Kauno (tiks ir Kauno m., ir Kauno r.)")
    s.add_argument("--tipas", type=_types_arg, help="tipai per kablelį, pvz. prasymas,leidimas_nauja "
                                                    "(numatyta: visi parduodami tipai)")
    s.add_argument("--limit", type=_int_arg(1), default=10, help="kiek signalų (numatyta 10)")
    s.add_argument("--antraste", help="laiško antraštė")
    s.add_argument("--days", type=_int_arg(0), default=30, help="kiek dienų atgal pagal dokumento datą (numatyta 30)")
    s.add_argument("--kontaktas", default="", help="kontaktinė eilutė pavyzdžio apačioje")
    s.add_argument("--failas", help="kur išsaugoti (numatyta isvestis/pavyzdys_..._DATA.html)")
    salis(s, "visos")
    s.set_defaults(func=cmd_sample)

    s = sub.add_parser("run", help="savaitinis paleidimas: fetch + build + builders + report")
    s.add_argument("--since", type=_date_arg, metavar="YYYY-MM-DD", help=since_help)
    salis(s, ", ".join(config.RUN_COUNTRIES))
    s.set_defaults(func=cmd_run)

    s = sub.add_parser("ee-order", help="užsakyti Estijos EHR ataskaitą (nuoroda atsiunčiama el. paštu)")
    s.add_argument("--email", required=True, help="el. pašto adresas, kuriuo EHR atsiųs nuorodą")
    s.add_argument("--ataskaita", default=config.EE_REPORT, choices=[config.EE_REPORT, config.EE_COORD_REPORT],
                   help=f"{config.EE_REPORT} – statiniai (numatyta), {config.EE_COORD_REPORT} – koordinatės")
    s.add_argument("--apskritis", help="apskritys per kablelį, pvz. Harju,Tartu (numatyta – visa Estija)")
    s.add_argument("--busenos", help=f"būsenų kodai per kablelį (numatyta {','.join(config.EE_ORDER_STATUSES)})")
    s.set_defaults(func=cmd_ee_order)

    s = sub.add_parser("demo", help=f"demonstraciniai duomenys į {DEMO_DB} ir ataskaita į {config.OUTPUT_DIR}/")
    s.set_defaults(func=cmd_demo)
    return p


def main(argv=None):
    # Windows konsolė ar planuoklio žurnalas gali būti ne UTF-8: lietuviška raidė neturi nutraukti darbo
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 1
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("Nutraukta.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())

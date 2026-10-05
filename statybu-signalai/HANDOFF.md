# Statybų signalų sistema: perdavimas tęsti debesies sesijoje

Tikslas: kas savaitę iš VTPSI „Infostatyba“ atvirų duomenų surinkti naujus statybą
leidžiančius dokumentus Lietuvoje, paversti juos signalais, praturtinti statytojo
įmonės duomenimis (JAR, Sodra) ir pateikti kaip CSV bei HTML ataskaitą.
Kalba: Python 3.10+, tik standartinė biblioteka (be pip priklausomybių).

## Kas jau padaryta

| Failas | Paskirtis |
| --- | --- |
| `config.py` | API adresas, laukų pavadinimai, signalų tipų taisyklės, svarbos balai |
| `db.py` | SQLite schema: `raw_records`, `signals`, `companies`, `runs` |
| `fetch.py` | Spinta API klientas su puslapiavimu ir datos filtru, `diagnose()`, CSV importas |
| `signals.py` | Grupavimas pagal dokumentą, tipo klasifikavimas, savivaldybė, WGS taškas, balas |
| `enrich.py` | JAR/Sodros CSV/ZIP įkėlimas su stulpelių atpažinimu, `builders.csv` |
| `report.py` | CSV eksportas, statytojų paieškos eilė, HTML ataskaita, statinis pavyzdys klientui |
| `templates/ataskaita.html` | Interaktyvi ataskaita: filtrai, Leaflet žemėlapis, CSV atsisiuntimas |

## Svarbūs faktai apie duomenis

- Rinkinys: data.gov.lt Nr. 1000, API modelis `datasets/gov/vtpsi/infostatyba/Statinys`.
- Laukai: `id, projekto_id, statinio_id, projekto_pavadinimas, projekto_reg_nr, projekto_metai,
  unikalus_numeris, statinio_paskirtis, statinio_pakeista_paskirtis, statinio_kategorija, adresas,
  statybos_rusis, statinio_pavadinimas, pastatymo_metai, kadastro_nr, ploto_reg_tipas,
  sklypo_reg_statusas, dokumento_reg_nr, dokumento_reg_data, iraso_paaiskinimas, iraso_data,
  dok_statusas, dok_tipo_kodas, dokumento_kategorija, dok_irasas, taskas_lks, taskas_wgs, uuid`.
- Vienas įrašas = statinys × dokumentas. Signalas = grupė pagal `dokumento_reg_nr`.
- `taskas_wgs` pavyzdys: `POINT (54.6750273775 25.2213355541)` (platuma pirma). `taskas_lks`: `POINT (6060527 578771)`.
- `dok_irasas` pavyzdžiai: „Deklaracija apie statybos užbaigimą / paskirties keitimą (tvirtina VTPSI)“,
  „Pažyma apie statinio statybą be nukrypimų nuo esminių statinio projekto sprendinių (tvirtina ekspertas)“.
  `dokumento_kategorija`: `aktas`, `prasymas`. `dok_statusas`: pvz. `Galiojantis`.
- **Statytojo lauko rinkinyje nėra.** Pirmoje versijoje statytojas įrašomas rankiniu būdu į
  `duomenys/builders.csv` (`dokumento_reg_nr;statytojo_kodas;statytojo_pavadinimas;pastaba`).
- **data.gov.lt ugniasienė blokavo užklausas iš užsienio duomenų centro IP.** Debesies VM greičiausiai
  irgi bus užblokuota, todėl čia viską testuok su demonstraciniais duomenimis. Tikras paleidimas –
  iš Lietuvos IP (savininko kompiuteris arba LT VPS).
- Spinta užklausų sintaksė: `?dokumento_reg_data>="2026-09-01"&limit(1000)`, kitas puslapis
  `&page("<_page.next>")`. Jei datos filtras grąžina klaidą, `fetch.py` pereina prie viso rinkinio.

## Būsena (2026-10-05): atlikta

Visi šeši anksčiau likę darbai padaryti, sistema išplėsta Latvijai, Lenkijai ir Estijai:

1. `sistema.py` – visos komandos (`diagnose`, `fetch`, `import-csv`, `build`, `enrich`, `builders`, `report`,
   `sample`, `run`, `demo`) ir naujos: `import` (bet kurios šalies failai ar nuorodos), `ee-order`, `--salis`.
2. `demo/generate_demo.py` – 87 LT įrašai (48 dokumentai, 7 savivaldybės, visi tipai, DEMO įmonės,
   builders/JAR/Sodros failai) ir LV/PL/EE failai tikrais šaltinių formatais.
3. `tests/` – 71 testas (`python -m unittest`), praeina su Python 3.10–3.13, be tinklo.
4. `README.md`, 5. `run_weekly.bat`, `.gitignore`, `.gitattributes`, 6. `PLANAS.md`.

Kitos šalys (`saltiniai/`): LV – BIS CSV iš data.gov.lv (bylų stadijų pokyčiai), PL – GUNB RWDZ ZIP
(leidimai su investuotoju, pranešimai), EE – EHR atvirų duomenų API (ataskaita užsakoma el. paštu, importas,
L-EST97 -> WGS84). LV ir PL patikrinti su tikrais duomenimis iš šios aplinkos (gyvas `run`: ~870 LV ir
~1 100 PL signalų per 30 d., ~30 s). LT API iš debesies užblokuotas („Web Page Blocked“), kaip ir tikėtasi.

Esamo kodo pataisymai (rasti rašant testus):
- `config.SIGNAL_RULES`: abu šio failo `dok_irasas` pavyzdžiai buvo klasifikuojami neteisingai
  („Deklaracija apie statybos užbaigimą / paskirties keitimą“ – kaip paskirties keitimo leidimas,
  „Pažyma ... be nukrypimų“ – kaip „Kita“). Dabar abu – „Statybos užbaigimas“.
- `report.fetch_rows`: `COALESCE(s.builder_name, c.name)` neveikė – `dict(sqlite3.Row)` ima pirmą vienodo
  pavadinimo stulpelį, todėl JAR pavadinimas niekada nepatekdavo į ataskaitą.
- `enrich._read_any`: `csv.Sniffer` Sodros failui parinkdavo kablelį (jis yra antraštėje ir sumose);
  skirtukas dabar nustatomas pagal antraštę.
- `fetch.read_csv` skaito srautu ir tikrina stulpelius; ugniasienės puslapis atpažįstamas iškart.
- `signals`: statiniai skaičiuojami ir pagal `statinio_id` (nauji statiniai neturi unikalaus numerio);
  paskirties balas – pagal vertingiausią statinį (tinklai prie namo balo nebemažina).
- `db`: šalies stulpeliai su automatine migracija, `taskai` lentelė koordinatėms.

## Kas liko (reikia Lietuvos IP arba savininko sprendimo)

- Paleisti `python sistema.py diagnose` ir pirmą `run` iš Lietuvos IP: patikrinti, ar Spinta datos filtras
  veikia, ar `config.F` laukai sutampa ir kokia „Kita“ dalis (`dok_irasas` reikšmes pritaikyti `SIGNAL_RULES`).
- `config.py`: `USER_AGENT` kontaktas, `INFOSTATYBA_SEARCH_URL`, `RUN_COUNTRIES`, `PL_WOJEWODZTWA`.
- EE: pirmą kartą užsakyti ataskaitą (`ee-order --email`) ir patikrinti tikro failo formatą (skirtukas,
  būsenų reikšmės); adapteris parašytas pagal EHR API metaduomenis, tikro failo dar nematėme.
- Įmonių duomenys LV/PL/EE (Uzņēmumu reģistrs, KRS/REGON, äriregister) dar nejungti – kol kas tik LT JAR/Sodra.

## Priėmimo kriterijai

- `python sistema.py demo` be klaidų sukuria `isvestis/` CSV ir HTML; HTML atsidaro naršyklėje.
- `python -m unittest` praeina.
- Jokių išorinių priklausomybių.
- Kodas ir pranešimai lietuviškai, kaip esamuose failuose.

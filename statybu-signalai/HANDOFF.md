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

## Likę darbai

1. `sistema.py` – CLI (argparse), komandos:
   - `diagnose` – `fetch.diagnose()`
   - `fetch [--since YYYY-MM-DD]` – jei nenurodyta: `db.last_since()` minus `OVERLAP_DAYS`, pirmą kartą `FIRST_RUN_DAYS`
   - `import-csv <failas> [--since]` – rankiniu būdu atsisiųstas CSV iš data.gov.lt
   - `build` – perkuria signalus iš `raw_records` (tik paveiktiems dokumentams), praleidžia `is_excluded`
   - `enrich <failas> [--all]` – JAR/Sodros failas; numatytai įkelia tik įmones iš `signals.builder_code`
   - `builders` – `enrich.apply_builders()`
   - `report [--days 7] [--all-types]` – CSV, statytojų eilė, HTML į `isvestis/` su data pavadinime
   - `sample --paskirtis X --savivaldybe Y --tipas Z --limit 10 --antraste "..."` – pavyzdys klientui
   - `run` – fetch + build + builders + report (savaitiniam paleidimui), įrašo į `runs`
   - `demo` – sugeneruoja demonstracinius duomenis į atskirą DB (`duomenys/demo.sqlite`) ir ataskaitą
2. `demo/generate_demo.py` – ~80 tikroviškų įrašų su tiksliais laukų pavadinimais, keli dokumentai su
   keliais statiniais, įvairūs tipai ir savivaldybės (Vilniaus m., Kauno m., Kauno r., Klaipėdos r.,
   Šiaulių m., Panevėžio m., Vilniaus r.), WGS taškai tose vietose. Įmonių pavadinimai su žodžiu „DEMO“.
3. Testai (`tests/`, unittest, kad nereikėtų pytest): `classify`, `wgs_point` (abi tvarkos), `municipality`,
   `build_signal` grupavimas ir balas, `enrich._map_columns` su JAR ir Sodros stiliaus antraštėmis,
   `report` smoke testas (HTML sugeneruojamas, JSON validus).
4. `README.md` (lietuviškai): diegimas, komandos, savaitinis paleidimas (`run_weekly.bat` Windows
   užduočių planuoklei ir cron eilutė), kaip pildyti `builders.csv`.
5. `run_weekly.bat`, `.gitignore` (`duomenys/*.sqlite`, `isvestis/`).
6. `PLANAS.md`: architektūra, 4 savaičių planas, pardavimai (viena niša, pavyzdys kaip pasiūlymas,
   kainų lygiai 49–79 / 149–249 / 300–500 / nuo 1000 € per mėn.), teisiniai klausimai (BDAR, licencija
   be perpardavimo teisės, veiklos forma, darbo sutarties apribojimai), sprendimo kriterijus
   (3–5 įmonės sutinka mokėti ar rimtai bandyti po 20–30 pavyzdžių).

## Priėmimo kriterijai

- `python sistema.py demo` be klaidų sukuria `isvestis/` CSV ir HTML; HTML atsidaro naršyklėje.
- `python -m unittest` praeina.
- Jokių išorinių priklausomybių.
- Kodas ir pranešimai lietuviškai, kaip esamuose failuose.

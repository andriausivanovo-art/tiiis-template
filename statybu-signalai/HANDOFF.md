# Statybų signalų sistema: perdavimas tęsti debesies sesijoje

Tikslas: kas savaitę iš „Infostatyba“ (SSVA, buv. VTPSI) atvirų duomenų surinkti naujus statybą
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

## Svarbūs faktai apie duomenis (patikrinta 2026-10-06 su tikrais duomenimis)

- Rinkinys: data.gov.lt Nr. 1000, API modelis `datasets/gov/ssva/infostatyba/Statinys` (2025-07 perkeltas iš
  `vtpsi`; senasis kelias liko `config.MODEL_FALLBACKS`). Licencija CC BY 4.0, atnaujinama kasdien.
- Tie patys duomenys (tie patys laukai, be `uuid`) – SSVA ArcGIS paslaugoje
  `https://www.geoportal.lt/mapproxy/rest/services/infostatyba_duomenys/MapServer/0` (data.gov.lt Nr. 3740),
  pasiekiama ir iš užsienio; programa ją naudoja, kai data.gov.lt blokuoja (`config.LT_SOURCE = "auto"`).
- Laukai: `id, projekto_id, statinio_id, projekto_pavadinimas, projekto_reg_nr, projekto_metai,
  unikalus_numeris, statinio_paskirtis, statinio_pakeista_paskirtis, statinio_kategorija, adresas,
  statybos_rusis, statinio_pavadinimas, pastatymo_metai, kadastro_nr, ploto_reg_tipas,
  sklypo_reg_statusas, dokumento_reg_nr, dokumento_reg_data, iraso_data,
  dok_statusas, dok_tipo_kodas, dokumento_kategorija, dok_irasas, taskas_lks, taskas_wgs, uuid`
  (`iraso_paaiskinimas` pašalintas 2026-04).
- Vienas įrašas = statinys × dokumentas; `id` – įrašo ID (unikalus), `uuid` – dokumento ID (bendras visiems
  jo statiniams, todėl raktu netinka). Signalas = grupė pagal `dokumento_reg_nr`.
- **Ankstesnė šio failo prielaida buvo klaidinga:** `dok_irasas` turi tik „prasymas“, „aktas“ arba
  „laukiama patvirtinimo“. Dokumento pavadinimas – `dokumento_kategorija` (pvz. „Leidimas statyti naują (- us)
  statinį (- ius)“), o tipą tiksliausiai nusako `dok_tipo_kodas` (SRA – prašymas, LSNS – leidimas statyti,
  LRS – rekonstruoti, ANN2 – statybos pradžia (be pavadinimo), ARCCR/ACCR2 – užbaigimo deklaracijos ...).
  Klasifikuojama pagal `config.LT_DOC_TYPES`, o nežinomi kodai – pagal pavadinimą (`SIGNAL_RULES`).
- `dokumento_reg_nr` = `<KODAS>-<NN>-<YYMMDD>-<eil. nr.>`; NN – savivaldybės kodas (`LT_SAV_BY_DOC_CODE`,
  patikrinta su adresais), 00/20/30 – nacionaliniai išdavėjai. Miesto adresuose savivaldybė nerašoma
  („Vilnius, Ozo g. 25“), todėl ji atpažįstama pagal miestą (`signals.CITIES`).
- `dok_statusas`: Galiojantis, Negaliojantis, Užregistruotas, Tikrinamas, Patenkintas, Atmestas,
  Nepatenkintas, ... („Panaikintas“ nebūna). Atmetami: `config.EXCLUDED_STATUSES`.
- `taskas_wgs` pavyzdys: `POINT (54.6750273775 25.2213355541)` (platuma pirma). `taskas_lks`: `POINT (6060527 578771)`.
- **Statytojo lauko rinkinyje nėra.** Statytojas įrašomas rankiniu būdu į
  `duomenys/builders.csv` (`dokumento_reg_nr;statytojo_kodas;statytojo_pavadinimas;pastaba`).
- Spinta užklausų sintaksė: `?dokumento_reg_data>="2026-09-01"&limit(1000)`, kitas puslapis
  `&page("<_page.next>")`. Tik HTTP 400 reiškia, kad netinka filtras; 404 – neteisingas modelio kelias,
  429/5xx – kartojama, o nepavykus šalis pažymima nepasiekta.

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

## Būsena (2026-10-06): peržiūra ir tikri duomenys

Nepriklausoma peržiūra (35 radiniai, 34 patvirtinti) ir tikrų duomenų tyrimas. Pagrindiniai pakeitimai:

- **LT:** klasifikavimas pagal `dok_tipo_kodas`, savivaldybė iš dokumento numerio ir miesto, tikros būsenos,
  ArcGIS atsarginis šaltinis, įrašų raktas `id`, pasikeitę įrašai perrašomi (panaikinti dokumentai dingsta),
  ZIP/URL/Windows-1257 importas. Gyvas bandymas per ArcGIS (savaitė): ~2 200 signalų, „Kita“ – 0,
  savivaldybė – visiems, koordinatės – 98 %.
- **EE:** vietoj el. pašto užsakymo – viešas EHR statinių API (pokyčių srautas + dokumentų istorija +
  statinio duomenys), signalas = naujas statybos dokumentas (`EE_DOC_TYPES`); tik pastatai; Cloudflare
  ribojimas (~1 užklausa/s, po 429 lėtėjama, vėliau atsigauna); EE įtraukta į `run` (~35–55 min. per savaitę). El. pašto ataskaita liko atsarginiu keliu
  (`ee-order --nuo`).
- **LV/EE būsenos** lentelėje `busenos`: senesnių bylų stadijų pokyčiai tampa signalais, nutrauktos bylos ir
  neįgyvendinti statiniai pašalinami (kartu su žaliais įrašais).
- **PL:** pranešimai tikrinami 90 d. atgal (registre atsiranda vėluodami), vienos vaivadijos klaida kitų
  nestabdo, investuotojas rodomas tik organizacijoms (BDAR).
- **Patikimumas:** nutrūkę atsisiuntimai atpažįstami, ZIP pagal turinį, ilgi CSV laukai, tinklo klaidos.
- **CLI ir ataskaita:** failai nebeperrašomi (`_2`, `_3`), `report --paskutinis`, `sample --savivaldybe`
  ieško ir adrese, HTML žymeklio paspaudimas veikia visoms šalims, „Bet kokia svarba“ rodo ir neigiamus balus,
  `run_weekly.bat` `>nul` klaida.
- **enrich:** srautinis skaitymas, LV (UR, VID, BIS) ir EE (e-äriregister) registrų stulpeliai.
- **PLANAS:** el. pašto rinkodara (LT nuo 2026-04-22 juridiniams asmenims be sutikimo, PL – su sutikimu),
  BDAR (adresai, kadastro numeriai, verslininkų vardai), PVM registracija paslaugoms ES įmonėms.
- **Antroji peržiūra (21 radinys, visi patvirtinti ir pataisyti):** EE pokyčių srauto žymė (nepavykęs ar
  pavėlavęs paleidimas nieko nepraranda), dalinis rezultatas išsaugomas (`PartialSourceError`, kodas 2),
  pertraukiklis, kai EHR neatsako, ribotuvas atsigauna po 429; LT – vėlesni būsenų pokyčiai (atmesti
  prašymai) pagal `iraso_data`, nauji kodai, `diagnose` rodo nežinomus kodus ir per ArcGIS; PL – investuotojų
  filtras pagal ištisus žodžius, nepavykęs failas imamas kitą kartą nuo praleistos datos; LV/EE – būsenos
  užpildomos iš senesnės bazės, `--since 2000-01-01` vėl veikia; CLI – `sample` neperrašo, licencijos
  pavyzdyje, „ne signalai“ skaičiuojami atskirai; PLANAS – Lenkijoje ir skambučiams reikia sutikimo.
- Gyvi bandymai 2026-10-06: LT per ArcGIS (savaitė, ~2 200 signalų), EE per API (para, 243 pastatai,
  117 signalų, 8,5 min.).
- **Trečiasis patikrinimas (pataisymų patikra, 14 radinių, pataisyti):** EE – atidėtiems statiniams
  išlaikomas platesnis dokumentų laikotarpis, pakartojimai sujungiami su srautu, apdorojami po jo ir
  pasibaigia po `EE_API_RETRY_TIMES`, srautas skaitomas tik iki `EE_API_MAX_BUILDINGS`; LV/EE – atkurtos
  būsenos įrašomos; PL – „Spółka z o.o.“, viešųjų įstaigų būdvardžiai, seni vardai išvalomi perskaičiuojant;
  LT – nepavykusi būsenų užklausa – dalinis rezultatas su žyme; seną bazę pirmą kartą perskaičiuoja visą.
- Testai: 129, praeina su Python 3.10–3.13; tinklo užklausos testuose draudžiamos.

## Kas liko (reikia savininko sprendimo arba Lietuvos IP)

- `python sistema.py diagnose` iš Lietuvos IP: ar data.gov.lt atsako naujuoju `ssva` keliu (iš čia
  neprieinama); jei ne – sistema vis tiek veiks per ArcGIS.
- `config.py`: `USER_AGENT` kontaktas, `INFOSTATYBA_SEARCH_URL`, `RUN_COUNTRIES`, `PL_WOJEWODZTWA`,
  ar įtraukti Estijos inžinerinius statinius (`EE_RAJATISED`).
- Kodai be pavadinimo (ANN2, PTDP, PPVA, LNTO) atpažinti pagal įrašus – vertėtų patikslinti su SSVA.
- PL ir EE statytojų/investuotojų įmonių duomenys (KRS, äriregister) – tik per `builders.csv` ir `enrich`.

## Priėmimo kriterijai

- `python sistema.py demo` be klaidų sukuria `isvestis/` CSV ir HTML; HTML atsidaro naršyklėje.
- `python -m unittest` praeina.
- Jokių išorinių priklausomybių.
- Kodas ir pranešimai lietuviškai, kaip esamuose failuose.

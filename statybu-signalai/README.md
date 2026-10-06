# Statybų signalai

Kas savaitę iš atvirų statybų registrų duomenų surenka naujus statybą leidžiančius ir kitus
statybos eigos dokumentus, paverčia juos **signalais** (kas, kur, kokia stadija, kiek svarbu),
praturtina statytojo įmonės duomenimis ir pateikia kaip CSV, HTML ataskaitą su žemėlapiu ir
el. laiškui tinkantį pavyzdį klientui.

Šalys ir šaltiniai:

| Šalis | Šaltinis | Kaip gaunama | Statytojas | Koordinatės |
| --- | --- | --- | --- | --- |
| LT | „Infostatyba“ (SSVA, buv. VTPSI), data.gov.lt rinkinys Nr. 1000 | data.gov.lt API automatiškai; jei jis nepasiekiamas – tie patys duomenys iš SSVA ArcGIS paslaugos (geoportal.lt); dar vienas kelias – CSV | rankiniu būdu (`builders.csv`), įmonės duomenys iš JAR ir Sodros | yra |
| LV | Būvniecības informācijas sistēma (BIS), data.gov.lv, CC0 | trys CSV automatiškai | nėra atviruose duomenyse | daliai objektų |
| PL | GUNB „Rejestr Wniosków, Decyzji i Zgłoszeń“ | ZIP failai automatiškai (vaivadijos ir pranešimai) | investuotojas (leidimuose) | nėra |
| EE | Ehitisregister (EHR) viešas statinių API | API automatiškai (statinių dokumentai); atsarginis kelias – ataskaita el. paštu | nėra | yra |

Python 3.10 ar naujesnis, tik standartinė biblioteka – nieko diegti per `pip` nereikia.

## Greita pradžia

```
python sistema.py demo
```

Sukuria demonstracinę bazę `duomenys/demo.sqlite` (visos keturios šalys, objektai ir įmonės išgalvoti,
įmonių pavadinimuose yra žodis „DEMO“) ir failus aplanke `isvestis/`:

- `demo_ataskaita_DATA.html` – interaktyvi ataskaita: filtrai pagal tipą, šalį, savivaldybę, svarbą, paieška,
  žemėlapis, CSV atsisiuntimas. Atsidaro naršyklėje dukart spragtelėjus; žemėlapiui reikia interneto.
- `demo_signalai_DATA.csv` – tie patys signalai Excel'iui (kabliataškis, UTF-8).
- `demo_statytoju_eile_DATA.csv` – leidimai be nustatyto statytojo (rankinei paieškai).
- `demo_pavyzdys_daugiabuciai_DATA.html` – pavyzdys klientui.

`DATA` – data (savaitinio `run` – data ir laikas, pvz. `2026-10-05_0715`). Jei tokiu vardu failas jau yra,
pridedama `_2`, `_3`…, todėl ankstesnės ataskaitos neperrašomos (išskyrus `demo`).

Testai: `python -m unittest` (paleisti programos aplanke; tinklo nereikia).

## Diegimas

1. Įdiekite Python 3.10+ (python.org; Windows diegimo lange pažymėkite „Add python.exe to PATH“).
2. Nukopijuokite aplanką `statybu-signalai` į kompiuterį, pvz. `C:\statybu-signalai`.
3. Paleiskite `python sistema.py demo`, tada `python sistema.py diagnose`.
4. Faile `config.py` įrašykite savo kontaktą į `USER_AGENT` ir, jei reikia, susiaurinkite
   `RUN_COUNTRIES` (šalys savaitiniam paleidimui) ir `PL_WOJEWODZTWA` (Lenkijos vaivadijos).

**Svarbu dėl Lietuvos:** data.gov.lt ugniasienė blokuoja užklausas iš užsienio duomenų centrų IP adresų
(patikrinta: grąžinamas puslapis „Web Page Blocked“). Tada programa pati ima tuos pačius Infostatybos
duomenis iš SSVA ArcGIS paslaugos geoportal.lt (data.gov.lt rinkinys Nr. 3740; 2026-10-06 ji atnaujinama kasdien
ir pasiekiama iš užsienio). Kelią galima pasirinkti `config.LT_SOURCE`: `auto` (numatyta), `spinta`, `arcgis`.
Latvijos, Lenkijos ir Estijos šaltiniai 2026-10-06 veikė ir iš užsienio.

## Komandos

| Komanda | Ką daro |
| --- | --- |
| `diagnose [--salis LT,LV,PL,EE]` | patikrina ryšį su šaltiniais, ar nepasikeitė laukų pavadinimai, ir parodo dažniausias LT dokumentų reikšmes (taisyklėms derinti) |
| `fetch [--since YYYY-MM-DD] [--salis ...]` | parsisiunčia naujus įvykius; be `--since` – nuo paskutinės turimos datos minus 7 d., pirmą kartą – 30 d. |
| `import FAILAI... [--salis XX] [--since ...]` | įkelia rankiniu būdu atsisiųstus failus ar nuorodas (LT CSV/ZIP, LV trys BIS CSV, PL ZIP/CSV, EE ataskaitos); be `--since` – bent 30 d. atgal |
| `import-csv FAILAS [--since ...]` | tas pats Lietuvai (data.gov.lt CSV arba ZIP, UTF-8 ar Excel'io Windows-1257) |
| `build [--all]` | perskaičiuoja signalus tik paveiktiems dokumentams; `--all` – visiems (pvz., pakeitus `config.py`) |
| `builders` | perkelia statytojus iš `duomenys/builders.csv` į signalus |
| `enrich FAILAS [--all]` | įkelia JAR arba Sodros CSV/ZIP; numatytai tik įmones, kurios jau yra statytojai |
| `report [--days 7] [--all-types] [--gauti \| --paskutinis] [--salis ...]` | CSV, statytojų eilė ir HTML į `isvestis/`; `--gauti` – pagal gavimo, ne dokumento datą; `--paskutinis` – tie patys signalai kaip paskutinio `run` ataskaitoje (pvz., įrašius statytojus) |
| `sample --paskirtis X --savivaldybe Y --tipas Z --limit 10 --antraste "..."` | statinis pavyzdys klientui (dar `--days 30`, `--salis`, `--kontaktas`, `--failas`) |
| `run [--salis ...]` | savaitinis paleidimas: fetch + build + builders + report |
| `ee-order --email ADRESAS [--apskritis Harju] [--nuo YYYY-MM-DD]` | atsarginis Estijos kelias: užsako EHR ataskaitą (nuoroda atsiunčiama el. paštu) |
| `demo` | demonstraciniai duomenys ir ataskaita |

Bendra parinktis `--db FAILAS` leidžia dirbti su kita baze, pvz.
`python sistema.py --db duomenys/demo.sqlite report --days 30`.

Išėjimo kodai: 0 – gerai, 1 – blogi duomenys ar failas, 2 – nepasiektas šaltinis (savaitinis
paleidimas vis tiek sukuria ataskaitą iš pasiekiamų šalių), 3 – `run_weekly.bat` nerado Python.

Pavyzdžiai:

```
python sistema.py sample --paskirtis daugiabu --savivaldybe Kauno --tipas prasymas,leidimas_nauja --antraste "Kauno daugiabučiai"
python sistema.py sample --salis PL --paskirtis magazyn --days 14 --kontaktas "Vardenis, tel. +370 600 00000"
python sistema.py report --days 30 --salis LV,EE
```

`--paskirtis` ir `--savivaldybe` ieško fragmento be didžiųjų raidžių ir diakritikų („sandeliav“ ras „Sandėliavimo“).
Signalų tipai: `prasymas`, `leidimas_nauja`, `leidimas_rekonstrukcija`, `leidimas_atnaujinimas`,
`paskirties_keitimas`, `pranesimas`, `pradzia`, `uzbaigimas`, `pritarimas`, `griovimas`, `kita`.

## Savaitinis paleidimas

`run` sudaro ataskaitą iš signalų, atsiradusių po ankstesnio sėkmingo paleidimo, todėl vėluojantys
įrašai nepradingsta, o tas pats signalas dviejose savaitėse nesikartoja. Pirmą kartą – visi gauti signalai.
Riba – ankstesnio sėkmingo `run` pabaigos laikas (lentelė `runs`). Jei kuri šalis nepasiekta ar gauta tik iš
dalies (išėjimo kodas 2, priežastis – žurnale), kitas paleidimas ją ima nuo praleistos vietos, o jos signalai
pateks į kitos savaitės ataskaitą. Visas paleidimas trunka ~45–70 min. (ilgiausiai – Estija, ~2 s vienam
pastatui, ir Lenkija).

### Windows užduočių planuoklis

`run_weekly.bat` pats nueina į programos aplanką, paleidžia `sistema.py run` ir rašo žurnalą
`isvestis\paleidimai.log`. Užduotį pirmadieniais 7:15 sukurkite komandinėje eilutėje:

```
schtasks /Create /SC WEEKLY /D MON /ST 07:15 /TN "Statybu signalai" /TR "C:\statybu-signalai\run_weekly.bat"
```

arba per „Užduočių planuoklis“ -> „Kurti paprastą užduotį“ -> veiksmas „Paleisti programą“ -> `run_weekly.bat`.
Kompiuteris tuo metu turi būti įjungtas (nustatymuose galima pažymėti „Paleisti kuo greičiau, jei praleista“).

### Linux (cron)

```
15 7 * * 1 cd /opt/statybu-signalai && mkdir -p isvestis && PYTHONUTF8=1 python3 sistema.py run >> isvestis/paleidimai.log 2>&1
```

## Kas savaitę rankomis

1. Atidarykite `isvestis/ataskaita_DATA.html`.
2. **Statytojai (LT).** Infostatyboje statytojo lauko atviruose duomenyse nėra. Atidarykite
   `isvestis/statytoju_eile_DATA.csv` (svarbiausi viršuje), suraskite dokumentą Infostatybos paieškoje
   pagal numerį ir užpildykite `statytojo_kodas` ir `statytojo_pavadinimas`. Užpildytas eilutes
   nukopijuokite į `duomenys/builders.csv` (pirmi keturi stulpeliai, kiti nebūtini) ir paleiskite:

   ```
   python sistema.py builders
   python sistema.py report --paskutinis
   ```

   `report --paskutinis` sukuria naują ataskaitą su tais pačiais signalais kaip paskutinio `run`, jau su
   statytojais (ankstesnis failas neperrašomas).

3. **Kartą per mėnesį** atsisiųskite JAR ir Sodros atvirus duomenis (Registrų centras, atvira.sodra.lt –
   „Draudėjų duomenys“) ir įkelkite: `python sistema.py enrich JAR.csv`, `python sistema.py enrich sodra.zip`.
   Ataskaitoje atsiras darbuotojų skaičius, EVRK ir įmonės statusas. Stulpeliai atpažįstami automatiškai.

### builders.csv

```
dokumento_reg_nr;statytojo_kodas;statytojo_pavadinimas;pastaba
LSNS-13-260921-00012;302345678;UAB „Pavyzdys“;
LRS-15-260918-00031;;Fizinis asmuo;asmens duomenų nekaupiame
```

- Skirtukas – kabliataškis; failą galima pildyti Excel'yje (išsaugokite kaip CSV).
- Užtenka kodo: pavadinimą ataskaita paims iš JAR (po `enrich`).
- **Fizinių asmenų vardų ir pavardžių nerašykite** (BDAR): įrašykite „Fizinis asmuo“, kad signalas
  nebegrįžtų į paieškos eilę.
- Kitoms šalims stulpelyje `dokumento_reg_nr` naudokite signalo ID iš CSV (pvz. `LV:BIS-BL-...:iecere`).

## Signalai, tipai ir svarba

Signalas – vienas dokumentas ar įvykis: LT – dokumentas (visi jo statiniai kartu; tipas pagal dokumento
kodą `dok_tipo_kodas`, pvz. SRA – prašymas, LSNS – leidimas statyti, ANN2 – statybos pradžia, žr. `LT_DOC_TYPES`), LV – bylos stadijos
pasikeitimas, PL – leidimas arba pranešimas (visi sklypai kartu), EE – naujas statinio statybos dokumentas.
Panaikinti dokumentai (LT), nutrauktos bylos (LV) ir neįgyvendinti ar ištrinti statiniai (EE) iš signalų
pašalinami. Tipas nustatomas pagal `config.py` taisykles (`SIGNAL_RULES`, `LV_STAGES`, `LV_WORKS`, `PL_WORKS`,
`EE_DOC_TYPES`, `EE_STATUSES`). Svarba (−2…9) = tipo taškai + vertingiausios paskirties taškai (daugiabučiai, komercija,
pramonė aukščiau; inžineriniai tinklai, ūkiniai pastatai žemiau) + kategorija (LT) + didelis objektas
(daug statinių, PL – kubatūra nuo 5000 m³). Pakeitę taisykles, paleiskite `python sistema.py build --all`.
Atnaujinus programą seną bazę ji pirmą kartą perskaičiuoja visą pati (nauji tipai, savivaldybės, filtrai).

Ataskaitoje numatytai rodomi tik parduodami tipai (`SELLABLE_TYPES`); `--all-types` prideda rašytinius
pritarimus, griovimą ir neatpažintus dokumentus. Jei LT signalų atsiranda „Kita“, paleiskite `diagnose`:
jis parodo dokumentų kodus, kurių nėra `LT_DOC_TYPES`; įrašykite juos ten ir paleiskite `build --all`.
Patikrinimų aktai, privalomieji nurodymai, specialieji reikalavimai ir pan. signalais nelaikomi.

## Šalių ypatumai

- **LT.** Lauke `dok_irasas` yra tik „prasymas“ / „aktas“, dokumento pavadinimas – `dokumento_kategorija`,
  o tipą tiksliausiai nusako kodas `dok_tipo_kodas` (jis yra ir dokumento numerio pradžioje). Savivaldybė
  imama iš dokumento numerio (`LSNS-21-…` – Kauno m. sav., `LT_SAV_BY_DOC_CODE`), o nacionalinių dokumentų
  (`…-00-…`) – iš adreso („Vilnius, Ozo g. 25“ – Vilniaus m. sav.). Atmesti, nepatenkinti, negaliojantys
  dokumentai pašalinami: kartu su naujais dokumentais imami ir anksčiau gautų dokumentų pasikeitimai
  (pagal `iraso_data`), net jei prašymas atmestas po kelių savaičių; jei šių pokyčių gauti nepavyksta,
  šalis pažymima gauta iš dalies, o kitą kartą jie imami nuo ten pat. Tas pats projektas gali turėti kelis
  prašymus (pakartotinai pateiktus). 2026-10-06
  bandymas (savaitė): ~2 200 signalų – ~1 000 prašymų, ~230 leidimų, ~220 statybos pradžių, ~750 užbaigimų;
  savivaldybė nustatyta visiems, koordinatės – 98 %.
  Rinkinys 2025 m. perkeltas iš `datasets/gov/vtpsi/infostatyba` į `datasets/gov/ssva/infostatyba`;
  programa bando naują kelią, o gavusi 404 – senąjį (`config.MODEL`, `MODEL_FALLBACKS`). Jei data.gov.lt
  laikinai neatsako (429, 5xx), užklausa kartojama; nepavykus – šalis pažymima nepasiekta, o ne praleidžiama
  tyliai. Pasikeitę įrašai (pvz., panaikintas dokumentas) perrašomi ir signalas perskaičiuojamas.
- **LV.** Naudojami rinkiniai „Būvniecības lietu saraksts“, „Būvniecības lietu objekti“ ir
  „Jaunbūvju ģeotelpiskie dati“ (kasdien, ~155 MB). Rinkiniuose yra tik dabartinė bylos stadija, todėl
  signalas – nauja byla arba jau žinomos bylos stadijos pasikeitimas (sekama `LV_TRACK_DAYS` dienų).
  Žinomos stadijos saugomos lentelėje `busenos`: pirmą kartą senesnės bylos tik įsimenamos, o jų vėlesni
  stadijų pasikeitimai jau tampa signalais.
  Darbai pagal pranešimą (pvz., buto atnaujinimas) žymimi „Pranešimas (be leidimo)“, nutrauktos bylos atmetamos.
  Paskirtys ir procedūros išverstos į lietuvių kalbą, pavadinimai ir adresai palikti originalūs.
- **PL.** Leidimų failai – po vieną vaivadijai (7–46 MB), pranešimų failas – visai šaliai (~26 MB).
  Visos 16 vaivadijų ir pranešimai apdorojami per ~3,5 min. (~13 900 signalų per 30 d.). Jei reikia tik kelių
  vaivadijų, sumažinkite `PL_WOJEWODZTWA`. Nepavykęs vienos vaivadijos failas kitų nesustabdo, bet šalis
  pažymima gauta iš dalies (kodas 2), o kitą kartą tas failas imamas nuo praleistos datos.
  Pranešimai registre atsiranda su vėlavimu, todėl jie tikrinami `PL_ZGLOSZENIA_LOOKBACK_DAYS` (90) dienų atgal. Koordinačių registre nėra (signalai matomi sąraše).
  Projektuotojų vardai ir pavardės į bazę neįrašomi.
- **EE.** Naudojamas viešas EHR statinių API (be registracijos): pokyčių srautas parodo, kurie statiniai
  keitėsi, o jų dokumentų istorijoje ieškoma statybos dokumentų (projektavimo sąlygos, statybos leidimo
  prašymas ir leidimas, statybos pranešimas, pradžia, naudojimo leidimas, griovimas – `EE_DOC_TYPES`).
  Adresų, savininkų ir pan. pakeitimai praleidžiami. Numatytai tikrinami tik pastatai (EHR kodas „1…“);
  inžineriniai statiniai – vamzdynai, gręžiniai, gatvės (kodas „2…“) – sudaro pusę pokyčių, bet pastatų
  rinkai mažai vertingi (`EE_RAJATISED = True` – įtraukti). EHR saugo Cloudflare: dažniau nei ~1 užklausa per
  sekundę gaunamas HTTP 429 ir ~20 min. ribojimas, todėl užklausos siunčiamos nuosekliai (`EE_API_RPS`),
  po 429 – rečiau (vėliau greitis atsigauna). Kiek pokyčių srauto apdorota, įsimenama (lentelė `busenos`,
  `EE_ZYMA`): kitas paleidimas tęsia nuo ten, todėl nepavykęs ar pavėlavęs paleidimas nieko nepraranda.
  Jei EHR riboja per dažnai (`EE_API_MAX_429`) ar neatsako (`EE_API_MAX_FAILS_IN_ROW`), gavimas sustabdomas,
  gauti įvykiai išsaugomi, o likusius paima kitas paleidimas. Pirmą kartą imamos `EE_FIRST_RUN_DAYS` (7)
  dienos, vienu kartu – ne daugiau kaip `EE_API_MAX_BUILDINGS` statinių. Per savaitę keičiasi ~1 000–1 500
  pastatų, Estija užtrunka ~35–55 min. (2026-10-06 bandymas: 243 pastatai per parą – 8,5 min., 117 statybos
  dokumentų; savivaldybė ir koordinatės – visiems). Atsarginis kelias – ataskaitos el. paštu:
  `python sistema.py ee-order --email jusu@adresas.lt --nuo 2026-09-01`, gavus nuorodą –
  `python sistema.py import --salis EE <nuoroda>` (signalai tada pagal statinio būseną; abiejų kelių
  vienu metu nenaudokite – tas pats statinys gautų du signalus). Klasifikatoriai (paskirtys, savivaldybės) –
  `saltiniai/ee_klasifikatoriai.json`. Duomenų licencija – CC BY-SA 3.0 (nurodykite šaltinį).

## Problemos

- **„API užklausą užblokavo data.gov.lt ugniasienė“** – su `LT_SOURCE = "auto"` duomenys automatiškai
  imami iš SSVA ArcGIS paslaugos. Jei neveikia ir ji, paleiskite iš Lietuvos IP arba data.gov.lt rinkinio
  Nr. 1000 puslapyje atsisiųskite „Statinys“ CSV ir įkelkite `python sistema.py import-csv failas.csv`
  (numatytai imami 30 d.; visiems – `--since 2000-01-01`).
- **„EHR riboja užklausas (HTTP 429)“** – Estijos registras laikinai ribojo greitį; kitas paleidimas tęs nuo
  ten pat. Jei kartojasi kas savaitę, sumažinkite `config.EE_API_RPS` (pvz., 0.5).
- **Pasikeitė laukai** – `python sistema.py diagnose` parodo trūkstamus; pavadinimai keičiami tik `config.py`
  (LT `F`) arba šaltinio modulyje `saltiniai/*.py`.
- **Ataskaitoje nėra žemėlapio** – reikia interneto (Leaflet ir OpenStreetMap plytelės); sąrašas,
  filtrai ir CSV veikia ir be jo.
- **Keisti simboliai žurnale** – `run_weekly.bat` nustato `PYTHONUTF8=1`; atidarykite žurnalą kaip UTF-8.
- **„nepavyko ištrinti duomenys/demo.sqlite“** – uždarykite programą, kuri tą failą laiko atidarytą.

## Failai

| Failas | Paskirtis |
| --- | --- |
| `sistema.py` | komandinė eilutė |
| `config.py` | adresai, laukai, klasifikavimo ir svarbos taisyklės, šalių nustatymai |
| `db.py` | SQLite: `raw_records`, `signals`, `companies`, `taskai` (koordinatės), `busenos` (LV/EE būsenos), `runs` |
| `fetch.py`, `signals.py` | Lietuvos API klientas ir signalų sudarymas |
| `saltiniai/` | šaltiniai pagal šalis: `lt.py`, `lv.py`, `pl.py`, `ee.py` |
| `enrich.py` | JAR/Sodros įkėlimas, `builders.csv` |
| `report.py`, `templates/ataskaita.html` | CSV, HTML ataskaita, pavyzdys klientui |
| `demo/generate_demo.py` | demonstraciniai duomenys tikrais šaltinių formatais |
| `tests/` | `python -m unittest` |
| `run_weekly.bat` | savaitinis paleidimas Windows planuoklyje |
| `PLANAS.md` | architektūra, 4 savaičių planas, pardavimai, teisiniai klausimai |

`duomenys/` (bazės, `builders.csv`, JAR/Sodros failai) ir `isvestis/` į git neįtraukiami (`.gitignore`):
`builders.csv` gali turėti asmens duomenų, todėl jo atsargines kopijas darykite atskirai.

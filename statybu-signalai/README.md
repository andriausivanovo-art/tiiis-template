# Statybų signalai

Kas savaitę iš atvirų statybų registrų duomenų surenka naujus statybą leidžiančius ir kitus
statybos eigos dokumentus, paverčia juos **signalais** (kas, kur, kokia stadija, kiek svarbu),
praturtina statytojo įmonės duomenimis ir pateikia kaip CSV, HTML ataskaitą su žemėlapiu ir
el. laiškui tinkantį pavyzdį klientui.

Šalys ir šaltiniai:

| Šalis | Šaltinis | Kaip gaunama | Statytojas | Koordinatės |
| --- | --- | --- | --- | --- |
| LT | VTPSI „Infostatyba“, data.gov.lt rinkinys Nr. 1000 | API automatiškai; atsarginis kelias – CSV | rankiniu būdu (`builders.csv`), įmonės duomenys iš JAR ir Sodros | yra |
| LV | Būvniecības informācijas sistēma (BIS), data.gov.lv, CC0 | trys CSV automatiškai | nėra atviruose duomenyse | daliai objektų |
| PL | GUNB „Rejestr Wniosków, Decyzji i Zgłoszeń“ | ZIP failai automatiškai (vaivadijos ir pranešimai) | investuotojas (leidimuose) | nėra |
| EE | Ehitisregister (EHR) atvirų duomenų API | ataskaita užsakoma el. paštu, tada importuojama | nėra | iš kontūrų ataskaitos |

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

Testai: `python -m unittest` (paleisti programos aplanke; tinklo nereikia).

## Diegimas

1. Įdiekite Python 3.10+ (python.org; Windows diegimo lange pažymėkite „Add python.exe to PATH“).
2. Nukopijuokite aplanką `statybu-signalai` į kompiuterį, pvz. `C:\statybu-signalai`.
3. Paleiskite `python sistema.py demo`, tada `python sistema.py diagnose`.
4. Faile `config.py` įrašykite savo kontaktą į `USER_AGENT` ir, jei reikia, susiaurinkite
   `RUN_COUNTRIES` (šalys savaitiniam paleidimui) ir `PL_WOJEWODZTWA` (Lenkijos vaivadijos).

**Svarbu dėl Lietuvos:** data.gov.lt ugniasienė blokuoja užklausas iš užsienio duomenų centrų IP adresų
(patikrinta: grąžinamas puslapis „Web Page Blocked“). Lietuvos duomenis imkite iš kompiuterio Lietuvoje
arba LT VPS. Latvijos, Lenkijos ir Estijos šaltiniai 2026-10-05 veikė ir iš užsienio.

## Komandos

| Komanda | Ką daro |
| --- | --- |
| `diagnose [--salis LT,LV,PL,EE]` | patikrina ryšį su šaltiniais ir ar nepasikeitė laukų pavadinimai |
| `fetch [--since YYYY-MM-DD] [--salis ...]` | parsisiunčia naujus įvykius; be `--since` – nuo paskutinės turimos datos minus 7 d., pirmą kartą – 30 d. |
| `import FAILAI... [--salis XX] [--since ...]` | įkelia rankiniu būdu atsisiųstus failus ar nuorodas (LT CSV, LV trys BIS CSV, PL ZIP/CSV, EE ataskaitos) |
| `import-csv FAILAS [--since ...]` | tas pats Lietuvai (data.gov.lt CSV) |
| `build [--all]` | perskaičiuoja signalus tik paveiktiems dokumentams; `--all` – visiems (pvz., pakeitus `config.py`) |
| `builders` | perkelia statytojus iš `duomenys/builders.csv` į signalus |
| `enrich FAILAS [--all]` | įkelia JAR arba Sodros CSV/ZIP; numatytai tik įmones, kurios jau yra statytojai |
| `report [--days 7] [--all-types] [--gauti] [--salis ...]` | CSV, statytojų eilė ir HTML į `isvestis/`; `--gauti` – pagal gavimo, ne dokumento datą |
| `sample --paskirtis X --savivaldybe Y --tipas Z --limit 10 --antraste "..."` | statinis pavyzdys klientui (dar `--days 30`, `--salis`, `--kontaktas`, `--failas`) |
| `run [--salis ...]` | savaitinis paleidimas: fetch + build + builders + report |
| `ee-order --email ADRESAS [--apskritis Harju,Tartu]` | užsako Estijos EHR ataskaitą (nuoroda atsiunčiama el. paštu) |
| `demo` | demonstraciniai duomenys ir ataskaita |

Bendra parinktis `--db FAILAS` leidžia dirbti su kita baze, pvz.
`python sistema.py --db duomenys/demo.sqlite report --days 30`.

Išėjimo kodai: 0 – gerai, 1 – blogi duomenys ar failas, 2 – nepasiektas šaltinis (savaitinis
paleidimas vis tiek sukuria ataskaitą iš pasiekiamų šalių).

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
   python sistema.py report --gauti --days 7
   ```

3. **Kartą per mėnesį** atsisiųskite JAR ir Sodros atvirus duomenis (Registrų centras, atvira.sodra.lt –
   „Draudėjų duomenys“) ir įkelkite: `python sistema.py enrich JAR.csv`, `python sistema.py enrich sodra.zip`.
   Ataskaitoje atsiras darbuotojų skaičius, EVRK ir įmonės statusas. Stulpeliai atpažįstami automatiškai.
4. **Estija:** `python sistema.py ee-order --email jusu@adresas.lt`; gavę laišką su nuoroda –
   `python sistema.py import --salis EE <nuoroda>`; koordinatėms kartą per kelias savaites užsakykite
   ir `--ataskaita ehitise_ruumikuju`, tada `build --all`.

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

Signalas – vienas dokumentas ar įvykis: LT – dokumentas (visi jo statiniai kartu), LV – bylos stadijos
pasikeitimas, PL – leidimas arba pranešimas (visi sklypai kartu), EE – statinio būsenos pasikeitimas.
Tipas nustatomas pagal `config.py` taisykles (`SIGNAL_RULES`, `LV_STAGES`, `LV_WORKS`, `PL_WORKS`,
`EE_STATUSES`). Svarba (−2…9) = tipo taškai + vertingiausios paskirties taškai (daugiabučiai, komercija,
pramonė aukščiau; inžineriniai tinklai, ūkiniai pastatai žemiau) + kategorija (LT) + didelis objektas
(daug statinių, PL – kubatūra nuo 5000 m³). Pakeitę taisykles, paleiskite `python sistema.py build --all`.

Ataskaitoje numatytai rodomi tik parduodami tipai (`SELLABLE_TYPES`); `--all-types` prideda rašytinius
pritarimus, griovimą ir neatpažintus dokumentus. Jei daug LT signalų patenka į „Kita“, paleiskite
`diagnose`, pažiūrėkite `dok_irasas` reikšmes ir papildykite `SIGNAL_RULES`.

## Šalių ypatumai

- **LV.** Naudojami rinkiniai „Būvniecības lietu saraksts“, „Būvniecības lietu objekti“ ir
  „Jaunbūvju ģeotelpiskie dati“ (kasdien, ~155 MB). Rinkiniuose yra tik dabartinė bylos stadija, todėl
  signalas – nauja byla arba jau žinomos bylos stadijos pasikeitimas (sekama `LV_TRACK_DAYS` dienų).
  Darbai pagal pranešimą (pvz., buto atnaujinimas) žymimi „Pranešimas (be leidimo)“, nutrauktos bylos atmetamos.
  Paskirtys ir procedūros išverstos į lietuvių kalbą, pavadinimai ir adresai palikti originalūs.
- **PL.** Leidimų failai – po vieną vaivadijai (7–46 MB), pranešimų failas – visai šaliai (~26 MB).
  Pirmame bandyme vienos vaivadijos ir pranešimų apdorojimas užtruko ~8 s. Jei reikia tik kelių
  vaivadijų, sumažinkite `PL_WOJEWODZTWA`. Koordinačių registre nėra (signalai matomi sąraše).
  Projektuotojų vardai ir pavardės į bazę neįrašomi.
- **EE.** EHR atviri duomenys pateikiami kaip užsakomos ataskaitos (nuoroda – el. paštu), todėl Estija
  neįtraukta į automatinį `run`. Numatytai užsakomi planuojami ir statomi statiniai; klasifikatoriai
  (paskirtys, savivaldybės) – `saltiniai/ee_klasifikatoriai.json`.

## Problemos

- **„API užklausą užblokavo data.gov.lt ugniasienė“** – paleiskite iš Lietuvos IP arba data.gov.lt
  rinkinio Nr. 1000 puslapyje atsisiųskite „Statinys“ CSV ir įkelkite `python sistema.py import-csv failas.csv`
  (numatytai imami 30 d.; visiems – `--since 2000-01-01`).
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
| `db.py` | SQLite: `raw_records`, `signals`, `companies`, `taskai`, `runs` |
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

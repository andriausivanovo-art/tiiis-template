# Statybų signalų verslo ir techninis planas

Idėja: kas savaitę iš atvirų statybų registrų surinkti naujus statybą leidžiančius dokumentus ir statybos
eigos įvykius, sutvarkyti juos į aiškius **signalus** ir parduoti tiems, kuriems svarbu sužinoti apie
objektą anksčiau už konkurentus: medžiagų ir įrangos tiekėjams, subrangovams, paslaugų įmonėms.
Pradedama nuo Lietuvos, Latvija, Lenkija ir Estija jau prijungtos techniškai, bet parduodama nuo vienos nišos.

## 1. Architektūra

```
 Šaltiniai (kas savaitę)                    SQLite (duomenys/signalai.sqlite)          Išvestys (isvestis/)
 ─────────────────────────                  ──────────────────────────────────         ───────────────────────
 LT Infostatyba (data.gov.lt API/CSV) ──┐
 LV BIS (data.gov.lv, 3 CSV)          ──┼─> raw_records (įvykiai, šalis) ──> signals ──> signalai_DATA.csv
 PL GUNB RWDZ (ZIP: leidimai,         ──┤        │ saltiniai/*.py:              │       statytoju_eile_DATA.csv
    pranešimai)                         │        │ tipas, vieta, balas          │       ataskaita_DATA.html
 EE EHR (užsakoma ataskaita, importas)──┘        │                              │       pavyzdys_..._DATA.html
                                                 │   builders.csv (rankomis) ───┤
                                                 │   JAR, Sodra (kas mėnesį) ───┘ companies
                                                 └── runs (paleidimų žurnalas, savaitės riba)
```

- **Vienas šaltinis – vienas modulis** (`saltiniai/lt.py`, `lv.py`, `pl.py`, `ee.py`) su ta pačia sąsaja:
  atsisiųsti / nuskaityti failus, atrinkti naujus įvykius, sudaryti signalą. Ataskaitos šalių neskiria.
- **Įvykis, ne būsena.** LT kiekvienas dokumentas jau yra įvykis. LV ir EE skelbia tik dabartinę bylos ar
  statinio būseną, todėl įvykis = (byla/statinys, stadija): stadijos pasikeitimas tampa nauju signalu.
- **Savaitės riba** – ankstesnio sėkmingo `run` laikas: vėluojantys įrašai nepradingsta, signalai nesikartoja.
- **Be priklausomybių:** Python 3.10+ standartinė biblioteka, SQLite. HTML ataskaita naudoja Leaflet ir
  OpenStreetMap plyteles iš interneto; be ryšio veikia sąrašas ir filtrai.
- **Vieta paleisti:** Lietuvos IP (savininko kompiuteris arba LT VPS), nes data.gov.lt blokuoja užsienio
  duomenų centrus. LV, PL, EE šaltiniai pasiekiami ir iš užsienio.
- **Rankinis darbas, kurio neišvengsime:** LT statytojo nustatymas (Infostatybos paieška). Tai pagrindinė
  savikainos dalis, todėl kainos priklauso nuo to, ar klientui reikia statytojo.

Apimtis pirmame bandyme su tikrais duomenimis (2026-10-05, paskutinės 30 d.): LV – ~870 signalų
(~170 naujų bylų per savaitę); PL – ~300 leidimų vienoje mažesnėje (Opolės) vaivadijoje ir ~800 pranešimų
visoje šalyje (pranešimai registre atsiranda su vėlavimu, todėl vėliau jų padaugėja).

## 2. Keturių savaičių planas

**1 savaitė – duomenys ir kokybė**
- Paleisti `diagnose` ir pirmą `run` iš Lietuvos IP; sukurti savaitinę užduotį (`run_weekly.bat`).
- Peržiūrėti LT `dok_irasas` reikšmes ir „Kita“ dalį; jei didesnė nei ~10 %, papildyti `SIGNAL_RULES`, `build --all`.
- Patikrinti savivaldybių ir koordinačių užpildymą, 20 atsitiktinių signalų palyginti su Infostatyba.
- Įvertinti, kiek laiko užtrunka nustatyti vieną statytoją (tikslas – iki 2 min.).

**2 savaitė – niša ir pavyzdžiai**
- Pasirinkti vieną nišą (žr. 3 skyrių), jos filtrus: tipai, paskirtis, regionas.
- Sudaryti 30–50 potencialių klientų sąrašą (įmonės kodas, sprendimų priėmėjas, kontaktai iš viešų šaltinių).
- Kiekvienam paruošti asmeninį pavyzdį: `python sistema.py sample --paskirtis ... --savivaldybe ... --antraste "..."`,
  su nustatytais statytojais svarbiausiems 10 signalų.

**3 savaitė – pardavimai**
- Išsiųsti 20–30 pavyzdžių (asmeniškai adresuotas laiškas + skambutis po 2–3 d.).
- Pasiūlyti 2–4 savaičių bandomąjį laikotarpį: kas pirmadienį tas pats sąrašas jų nišai.
- Užrašyti atsiliepimus: ko trūksta (statytojas? kontaktas? kitas regionas? kitos šalys?), kiek mokėtų.

**4 savaitė – sprendimas**
- Suskaičiuoti, kiek įmonių sutiko mokėti arba rimtai bando (žr. 6 skyrių).
- Jei kriterijus pasiektas – įforminti veiklą ir sutartį, nustatyti kainas, planuoti antrą nišą arba šalį.
- Jei ne – pakeisti nišą ir kartoti 2–3 savaites arba sustoti, kol sąnaudos mažos.

## 3. Pardavimai

**Viena niša pradžiai.** Signalai vertingi tiems, kurių produktas reikalingas konkrečiu statybos etapu ir kurie
patys aktyviai ieško objektų. Kandidatai (kiekvienam – kuris signalas svarbiausias):
- langų, durų, fasadų gamintojai ir montuotojai – leidimai naujai statybai ir rekonstrukcijai, daugiabučiai;
- vėdinimo, šildymo, elektros, gaisrinės saugos rangovai – prašymai ir leidimai, komerciniai ir daugiabučiai;
- liftų, saulės elektrinių tiekėjai – daugiabučiai, pramonė, sandėliai;
- valymo, apsaugos, baldų, IT įrengimo įmonės – statybos užbaigimas;
- statybinių medžiagų prekyba – statybos pradžia (LV ir EE etapai, PL pranešimai apie vienbučius namus).

Rinkitės nišą, kurioje vienas sandoris vertas tūkstančių eurų, o klientai jau turi pardavimų žmones.

**Pavyzdys – tai pasiūlymas.** Ne aprašas, o 10 tikrų praėjusio mėnesio objektų kliento regione ir nišoje
(`sample`), su statytojais svarbiausiems. Laiške: „Tokį sąrašą gautumėte kiekvieną pirmadienį. Ar bent du iš
šių objektų jums buvo nežinomi?“

**Kainų lygiai (EUR per mėnesį, be PVM):**

| Lygis | Kaina | Kas įeina |
| --- | --- | --- |
| Bazinis | 49–79 | Savaitinis sąrašas (CSV ir HTML) vienai nišai ir regionui, be statytojų |
| Profesionalus | 149–249 | + statytojai ir įmonės duomenys (darbuotojai, EVRK) svarbiausiems signalams, keli regionai |
| Komandai | 300–500 | Visa Lietuva arba kelios šalys (LV, PL, EE), kelios nišos, CSV importui į CRM, prioritetiniai signalai |
| Individualus | nuo 1000 | Pagal užsakymą: integracija (API ar CRM), istorija ir analitika, papildomi šaltiniai, aptarnavimas |

Metinis apmokėjimas – du mėnesiai nemokamai. Pirmiems 3 klientams – nuolaida mainais už grįžtamąjį ryšį
ir atsiliepimą.

**Kitos šalys** – antras žingsnis: pirmiausia klientams, kurie jau dirba LV, PL ar EE (pvz., Lietuvos gamintojai,
eksportuojantys į Lenkiją). Lenkijos rinka didžiausia, joje leidimuose jau yra investuotojas – mažiau rankinio darbo.

## 4. Teisiniai klausimai

Tai ne teisinė konsultacija: prieš pirmą mokamą sutartį verta pasitarti su teisininku (bent dėl BDAR ir sutarties).

**Asmens duomenys (BDAR)**
- Statytojas gali būti fizinis asmuo – jo vardo ir pavardės nekaupiame ir neparduodame: `builders.csv`
  rašome „Fizinis asmuo“. Lenkijos registre fizinio asmens investuotojas nepateikiamas, o projektuotojų
  vardų ir pavardžių sistema į bazę neįrašo.
- Individualių įmonių ir verslininkų pavadinimuose gali būti vardas ir pavardė (pvz., „Jonas Jonaitis IĮ“)
  – tai asmens duomenys. Teisinis pagrindas – teisėtas interesas; atlikite ir išsaugokite teisėto intereso
  vertinimą, privatumo pranešimą svetainėje, saugojimo terminą (pvz., 24 mėn.), galimybę prieštarauti.
- Tiesioginė rinkodara el. paštu: siųskite asmeniškai adresuotus pasiūlymus įmonių bendriesiems ar
  pareigybių adresams, su aiškia atsisakymo galimybe. Masinius laiškus fiziniams asmenims riboja
  Elektroninių ryšių įstatymas – jų nesiųskite be sutikimo.
- `builders.csv` ir bazė į viešas saugyklas nekeliami (`.gitignore`); atsarginės kopijos – šifruotos.

**Duomenų licencijos ir šaltinio nurodymas**
- Kiekvieno rinkinio licenciją patikrinkite jo kortelėje (data.gov.lt, data.gov.lv, GUNB, EHR) ir laikykitės
  sąlygų; BIS rinkiniai data.gov.lv paskelbti su CC0. Ataskaitose visada nurodykite šaltinius
  (tai jau daroma ataskaitos ir pavyzdžio apačioje).
- Žemėlapio plytelės iš OpenStreetMap serverių tinka nedideliam vidiniam naudojimui. Jei HTML ataskaitas
  gaus daug klientų, pereikite prie komercinio plytelių tiekėjo ir laikykitės OSM autorystės reikalavimų.

**Licencija klientui be perpardavimo teisės**
- Sutartyje: klientas gauna neišimtinę teisę naudoti signalus savo vidinei veiklai; draudžiama perparduoti,
  perduoti tretiesiems asmenims ar skelbti; duomenys teikiami „kaip yra“ (atviri registrai gali klysti ar vėluoti);
  atsakomybė ribojama mėnesio mokesčiu; sutartis nutraukiama su 30 d. įspėjimu.
- Vertė – ne pati informacija (ji vieša), o atranka, tvarkymas, statytojų nustatymas ir reguliarumas.

**Veiklos forma**
- Bandymo etapui – individuali veikla pagal pažymą (paprasta apskaita, mažos sąnaudos). Patikrinkite, ar
  veikla tinka verslo liudijimui – tikėtina, kad ne.
- Kai atsiranda keli nuolatiniai klientai arba norisi riboti atsakomybę – mažoji bendrija (MB): paprasta
  steigti, valdyti, galima įtraukti partnerį.
- PVM mokėtoju registruotis privaloma viršijus VMI nustatytą metinę pajamų ribą (aktualią sumą patikrinkite
  VMI); klientai – įmonės, todėl ir savanoriška registracija dažnai nebloga.
- Sąskaitoms ir sutartims – paprastas buhalterinės apskaitos įrankis nuo pirmo kliento.

**Darbo sutarties apribojimai**
- Perskaitykite savo darbo sutartį ir darbovietės tvarkas: nekonkuravimo susitarimą, konfidencialumą,
  intelektinę nuosavybę (ar darbdavys nepretenduoja į ne darbo metu sukurtą programinę įrangą),
  reikalavimą deklaruoti papildomą veiklą.
- Nenaudokite darbdavio kompiuterio, laiko, prieigų ar neviešų duomenų; nesiūlykite paslaugos darbdavio
  klientams ar tiekėjams be raštiško sutikimo.
- Jei dirbate viešajame sektoriuje (ypač statybų, teritorijų planavimo ar priežiūros srityje), galioja
  interesų konfliktų ir papildomo darbo apribojimai: veiklą deklaruokite ir gaukite leidimą prieš pradėdami.

## 5. Rizikos

| Rizika | Ką darome |
| --- | --- |
| Šaltinis pakeičia laukus ar formatą | `diagnose` kas savaitę; laukų pavadinimai vienoje vietoje; testai |
| data.gov.lt blokuoja užklausas | paleidimas iš LT IP; atsarginis CSV importas |
| Statytojo nustatymas užtrunka | prioritetas pagal svarbą; statytojai tik aukštesniuose kainų lygiuose |
| Klientai nemato vertės | 20–30 pavyzdžių prieš bet kokias investicijas; niša keičiama greitai |
| Konkurentai (esamos statybų informacijos paslaugos) | siaura niša, kaina, greitis, kelios šalys vienoje vietoje |

## 6. Sprendimo kriterijus

Po 20–30 išsiųstų asmeninių pavyzdžių (ne vėliau kaip per 4 savaites):

- **Tęsti**, jei **3–5 įmonės** sutinka mokėti arba rimtai bando – naudoja savaitinį sąrašą bent 2 savaites
  ir atsako, kokių objektų ėmėsi.
- **Keisti nišą**, jei atsakymų daug, bet mokėti niekas nenori – problema ne duomenyse, o pasiūlyme.
- **Sustoti**, jei po dviejų nišų sutikusių mažiau nei 3: laiko sąnaudos per didelės, o duomenys ir kodas lieka
  naudingi kitam bandymui.

# KZIN – koordinačių žiniaraštis (AutoCAD)

`KZIN.lsp` yra funkcijos **PZIN** („Koordinačių žiniaraštis“) iš *Matininkas 2015 for AutoCAD* (VĮ Registrų centras, `mati2004.arx`) atitikmuo, parašytas AutoLISP kalba. Komanda vadinasi **KZIN**.

## Įkėlimas

1. AutoCAD komandų eilutėje paleiskite `APPLOAD` ir pasirinkite `KZIN.lsp`.
   Jei norite, kad failas būtų įkeliamas kiekvieną kartą, pridėkite jį į *Startup Suite*.
2. Paleiskite komandą `KZIN`.

Lietuviškos raidės sukuriamos vykdymo metu, todėl failo koduotė nesvarbi. Tekstuose jos užrašytos žymėmis: `{s}` = š, `{ee}` = ė ir pan. Dialogo lange raidės užrašomos `\U+XXXX` kodais. Veikia su AutoCAD 2021+ (`LISPSYS = 1`). Senesnėse versijose raidės rodomos teisingai tik tada, kai Windows naudoja baltų (1257) kodų lentelę.

## Kaip veikia (kaip originale)

| Mygtukas | Veiksmas |
|---|---|
| **Ribos linija** | Pažymėkite polilinija be lankų, spausdami arti viršūnės, nuo kurios bus pradėta numeracija. Polilinija uždaroma, taškai numeruojami pagal laikrodžio rodyklę, linija perkeliama į sluoksnį `riba`. Tipas **R**. |
| **Ašinę liniją** | Pažymėkite polilinijos pradžią arba pabaigą. Kiekvienam taškui skaičiuojamas `Km = pradinis Km + atstumas išilgai linijos / 1000` (3 skaičiai po kablelio), linija perkeliama į sluoksnį `asis`. Tipas **A**. |
| **Centro tašką** | Taškiniai objektai (tipas **O**). Žymėkite taškus vieną po kito, **Enter** – baigti. |
| **Ištrinti objekto taškus** | Ištrina visus pažymėtos linijos taškus (arba vieną pažymėtą taško bloką). |
| **Koordinatės išnaša** | Išnaša su taško X ir Y koordinatėmis. |
| **Linijos išnaša** | Išnaša su tekstu `a-b` (pirmo ir paskutinio linijos taško Eil.Nr.) ir `L = ilgis`. |
| **Pridėti tašką į liniją / Ištrinti tašką iš linijos** | Prideda arba pašalina polilinijos viršūnę kartu su jos taško bloku. |
| **Pernumeruoti taškus** | Pernumeruoja taškus nuo nurodyto numerio, pvz., `1.1` → 1.1, 1.2, …; eiliškumą galima imti iš linijos arba žymėti taškus po vieną. |
| **Saugoti** (bloko nustatymai) | Pritaiko žymėjimo aukštį, V/H poziciją ir taško dydį visiems taškams brėžinyje. |

- **Nr.** laukelis: `1.1` reiškia priešdėlį `1.` ir numerius nuo 1, `5` reiškia numerius 5, 6, … Po kiekvieno veiksmo laukelyje įrašomas kitas laisvas numeris.
- Taškai žymimi bloku `koordinate` sluoksnyje `Koordinate`. Blokas turi apskritimą ir atributus `Koordinate` (numeris), `KM` ir `TYPE` (1 – riba, 2 – ašis, 3 – objektas). Bloko struktūra ta pati kaip Matininko, todėl sąraše rodomi ir su PZIN sukurti taškai.
- Jei taškas su tokiomis pat koordinatėmis (0,01 m tikslumu) jau yra, jis antrą kartą neįterpiamas. Besidubliuojantys taškai sąraše pažymimi `*`.
- **X** yra šiaurės koordinatė (AutoCAD Y), **Y** – rytų koordinatė (AutoCAD X), kaip LKS-94 sistemoje.
- Nustatymai saugomi brėžinyje (žodyne `KZIN_NUSTATYMAI`). Jei brėžinyje yra Matininko nustatymų, jie perimami.

## Papildomos galimybės

Originale jų nėra:
- **Įterpti lentelę** – į brėžinį įterpia žiniaraštį kaip AutoCAD lentelę (TABLE);
- **Eksportuoti CSV** – išsaugo žiniaraštį `.csv` faile (skirtukas `;`).

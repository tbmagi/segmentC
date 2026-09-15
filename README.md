# Kundesegmentering

Læser rå salgsdata fra Excel (`.xlsx`, `.xlsm`, `.xls`) og producerer
interaktive HTML scatter-plots
(Plotly) samt en formateret Excel-rapport. Hvert punkt er enten én kundegruppe
eller ét item no.

De to akser er:

- **X: Gross Margin %** – beregnet pr. item på dets seneste aktivitetsmåned(er)
  og lagt vægtet sammen til kundegruppe-niveau.
- **Y: Turnover** – summen af salget i et rullende vindue på N måneder.

## Kom i gang

```bash
pip install -r requirements.txt
python run_gui.py
```

Tkinter følger med de fleste Python-installationer. På Debian/Ubuntu skal det
installeres separat: `sudo apt install python3-tk`.

## Et program der kan dobbeltklikkes

Skal programmet bruges på en maskine uden Python, pakkes det til én fil:

```bash
python build_exe.py          # eller: dobbeltklik byg_exe.bat på Windows
```

Scriptet installerer selv det der mangler, henter PyInstaller og lægger
resultatet i `dist/`. På Windows hedder det `Kundesegmentering.exe`. Filen
indeholder Python, pandas og plotly, så den kan kopieres til en anden maskine
og startes ved at dobbeltklikke — der skal ikke installeres noget.

Byggemaskinen skal være samme slags som brugsmaskinen: PyInstaller kan ikke
lave en Windows-exe fra en Mac eller omvendt. Der skal være Python 3.10 eller
nyere med Tkinter på den maskine der bygger.

| Tilvalg | Gør |
| --- | --- |
| `--mappe` | en mappe i stedet for én fil — starter hurtigere, men hele mappen skal følge med |
| `--spring-over` | installer ikke afhængigheder først |
| `--behold` | ryd ikke op efter byggeriet (til fejlsøgning) |

Første start på en enkelt fil tager typisk 5–15 sekunder: filen pakker sig
selv ud i en midlertidig mappe. Derefter går det hurtigt.

Programmet skriver sin dato-mappe ved siden af sig selv, så læg det et sted
hvor der må skrives — skrivebordet eller et fællesdrev, ikke
`C:\Program Files`.

## Uden brugerflade

Beregningen kan køres direkte fra et script eller en notebook:

```python
from segmentering import Config, run_analysis

cfg = Config(
    input_path=r"C:\data\Clean_data.xlsx",
    reference_date="05-2026",          # MM-ÅÅÅÅ
    turnover_window_months=12,
    output_basename="kunde_segmentering",
    output_dir=r"C:\rapporter",
)
results = run_analysis(cfg)
```

`run_analysis` tager også en `log`-funktion, hvis fremdriftsteksten skal et
andet sted hen end til `print`. Brugerfladen viser kun det seneste trin og en
fremdriftsbjælke; hele udskriften lægges i `analyse-log.txt` ved siden af
resultatet.

## Datakrav

Overskriftsrækken findes automatisk, så tabellen må gerne starte længere nede
i arket — en forside, et logo eller nogle nøgletal ovenover gør ingen skade.

Filen skal indeholde disse kolonner (navnene matches uafhængigt af store og
små bogstaver):

`Statistics group`, `Item no.`, `Year-mo`, `Cost`, `Qty.`, `Turnover DKK`,
`Local_COGS_DKK`, `Local_GP_DKK`

Disse er valgfrie og aktiverer hver sin funktion:

| Kolonne | Bruges til |
| --- | --- |
| `Turnover type` | frasortering og CN/DK-opdeling |
| `Fiscal year` | identifikation af nye kunder |
| `Industry_segment` | kantfarve på kundegruppe-plottet, med en fremhæv-knap pr. branche |
| `KAM` | tænd/sluk-knapper pr. key account manager på begge plots |

Manglende obligatoriske kolonner giver en fejlbesked der siger præcis hvilke
der mangler, og hvad der faktisk stod i overskriftsrækken.

## Hvordan data behandles

1. **Frasortering** – perioder efter dags dato (budgettal), ekskluderede
   kundegrupper og turnover-typer, rækker med turnover 0, og "døde" items uden
   aktivitet i kundens turnover-vindue.
2. **Item-type** – item no. klassificeres som sinter (70–77) eller støbe
   (60–67) ud fra de to første cifre og mindst 6 cifre. Et suffix på nummeret
   overruler reglen: `-S1` sinter, `-S2` støbe, `-S0` fjern helt.
3. **Kundetype** – hver kundegruppe bliver Ny, Eksisterende eller Tidligere.
4. **GM% pr. item** – seneste aktivitetsmåned, eller de seneste N måneder
   summeret hvis vægtet GM% er slået til.
5. **Turnover-vindue** – forankret enten i kundens eller i det enkelte items
   seneste aktivitet. De to plots kan have hver sin forankring.
6. **Outlier-filter** – valgfrit z-score-filter inden for hver kundegruppe.
7. **Kundekategori** – A/B/C/D ud fra turnover-båndet, med `+`/`-` alt efter om
   GM% når kategoriens krav.
8. **KAM** – kunden tildeles den key account manager der står på den seneste
   aktivitet, så et skift undervejs slår igennem. Store og små bogstaver er
   uden betydning (`PHA` og `pHA` er samme person), og kunder uden KAM samles
   under `(Blank)`.
9. **Output** – HTML-plots og Excel-rapport.

## De to plots

Begge plots lister punkterne i legenden til højre, grupperet efter
kundekategori (A+, A-, B+ …). Klik på et navn slår det enkelte punkt fra;
knapperne under plottet slår en hel blok fra:

| Plot | Ét punkt er | Legenden viser | Farven følger |
| --- | --- | --- | --- |
| Kundegruppe | én kundegruppe | kundenavne pr. kategori | kundetype |
| Item | ét item no. | kundenavne pr. kategori | kundegruppe |

Knaprækkerne under kundegruppe-plottet er kundetype, kategori, KAM og
branche. Under item-plottet er de volumenkrav, kategori og KAM.

Knaprækkerne virker som **filtre der begrænser hinanden**, ikke som
uafhængige kontakter. Har du slået alt fra på nær én KAM, og slukker og
tænder du så for en kundetype, kommer kun den ene KAMs kunder tilbage — ikke
alle kunder af den type. Et punkt vises kun hvis det slipper gennem hver
eneste række.

Nederst — under de rækker den nulstiller — sidder knappen **↺ Nulstil alle
filtre**, der slår alle filterrækker fra på én gang. Valget af volumenkrav på
item-plottet røres ikke — det er et radiovalg, ikke et filter.

Bemærk at et klik i legenden er et engangsvalg: næste gang du rører en
filterknap, beregnes synligheden forfra ud fra knapperne alene.

Hele forløbet er også beskrevet i programmets eget hjælpevindue, med et
gennemgående regneeksempel.

## Udsnit og filnavne

Analysen kører ét **udsnit** ad gangen. Udsnittene udspændes af tre valg i
indstillingerne — emne-type, geografi og kundeudvalg — og hvert udsnit får sit
eget sæt filer og Excel-faner, beregnet forfra på netop de rækker. Plottet og
fanerne for et udsnit viser derfor altid de samme tal.

```
<basis>_kundegruppe[_sinter|_stoebe][_cn|_dk][_eks].html
<basis>_item[_sinter|_stoebe][_cn|_dk][_eks].html
<basis>.xlsx
```

Plotly-biblioteket lægges ind i hver HTML-fil. Det gør filen ca. 4 MB større,
men den virker til gengæld uden internet, bag en firewall der blokerer
`cdn.plot.ly`, og når den sendes videre som en enkelt vedhæftet fil. Hentes
biblioteket udefra, ser en tom side nøjagtig ud som en tom analyse.

## Hvor resultatet havner

Står output-mappen tom, oprettes en dateret mappe ved siden af programmet:

```
Kundesegmentering 2026-09-15/
  kunde_segmentering_kundegruppe.html
  kunde_segmentering_item.html
  kunde_segmentering.xlsx
```

## Egne standardværdier

Knappen **Gem som mine standardværdier** i indstillingsvinduet skriver
`segmentering_indstillinger.json` ved siden af programmet. Den læses næste
gang programmet åbnes, og følger med hvis mappen kopieres til en kollega.

Dags dato og ny-regnskabsår gemmes ikke — de udfyldes altid ud fra dagens
dato. Er det 15-09-2026, står der `09-2026` og `2026/2027`.

## Projektets opbygning

```
segmentering/          beregningen – kan bruges helt uden brugerflade
  config.py            Config, bånd, output-stier, validering
  dataio.py            indlæsning, kolonne-normalisering, rækkefiltre
  classify.py          item-type, kundetype, kundekategori
  metrics.py           GM%-grundlag, turnover-vindue, aggregering
  outliers.py          z-score-filter pr. kundegruppe
  plots.py             Plotly-figurerne
  excel_report.py      rapportens faneblade og formatering
  pipeline.py          orkestrering af udsnittene

gui/                   Tkinter-brugerfladen
  app.py               hovedvinduet
  widgets.py           hjælpebobler, sektioner, rulbar side
  help_window.py       "Sådan behandles data"

run_gui.py             start brugerfladen
build_exe.py           pak programmet til én fil der kan dobbeltklikkes
byg_exe.bat            samme, til dobbeltklik på Windows
kundesegmentering.ico  ikon på den byggede programfil
docs/                  Word-introduktionen og scriptet der bygger den
tests/                 pytest-tests af beregningslogikken
```

Konfigurationen sendes som et `Config`-objekt hele vejen igennem. Ingen
funktion læser eller ændrer globale indstillinger, så hvert trin kan afprøves
for sig, og flere analyser kan køre i samme proces uden at påvirke hinanden.

## Introduktion til nye brugere

`docs/Kundesegmentering-introduktion.docx` beskriver værktøjet for en kollega
der skal overtage det: hvad analysen gør, hvordan tallene bliver til, og
hvordan graferne læses — uden kode. Den bygges om med:

```bash
npm install docx
node docs/build_doc.js
```

Rettelser hører hjemme i `docs/build_doc.js`, så dokumentet kan bygges igen.

## Tests

```bash
pip install pytest
python -m pytest tests/ -q
```

Tre af testene rører brugerfladen og springes over hvis Tkinter mangler.

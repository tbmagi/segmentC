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
andet sted hen end til `print`.

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

Bemærk at et klik i legenden er et engangsvalg: næste gang du rører en
filterknap, beregnes synligheden forfra ud fra knapperne alene.

Hele forløbet er også beskrevet i programmets eget hjælpevindue, med et
gennemgående regneeksempel.

## Analyseenheder

Emne-type (sinter/støb) og produktionssted (DK/CN) laver ikke hver sit sæt
filer. De er egenskaber ved den enkelte analyseenhed og tændes og slukkes
direkte i grafen sammen med kundetype, kategori og KAM.

En kunde med både sinter og støb bliver derfor til flere enheder med hver sin
omsætning og margin. Kendetegn tilføjes kun når de er nødvendige for at
skelne:

| Kunden har | Enhedens navn |
| --- | --- |
| kun sinter, kun DK | `GRUNDFOSS` |
| sinter og støb | `GRUNDFOSS (Sinter)`, `GRUNDFOSS (Støb)` |
| sinter i både DK og CN | `GRUNDFOSS (DK)`, `GRUNDFOSS (CN)` |
| begge dele | `GRUNDFOSS (Sinter, DK)` … |

Varer der hverken er sinter eller støb samles under `Andet`, og
turnover-typer der hverken er DK eller CN under `Øvrig` — så intet forsvinder
uden at kunne ses.

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
dato. Er det 15-09-2026, står der `09-2026` og `2026/27`.

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
tests/                 pytest-tests af beregningslogikken
```

Konfigurationen sendes som et `Config`-objekt hele vejen igennem. Ingen
funktion læser eller ændrer globale indstillinger, så hvert trin kan afprøves
for sig, og flere analyser kan køre i samme proces uden at påvirke hinanden.

## Tests

```bash
pip install pytest
python -m pytest tests/ -q
```

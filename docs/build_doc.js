/**
 * Bygger Word-introduktionen til kundesegmenteringen.
 *
 *   npm install docx
 *   node docs/build_doc.js [ud-fil.docx]
 *
 * Dokumentet er skrevet til en kollega der skal overtage værktøjet. Det
 * beskriver hvad programmet gør og hvorfor — ikke hvordan koden er skruet
 * sammen. Rettelser hører hjemme her, så dokumentet kan bygges igen.
 */

const fs = require("fs");
const path = require("path");
const {
  AlignmentType,
  BorderStyle,
  Document,
  Footer,
  HeadingLevel,
  ImageRun,
  PageBreak,
  PageNumber,
  Packer,
  Paragraph,
  ShadingType,
  Table,
  TableCell,
  TableRow,
  TextRun,
  WidthType,
  convertInchesToTwip,
} = require("docx");

// --- Farver og mål -----------------------------------------------------------

const BLUE = "1A4A7A";
const MID_BLUE = "2A5A8A";
const GREY = "555555";
const NOTE_FILL = "FFF8E1";
const CODE_FILL = "F2F2F2";
const HEAD_FILL = "1A4A7A";
const ALT_FILL = "F5F8FB";

// --- Byggeklodser ------------------------------------------------------------

const title = (text) =>
  new Paragraph({
    spacing: { before: 0, after: 120 },
    children: [
      new TextRun({ text, bold: true, size: 56, color: BLUE, font: "Calibri Light" }),
    ],
  });

const subtitle = (text) =>
  new Paragraph({
    spacing: { after: 400 },
    children: [new TextRun({ text, size: 28, color: GREY, font: "Calibri Light" })],
  });

const h1 = (text) =>
  new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 360, after: 160 },
    children: [new TextRun({ text, bold: true, size: 32, color: BLUE })],
  });

const h2 = (text) =>
  new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 260, after: 100 },
    children: [new TextRun({ text, bold: true, size: 24, color: MID_BLUE })],
  });

/** Brødtekst. Fed markeres med **stjerner** midt i teksten. */
const p = (text, options = {}) => {
  const runs = [];
  text.split(/(\*\*[^*]+\*\*)/).forEach((part) => {
    if (!part) return;
    const bold = part.startsWith("**") && part.endsWith("**");
    runs.push(
      new TextRun({
        text: bold ? part.slice(2, -2) : part,
        bold,
        size: 22,
        italics: options.italics || false,
        color: options.color,
      })
    );
  });
  return new Paragraph({
    spacing: { after: options.after === undefined ? 140 : options.after },
    indent: options.indent ? { left: convertInchesToTwip(0.25) } : undefined,
    children: runs,
  });
};

const bullet = (text, level = 0) => {
  const runs = [];
  text.split(/(\*\*[^*]+\*\*)/).forEach((part) => {
    if (!part) return;
    const bold = part.startsWith("**") && part.endsWith("**");
    runs.push(new TextRun({ text: bold ? part.slice(2, -2) : part, bold, size: 22 }));
  });
  return new Paragraph({
    bullet: { level },
    spacing: { after: 60 },
    children: runs,
  });
};

const numbered = (text, instance) => {
  const runs = [];
  text.split(/(\*\*[^*]+\*\*)/).forEach((part) => {
    if (!part) return;
    const bold = part.startsWith("**") && part.endsWith("**");
    runs.push(new TextRun({ text: bold ? part.slice(2, -2) : part, bold, size: 22 }));
  });
  return new Paragraph({
    numbering: { reference: "steps", level: 0, instance },
    spacing: { after: 80 },
    children: runs,
  });
};

/** Fastbredde-blok til filnavne, formler og opstillinger. */
const code = (lines) =>
  new Paragraph({
    spacing: { before: 100, after: 160 },
    shading: { type: ShadingType.CLEAR, fill: CODE_FILL },
    indent: { left: convertInchesToTwip(0.2) },
    children: lines.flatMap((line, i) => [
      ...(i ? [new TextRun({ break: 1 })] : []),
      new TextRun({ text: line, font: "Consolas", size: 19 }),
    ]),
  });

/** Fremhævet bemærkning med en gul baggrund. */
const note = (heading, text) =>
  new Paragraph({
    spacing: { before: 140, after: 180 },
    shading: { type: ShadingType.CLEAR, fill: NOTE_FILL },
    border: {
      top: { style: BorderStyle.SINGLE, size: 2, color: "E8D48B" },
      bottom: { style: BorderStyle.SINGLE, size: 2, color: "E8D48B" },
      left: { style: BorderStyle.SINGLE, size: 12, color: "E8B44B" },
      right: { style: BorderStyle.SINGLE, size: 2, color: "E8D48B" },
    },
    indent: { left: convertInchesToTwip(0.12), right: convertInchesToTwip(0.12) },
    children: [
      new TextRun({ text: `${heading}  `, bold: true, size: 21 }),
      new TextRun({ text, size: 21 }),
    ],
  });

const cell = (text, options = {}) =>
  new TableCell({
    shading: options.fill ? { type: ShadingType.CLEAR, fill: options.fill } : undefined,
    margins: { top: 90, bottom: 90, left: 130, right: 130 },
    width: options.width ? { size: options.width, type: WidthType.PERCENTAGE } : undefined,
    children: [
      new Paragraph({
        spacing: { after: 0 },
        children: [
          new TextRun({
            text,
            bold: options.head || false,
            color: options.head ? "FFFFFF" : undefined,
            size: options.mono ? 19 : 21,
            font: options.mono ? "Consolas" : undefined,
          }),
        ],
      }),
    ],
  });

const table = (headers, rows, widths, mono = false) =>
  new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    borders: {
      top: { style: BorderStyle.SINGLE, size: 1, color: "C8D4E0" },
      bottom: { style: BorderStyle.SINGLE, size: 1, color: "C8D4E0" },
      left: { style: BorderStyle.SINGLE, size: 1, color: "C8D4E0" },
      right: { style: BorderStyle.SINGLE, size: 1, color: "C8D4E0" },
      insideHorizontal: { style: BorderStyle.SINGLE, size: 1, color: "C8D4E0" },
      insideVertical: { style: BorderStyle.SINGLE, size: 1, color: "C8D4E0" },
    },
    rows: [
      new TableRow({
        tableHeader: true,
        children: headers.map((text, i) =>
          cell(text, { head: true, fill: HEAD_FILL, width: widths && widths[i] })
        ),
      }),
      ...rows.map(
        (row, r) =>
          new TableRow({
            children: row.map((text, i) =>
              cell(text, {
                fill: r % 2 ? ALT_FILL : undefined,
                width: widths && widths[i],
                mono: mono && i === 0,
              })
            ),
          })
      ),
    ],
  });

const spacer = (after = 200) =>
  new Paragraph({ spacing: { after }, children: [new TextRun("")] });

/**
 * En figur med billedtekst.
 *
 * Figurerne bygges af docs/build_figures.py. Er de ikke bygget endnu, springes
 * de over med en advarsel i stedet for at vælte hele dokumentet — teksten kan
 * stå på egne ben.
 */
// px ved 96 dpi. 588 px ~ 6,1" og har luft til A4-margenerne (6,27" fri bredde).
const FIGURE_WIDTH = 588;

const figure = (name, width, height, caption) => {
  const file = path.join(__dirname, "figurer", `${name}.png`);
  if (!fs.existsSync(file)) {
    console.warn(`  ! figuren ${name}.png mangler — kør docs/build_figures.py`);
    return [];
  }
  return [
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 200, after: 60 },
      children: [
        new ImageRun({
          data: fs.readFileSync(file),
          type: "png",
          transformation: {
            width: FIGURE_WIDTH,
            height: Math.round((FIGURE_WIDTH * height) / width),
          },
        }),
      ],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 220 },
      children: [
        new TextRun({ text: caption, size: 19, italics: true, color: GREY }),
      ],
    }),
  ];
};

const pageBreak = () => new Paragraph({ children: [new PageBreak()] });

// --- Indholdet ---------------------------------------------------------------

const today = new Date().toLocaleDateString("da-DK", {
  day: "2-digit",
  month: "long",
  year: "numeric",
});

const body = [];
const add = (...items) => body.push(...items);

// Forside
add(
  spacer(1200),
  title("Kundesegmentering"),
  subtitle("En introduktion til hvordan analysen virker"),
  p(
    "Dette dokument beskriver hvad segmenteringsværktøjet gør, hvilke data " +
      "det bygger på, og hvordan resultatet skal læses. Det er skrevet til " +
      "dig der skal overtage værktøjet — ikke til den der skal rette i koden."
  ),
  spacer(600),
  p(`Version af ${today}`, { color: GREY }),
  pageBreak()
);

// Indhold
add(
  h1("Indhold"),
  ...[
    "1  Hvad værktøjet er til for",
    "2  Sådan starter du programmet",
    "3  Excel-filen programmet læser",
    "4  Sådan behandles data, trin for trin",
    "5  Et gennemgående regneeksempel",
    "6  De to grafer",
    "7  Knapperne under graferne",
    "8  Udsnit, filnavne og hvor resultatet havner",
    "9  Excel-rapporten",
    "10  Indstillinger og egne standardværdier",
    "11  Når noget går galt",
    "12  Ordliste",
    "13  Sådan bygges programmet igen",
  ].map((line) => p(line, { after: 90 })),
  pageBreak()
);

// 1
add(
  h1("1  Hvad værktøjet er til for"),
  p(
    "Værktøjet placerer hver kunde i et koordinatsystem med to akser, så det " +
      "kan ses på ét blik hvem der fylder meget, og hvem der tjenes penge på:"
  ),
  bullet(
    "**X-aksen: Gross Margin %** — hvor stor en del af omsætningen der bliver " +
      "til dækningsbidrag."
  ),
  bullet(
    "**Y-aksen: Turnover** — hvor meget kunden har omsat for i et rullende " +
      "vindue på typisk 12 måneder."
  ),
  p(
    "Ud fra placeringen får hver kunde en **kundekategori** — A+, A-, B+, B- " +
      "og så videre. Bogstavet fortæller om volumen, og plus eller minus " +
      "fortæller om marginen lever op til kravet for netop den volumen. En " +
      "stor kunde med lav margin er altså ikke det samme som en lille kunde " +
      "med lav margin.",
    { after: 200 }
  ),
  p("Resultatet er to ting:"),
  bullet("Interaktive **grafer** (HTML-filer der åbnes i en browser)."),
  bullet("En **Excel-rapport** med tallene bag hvert punkt."),
  note(
    "Kort sagt:",
    "programmet regner ikke noget nyt ud som ikke allerede står i " +
      "salgsudtrækket. Det samler tallene op på kunde-niveau, skærer de " +
      "perioder fra der ikke skal tælle med, og tegner resultatet."
  )
);

// 2
add(
  h1("2  Sådan starter du programmet"),
  p(
    "Programmet er én enkelt fil — **Kundesegmentering.exe**. Den indeholder " +
      "alt hvad der skal bruges, så der skal ikke installeres Python eller " +
      "andet. Dobbeltklik på filen, og vinduet åbner."
  ),
  note(
    "Første start:",
    "tager typisk 5–15 sekunder, fordi filen pakker sig selv ud. Der sker " +
      "ikke noget på skærmen imens. Bagefter går det hurtigt."
  ),
  h2("Adgangskoden"),
  p(
    "Først kommer en lille boks der beder om en adgangskode. Tastes den " +
      "rigtigt, åbner programmet; ellers lukker det efter tre forsøg. Koden " +
      "får du af den der har givet dig programmet. Store og små bogstaver er " +
      "uden betydning."
  ),
  note(
    "Hvad koden er — og ikke er:",
    "den holder programmet fra at blive åbnet af nogen der ikke skal bruge " +
      "det. Den beskytter ikke data: selve Excel-filen og de mapper " +
      "programmet skriver i er ikke låst, og den der kan køre programmet kan " +
      "også prøve sig frem. Betragt den som en dørklokke, ikke som en lås."
  ),
  p(
    "Læg filen et sted hvor der må skrives — skrivebordet eller et " +
      "fællesdrev. Programmet lægger nemlig sit resultat i en **dateret " +
      "mappe ved siden af sig selv**:"
  ),
  code([
    "Kundesegmentering.exe",
    "Kundesegmentering 2026-09-15\\",
    "    kunde_segmentering_kundegruppe.html",
    "    kunde_segmentering_item.html",
    "    kunde_segmentering.xlsx",
  ]),
  p(
    "Ligger programmet i en mappe der er skrivebeskyttet — for eksempel " +
      "C:\\Program Files — kan det ikke gemme noget, og du får en fejlbesked " +
      "om det.",
    { after: 200 }
  ),
  h2("Vinduet"),
  p("Forsiden er bevidst kort. Der er tre felter du skal forholde dig til:"),
  table(
    ["Felt", "Hvad det er"],
    [
      [
        "Excel-fil",
        "Salgsudtrækket. Tryk “Vælg…” og find filen. Både .xlsx, .xlsm og .xls kan bruges.",
      ],
      [
        "Dags dato",
        "Skæringsdatoen for hele analysen, på formen MM-ÅÅÅÅ. Udfyldes automatisk med indeværende måned.",
      ],
      [
        "Ny-regnskabsår",
        "Regnskabsåret der bruges til at finde NYE kunder, på formen ÅÅÅÅ/ÅÅÅÅ. Udfyldes automatisk.",
      ],
    ],
    [26, 74]
  ),
  spacer(160),
  p(
    "Alt andet ligger bag knappen **Indstillinger**. Tryk **Kør analyse** når " +
      "felterne er udfyldt. Mens analysen kører, vises en bjælke der bevæger " +
      "sig, og nederst står hvilket trin der er i gang. Når den er færdig, " +
      "står der ✅ og stien til mappen med resultatet."
  ),
  note(
    "Hjælp undervejs:",
    "det lille blå spørgsmålstegn ved hvert felt forklarer feltet. Knappen " +
      "øverst — “Hjælp – hvordan behandles data?” — åbner den samme " +
      "gennemgang som kapitel 4 og 5 i dette dokument."
  ),
  pageBreak()
);

// 3
add(
  h1("3  Excel-filen programmet læser"),
  p(
    "Programmet leder selv efter overskriftsrækken, så tabellen må gerne " +
      "starte længere nede i arket. En forside, et logo eller nogle nøgletal " +
      "ovenover gør ingen skade — den første række der indeholder samtlige " +
      "påkrævede kolonnenavne bliver brugt som overskrift."
  ),
  h2("Påkrævede kolonner"),
  p(
    "Uden disse kan analysen ikke køre. Navnene matches uafhængigt af store " +
      "og små bogstaver."
  ),
  table(
    ["Kolonne", "Indhold"],
    [
      ["Statistics group", "Kundegruppen — det der bliver til ét punkt på kundegruppe-plottet."],
      ["Item no.", "Varenummeret."],
      ["Year-mo", "Perioden, fx 2026-05."],
      ["Turnover DKK", "Omsætning i kroner."],
      ["Local_COGS_DKK", "Vareforbrug i kroner."],
      ["Local_GP_DKK", "Dækningsbidrag i kroner."],
      ["Cost", "Kostpris."],
      ["Qty.", "Antal."],
    ],
    [30, 70],
    true
  ),
  spacer(160),
  note(
    "Mangler en kolonne?",
    "så stopper programmet med det samme og skriver præcis hvilke der " +
      "mangler — og hvad der faktisk stod i overskriftsrækken. Så er det " +
      "som regel et navn der er blevet stavet om i udtrækket."
  ),
  h2("Valgfrie kolonner"),
  p("Hver af disse låser en ekstra funktion op. Mangler de, kører analysen bare uden."),
  table(
    ["Kolonne", "Låser op for"],
    [
      ["Turnover type", "Frasortering af bestemte typer, og opdelingen i DK og CN."],
      ["Fiscal year", "Identifikation af nye kunder."],
      ["Industry_segment", "Farvet kant på kundegruppe-plottet og en fremhæv-knap pr. branche."],
      ["KAM", "Tænd/sluk-knapper pr. key account manager på begge grafer."],
    ],
    [30, 70],
    true
  ),
  pageBreak()
);

// 4
add(
  h1("4  Sådan behandles data, trin for trin"),
  p(
    "Rækkefølgen betyder noget: frasorteringen sker først, så alle beregninger " +
      "bygger på nøjagtig det samme grundlag."
  ),
  h2("Trin 1 — Frasortering"),
  p("Følgende rækker fjernes, inden der regnes:"),
  bullet(
    "**Perioder efter dags dato.** De regnes som budgettal. Er dags dato " +
      "06-2026, tæller 06-2026 med, mens 07-2026 og frem falder fra."
  ),
  bullet("**Ekskluderede kundegrupper** — fx interne konti og testkunder."),
  bullet("**Ekskluderede turnover-typer.**"),
  bullet("**Rækker med turnover 0**, der ellers forvrænger margin-beregningen."),
  bullet(
    "**Døde items** — varer uden aktivitet inden for kundens turnover-vindue. " +
      "En vare der sidst blev solgt for to år siden skal ikke trække kundens " +
      "margin i nogen retning i dag."
  ),
  ...figure(
    "budgettal", 1000, 268,
    "Figur 1 — Måneder efter dags dato er endnu ikke realiseret og tælles ikke med."
  ),
  h2("Døde items — den frasortering der flytter mest"),
  p(
    "Den sidste af de fem er værd at dvæle ved, for den er den eneste der " +
      "fjerner noget som faktisk ER solgt. Reglen er enkel: **har en vare " +
      "ingen aktivitet inden for kundens turnover-vindue, ryger den helt ud " +
      "af analysen** — også ud af margin-beregningen på X-aksen."
  ),
  ...figure(
    "doede-items", 1000, 584,
    "Figur 2 — Kundens vindue går 12 måneder bagud fra dens seneste aktivitet. " +
      "712347 blev sidst handlet længe før og falder ud."
  ),
  p(
    "Uden den regel ville en gammel handel hænge ved i det uendelige. I " +
      "eksemplet ovenfor blev 712347 sidst solgt i 2023-11 til 10 % margin. " +
      "Tælles den med, ser Eksempel A/S ud til at ligge på 34 % — regnes der " +
      "kun på det kunden faktisk handler i dag, er tallet 44 %. Det er " +
      "forskellen på en kunde man vil have flere af, og en man skal se på."
  ),
  note(
    "Bemærk:",
    "vinduet regnes altid fra KUNDENS seneste aktivitet, uanset hvad " +
      "forankringen er sat til under Beregning. Ellers ville en vare kunne " +
      "holde sig selv i live."
  ),
  h2("Rammer det så de tidligere kunder?"),
  p(
    "Nej. Det er det første man frygter, når man hører at gamle varer " +
      "sorteres fra — for en tidligere kunde er jo netop en hvis handel " +
      "ligger tilbage i tiden. Men vinduet er **ikke** låst til kalenderen. " +
      "Det lægges 12 måneder bagud fra **den enkelte kundes egen seneste " +
      "aktivitet**, og det gælder alle kunder, uanset type."
  ),
  ...figure(
    "tidligere-kunder", 1000, 764,
    "Figur 3 — Hver kunde får sit eget vindue. Nederst ses hvad der ville ske " +
      "hvis vinduet i stedet lå fast på dags dato."
  ),
  p(
    "En tidligere kunde bliver altså målt på sine egne sidste 12 handelsmåneder, " +
      "præcis som en aktiv kunde bliver målt på sine. Begge mister det de " +
      "handlede før det — samme regel, samme udfald."
  ),
  p(
    "Havde vinduet ligget fast på dags dato, ville billedet være et helt " +
      "andet: så ville en kunde der stoppede for fire år siden ikke have en " +
      "eneste vare inden for vinduet, og hele kunden ville forsvinde ud af " +
      "analysen. Det er lige netop dét, forankringen i kunden forhindrer."
  ),
  note(
    "Og kundetypen flytter sig ikke:",
    "den vare der bærer kundens seneste aktivitet er per definition inde i " +
      "kundens eget vindue, så den overlever altid filteret. Derfor kan " +
      "frasorteringen aldrig ændre hvornår en kunde sidst handlede — og " +
      "dermed heller ikke om den er Eksisterende, Ny eller Tidligere."
  ),
  h2("Trin 2 — Item-type: sinter eller støb"),
  p("Varenummeret afgør typen ud fra de to første cifre:"),
  code([
    "60-67 + mindst 6 cifre   →  Støbe",
    "70-77 + mindst 6 cifre   →  Sinter",
    "alt andet                →  frasorteres",
  ]),
  p("Et suffix på varenummeret overruler reglen:"),
  code(["-S1  →  Sinter", "-S2  →  Støbe", "-S0  →  fjern fra segmenteringen"]),
  h2("Trin 3 — Kundetype"),
  p(
    "To perioder afgør det hele, og begge regnes ud fra **datoerne i data**. " +
      "Kolonnen “Fiscal year” bruges ikke længere: den kunne være skrevet " +
      "“2026/27” ét sted og “2026/2027” et andet, og så faldt en ny kunde " +
      "stiltiende ned i “Eksisterende”."
  ),
  bullet(
    "**Ny-regnskabsåret** løber fra sin startmåned og tolv måneder frem. " +
      "Begynder året i maj, er 2026/27 altså 05-2026 til og med 04-2027."
  ),
  bullet(
    "**Eksisterende-vinduet** er N måneder bagud fra dags dato, typisk 24. " +
      "Med dags dato 09-2026 er det 09-2024 til og med 09-2026."
  ),
  p(
    "De to perioder **overlapper** — her fra 05-2026 og frem. Derfor afgøres " +
      "typen i en fast rækkefølge:"
  ),
  table(
    ["Type", "Betyder"],
    [
      [
        "Ny",
        "HELE kundens historik ligger inden for ny-regnskabsåret. Det er ikke nok at den seneste handel gør det.",
      ],
      [
        "Genopstået",
        "Handler i ny-året, men har ikke handlet i vinduet i tiden op til året begyndte. Kunden har ligget stille og er tilbage.",
      ],
      [
        "Eksisterende",
        "Ikke ny eller genopstået, men mindst én handel ligger inden for eksisterende-vinduet.",
      ],
      ["Tidligere", "Al aktivitet ligger før vinduet."],
    ],
    [22, 78]
  ),
  ...figure(
    "kundetyper", 1000, 640,
    "Figur 4 — De fem tilfælde. De to perioder overlapper, og rækkefølgen af " +
      "reglerne afgør hvad der sker i overlappet."
  ),
  p(
    "Kunde C er den genopståede. Den handlede i 2023 og igen i 2026, altså " +
      "med tre års pause. Den er **ikke** ny — en kunde man har handlet med " +
      "før er ikke en ny kunde — og den er heller ikke tidligere, for den " +
      "handler jo igen."
  ),
  p(
    "Forskellen på **Genopstået** og **Eksisterende** er hullet. To kunder " +
      "kan begge have handlet i sidste måned og begge have gammel historik; " +
      "den ene har handlet støt hele vejen, den anden har ikke rørt os i " +
      "årevis. Det er to forskellige situationer for en sælger, og de har " +
      "derfor hver sin farve på kundegruppe-grafen."
  ),
  note(
    "I praksis:",
    "måneder efter dags dato er budgettal og sorteres fra i trin 1. Den del " +
      "af ny-regnskabsåret der ligger ude i fremtiden kan derfor ikke gøre " +
      "nogen til en ny kunde — reelt er ny-året 05-2026 til 09-2026."
  ),
  note(
    "Pas på formatet:",
    "ny-regnskabsåret skrives ÅÅÅÅ/ÅÅÅÅ, fx 2026/2027. Hvilken måned året " +
      "begynder i sættes under Indstillinger → Kundetyper; som udgangspunkt " +
      "er det maj."
  ),
  h2("Trin 4 — Gross Margin % pr. vare"),
  p(
    "For hvert par af kundegruppe og varenummer findes den seneste måned med " +
      "aktivitet. Som standard er det kun den måned der tæller med i " +
      "margin-beregningen; ældre måneder ignoreres."
  ),
  p(
    "Slås **vægtet GM%** til, summeres de N seneste aktivitetsmåneder i " +
      "stedet, og marginen regnes som SUM(GP) delt med SUM(Turnover) over " +
      "hele perioden. Det dæmper støj fra enkeltmåneder — kampagnepriser, " +
      "engangsrabatter, valutaudsving."
  ),
  h2("Trin 5 — Turnover-vindue"),
  p(
    "Y-aksen er summen af omsætningen i et rullende vindue på N måneder. " +
      "Vinduet kan forankres to steder, og de to grafer må gerne have hver sin:"
  ),
  bullet(
    "**Kunden** — vinduet regnes bagud fra kundegruppens seneste aktivitet. " +
      "Alle varer under samme kunde dækker præcis samme kalenderperiode."
  ),
  bullet(
    "**Item** — vinduet regnes bagud fra hver vares egen seneste aktivitet. " +
      "To varer hos samme kunde kan have forskudte perioder."
  ),
  ...figure(
    "forankring", 1000, 502,
    "Figur 5 — Samme to varer, samme data. Forankringen afgør hvilken " +
      "periode hver vare måles over."
  ),
  h2("Trin 6 — Outlier-filter"),
  p(
    "Valgfrit. Inden for hver kundegruppe kan enkeltvarer der ligger " +
      "ekstremt langt fra gennemsnittet sorteres fra, så de ikke trækker " +
      "hele kunden skævt. Tærsklen sættes i antal standardafvigelser: 1 er " +
      "aggressiv, 2 er det typiske valg, 3 fjerner kun det virkelig " +
      "ekstreme."
  ),
  h2("Trin 7 — Kundekategori"),
  p(
    "Kunden placeres i et turnover-bånd — A, B, C eller D — og får derefter " +
      "et plus eller et minus alt efter om marginen når båndets krav."
  ),
  code([
    "A:  over 5 mio.        krav 20 %      →  A+ hvis GM% > 20, ellers A-",
    "B:  1 – 5 mio.         krav 22 %      →  B+ / B-",
    "C:  0,5 – 1 mio.       krav 25 %      →  C+ / C-",
    "D:  under 0,5 mio.     krav 30 %      →  D+ / D-",
  ]),
  p(
    "Grænserne og kravene kan ændres i indstillingerne. Bemærk at kravet " +
      "stiger jo mindre kunden er: en lille ordre skal tjene mere hjem i " +
      "procent for at være lige så interessant.",
    { after: 200 }
  ),
  h2("Trin 8 — KAM"),
  p(
    "Kunden tildeles den key account manager der står på den **seneste** " +
      "aktivitet, så et skift undervejs slår igennem. Store og små bogstaver " +
      "er uden betydning — PHA og pHA er samme person — og kunder uden KAM " +
      "samles under **(Blank)**."
  ),
  h2("Trin 9 — Output"),
  p("Graferne og Excel-rapporten skrives til den daterede mappe."),
  pageBreak()
);

// 5
add(
  h1("5  Et gennemgående regneeksempel"),
  p(
    "Eksempel A/S har handlet på tre varenumre. Turnover-vinduet er 12 " +
      "måneder, og kundens seneste aktivitet er 2025-08. Vinduet dækker " +
      "derfor 2024-09 til 2025-08."
  ),
  table(
    ["Item", "Seneste aktivitet", "I vinduet?", "Turnover", "GP"],
    [
      ["712345", "2025-05", "Ja", "8.000", "2.400"],
      ["712346", "2025-08", "Ja", "20.000", "10.000"],
      ["712347", "2023-11", "Nej — fjernes", "12.000", "1.200"],
    ],
    [16, 24, 24, 18, 18],
    true
  ),
  spacer(160),
  p(
    "712347 blev sidst handlet for næsten to år siden og falder uden for " +
      "vinduet. Den sorteres fra i trin 1, og resten bygger kun på 712345 og " +
      "712346. Tallene står med for at vise hvad der bliver lagt til side — " +
      "de indgår ikke i nogen beregning. Det er den samme kunde som i " +
      "figur 2.",
    { italics: true, color: GREY }
  ),
  h2("X-koordinatet: Gross Margin %"),
  code([
    "GP:        2.400 + 10.000  =  12.400",
    "Turnover:  8.000 + 20.000  =  28.000",
    "GM%     =  12.400 / 28.000 =  44 %",
  ]),
  p("44 % er X-koordinatet for Eksempel A/S på kundegruppe-plottet."),
  h2("Y-koordinatet: Turnover i vinduet"),
  code(["Turnover:  8.000 + 20.000  =  28.000 DKK"]),
  p(
    "28.000 DKK er Y-koordinatet. Bemærk at det er det samme tal der indgår " +
      "i begge beregninger — marginen er et forhold, omsætningen er en sum."
  ),
  h2("Kategorien"),
  p(
    "28.000 DKK ligger under 0,5 mio. og falder derfor i bånd **D**, hvor " +
      "kravet er 30 %. Kundens margin er 44 %, altså over kravet, og " +
      "kategorien bliver **D+**: en lille kunde, men en sund en af slagsen."
  ),
  note(
    "Det vigtige:",
    "hvert punkt i graferne kan altid føres tilbage til nogle få rækker i " +
      "Excel-filen. Er et tal overraskende, så find kunden i Excel-rapporten — " +
      "der står de mellemregninger punktet er bygget af."
  ),
  pageBreak()
);

// 6
add(
  h1("6  De to grafer"),
  p(
    "Der laves to grafer for hvert udsnit. De besvarer to forskellige " +
      "spørgsmål og skal læses hver for sig."
  ),
  table(
    ["", "Kundegruppe-grafen", "Item-grafen"],
    [
      ["Ét punkt er", "én kundegruppe", "ét varenummer hos én kunde"],
      ["Farven følger", "kundetypen", "kundegruppen"],
      ["Legenden viser", "kundenavne pr. kategori", "kundenavne pr. kategori"],
      ["Baggrunden viser", "A/B/C/D-zonerne", "volumenområder for ét niveau ad gangen"],
      [
        "Bruges til",
        "hvem er vigtige, og hvem tjener vi penge på",
        "hvilke varer trækker en kunde op eller ned",
      ],
    ],
    [20, 40, 40]
  ),
  spacer(200),
  p(
    "På begge grafer står punkterne i legenden til højre, grupperet efter " +
      "kundekategori — A+, A-, B+ og så videre. Et klik på et navn slår det " +
      "enkelte punkt fra. Et **dobbeltklik** viser kun den ene kunde og " +
      "skjuler alle andre — det virker både på navnet i legenden og på " +
      "selve punktet i grafen. Dobbeltklik igen bringer resten tilbage."
  ),
  p(
    "Baggrundsfarverne er zoner, ikke data. De viser hvor grænserne mellem " +
      "kategorierne går, så det kan ses om en kunde ligger lige på vippen."
  ),
  note(
    "Akserne:",
    "X-aksen er lineær og Y-aksen logaritmisk, og det kan ikke laves om. " +
      "Gross Margin % ligger inden for et snævert interval og læses som " +
      "procentpoint. Omsætningen spænder derimod over flere størrelses" +
      "ordener, og på en lineær akse ville alt andet end de største kunder " +
      "klumpe sammen nede ved nul."
  ),
  p(
    "Øverst til venstre over kundegruppe-grafen står en lille **farvekode**, " +
      "der siger hvilken farve der hører til hvilken kundetype. Den ligger " +
      "uden for selve grafen, så den hverken stjæler plads fra punkterne " +
      "eller kan slås fra ved et uheld. Farvelægges der efter Industry " +
      "segment i stedet, viser farvekoden brancherne."
  ),
  note(
    "Graferne virker uden internet.",
    "Hele tegnebiblioteket ligger inde i HTML-filen. Derfor fylder hver fil " +
      "omkring 4 MB, men den kan til gengæld åbnes hvor som helst — også " +
      "sendt videre til en kollega som en enkelt vedhæftet fil."
  )
);

// 7
add(
  h1("7  Knapperne under graferne"),
  p(
    "Under hver graf er der rækker af knapper. De virker som **filtre der " +
      "begrænser hinanden** — ikke som uafhængige kontakter."
  ),
  table(
    ["Række", "Findes på", "Gør"],
    [
      ["Vis/skjul kundetype", "kundegruppe-grafen", "slår Eksisterende, Ny eller Tidligere fra"],
      ["Vis/skjul kategori", "begge", "slår en hel kategori-blok fra"],
      ["Vis/skjul KAM", "begge", "slår én key account managers kunder fra"],
      ["Fremhæv branche", "kundegruppe-grafen", "tykkere kant på én branche — skjuler intet"],
      ["Volumenkrav", "item-grafen", "skifter hvilket niveaus zoner der tegnes"],
      ["↺ Nulstil alle filtre", "begge, nederst", "slår alle filterrækker fra på én gang"],
    ],
    [26, 26, 48]
  ),
  spacer(200),
  h2("Farverne på knapperne"),
  p(
    "En knap er **grøn når den er tændt** og **rød når den er slukket**, så " +
      "det kan ses på afstand hvad der er slået fra."
  ),
  bullet(
    "**Filterknapper** (kundetype, kategori, KAM): grøn betyder at værdien " +
      "vises, rød at den er skjult. Alle starter grønne."
  ),
  bullet(
    "**Volumenkrav** har omvendt fortegn, fordi det er et enten-eller-valg: " +
      "den valgte er grøn, de fravalgte røde."
  ),
  bullet(
    "**Fremhæv branche** bliver hverken grøn eller rød. De knapper skjuler " +
      "ingenting — de gør kun én branche tykkere i kanten — og rød ville " +
      "påstå at noget var slået fra."
  ),
  p(
    "De to nuancer er valgt så de også er forskellige i lyshed: den røde er " +
      "mærkbart mørkere end den grønne. Er man rødgrønt farveblind, kan " +
      "tilstanden derfor stadig aflæses.",
    { italics: true, color: GREY }
  ),
  h2("Hvad “filtre der begrænser hinanden” betyder"),
  p(
    "Forestil dig at du har slået alt fra på nær én KAM. Hvis du så slukker " +
      "og tænder for kundetypen “Tidligere”, kommer **kun den ene KAM's** " +
      "tidligere kunder tilbage — ikke alle tidligere kunder. Et punkt vises " +
      "kun hvis det slipper gennem hver eneste række."
  ),
  p(
    "Det er værd at vænne sig til, for det er den opførsel man forventer af " +
      "et filter, og den gør det muligt at skrue ned ad flere veje på samme " +
      "tid uden at miste overblikket."
  ),
  note(
    "Gået i ged?",
    "Knappen **↺ Nulstil alle filtre** nederst under graferne rydder alle " +
      "filterrækker på én gang. Valget af volumenkrav på item-grafen røres " +
      "ikke — det er et enten-eller-valg, ikke et filter."
  ),
  p(
    "Et klik i legenden er et engangsvalg: næste gang du rører en " +
      "filterknap, regnes synligheden forfra ud fra knapperne alene.",
    { italics: true, color: GREY }
  ),
  pageBreak()
);

// 8
add(
  h1("8  Udsnit, filnavne og hvor resultatet havner"),
  p(
    "Analysen kører ét **udsnit** ad gangen. Udsnittene udspændes af tre valg " +
      "i indstillingerne:"
  ),
  bullet("**Emne-type** — samlet, kun sinter, kun støb."),
  bullet("**Geografi** — samlet, kun DK, kun CN."),
  bullet("**Kundeudvalg** — alle kunder, eller kun de eksisterende."),
  p(
    "Hvert udsnit får sit eget sæt filer og sine egne faner i Excel, og tallene " +
      "er regnet forfra på netop de rækker udsnittet dækker. Grafen og fanerne " +
      "for et udsnit viser derfor altid det samme.",
    { after: 200 }
  ),
  code([
    "<basis>_kundegruppe[_sinter|_stoebe][_cn|_dk][_eks].html",
    "<basis>_item[_sinter|_stoebe][_cn|_dk][_eks].html",
    "<basis>.xlsx",
  ]),
  note(
    "Bemærk:",
    "slår du både sinter/støb og DK/CN til, bliver det hurtigt mange filer. " +
      "Det er med vilje — hver fil er ét spørgsmål med ét svar. Slå de " +
      "opdelinger fra du ikke skal bruge."
  ),
  h2("Mappen"),
  p(
    "Står output-mappen tom i indstillingerne — og det gør den som " +
      "udgangspunkt — oprettes der en dateret mappe ved siden af programmet " +
      "hver gang analysen køres. Så bliver gamle kørsler stående, og det kan " +
      "altid ses hvornår et tal blev lavet."
  ),
  p(
    "Går noget galt undervejs, stopper programmet og viser fejlen i en boks. " +
      "Der skrives ingen logfil."
  )
);

// 9
add(
  h1("9  Excel-rapporten"),
  p(
    "Excel-filen indeholder tallene bag hvert punkt i graferne — det er her " +
      "man går hen når et punkt ser mærkeligt ud. Der er tre faner pr. udsnit " +
      "og en fane med de indstillinger kørslen brugte. Fanerne ser ens ud " +
      "hver gang; der er ikke noget at vælge."
  ),
  table(
    ["Fane", "Indeholder"],
    [
      ["Oversigt", "én række pr. kundegruppe: type, KAM, kategori, omsætning og GM%"],
      ["Items_alle", "alle varer, inden outlier-filteret"],
      ["Items_filt", "de varer der faktisk blev tegnet"],
      ["Parametre", "de indstillinger kørslen brugte"],
    ],
    [24, 76]
  ),
  spacer(200),
  p(
    "Er outlier-filteret slået til, kan det ses i rapporten hvilke varer der " +
      "blev sorteret fra, og hvorfor."
  )
);

// 10
add(
  h1("10  Indstillinger og egne standardværdier"),
  p(
    "Knappen **Indstillinger** åbner alt det der ikke skal røres hver gang. " +
      "Indstillingerne deler felter med forsiden, så en ændring slår igennem " +
      "med det samme — der er ikke noget at gemme eller bekræfte."
  ),
  table(
    ["Afsnit", "Handler om"],
    [
      ["Placering af resultatet", "output-mappe og basisnavn på filerne"],
      ["Kundetyper", "hvor mange måneder bagud en kunde regnes som eksisterende"],
      ["Frasortering", "ekskluderede grupper og typer, nul-rækker, døde items, outliers"],
      ["Opdeling af plots", "sinter/støb og DK/CN, og hvilke turnover-typer der hører til hvad"],
      ["Beregning", "turnover-vinduets længde, forankring, vægtet GM%"],
      ["Grænser og områder", "kategori-grænser og volumenområder"],
    ],
    [30, 70]
  ),
  spacer(200),
  h2("Gem dine egne standardværdier"),
  p(
    "Nederst i indstillingsvinduet er der to knapper. **Gem som mine " +
      "standardværdier** skriver de nuværende indstillinger til en lille fil " +
      "ved siden af programmet. Den læses næste gang programmet åbnes, og " +
      "følger med hvis mappen kopieres til en kollega."
  ),
  p(
    "**Nulstil til fabriksindstillinger** kasserer den fil igen. Dags dato " +
      "og ny-regnskabsår gemmes aldrig — de udfyldes altid ud fra dagens " +
      "dato, så programmet ikke stivner på den dag indstillingerne blev gemt."
  ),
  note(
    "Et godt råd:",
    "sæt indstillingerne én gang sammen med den der har brugt værktøjet før, " +
      "og gem dem som standard. Så er der kun tre felter at forholde sig til " +
      "på forsiden derefter."
  ),
  pageBreak()
);

// 11
add(
  h1("11  Når noget går galt"),
  table(
    ["Det ser sådan ud", "Det er som regel"],
    [
      [
        "“Følgende påkrævede kolonner mangler …”",
        "En kolonne er blevet stavet om i udtrækket. Beskeden viser både hvad der mangles, og hvad der faktisk stod.",
      ],
      [
        "Ingen kunder er “Ny”",
        "Ny-regnskabsåret passer ikke med kolonnen “Fiscal year”. Tjek formatet — der skal stå fx 2026/2027.",
      ],
      [
        "Færre kunder end forventet",
        "Perioder efter dags dato er skåret fra som budgettal, eller en kundegruppe står på ekskluder-listen.",
      ],
      [
        "En graf er helt tom",
        "Udsnittet indeholder ingen rækker — fx kun sinter i en fil uden sinter-varer.",
      ],
      [
        "Programmet kan ikke gemme",
        "Det ligger et sted der er skrivebeskyttet. Flyt det til skrivebordet eller et drev.",
      ],
      [
        "Vinduet forsvinder ved start",
        "Antivirus har sat filen i karantæne. Den er ikke underskrevet med et certifikat, og det reagerer nogle opsætninger på.",
      ],
    ],
    [38, 62]
  ),
  spacer(200),
  p(
    "Fejlbeskeden vises i en boks når analysen stopper. Den er det første " +
      "sted at kigge — og det der skal sendes med videre hvis nogen skal " +
      "hjælpe."
  )
);

// 12
add(
  h1("12  Ordliste"),
  table(
    ["Ord", "Betyder"],
    [
      ["Kundegruppe", "Værdien i kolonnen “Statistics group”. Ét punkt på kundegruppe-grafen."],
      ["GM% / Gross Margin", "Dækningsbidrag delt med omsætning, i procent. X-aksen."],
      ["GP", "Gross Profit — dækningsbidraget i kroner."],
      ["COGS", "Cost of Goods Sold — vareforbruget."],
      ["Turnover-vindue", "De seneste N måneder der tælles med i omsætningen. Y-aksen."],
      ["Forankring", "Om vinduet regnes fra kundens eller fra varens seneste aktivitet."],
      ["Kundekategori", "A+, A-, B+ … Bogstavet er volumen, tegnet er om marginen når kravet."],
      ["Kundetype", "Eksisterende, Ny eller Tidligere."],
      ["Item-type", "Sinter eller støb, udledt af varenummeret."],
      ["Outlier", "En vare der ligger så langt fra kundens gennemsnit at den kan sorteres fra."],
      ["Udsnit", "Én kombination af emne-type, geografi og kundeudvalg. Får sit eget sæt filer."],
      ["KAM", "Key Account Manager — den ansvarlige for kunden."],
      ["Dags dato", "Skæringsdatoen. Perioder efter den regnes som budget og tælles ikke med."],
    ],
    [24, 76]
  ),
  pageBreak()
);

// 13
add(
  h1("13  Sådan bygges programmet igen"),
  p(
    "Dette kapitel er til den der skal vedligeholde værktøjet. Til daglig " +
      "brug er det ikke nødvendigt."
  ),
  p(
    "Programfilen bygges af kildekoden med ét script. På den maskine der " +
      "bygger, skal der være **Python 3.10 eller nyere** installeret fra " +
      "python.org — resten henter scriptet selv."
  ),
  code([
    "python build_exe.py",
    "",
    "eller på Windows: dobbeltklik byg_exe.bat",
  ]),
  p(
    "Resultatet lægges i mappen **dist**. Første byg tager et par minutter; " +
      "derefter går det hurtigere."
  ),
  table(
    ["Tilvalg", "Gør"],
    [
      ["--mappe", "bygger en mappe i stedet for én fil. Starter hurtigere, men hele mappen skal følge med."],
      ["--spring-over", "installerer ikke afhængigheder først."],
      ["--behold", "rydder ikke op bagefter — til fejlsøgning."],
    ],
    [24, 76],
    true
  ),
  spacer(200),
  note(
    "Vigtigt:",
    "PyInstaller kan ikke bygge på tværs af styresystemer. En Windows-exe " +
      "skal bygges på en Windows-maskine, og et Mac-program på en Mac."
  ),
  p(
    "Beregningen kan også bruges uden brugerfladen — fra et script eller en " +
      "notebook — hvis der en dag skal laves noget andet med de samme tal. " +
      "Det er beskrevet i projektets README sammen med testene."
  )
);

// --- Dokumentet --------------------------------------------------------------

const doc = new Document({
  creator: "Kundesegmentering",
  title: "Kundesegmentering – introduktion",
  description: "Sådan virker kundesegmenteringen",
  styles: {
    default: {
      document: { run: { font: "Calibri", size: 22 } },
    },
  },
  numbering: {
    config: [
      {
        reference: "steps",
        levels: [
          {
            level: 0,
            format: "decimal",
            text: "%1.",
            alignment: AlignmentType.START,
            style: { paragraph: { indent: { left: 460, hanging: 260 } } },
          },
        ],
      },
    ],
  },
  sections: [
    {
      properties: {
        page: {
          margin: {
            top: convertInchesToTwip(1),
            bottom: convertInchesToTwip(1),
            left: convertInchesToTwip(1),
            right: convertInchesToTwip(1),
          },
        },
      },
      footers: {
        default: new Footer({
          children: [
            new Paragraph({
              alignment: AlignmentType.CENTER,
              children: [
                new TextRun({ text: "Kundesegmentering  ·  side ", size: 18, color: GREY }),
                new TextRun({ children: [PageNumber.CURRENT], size: 18, color: GREY }),
              ],
            }),
          ],
        }),
      },
      children: body,
    },
  ],
});

const out = process.argv[2] || path.join(__dirname, "Kundesegmentering-introduktion.docx");
Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(out, buffer);
  console.log(`Skrevet: ${out}  (${(buffer.length / 1024).toFixed(0)} kB)`);
});

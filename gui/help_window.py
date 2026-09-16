"""
Hjælpevinduet "Sådan behandles data".

Indholdet står som data nederst i filen og tegnes af én generisk funktion, så
teksten kan rettes uden at røre ved layout-koden.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, scrolledtext

# Afsnitstyper. Hver knytter sig til en tekst-tag der sættes op i _configure_tags.
TITLE = "h1"
HEADING = "h2"
BODY = "body"
NOTE = "ital"  # dæmpet forklarende bemærkning
CODE = "kode"
TABLE = "tabel"  # fastbredde-opstilling
EXAMPLE = "eks"  # fremhævet eksempel-blok

Block = tuple[str, str]


def _configure_tags(widget: scrolledtext.ScrolledText) -> None:
    widget.tag_configure(
        TITLE, font=("Helvetica", 14, "bold"), foreground="#1a4a7a", spacing1=10, spacing3=8
    )
    widget.tag_configure(
        HEADING, font=("Helvetica", 11, "bold"), foreground="#2a5a8a", spacing1=8, spacing3=4
    )
    widget.tag_configure(BODY, font=("Helvetica", 10))
    widget.tag_configure(NOTE, font=("Helvetica", 10, "italic"), foreground="#555")
    widget.tag_configure(CODE, font=("Courier", 10), background="#f0f0f0")
    widget.tag_configure(TABLE, font=("Courier", 9), lmargin1=15, lmargin2=15)
    widget.tag_configure(
        EXAMPLE,
        font=("Courier", 9),
        background="#fffbe0",
        lmargin1=15,
        lmargin2=15,
        rmargin=15,
        spacing1=4,
        spacing3=4,
    )


def show_help_window(parent: tk.Misc) -> tk.Toplevel:
    """Åbner hjælpevinduet centreret over hovedvinduet."""
    window = tk.Toplevel(parent)
    window.title("Hjælp – sådan behandles data")
    window.geometry("780x640")
    window.minsize(600, 400)

    frame = ttk.Frame(window, padding=(15, 15))
    frame.pack(fill="both", expand=True)

    text = scrolledtext.ScrolledText(
        frame, wrap="word", font=("Helvetica", 10), padx=10, pady=10
    )
    text.pack(fill="both", expand=True)
    _configure_tags(text)

    for tag, content in HELP_CONTENT:
        text.insert("end", content, tag)
    text.configure(state="disabled")

    buttons = ttk.Frame(window, padding=(15, 0, 15, 15))
    buttons.pack(fill="x")
    ttk.Button(buttons, text="Luk", command=window.destroy).pack(side="right")

    window.transient(parent)
    window.update_idletasks()
    x = parent.winfo_rootx() + (parent.winfo_width() - window.winfo_width()) // 2
    y = parent.winfo_rooty() + 40
    window.geometry(f"+{max(x, 0)}+{max(y, 0)}")
    return window


HELP_CONTENT: list[Block] = [
    (TITLE, "Sådan behandles dine salgsdata\n"),
    (
        BODY,
        "Programmet tager rå salgsdata fra Excel og laver interaktive HTML "
        "scatter-plots, hvor hvert punkt er én kundegruppe eller ét item no. "
        "Nedenfor er hele rejsen fra rå data til plot, med et eksempel der "
        "følges hele vejen igennem.\n\n",
    ),

    (HEADING, "Trin 1: Frasortering af rækker og døde items\n"),
    (
        BODY,
        "Først fjernes de rækker der ikke skal med:\n"
        "  • Kundegrupper på din 'Ekskluder kundegrupper'-liste\n"
        "  • Rækker hvis 'Turnover type' står på din ekskluder-liste "
        "(typisk interne posteringer og korrektioner)\n"
        "  • Rækker hvor Turnover DKK er 0 (hvis slået til)\n\n"
        "Derefter frasorteres døde items (hvis 'Fjern døde items' er slået til):\n"
        "  • For hver kundegruppe findes kundens seneste aktivitetsmåned\n"
        "  • Items uden aktivitet inden for kundens turnover-vindue fjernes helt\n"
        "  • Det sker FØR alle beregninger, så begge akser og begge plots "
        "bygger på præcis det samme grundlag\n\n",
    ),

    (HEADING, "Trin 2: Klassifikation af item no.\n"),
    (BODY, "Hvert item no. tildeles en type ud fra sine to første cifre:\n"),
    (
        TABLE,
        "    60-67 + mindst 6 cifre  →  Støbe\n"
        "    70-77 + mindst 6 cifre  →  Sinter\n"
        "    alt andet               →  frasorteres\n\n",
    ),
    (BODY, "Et suffix på item no. i Excel-filen overruler den automatiske regel:\n"),
    (
        TABLE,
        "    -S1  →  Sinter\n"
        "    -S2  →  Støbe\n"
        "    -S0  →  fjern fra segmenteringen\n\n",
    ),

    (HEADING, "Trin 3: Kundetype\n"),
    (
        BODY,
        "Hver kundegruppe klassificeres som én af tre typer:\n"
        "  • Ny – aktivitet kun i det valgte regnskabsår, ingen tidligere historik\n"
        "  • Eksisterende – aktivitet inden for 'Eksisterende kunde vindue' "
        "bagud fra 'Dags dato'\n"
        "  • Tidligere – al aktivitet ligger uden for begge vinduer\n\n",
    ),

    (HEADING, "Trin 4: Pr. item no. – seneste måned(er)\n"),
    (
        BODY,
        "For hvert unikt (kundegruppe, item no.) findes den seneste måned med "
        "aktivitet. Som standard bruges kun den måned til GM-beregningen, og "
        "ældre måneder ignoreres. Er der flere rækker i samme seneste måned, "
        "lægges de sammen.\n\n"
        "Slår du 'Vægtet GM% over seneste N måneder' til, summeres i stedet de "
        "N seneste aktivitetsmåneder pr. item, og GM% = SUM(GP) / SUM(Turnover) "
        "over hele perioden. Det dæmper støj fra enkeltmåneder.\n\n",
    ),

    (HEADING, "Eksempel\n"),
    (
        BODY,
        "Eksempel A/S har handlet på tre items. Turnover-vinduet er 12 måneder, "
        "og kundens seneste aktivitet er 2025-08:\n\n",
    ),
    (
        EXAMPLE,
        "  Item     Seneste akt.  I vinduet?  Turnover    GP\n"
        "  ──────────────────────────────────────────────────────\n"
        "  712345   2025-05       Ja           8.000     2.400  (30% GM)\n"
        "  712346   2025-08       Ja          20.000    10.000  (50% GM)\n"
        "  712347   2023-11       Nej          12.000     1.200  (10% GM)\n\n",
    ),
    (
        NOTE,
        "712347 blev sidst handlet for næsten to år siden og falder uden for "
        "vinduet. Den sorteres fra i trin 1, og resten bygger kun på 712345 "
        "og 712346.\n\n"
        "Det flytter noget: med filteret bliver kundens GM% 12.400/28.000 = "
        "44%. Uden ville den gamle handel til 10% margin trække den ned på "
        "13.600/40.000 = 34%.\n\n",
    ),

    (HEADING, "Trin 5: GM% pr. kundegruppe (X-aksen)\n"),
    (BODY, "Items lægges sammen til ét vægtet GM% pr. kunde:\n\n"),
    (CODE, "  Samlet GM% = SUM(GP) / SUM(Turnover)\n"),
    (BODY, "\nFortsat med eksemplet:\n\n"),
    (
        EXAMPLE,
        "  GP:        2.400 + 10.000 = 12.400\n"
        "  Turnover:  8.000 + 20.000 = 28.000\n"
        "  GM%     =  12.400 / 28.000 = 44%\n\n",
    ),
    (BODY, "44% er X-koordinatet for Eksempel A/S på kundegruppe-plottet.\n\n"),

    (HEADING, "Trin 6: Turnover-vindue (Y-aksen)\n"),
    (
        BODY,
        "Y-aksen er summen af salget i de seneste N måneder. Men N måneder "
        "bagud fra hvad? Det afgør forankringen, som vælges i sektion 5:\n\n"
        "  • Forankring = Kunden: vinduet regnes bagud fra KUNDEGRUPPENS "
        "seneste aktivitet, så alle items i samme kunde dækker præcis samme "
        "kalenderperiode. Det giver det mest retvisende billede af kundens "
        "samlede omsætning, og er standard for kundegruppe-plottet.\n\n"
        "  • Forankring = Item: vinduet regnes bagud fra HVERT ITEMS egen "
        "seneste aktivitet, så hvert item måles over sine egne seneste N "
        "aktive måneder. Det er standard for item-plottet.\n\n"
        "Med N=12 og forankring = Kunden bliver vinduet 2024-09 til 2025-08:\n\n",
    ),
    (
        EXAMPLE,
        "  712345 i vinduet:   8.000\n"
        "  712346 i vinduet:  20.000\n"
        "  Samlet vindue   =  28.000\n\n",
    ),

    (HEADING, "Trin 6b: Item-plottet\n"),
    (
        BODY,
        "Kundegruppe-plottet koger hele kunden ned til ét punkt. Item-plottet "
        "gør det modsatte: hvert item no. får sit eget punkt, så du kan se "
        "hvilke varer der trækker kunden op eller ned.\n\n"
        "Med forankring = Item får de to varer forskudte vinduer, fordi de "
        "sidst blev solgt i hver sin måned:\n\n",
    ),
    (
        EXAMPLE,
        "  Item     Egen seneste akt.  Eget vindue           Y (turnover)\n"
        "  ─────────────────────────────────────────────────────────────\n"
        "  712345   2025-05            2024-06 til 2025-05      8.000\n"
        "  712346   2025-08            2024-09 til 2025-08     20.000\n\n",
    ),
    (
        NOTE,
        "Derfor kan samme vare have to lidt forskellige turnover-tal alt efter "
        "hvilket plot du kigger på. Det er ikke en fejl: forankring = Item "
        "spørger \"hvor stor var varen da den sidst var aktiv?\", mens "
        "forankring = Kunden spørger \"hvor stor er varen i kundens aktuelle "
        "periode?\". Begge tal står i hver sin kolonne i Excel-rapporten.\n\n",
    ),

    (HEADING, "Trin 7: Outlier-filter (valgfrit)\n"),
    (
        BODY,
        "Når 'Fjern outliers' er slået til, fjernes items der afviger markant "
        "fra normalen inden for samme kundegruppe, inden de lægges sammen til "
        "kundegruppe-niveau. For hvert item beregnes en z-score = "
        "(værdi − snit) / standardafvigelse, og items over tærsklen droppes.\n\n",
    ),
    (
        TABLE,
        "    3  →  mild filtrering (kun ekstreme outliers)\n"
        "    2  →  moderat (typisk valg)\n"
        "    1  →  aggressiv\n\n",
    ),
    (
        NOTE,
        "En kundegruppe med kun ét item filtreres aldrig, og en gruppe hvor "
        "alle items ser ekstreme ud beholdes urørt frem for at forsvinde.\n\n",
    ),

    (HEADING, "Trin 8: Plots og Excel-rapport\n"),
    (
        BODY,
        "Til sidst gemmes plottene som HTML og en Excel-rapport med faner pr. "
        "udsnit: en oversigt pr. kundegruppe, item-detaljer, eventuelle "
        "fjernede outliers, og en fane med de parametre kørslen brugte.\n\n"
        "Hvert udsnit — emne-type, geografi og eventuelt 'kun eksisterende "
        "kunder' — får sit eget sæt filer og faner, beregnet forfra på netop "
        "de rækker. Plottet og fanerne for et udsnit viser derfor altid de "
        "samme tal.\n",
    ),
]

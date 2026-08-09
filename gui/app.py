"""
Hovedvinduet for kundesegmenteringen.

Vinduet er delt i nummererede sektioner, én ``_build_*``-metode hver. To
metoder binder skærmen sammen med beregningen: ``_load_config`` skriver et
``Config`` ud i felterne, og ``_build_config`` læser felterne tilbage til et
``Config``. Alt andet er præsentation.
"""

from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
import traceback
from tkinter import filedialog, messagebox, scrolledtext, ttk

from segmentering import Config
from segmentering.config import Band
from segmentering.pipeline import run_analysis

from .help_window import show_help_window
from .widgets import (
    Disclosure,
    HINT_COLOUR,
    ScrollableFrame,
    heading,
    help_icon,
    labelled_entry,
    section,
    set_enabled,
)

# Forankring vises med kundens sprog, men gemmes som pakkens værdier.
ANCHOR_LABELS = {"group": "Kunden", "item": "Item"}
ANCHOR_VALUES = {label: value for value, label in ANCHOR_LABELS.items()}

CATEGORY_LEVELS = ["A", "B", "C", "D"]
VOLUME_ZONE_NAMES = ["Stor volumen", "Mellem volumen", "Lille volumen"]
LEVEL_COLOURS = {"A": "#2ecc71", "B": "#3498db", "C": "#f39c12", "D": "#9b59b6"}
ZONE_COLOURS = {
    "Stor volumen": "#2ecc71",
    "Mellem volumen": "#3498db",
    "Lille volumen": "#f39c12",
}

BAND_FORMAT_HINT = "Format: min,max,gm%  (maks tom = ingen øvre grænse)"


def format_band(band: Band) -> str:
    """Skriver et bånd som 'min,max,gm%' — det format felterne bruger."""
    upper = "" if band.turnover_max is None else str(int(band.turnover_max))
    return f"{int(band.turnover_min)},{upper},{int(round(band.gm_min * 100))}"


def parse_band(text: str, label: str) -> Band:
    """Læser 'min,max,gm%' tilbage til et ``Band``."""
    parts = [part.strip() for part in text.split(",")]
    if len(parts) != 3:
        raise ValueError(
            f"{label}: forventet formatet 'min,max,gm%' (maks kan være tom), "
            f"fik: '{text}'"
        )
    try:
        turnover_min = float(parts[0])
        turnover_max = None if parts[1] == "" else float(parts[1])
        gm_min = float(parts[2]) / 100.0
    except ValueError as exc:
        raise ValueError(
            f"{label}: kunne ikke læse tallene i '{text}'. Brug fx 500000,,20"
        ) from exc
    return Band(turnover_min, turnover_max, gm_min)


def split_list(text: str) -> list[str]:
    return [part.strip() for part in text.split(",") if part.strip()]


def describe_failure(exc: BaseException) -> str:
    """
    Laver en besked brugeren kan handle på.

    Fejl vi selv rejser undervejs — manglende kolonner, en fil der ikke kan
    åbnes, en ugyldig indstilling — er allerede formuleret på dansk og vises
    som de er. Alt andet er en programfejl, og der henvises til loggen, hvor
    hele udskriften står.
    """
    if isinstance(exc, (ValueError, FileNotFoundError, PermissionError, KeyError)):
        message = str(exc).strip()
        if message:
            return message
    return (
        f"Der opstod en uventet fejl: {type(exc).__name__}.\n\n"
        "Hele fejlbeskeden står i loggen nederst i vinduet."
    )


class SegmenteringApp(tk.Tk):
    """Tkinter-vinduet der styrer en analyse-kørsel."""

    #: Hvor ofte hovedtråden tømmer beskedkøen fra beregningen.
    POLL_INTERVAL_MS = 80

    def __init__(self) -> None:
        super().__init__()
        self.title("Kundesegmentering")
        self.minsize(760, 650)
        self.resizable(True, True)

        # Beskeder fra beregningstråden til hovedtråden.
        self._events: queue.Queue[tuple[str, object]] = queue.Queue()

        self._configure_style()
        self._create_variables()
        self._build_ui()
        self.restore_defaults()

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Run.TButton", font=("Helvetica", 11, "bold"), padding=8)
        style.configure("TLabelframe.Label", font=("Helvetica", 9, "bold"))
        style.configure(
            "Toolbutton", font=("Helvetica", 9), padding=2, relief="flat", anchor="w"
        )

    # -- Variabler ------------------------------------------------------------

    def _create_variables(self) -> None:
        self.var_input_path = tk.StringVar()
        self.var_output_dir = tk.StringVar()
        self.var_basename = tk.StringVar()

        self.var_reference_date = tk.StringVar()
        self.var_existing_months = tk.IntVar()
        self.var_new_fiscal_year = tk.StringVar()

        self.var_excluded_groups = tk.StringVar()
        self.var_excluded_turnover_types = tk.StringVar()
        self.var_drop_zero = tk.BooleanVar()
        self.var_drop_dead_items = tk.BooleanVar()

        self.var_remove_outliers = tk.BooleanVar()
        self.var_outlier_std = tk.IntVar()
        self.var_outlier_metric = tk.StringVar()

        self.var_split_item_type = tk.BooleanVar()
        self.var_geo_split = tk.BooleanVar()
        self.var_cn_types = tk.StringVar()
        self.var_dk_types = tk.StringVar()

        self.var_window_months = tk.IntVar()
        self.var_group_anchor = tk.StringVar()
        self.var_item_anchor = tk.StringVar()
        self.var_weighted_gm = tk.BooleanVar()
        self.var_gm_months = tk.IntVar()

        self.var_y_scale = tk.StringVar()
        self.var_x_scale = tk.StringVar()
        self.var_colour_by = tk.StringVar(value="kundetype")

        self.var_bands = {level: tk.StringVar() for level in CATEGORY_LEVELS}
        self.var_zones = {
            level: {zone: tk.StringVar() for zone in VOLUME_ZONE_NAMES}
            for level in CATEGORY_LEVELS
        }

        self.var_excel_detail = tk.StringVar()

    # -- Opbygning ------------------------------------------------------------

    def _build_ui(self) -> None:
        page = ScrollableFrame(self)

        toolbar = ttk.Frame(page, padding=(10, 6))
        toolbar.pack(fill="x", side="top")
        ttk.Button(
            toolbar,
            text="❓  Hjælp – hvordan behandles data?",
            command=lambda: show_help_window(self),
        ).pack(side="left")
        ttk.Button(
            toolbar, text="Nulstil til standarder", command=self.restore_defaults
        ).pack(side="right")

        self._build_file_section(page)
        self._build_dates_section(page)
        self._build_filter_section(page)
        self._build_split_section(page)
        self._build_calculation_section(page)
        self._build_axes_section(page)
        self._build_output_section(page)
        self._build_run_section(page)
        self._build_log_section(page)

    def _build_file_section(self, parent: tk.Widget) -> None:
        frame = section(parent, "1  Datafil")
        frame.pack(fill="x", padx=10, pady=5)

        ttk.Label(frame, text="Excel-fil (input):").grid(row=0, column=0, sticky="w", pady=3)
        ttk.Entry(frame, textvariable=self.var_input_path, width=55).grid(
            row=0, column=1, padx=5, pady=3, sticky="ew"
        )
        ttk.Button(frame, text="Vælg…", command=self._choose_input_file).grid(
            row=0, column=2, padx=2
        )
        help_icon(
            frame,
            "Sti til Excel-filen med rå salgsdata.\n\n"
            "Overskriftsrækken findes automatisk, så det gør ikke noget at "
            "tabellen starter længere nede i arket.\n\n"
            "Påkrævede kolonner: Statistics group, Item no., Year-mo, Cost, "
            "Qty., Turnover DKK, Local_COGS_DKK, Local_GP_DKK.\n\n"
            "Valgfri kolonner:\n"
            "  • Turnover type     – til frasortering og CN/DK-opdeling\n"
            "  • Fiscal year       – til ny-kunde klassifikation\n"
            "  • Industry_segment  – til farvelogik på plottet\n"
            "  • KAM               – giver tænd/sluk-knapper pr. key account\n"
            "                        manager på begge plots. Store og små\n"
            "                        bogstaver er uden betydning, og kunder\n"
            "                        uden KAM samles under '(Blank)'\n\n"
            "Rækker med en periode efter 'Dags dato' regnes som budgettal og "
            "udelades.",
        ).grid(row=0, column=3, padx=(4, 0))

        ttk.Label(frame, text="Output-mappe:").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Entry(frame, textvariable=self.var_output_dir, width=55).grid(
            row=1, column=1, padx=5, pady=3, sticky="ew"
        )
        ttk.Button(frame, text="Vælg…", command=self._choose_output_dir).grid(
            row=1, column=2, padx=2
        )
        help_icon(
            frame,
            "Mappe hvor HTML-plots og Excel-rapporten gemmes.\n\n"
            "Lad feltet stå tomt for at gemme i samme mappe som programmet.",
        ).grid(row=1, column=3, padx=(4, 0))

        ttk.Label(frame, text="Basisnavn (filer):").grid(row=2, column=0, sticky="w", pady=3)
        ttk.Entry(frame, textvariable=self.var_basename, width=55).grid(
            row=2, column=1, padx=5, pady=3, sticky="ew"
        )
        help_icon(
            frame,
            "Fælles basisnavn for alle genererede filer:\n"
            "  <basis>_kundegruppe.html\n"
            "  <basis>_item.html\n"
            "  <basis>.xlsx\n\n"
            "Emne-type, geografi og kundeudvalg tilføjer suffikser:\n"
            "  _sinter / _stoebe · _cn / _dk · _eks\n\n"
            "Skriv uden filendelse, fx: kunde_segmentering",
        ).grid(row=2, column=3, padx=(4, 0))

        frame.columnconfigure(1, weight=1)

    def _build_dates_section(self, parent: tk.Widget) -> None:
        frame = section(parent, "2  Datoer & kundetyper")
        frame.pack(fill="x", padx=10, pady=5)

        heading(frame, "Felterne nedenfor definerer de tre kundetyper:").grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 2)
        )
        labelled_entry(
            frame, "Dags dato:", self.var_reference_date, row=1, hint="MM-ÅÅÅÅ",
            tooltip=(
                "Reference-datoen hele segmenteringen tager udgangspunkt i.\n\n"
                "Format: MM-ÅÅÅÅ, fx 05-2026.\n\n"
                "Perioder EFTER denne måned regnes som budgettal og udelades. "
                "Er dags dato 06-2026, tæller 06-2026 med, mens 07-2026 og "
                "frem falder fra."
            ),
        )
        labelled_entry(
            frame, "Eksisterende kunde vindue:", self.var_existing_months, row=2,
            width=6, hint="måneder bagud fra dags dato",
            tooltip=(
                "Antal måneder bagud fra 'Dags dato' der definerer vinduet for "
                "eksisterende kunder.\n\nTypisk værdi: 24 (2 år)."
            ),
        )
        labelled_entry(
            frame, "Ny-regnskabsår:", self.var_new_fiscal_year, row=3, hint="fx 2026/27",
            tooltip=(
                "Regnskabsår til identifikation af NYE kunder.\n\n"
                "En kunde er 'Ny' hvis den har aktivitet i dette år og ingen "
                "tidligere historik.\n\n"
                "Lad feltet stå tomt for ikke at bruge regnskabsår-logikken."
            ),
        )

        ttk.Separator(frame, orient="horizontal").grid(
            row=4, column=0, columnspan=4, sticky="ew", pady=6
        )
        self.label_customer_types = ttk.Label(
            frame, text="", foreground="#333", justify="left", font=("Helvetica", 9)
        )
        self.label_customer_types.grid(
            row=5, column=0, columnspan=4, sticky="w", pady=(0, 2)
        )
        for variable in (
            self.var_reference_date,
            self.var_existing_months,
            self.var_new_fiscal_year,
        ):
            variable.trace_add("write", lambda *_: self._update_customer_type_summary())

        frame.columnconfigure(3, weight=1)

    def _build_filter_section(self, parent: tk.Widget) -> None:
        frame = section(parent, "3  Frasortering")
        frame.pack(fill="x", padx=10, pady=5)

        ttk.Label(frame, text="Ekskluder kundegrupper\n(komma-separeret):").grid(
            row=0, column=0, sticky="nw", pady=3
        )
        ttk.Entry(frame, textvariable=self.var_excluded_groups, width=45).grid(
            row=0, column=1, sticky="ew", padx=5, pady=3
        )
        help_icon(
            frame,
            "Kundegrupper der fjernes fra analysen.\n\n"
            "Match er uafhængigt af store og små bogstaver. Adskil med komma.\n\n"
            "Eksempel: FJ, INTERN, TEST KUNDE",
        ).grid(row=0, column=2, sticky="nw", padx=(0, 4), pady=3)

        ttk.Label(frame, text="Ekskluder turnover-typer\n(komma-separeret):").grid(
            row=1, column=0, sticky="nw", pady=3
        )
        ttk.Entry(frame, textvariable=self.var_excluded_turnover_types, width=45).grid(
            row=1, column=1, sticky="ew", padx=5, pady=3
        )
        help_icon(
            frame,
            "Rækker med disse værdier i kolonnen 'Turnover type' frasorteres.\n\n"
            "Match er uafhængigt af store og små bogstaver. Adskil med komma.",
        ).grid(row=1, column=2, sticky="nw", padx=(0, 4), pady=3)

        ttk.Checkbutton(
            frame, text="Fjern rækker med Turnover = 0", variable=self.var_drop_zero
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=3)
        help_icon(
            frame,
            "Frasortér rækker hvor Turnover DKK er 0 eller mangler.\n\n"
            "Anbefales slået til – nul-rækker forvrænger GM%-beregningen.",
        ).grid(row=2, column=2, sticky="w", padx=(0, 4), pady=3)

        ttk.Checkbutton(
            frame, text="Fjern døde items", variable=self.var_drop_dead_items
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=3)
        help_icon(
            frame,
            "Frasorterer items uden aktivitet inden for kundegruppens "
            "turnover-vindue.\n\n"
            "Forankringen er altid kundens seneste aktivitetsdato, uafhængigt "
            "af forankringsvalget i sektion 5.\n\n"
            "Frasorteringen sker FØR alle beregninger, så både GM% (X-aksen), "
            "turnover-vinduet (Y-aksen) og item-plottet bygger på det samme "
            "grundlag.",
        ).grid(row=3, column=2, sticky="w", padx=(0, 4), pady=3)

        ttk.Separator(frame, orient="horizontal").grid(
            row=4, column=0, columnspan=3, sticky="ew", pady=6
        )
        heading(frame, "Outlier-frasortering:").grid(
            row=5, column=0, columnspan=3, sticky="w", pady=(0, 1)
        )
        ttk.Checkbutton(
            frame,
            text="Fjern outliers",
            variable=self.var_remove_outliers,
            command=self._update_outlier_state,
        ).grid(row=6, column=0, columnspan=2, sticky="w", pady=3)
        help_icon(
            frame,
            "Frasorterer ekstreme items inden for hver kundegruppe, inden de "
            "lægges sammen til kundegruppe-niveau.\n\n"
            "Z-score = (værdi − gennemsnit) / standardafvigelse. Items med "
            "|z-score| over tærsklen fjernes.",
        ).grid(row=6, column=2, sticky="w", padx=(0, 4))

        outlier = ttk.Frame(frame)
        outlier.grid(row=7, column=0, columnspan=3, sticky="ew", padx=(15, 0), pady=(0, 3))

        self.label_outlier_std = ttk.Label(outlier, text="Tærskel (std):")
        self.label_outlier_std.grid(row=0, column=0, sticky="w", pady=3)
        self.combo_outlier_std = ttk.Combobox(
            outlier, textvariable=self.var_outlier_std, width=5,
            values=[1, 2, 3], state="readonly",
        )
        self.combo_outlier_std.grid(row=0, column=1, sticky="w", padx=5)
        self.label_outlier_hint = ttk.Label(
            outlier, text="1 = aggressiv · 2 = moderat · 3 = mild", foreground=HINT_COLOUR
        )
        self.label_outlier_hint.grid(row=0, column=2, sticky="w", padx=(0, 4))
        help_icon(
            outlier,
            "Antal standardafvigelser for outlier-detektion:\n\n"
            "  • 3  →  mild (kun ekstreme outliers fjernes)\n"
            "  • 2  →  moderat (typisk valg)\n"
            "  • 1  →  aggressiv",
        ).grid(row=0, column=3, sticky="w", padx=(0, 4))

        self.label_outlier_metric = ttk.Label(outlier, text="Metrik:")
        self.label_outlier_metric.grid(row=1, column=0, sticky="w", pady=3)
        self.combo_outlier_metric = ttk.Combobox(
            outlier, textvariable=self.var_outlier_metric, width=12,
            values=["begge", "turnover", "gm", "ingen"], state="readonly",
        )
        self.combo_outlier_metric.grid(row=1, column=1, sticky="w", padx=5)
        help_icon(
            outlier,
            "Hvilke mål der udløser frasortering:\n\n"
            "  • begge    : Turnover ELLER GM% er ekstrem\n"
            "  • turnover : kun usædvanlig høj/lav omsætning\n"
            "  • gm       : kun usædvanlig høj/lav margin\n"
            "  • ingen    : ingen filtrering",
        ).grid(row=1, column=2, sticky="w", padx=(0, 4))

        frame.columnconfigure(1, weight=1)

    def _build_split_section(self, parent: tk.Widget) -> None:
        frame = section(parent, "4  Opdeling af plots")
        frame.pack(fill="x", padx=10, pady=5)

        ttk.Checkbutton(
            frame, text="Opdel plots i sinter og støb", variable=self.var_split_item_type
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=3)
        help_icon(
            frame,
            "Når den er slået til, genereres to sæt plots: ét for sinter-emner "
            "og ét for støbe-emner.\n\n"
            "Item no. klassificeres automatisk:\n"
            "  • 60-67 + mindst 6 cifre  →  Støbe\n"
            "  • 70-77 + mindst 6 cifre  →  Sinter\n"
            "  • alt andet               →  frasorteres\n\n"
            "Manuel overrulning via suffix på item no.:\n"
            "  • -S1  →  Sinter\n"
            "  • -S2  →  Støbe\n"
            "  • -S0  →  fjern fra segmenteringen",
        ).grid(row=0, column=3, sticky="w", padx=(4, 0))

        ttk.Checkbutton(
            frame, text="Opdel plots i DK og CN", variable=self.var_geo_split
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=3)
        help_icon(
            frame,
            "Når den er slået til, genereres separate plots for DK og CN i "
            "tillæg til det samlede plot — for både sinter og støb.\n\n"
            "Kræver kolonnen 'Turnover type' i data. Hvilke turnover-typer der "
            "hører til CN henholdsvis DK sættes nedenfor.",
        ).grid(row=1, column=3, sticky="w", padx=(4, 0))

        geo_panel = ttk.Frame(frame)
        ttk.Label(geo_panel, text="CN turnover-typer (komma):").grid(
            row=0, column=0, sticky="w", pady=2
        )
        ttk.Entry(geo_panel, textvariable=self.var_cn_types, width=45).grid(
            row=0, column=1, sticky="ew", padx=5, pady=2
        )
        ttk.Label(geo_panel, text="DK turnover-typer (komma):").grid(
            row=1, column=0, sticky="w", pady=2
        )
        ttk.Entry(geo_panel, textvariable=self.var_dk_types, width=45).grid(
            row=1, column=1, sticky="ew", padx=5, pady=2
        )
        help_icon(
            geo_panel,
            "Definerer hvilke værdier i kolonnen 'Turnover type' der regnes som "
            "CN- henholdsvis DK-produktion. Adskil med komma.",
        ).grid(row=0, column=2, rowspan=2, sticky="w", padx=(4, 0))
        geo_panel.columnconfigure(1, weight=1)

        self.geo_disclosure = Disclosure(
            frame,
            "Turnover-typer pr. geografi",
            geo_panel,
            dict(row=3, column=0, columnspan=4, sticky="ew", padx=5, pady=(4, 0)),
        )
        self.geo_disclosure.button.grid(
            row=2, column=0, columnspan=3, sticky="w", pady=(8, 0)
        )
        frame.columnconfigure(2, weight=1)

    def _build_calculation_section(self, parent: tk.Widget) -> None:
        frame = section(parent, "5  Beregning")
        frame.pack(fill="x", padx=10, pady=5)

        heading(frame, "Turnover vindue (Y-aksen):").grid(
            row=0, column=0, columnspan=5, sticky="w", pady=(3, 1)
        )
        ttk.Label(frame, text="Måneder").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Spinbox(
            frame, textvariable=self.var_window_months, from_=1, to=120,
            increment=1, width=6,
        ).grid(row=1, column=1, sticky="w", padx=5)
        ttk.Label(
            frame, text="bagud fra seneste aktivitet", foreground=HINT_COLOUR
        ).grid(row=1, column=2, sticky="w", padx=(0, 5))
        help_icon(
            frame,
            "Antal måneder i det rullende turnover-vindue.\n\n"
            "Eksempel: 12 = summen af de seneste 12 måneder.\n\n"
            "Gross Margin % (X-aksen) påvirkes ikke af dette vindue.",
        ).grid(row=1, column=4, sticky="w", padx=(4, 0))

        anchor_help = (
            "  • Kunden : vinduet regnes N måneder bagud fra KUNDEGRUPPENS\n"
            "             seneste aktivitet. Alle items i én kunde dækker\n"
            "             præcis samme kalenderperiode.\n\n"
            "  • Item   : vinduet regnes N måneder bagud fra HVERT ITEMS\n"
            "             egen seneste aktivitet. To items i samme kunde\n"
            "             kan have forskudte perioder."
        )
        for row, (text, variable, values, extra) in enumerate(
            [
                (
                    "Kundegruppe plot forankring:",
                    self.var_group_anchor,
                    ["Kunden", "Item"],
                    "Standard: Kunden.",
                ),
                (
                    "Item plot forankring:",
                    self.var_item_anchor,
                    ["Item", "Kunden"],
                    "Standard: Item.",
                ),
            ],
            start=2,
        ):
            ttk.Label(frame, text=text).grid(row=row, column=0, sticky="w", pady=3)
            ttk.Combobox(
                frame, textvariable=variable, width=8, values=values, state="readonly"
            ).grid(row=row, column=1, sticky="w", padx=5)
            ttk.Label(frame, text="seneste aktivitet", foreground=HINT_COLOUR).grid(
                row=row, column=2, sticky="w", padx=(0, 5)
            )
            help_icon(frame, f"{anchor_help}\n\n{extra}").grid(
                row=row, column=4, sticky="w", padx=(4, 0)
            )

        ttk.Separator(frame, orient="horizontal").grid(
            row=4, column=0, columnspan=5, sticky="ew", pady=6
        )
        heading(frame, "Gross Margin % (X-aksen):").grid(
            row=5, column=0, columnspan=5, sticky="w", pady=(3, 1)
        )
        ttk.Checkbutton(
            frame,
            text="Vægtet GM% over seneste",
            variable=self.var_weighted_gm,
            command=self._update_gm_state,
        ).grid(row=6, column=0, sticky="w", pady=3)
        self.spin_gm_months = ttk.Spinbox(
            frame, textvariable=self.var_gm_months, from_=2, to=24, increment=1, width=5
        )
        self.spin_gm_months.grid(row=6, column=1, sticky="w", padx=5)
        ttk.Label(frame, text="måneder pr. item").grid(
            row=6, column=2, sticky="w", padx=(0, 5)
        )
        help_icon(
            frame,
            "Som standard bruges kun den seneste aktivitetsmåned pr. item til "
            "GM%-beregningen.\n\n"
            "Slås dette til, summeres de seneste N aktivitetsmåneder i stedet:\n"
            "  GM% = SUM(GP de N mdr.) / SUM(Turnover de N mdr.)\n\n"
            "Det giver et omsætningsvægtet snit der dæmper støj fra "
            "enkeltmåneder (kampagnepriser, engangsrabatter, valutaudsving).\n\n"
            "Turnover-vinduet (Y-aksen) påvirkes ikke.",
        ).grid(row=6, column=4, sticky="w", padx=(0, 4))

    def _build_axes_section(self, parent: tk.Widget) -> None:
        frame = section(parent, "6  Akser og områder")
        frame.pack(fill="x", padx=10, pady=5)

        ttk.Label(frame, text="Y-akse skala:").grid(row=0, column=0, sticky="w", pady=3)
        ttk.Combobox(
            frame, textvariable=self.var_y_scale, width=10,
            values=["linear", "log"], state="readonly",
        ).grid(row=0, column=1, sticky="w", padx=5)
        ttk.Label(frame, text="X-akse skala:").grid(row=0, column=2, sticky="w", padx=(15, 0))
        ttk.Combobox(
            frame, textvariable=self.var_x_scale, width=10,
            values=["linear", "log"], state="readonly",
        ).grid(row=0, column=3, sticky="w", padx=5)
        help_icon(
            frame,
            "Skalering af akserne.\n\n"
            "linear: direkte værdier.\n"
            "log: logaritmisk skala – nyttigt ved stor spredning i omsætning.\n\n"
            "Aksegrænser kan justeres direkte i grafen i browseren.",
        ).grid(row=0, column=4, sticky="w", padx=(4, 0))

        ttk.Separator(frame, orient="horizontal").grid(
            row=1, column=0, columnspan=6, sticky="ew", pady=6
        )

        self._build_band_panel(frame)
        self._build_zone_panel(frame)

    def _build_band_panel(self, parent: tk.Widget) -> None:
        outer = ttk.Frame(parent)
        top = ttk.Frame(outer)
        top.pack(fill="x", padx=5, pady=(3, 0))

        grid = ttk.Frame(top)
        grid.pack(side="left")
        for index, level in enumerate(CATEGORY_LEVELS):
            row, column = divmod(index, 2)
            column *= 2
            tk.Label(
                grid, text=f"{level}:", font=("Helvetica", 9, "bold"),
                foreground=LEVEL_COLOURS[level],
            ).grid(row=row, column=column, sticky="w", padx=(0 if column == 0 else 16, 2), pady=2)
            ttk.Entry(grid, textvariable=self.var_bands[level], width=25).grid(
                row=row, column=column + 1, sticky="w", padx=(0, 8), pady=2
            )

        help_icon(
            top,
            "Definerer de fire zoner på kundegruppe-plottet og hvilken kategori "
            "en kunde får i Excel.\n\n"
            "Format pr. felt: turnover_min, turnover_max, gm_min%\n\n"
            "Eksempel A: 5000000,,20  (> 5 mio. DKK, ingen øvre grænse, GM% > 20 %)\n"
            "Eksempel B: 1000000,5000000,22  (1–5 mio. DKK, GM% > 22 %)\n\n"
            "Båndene må ikke overlappe – hver omsætning skal kunne matche "
            "præcis én kategori.",
        ).pack(side="left", padx=(4, 0), anchor="n")

        ttk.Label(outer, text=BAND_FORMAT_HINT, foreground=HINT_COLOUR).pack(
            anchor="w", padx=5, pady=(0, 4)
        )

        self.band_disclosure = Disclosure(
            parent,
            "Kundekategori-grænser (A/B/C/D)",
            outer,
            dict(row=3, column=0, columnspan=6, sticky="ew", padx=5, pady=(4, 0)),
        )
        self.band_disclosure.button.grid(
            row=2, column=0, columnspan=5, sticky="w", pady=(3, 0)
        )

    def _build_zone_panel(self, parent: tk.Widget) -> None:
        panel = ttk.Frame(parent)

        for column, zone in enumerate(VOLUME_ZONE_NAMES):
            tk.Label(
                panel, text=zone, font=("Helvetica", 8, "bold"),
                foreground=ZONE_COLOURS[zone], width=22, anchor="center",
            ).grid(row=0, column=column + 1, padx=3, pady=(4, 2))
        help_icon(
            panel,
            "Definerer de farvede zoner inden for hvert niveau på item-plottet.\n\n"
            "Format pr. felt: turnover_min, turnover_max, gm_min%\n\n"
            "Eksempel: 500000,,20  (> 500.000 DKK, ingen øvre grænse, GM% > 20 %)\n\n"
            "Lad et felt stå helt tomt for at slå det pågældende område fra.",
        ).grid(row=0, column=4, sticky="w", padx=(4, 0))

        for row, level in enumerate(CATEGORY_LEVELS, start=1):
            tk.Label(
                panel, text=f"{level}:", font=("Helvetica", 9, "bold"),
                foreground=LEVEL_COLOURS[level], width=3, anchor="e",
            ).grid(row=row, column=0, sticky="e", padx=(5, 2))
            for column, zone in enumerate(VOLUME_ZONE_NAMES, start=1):
                ttk.Entry(panel, textvariable=self.var_zones[level][zone], width=22).grid(
                    row=row, column=column, padx=3, pady=2
                )

        ttk.Label(
            panel,
            text=f"{BAND_FORMAT_HINT} · tomt felt = inaktivt område",
            foreground=HINT_COLOUR,
        ).grid(row=5, column=0, columnspan=5, sticky="w", padx=5, pady=(2, 4))

        self.zone_disclosure = Disclosure(
            parent,
            "Volumenområder pr. niveau (A/B/C/D)",
            panel,
            dict(row=5, column=0, columnspan=6, sticky="ew", padx=5, pady=(4, 0)),
        )
        self.zone_disclosure.button.grid(
            row=4, column=0, columnspan=5, sticky="w", pady=(8, 0)
        )

    def _build_output_section(self, parent: tk.Widget) -> None:
        frame = section(parent, "7  Output")
        frame.pack(fill="x", padx=10, pady=5)

        ttk.Label(frame, text="Excel-detaljeringsgrad:").grid(
            row=0, column=0, sticky="w", pady=3
        )
        ttk.Combobox(
            frame, textvariable=self.var_excel_detail, width=12,
            values=["minimal", "kompakt", "fuld"], state="readonly",
        ).grid(row=0, column=1, sticky="w", padx=5)
        help_icon(
            frame,
            "Detaljeringsgrad i Excel-rapporten:\n\n"
            "  • fuld    : alle kolonner, inkl. gennemsnitstal pr. kundegruppe\n"
            "  • kompakt : de samlede tal pr. kundegruppe (anbefalet)\n"
            "  • minimal : kun det absolut nødvendige",
        ).grid(row=0, column=2, sticky="w", padx=(4, 4), pady=3)

    def _build_run_section(self, parent: tk.Widget) -> None:
        frame = ttk.Frame(parent, padding=(10, 8))
        frame.pack(fill="x")
        self.run_button = ttk.Button(
            frame, text="▶  Kør analyse", style="Run.TButton", command=self.run
        )
        self.run_button.pack(side="left", padx=(0, 10))
        self.status_label = ttk.Label(frame, text="")
        self.status_label.pack(side="left")

    def _build_log_section(self, parent: tk.Widget) -> None:
        frame = section(parent, "Log")
        frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.log_view = scrolledtext.ScrolledText(
            frame, height=12, state="disabled", font=("Courier", 9), wrap="word"
        )
        self.log_view.pack(fill="both", expand=True)
        ttk.Button(frame, text="Ryd log", command=self.clear_log).pack(
            anchor="e", pady=(4, 0)
        )

    # -- Konfiguration ind og ud ---------------------------------------------

    def restore_defaults(self) -> None:
        self._load_config(Config())

    def _load_config(self, cfg: Config) -> None:
        self.var_input_path.set(cfg.input_path)
        self.var_output_dir.set(cfg.output_dir or "")
        self.var_basename.set(cfg.output_basename)

        self.var_reference_date.set(cfg.reference_date)
        self.var_existing_months.set(cfg.existing_customer_months)
        self.var_new_fiscal_year.set(cfg.new_fiscal_year)

        self.var_excluded_groups.set(", ".join(cfg.excluded_customer_groups))
        self.var_excluded_turnover_types.set(", ".join(cfg.excluded_turnover_types))
        self.var_drop_zero.set(cfg.drop_zero_turnover)
        self.var_drop_dead_items.set(cfg.drop_dead_items)

        self.var_remove_outliers.set(cfg.remove_outliers)
        self.var_outlier_std.set(int(cfg.outlier_std_threshold))
        self.var_outlier_metric.set(cfg.outlier_metric)

        self.var_split_item_type.set(cfg.split_by_item_type)
        self.var_geo_split.set(cfg.geo_cn or cfg.geo_dk)
        self.var_cn_types.set(", ".join(cfg.cn_turnover_types))
        self.var_dk_types.set(", ".join(cfg.dk_turnover_types))

        self.var_window_months.set(cfg.turnover_window_months)
        self.var_group_anchor.set(ANCHOR_LABELS[cfg.group_plot_anchor])
        self.var_item_anchor.set(ANCHOR_LABELS[cfg.item_plot_anchor])
        self.var_weighted_gm.set(cfg.gm_months > 1)
        self.var_gm_months.set(cfg.gm_months if cfg.gm_months > 1 else 3)

        self.var_y_scale.set(cfg.y_scale)
        self.var_x_scale.set(cfg.x_scale)
        self.var_colour_by.set(cfg.colour_by)
        self.var_excel_detail.set(cfg.excel_detail)

        for level, variable in self.var_bands.items():
            band = cfg.category_bands.get(level)
            variable.set(format_band(band) if band else "")
        for level, zones in self.var_zones.items():
            configured = cfg.volume_zones.get(level, {})
            for zone, variable in zones.items():
                band = configured.get(zone)
                variable.set(format_band(band) if band else "")

        self._update_gm_state()
        self._update_outlier_state()
        self._update_customer_type_summary()

    def _build_config(self) -> Config:
        """Læser skærmen til et ``Config``. Rejser ValueError ved ugyldige felter."""
        defaults = Config()
        geo_split = self.var_geo_split.get()

        bands = {
            level: parse_band(variable.get(), f"Kundekategori {level}")
            for level, variable in self.var_bands.items()
        }
        zones: dict[str, dict[str, Band]] = {}
        for level, level_zones in self.var_zones.items():
            parsed = {}
            for zone, variable in level_zones.items():
                text = variable.get().strip()
                if text:  # tomt felt slår området fra
                    parsed[zone] = parse_band(text, f"Volumenområde {level} – {zone}")
            zones[level] = parsed

        return Config(
            input_path=self.var_input_path.get().strip(),
            reference_date=self.var_reference_date.get().strip(),
            existing_customer_months=int(self.var_existing_months.get()),
            new_fiscal_year=self.var_new_fiscal_year.get().strip(),
            excluded_customer_groups=split_list(self.var_excluded_groups.get()),
            excluded_turnover_types=split_list(self.var_excluded_turnover_types.get()),
            drop_zero_turnover=self.var_drop_zero.get(),
            drop_dead_items=self.var_drop_dead_items.get(),
            remove_outliers=self.var_remove_outliers.get(),
            outlier_std_threshold=float(self.var_outlier_std.get()),
            outlier_metric=self.var_outlier_metric.get(),
            split_by_item_type=self.var_split_item_type.get(),
            geo_combined=True,
            geo_cn=geo_split,
            geo_dk=geo_split,
            cn_turnover_types=split_list(self.var_cn_types.get())
            or defaults.cn_turnover_types,
            dk_turnover_types=split_list(self.var_dk_types.get())
            or defaults.dk_turnover_types,
            turnover_window_months=int(self.var_window_months.get()),
            group_plot_anchor=ANCHOR_VALUES[self.var_group_anchor.get()],
            item_plot_anchor=ANCHOR_VALUES[self.var_item_anchor.get()],
            gm_months=int(self.var_gm_months.get()) if self.var_weighted_gm.get() else 1,
            colour_by=self.var_colour_by.get(),
            y_scale=self.var_y_scale.get(),
            x_scale=self.var_x_scale.get(),
            category_bands=bands,
            volume_zones=zones,
            output_basename=self.var_basename.get().strip() or "kunde_segmentering",
            output_dir=self.var_output_dir.get().strip() or None,
            excel_detail=self.var_excel_detail.get(),
        )

    # -- Tilstand -------------------------------------------------------------

    def _update_gm_state(self) -> None:
        enabled = self.var_weighted_gm.get()
        set_enabled(enabled, self.spin_gm_months)
        if enabled and self.var_gm_months.get() < 2:
            self.var_gm_months.set(3)

    def _update_outlier_state(self) -> None:
        enabled = self.var_remove_outliers.get()
        set_enabled(
            enabled, self.combo_outlier_std, self.combo_outlier_metric, readonly=True
        )
        set_enabled(
            enabled, self.label_outlier_std, self.label_outlier_metric
        )
        self.label_outlier_hint.configure(
            foreground=HINT_COLOUR if enabled else "#aaa"
        )

    def _update_customer_type_summary(self) -> None:
        """Skriver en letlæselig forklaring af de tre kundetyper ud fra felterne."""
        reference = self.var_reference_date.get().strip() or "(dags dato)"
        try:
            months = int(self.var_existing_months.get())
        except (tk.TclError, ValueError):
            months = 0
        fiscal_year = self.var_new_fiscal_year.get().strip()

        new_line = (
            f"Ny:           aktivitet KUN i 'Ny-regnskabsår' ({fiscal_year}) "
            "og ingen tidligere historik"
            if fiscal_year
            else "Ny:           aktivitet efter 'Dags dato' og ingen tidligere historik"
        )
        self.label_customer_types.configure(
            text=(
                "Eksisterende: seneste aktivitet inden for 'Eksisterende kunde "
                f"vindue' ({months} måneder bagud fra 'Dags dato' {reference})\n"
                f"{new_line}\n"
                "Tidligere:    al aktivitet ligger uden for begge ovenstående vinduer"
            )
        )

    # -- Fil-dialoger ---------------------------------------------------------

    def _choose_input_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Vælg input-Excel-fil",
            filetypes=[
                ("Excel-filer", "*.xlsx *.xlsm *.xls"),
                ("Excel med makroer", "*.xlsm"),
                ("Alle filer", "*.*"),
            ],
        )
        if path:
            self.var_input_path.set(path)

    def _choose_output_dir(self) -> None:
        folder = filedialog.askdirectory(title="Vælg output-mappe")
        if folder:
            self.var_output_dir.set(folder)

    # -- Kørsel ---------------------------------------------------------------

    def run(self) -> None:
        try:
            cfg = self._build_config()
            cfg.validate()
        except (ValueError, tk.TclError) as exc:
            messagebox.showerror("Ugyldig indstilling", str(exc))
            return

        if not cfg.input_path or not os.path.isfile(cfg.input_path):
            messagebox.showerror(
                "Fil ikke fundet",
                f"Excel-filen blev ikke fundet:\n{cfg.input_path}",
            )
            return

        self.run_button.configure(state="disabled")
        self.status_label.configure(text="⏳ Analyserer…")
        self.log("=" * 50)
        self.log(f"Starter analyse: {cfg.input_path}")

        threading.Thread(target=self._worker, args=(cfg,), daemon=True).start()
        self._pump_events()

    def _worker(self, cfg: Config) -> None:
        """
        Kører analysen i en baggrundstråd.

        Tråden rører aldrig et widget. Den lægger udelukkende beskeder i køen,
        som hovedtråden tømmer i ``_pump_events`` — Tk må kun betjenes fra den
        tråd der ejer vinduet.
        """
        try:
            run_analysis(cfg, log=self.log)
        except Exception as exc:
            self.log(traceback.format_exc())
            self._events.put(("done", describe_failure(exc)))
        else:
            self._events.put(("done", None))

    def _pump_events(self) -> None:
        """
        Tømmer beskedkøen og planlægger sig selv igen indtil kørslen er slut.

        Kaldes kun fra hovedtråden, så alle widget-opdateringer sker der.
        """
        finished = False
        error: str | None = None
        try:
            while True:
                kind, payload = self._events.get_nowait()
                if kind == "log":
                    self._append_log(payload)
                elif kind == "done":
                    finished = True
                    error = payload

        except queue.Empty:
            pass

        if finished:
            self._finish(error)
        else:
            self.after(self.POLL_INTERVAL_MS, self._pump_events)

    def _finish(self, error: str | None) -> None:
        self.run_button.configure(state="normal")
        if error is None:
            self.status_label.configure(text="✅ Analyse færdig")
            self._append_log("Analyse afsluttet uden fejl.")
        else:
            self.status_label.configure(text="❌ Analysen fejlede")
            messagebox.showerror("Analysen kunne ikke gennemføres", error)

    # -- Log ------------------------------------------------------------------

    def log(self, message: str) -> None:
        """
        Modtager en linje fra beregningen. Må kaldes fra enhver tråd.

        Beskeden lægges i kø frem for at blive skrevet direkte, fordi Tk kun
        må betjenes fra hovedtråden.
        """
        self._events.put(("log", message))

    def _append_log(self, message: str) -> None:
        self.log_view.configure(state="normal")
        self.log_view.insert("end", f"{message}\n")
        self.log_view.see("end")
        self.log_view.configure(state="disabled")

    def clear_log(self) -> None:
        self.log_view.configure(state="normal")
        self.log_view.delete("1.0", "end")
        self.log_view.configure(state="disabled")


def main() -> None:
    SegmenteringApp().mainloop()

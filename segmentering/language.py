"""
Teksterne i plottene, på dansk og engelsk.

Kun graferne oversættes. Excel-rapporten, brugerfladen og logudskriften
bliver på dansk — de bruges af os selv, mens graferne er dem der bliver sendt
videre.

Alt hvad brugeren kan læse i en graf står her. Beregningen rører ikke disse
tekster: den arbejder på de danske værdier i data (``Eksisterende``,
``Stor volumen`` …), og oversættelsen sker først når figuren tegnes. Derfor
kan de to sprogudgaver bygges af nøjagtig det samme resultat, og et
filternavn i den engelske graf peger stadig på den samme række i data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True)
class Texts:
    """Alle brugervendte tekster i én graf."""

    code: str

    # Titler og akser
    group_title: str
    item_title: str
    x_axis: str
    group_y_axis: str  # {months}
    item_y_axis: str  # {months}

    # Undertitel
    existing_customers: str  # {start} {end} {months}
    turnover_window: str  # {months}
    edge_is_segment: str
    outliers_removed: str  # {threshold}

    # Legende
    legend_title: str
    category_group: str  # {category}
    no_category: str

    # Knaprækker
    row_customer_type: str
    row_category: str
    row_kam: str
    row_segment: str
    row_level: str
    level_button: str  # {level}
    reset_button: str

    # Farveforklaring
    key_customer_type: str
    key_segment: str

    # Hover
    hover_customer_group: str
    hover_customer_type: str
    hover_category: str
    hover_segment: str
    hover_kam: str
    hover_gm: str
    hover_turnover: str
    hover_last_sold: str

    # Søgefeltet på item-plottet
    search_label: str
    search_placeholder: str
    search_hint: str
    search_found: str  # {count}
    search_found_one: str
    search_none: str
    search_clear: str

    #: Danske værdier i data -> det der vises. Værdier uden en oversættelse
    #: vises som de er, så et KAM-navn eller en branche aldrig bliver rørt.
    customer_types: Mapping[str, str] = field(default_factory=dict)
    volume_zones: Mapping[str, str] = field(default_factory=dict)
    segment_labels: Mapping[str, str] = field(default_factory=dict)

    def customer_type(self, value: object) -> str:
        return self.customer_types.get(str(value), str(value))

    def volume_zone(self, value: object) -> str:
        return self.volume_zones.get(str(value), str(value))

    def segment_label(self, value: str) -> str:
        """
        Oversætter udsnittets navn, fx "Sinter - kun eksisterende kunder".

        Navnet sættes sammen af flere led i pipelinen, så hvert kendt led
        oversættes for sig og resten står uændret.
        """
        text = value
        for danish, english in self.segment_labels.items():
            text = text.replace(danish, english)
        return text


DANISH = Texts(
    code="da",
    group_title="Kundesegmentering – Kundegruppe",
    item_title="Kundesegmentering – Item scatter",
    x_axis="Gross Margin (%)",
    group_y_axis="Samlet Turnover DKK ({months} mdr. vindue)",
    item_y_axis="Turnover DKK – item niveau ({months} mdr. vindue)",
    existing_customers="Eksisterende kunder: {start} – {end} ({months} mdr.)",
    turnover_window="Turnover-vindue: rullende {months} mdr. fra seneste aktivitet",
    edge_is_segment="Kant = Industry segment",
    outliers_removed="Outliers fjernet (±{threshold} std)",
    legend_title="Kunder (klik = vis/skjul enkelt kunde · knap = hel blok)",
    category_group="Kategori {category}",
    no_category="Ingen kategori",
    row_customer_type="Vis/skjul kundetype:",
    row_category="Vis/skjul kategori:",
    row_kam="Vis/skjul KAM:",
    row_segment="Fremhæv branche:",
    row_level="Volumenkrav:",
    level_button="Krav {level}",
    reset_button="↺  Nulstil alle filtre",
    key_customer_type="Farve = kundetype:",
    key_segment="Farve = Industry segment:",
    hover_customer_group="Kundegruppe",
    hover_customer_type="Kundetype",
    hover_category="Kategori",
    hover_segment="Industry segment",
    hover_kam="KAM",
    hover_gm="GM%",
    hover_turnover="Turnover",
    hover_last_sold="Seneste solgt",
    search_label="Søg varenummer:",
    search_placeholder="fx 701234, 712345",
    search_hint="flere adskilles med komma eller mellemrum",
    search_found="{count} varer fremhævet",
    search_found_one="1 vare fremhævet",
    search_none="ingen varer matcher",
    search_clear="Ryd",
    customer_types={},
    volume_zones={},
    segment_labels={},
)

ENGLISH = Texts(
    code="en",
    group_title="Customer segmentation – Customer group",
    item_title="Customer segmentation – Item scatter",
    x_axis="Gross Margin (%)",
    group_y_axis="Total Turnover DKK ({months} month window)",
    item_y_axis="Turnover DKK – item level ({months} month window)",
    existing_customers="Existing customers: {start} – {end} ({months} months)",
    turnover_window="Turnover window: rolling {months} months from latest activity",
    edge_is_segment="Outline = Industry segment",
    outliers_removed="Outliers removed (±{threshold} std)",
    legend_title="Customers (click = show/hide one · button = whole block)",
    category_group="Category {category}",
    no_category="No category",
    row_customer_type="Show/hide customer type:",
    row_category="Show/hide category:",
    row_kam="Show/hide KAM:",
    row_segment="Highlight industry:",
    row_level="Volume requirement:",
    level_button="Level {level}",
    reset_button="↺  Reset all filters",
    key_customer_type="Colour = customer type:",
    key_segment="Colour = Industry segment:",
    hover_customer_group="Customer group",
    hover_customer_type="Customer type",
    hover_category="Category",
    hover_segment="Industry segment",
    hover_kam="KAM",
    hover_gm="GM%",
    hover_turnover="Turnover",
    hover_last_sold="Last sold",
    search_label="Search item no.:",
    search_placeholder="e.g. 701234, 712345",
    search_hint="separate several with a comma or a space",
    search_found="{count} items highlighted",
    search_found_one="1 item highlighted",
    search_none="no items match",
    search_clear="Clear",
    customer_types={
        "Eksisterende": "Existing",
        "Ny": "New",
        "Genopstået": "Revived",
        "Tidligere": "Former",
        "Ukendt": "Unknown",
    },
    volume_zones={
        "Stor volumen": "High volume",
        "Mellem volumen": "Medium volume",
        "Lille volumen": "Low volume",
    },
    segment_labels={
        "Alle emner": "All item types",
        "Sinter": "Sinter",
        "Støbe": "Cast",
        "kun eksisterende kunder": "existing customers only",
        "Outliers fjernet": "Outliers removed",
    },
)

#: Sprogene programmet kan skrive grafer på.
LANGUAGES: dict[str, Texts] = {DANISH.code: DANISH, ENGLISH.code: ENGLISH}

#: Mappen den engelske udgave lægges i, ved siden af de danske plots.
ENGLISH_SUBFOLDER = "English"

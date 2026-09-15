"""
Interaktive Plotly-scatterplots.

Der bygges to slags plots:

* **Kundegruppe-plottet** – ét punkt pr. kundegruppe, med A/B/C/D-zonerne
  tegnet som baggrund.
* **Item-plottet** – ét punkt pr. item no., med tre volumen-områder tegnet for
  ét kategori-niveau ad gangen. Niveauet skiftes med knapper under plottet.

Begge gemmes som selvstændige HTML-filer der kan åbnes i en browser.
"""

from __future__ import annotations

from typing import Callable, Mapping, Sequence

import numpy as np
import pandas as pd

from .classify import category_sort_key, classify_customer_category
from .config import (
    CATEGORY_COLOURS,
    CUSTOMER_TYPE_COLOURS,
    VOLUME_ZONE_COLOURS,
    Band,
    Config,
)
from .dataio import GEO, GROUP, INDUSTRY_SEGMENT, ITEM_NO, KAM, ReferenceDates
from .metrics import ITEM_GM, WINDOW_GROUP, WINDOW_ITEM, sort_kams

try:  # Plotly er en hård afhængighed for plots, men ikke for beregningerne.
    import plotly.colors as plotly_colours
    import plotly.graph_objects as go
    import plotly.io as pio

    PLOTLY_AVAILABLE = True
except ImportError:  # pragma: no cover - afhænger af miljøet
    PLOTLY_AVAILABLE = False

Log = Callable[[str], None]

# Zonerne tegnes vilkårligt store og klippes af Plotlys aksegrænser.
X_MAX_ZONE = 1000
Y_MAX_ZONE = 1e12

# Kantbredder på kundegruppe-plottet. Basisbredden gør Industry_segment-farven
# synlig; knapperne under plottet fremhæver ét segment ad gangen.
EDGE_WIDTH_BASE = 2.0
EDGE_WIDTH_HIGHLIGHT = 4.0
EDGE_WIDTH_PLAIN = 0.5
EDGE_COLOUR_PLAIN = "#333333"

CUSTOMER_TYPE_ORDER = ["Eksisterende", "Ny", "Tidligere"]

GRID_COLOUR = "rgba(200,200,200,0.4)"
PLOT_WIDTH = 1200
PLOT_HEIGHT = 750

# Knaprækker under plottet. Bredden af en knap kendes først når browseren har
# tegnet den, så den anslås ud fra etikettens længde — bevidst en anelse for
# rundhåndet, så knapper hellere står lidt spredt end oven i hinanden.
BUTTON_CHAR_PX = 6.5
BUTTON_PADDING_PX = 30
BUTTON_SPACING_PX = 10
# Knappernes x-koordinat er i "paper"-enheder, der spænder over PLOTOMRÅDET —
# ikke hele figuren. Området er smallere end figuren og skrumper yderligere
# når legenden er bred (item-plottet viser kundenavne). Bredden kendes først
# ved tegning, så her regnes med et bevidst lavt skøn: så bliver knapperne
# hellere spredt for godt ud og ombrudt for tidligt end lagt oven i hinanden.
BUTTON_AREA_PX = 640
BUTTON_ROW_GAP = 0.08  # lodret afstand mellem knaprækker (paper-koordinater)
BUTTON_ROW_MARGIN_PX = 45  # plads der skal reserveres pr. knaprække

# Binder alle knapper i en menu sig til ÉN egenskab, opfatter Plotly det som en
# "simpel binding" og sætter en overvåger på egenskaben. Overvågeren retter
# menuens aktiv-markering hver gang egenskaben ændrer sig — også når det var en
# anden knap der ændrede den, hvilket både fik knapper til at lyse op af sig
# selv og til at hoppe et par pixels til siden ved den ekstra gentegning.
#
# Ved at sætte én egenskab mere bliver bindingen ikke længere simpel, og
# overvågeren droppes. Værdien er den samme som sporene allerede har, så den
# ændrer intet visuelt — den er der kun for at bryde bindingen.
#
# Filterknapperne bruger nu ``method="skip"`` og binder sig slet ikke, så det
# er kun fremhæv-knapperne der har brug for vagten.
TOGGLE_GUARD = ("marker.opacity", 1)


def _danish_thousands(value: float) -> str:
    return f"{value:,.0f}".replace(",", ".")


def _qualitative_palette() -> list[str]:
    return (
        plotly_colours.qualitative.Plotly
        + plotly_colours.qualitative.D3
        + plotly_colours.qualitative.Light24
    )


#: De rækker af filterknapper begge grafer deler. Hver post er
#: (kolonne i data, overskrift, dimensionsnavn til scriptet).
SHARED_FILTER_ROWS = [
    ("_emnetype", "Vis/skjul emne-type:", "emnetype"),
    (GEO, "Vis/skjul produktion:", "geografi"),
    (KAM, "Vis/skjul KAM:", "kam"),
]

ITEM_TYPE_ORDER = ["Sinter", "Støb", "Andet"]


def _dimension_values(data: pd.DataFrame, column: str) -> list[object]:
    """Værdierne i en kolonne, i en fast og læsbar rækkefølge."""
    if column not in data.columns:
        return []
    values = data[column].dropna().unique().tolist()
    if column == KAM:
        return sort_kams(values)
    if column == "_emnetype":
        return [v for v in ITEM_TYPE_ORDER if v in values]
    return sorted(values, key=lambda v: (v == "Øvrig", str(v)))


def _colour_map(values: Sequence[object]) -> dict[object, str]:
    palette = _qualitative_palette()
    return {value: palette[i % len(palette)] for i, value in enumerate(values)}


# --- Zoner og referencelinjer ------------------------------------------------


def band_shapes(
    bands: Mapping[str, Band],
    colours: Mapping[str, str],
    fill_opacity: float,
    label_zones: bool,
) -> tuple[list[dict], list[dict]]:
    """
    Bygger Plotly-shapes og -annotationer for et sæt bånd.

    Hvert bånd bliver til et farvet rektangel, og der lægges gennemgående grå
    stiplede referencelinjer ved hver GM%-grænse (lodret) og hver
    turnover-grænse (vandret).

    Resultatet er rene dicts, så de både kan sættes ved opbygningen af figuren
    og skiftes ud senere via en ``relayout``-knap.
    """
    shapes: list[dict] = []
    annotations: list[dict] = []

    for name, band in bands.items():
        colour = colours.get(name, "#aaaaaa")
        x0 = band.gm_min * 100
        y0 = band.turnover_min
        y1 = band.turnover_max if band.turnover_max is not None else Y_MAX_ZONE
        shapes.append(
            dict(
                type="rect",
                xref="x",
                yref="y",
                x0=x0,
                y0=y0,
                x1=X_MAX_ZONE,
                y1=y1,
                fillcolor=colour,
                opacity=fill_opacity,
                line=dict(width=0),
                layer="below",
            )
        )
        if label_zones:
            annotations.append(
                dict(
                    x=x0,
                    y=y0,
                    xref="x",
                    yref="y",
                    text=str(name),
                    showarrow=False,
                    xanchor="left",
                    yanchor="bottom",
                    font=dict(size=11, color=colour),
                    bgcolor="rgba(255,255,255,0.6)",
                )
            )

    for gm_min in sorted({band.gm_min for band in bands.values()}):
        x_value = gm_min * 100
        shapes.append(
            dict(
                type="line",
                xref="x",
                yref="paper",
                x0=x_value,
                x1=x_value,
                y0=0,
                y1=1,
                line=dict(color="grey", width=1, dash="dash"),
                opacity=0.6,
                layer="below",
            )
        )
        annotations.append(
            dict(
                x=x_value,
                y=1.0,
                xref="x",
                yref="paper",
                text=f"{x_value:g}%",
                showarrow=False,
                xanchor="center",
                yanchor="bottom",
                font=dict(size=10, color="grey"),
            )
        )

    turnover_levels = sorted(
        {
            value
            for band in bands.values()
            for value in (band.turnover_min, band.turnover_max)
            if value is not None and value > 0
        }
    )
    for y_value in turnover_levels:
        shapes.append(
            dict(
                type="line",
                xref="paper",
                yref="y",
                x0=0,
                x1=1,
                y0=y_value,
                y1=y_value,
                line=dict(color="grey", width=1, dash="dash"),
                opacity=0.6,
                layer="below",
            )
        )
        annotations.append(
            dict(
                x=1.0,
                y=y_value,
                xref="paper",
                yref="y",
                text=_danish_thousands(y_value),
                showarrow=False,
                xanchor="right",
                yanchor="bottom",
                font=dict(size=10, color="grey"),
            )
        )

    return shapes, annotations


def _button_width(label: object) -> float:
    """Anslået bredde af en knap i paper-koordinater."""
    return (len(str(label)) * BUTTON_CHAR_PX + BUTTON_PADDING_PX) / BUTTON_AREA_PX


def _row_label(text: str, y: float) -> dict:
    """Overskrift til venstre for en knaprække, så rækkerne kan skelnes."""
    return dict(
        x=0.0,
        y=y,
        xref="paper",
        yref="paper",
        text=text,
        showarrow=False,
        xanchor="left",
        yanchor="top",
        font=dict(size=10, color="#555555"),
        yshift=-7,
    )


def _label_width(text: str) -> float:
    return (len(text) * BUTTON_CHAR_PX + 16) / BUTTON_AREA_PX


def toggle_buttons(
    values: Sequence[object], trace_values: Sequence[object]
) -> list[dict]:
    """
    Bygger én filterknap pr. værdi.

    Knapperne ændrer ikke selv noget: de bruger ``method="skip"``, så Plotly
    kun holder styr på om knappen er trykket ned. Synligheden beregnes bagefter
    af scriptet i :func:`filter_script`, som fællesmængden af alle rækker.

    Grunden er, at en knap ellers ikke kan andet end at sætte en fast værdi.
    Med ``visible=True`` på hver sin knap ville "vis Tidligere igen" tænde for
    ALLE tidligere kunder — også dem en KAM-knap havde slået fra. Ved at lade
    knapperne beskrive et filter og regne synligheden ud til sidst, kan
    rækkerne begrænse hinanden i stedet for at overskrive hinanden.

    Værdier uden spor får ingen knap.
    """
    present = [
        value for value in values if any(other == value for other in trace_values)
    ]
    return [
        dict(label=str(value), method="skip", args=[{}], args2=[{}])
        for value in present
    ]


#: JavaScript der lægges ind i den færdige HTML-fil. Det lytter efter klik på
#: filterknapperne og sætter synligheden ud fra ALLE rækker under ét.
_FILTER_SCRIPT = """
(function () {
  var gd = document.getElementById('{plot_id}');
  if (!gd) { return; }
  var dimensionByMenu = ((gd.layout && gd.layout.meta) || {}).filters || {};
  if (!Object.keys(dimensionByMenu).length) { return; }

  function apply() {
    var menus = (gd._fullLayout && gd._fullLayout.updatemenus)
                || (gd.layout && gd.layout.updatemenus) || [];
    // Saml de fravalgte værdier pr. række (kundetype, kategori, KAM ...).
    var deselected = {};
    Object.keys(dimensionByMenu).forEach(function (index) {
      var menu = menus[Number(index)];
      if (!menu || !menu.buttons || !menu.buttons.length) { return; }
      var dimension = dimensionByMenu[index];
      if (!deselected[dimension]) { deselected[dimension] = []; }
      if (menu.active === 0) {
        deselected[dimension].push(String(menu.buttons[0].label));
      }
    });
    // Et punkt vises kun hvis det slipper gennem hver eneste række.
    var visible = gd.data.map(function (trace) {
      var values = trace.meta || {};
      for (var dimension in deselected) {
        if (deselected[dimension].indexOf(String(values[dimension])) !== -1) {
          return 'legendonly';
        }
      }
      return true;
    });
    Plotly.restyle(gd, {visible: visible});
  }

  gd.on('plotly_buttonclicked', function () { setTimeout(apply, 0); });
})();
"""


def filter_script(fig: "go.Figure") -> str | None:
    """Returnerer filter-scriptet hvis figuren har filterknapper."""
    meta = fig.layout.meta or {}
    return _FILTER_SCRIPT if meta.get("filters") else None


def stack_button_rows(
    groups: Sequence[tuple[str, str | None, list[dict]]], y_start: float
) -> tuple[list[dict], list[dict], int, list[str | None]]:
    """
    Lægger flere navngivne knapgrupper under hinanden.

    Hver gruppe er ``(overskrift, filterrække, knapper)``. Filterrækken er
    navnet på den dimension knapperne filtrerer på — ``None`` for rækker der
    ikke er filtre, fx "Fremhæv branche".

    Returnerer menuerne, rækkeoverskrifterne, det samlede antal rækker og en
    liste med filterrækken for hver menu, så kalderen kan fortælle scriptet
    hvilken menu der hører til hvilken dimension.
    """
    menus: list[dict] = []
    annotations: list[dict] = []
    dimensions: list[str | None] = []
    y = y_start
    total_rows = 0
    for label, dimension, buttons in groups:
        if not buttons:
            continue
        row_menus, rows = flow_button_menus(
            buttons, y_start=y, x_offset=_label_width(label)
        )
        menus.extend(row_menus)
        dimensions.extend([dimension] * len(row_menus))
        annotations.append(_row_label(label, y))
        y -= rows * BUTTON_ROW_GAP
        total_rows += rows
    return menus, annotations, total_rows, dimensions


def filter_metadata(dimensions: Sequence[str | None]) -> dict:
    """
    Oversætter menu-rækkefølgen til det opslag scriptet skal bruge.

    Nøglen er menuens plads i ``updatemenus``; værdien er dimensionen.
    Menuer uden dimension udelades.
    """
    return {
        "filters": {
            str(index): dimension
            for index, dimension in enumerate(dimensions)
            if dimension
        }
    }


def flow_button_menus(
    buttons: Sequence[dict], y_start: float, x_offset: float = 0.0
) -> tuple[list[dict], int]:
    """
    Placerer én-knaps-menuer på rad og bryder til en ny række når rækken er fuld.

    Hver knap får sin egen menu, fordi Plotly kun kan holde ét aktivt valg pr.
    menu — og her skal flere kunne være trykket ned samtidig. Til gengæld skal
    placeringen så regnes ud manuelt. Tidligere blev x-positionen lagt sammen
    og klippet ved 0.95, hvilket stablede alle knapper oven på hinanden så
    snart rækken var fuld. Nu ombrydes der i stedet.

    Returnerer menuerne og hvor mange rækker de fylder, så kalderen kan
    reservere plads under plottet.
    """
    menus: list[dict] = []
    spacing = BUTTON_SPACING_PX / BUTTON_AREA_PX
    x = x_offset
    rows = 1
    for button in buttons:
        width = _button_width(button.get("label", ""))
        if x > x_offset and x + width > 1.0:
            x = x_offset
            rows += 1
        menus.append(
            dict(
                type="buttons",
                direction="right",
                showactive=True,
                active=-1,
                x=x,
                xanchor="left",
                y=y_start - (rows - 1) * BUTTON_ROW_GAP,
                yanchor="top",
                pad={"r": 4, "t": 4},
                buttons=[button],
            )
        )
        x += width + spacing
    return menus, rows


def category_zone_shapes(cfg: Config) -> tuple[list[dict], list[dict]]:
    return band_shapes(
        cfg.category_bands, CATEGORY_COLOURS, fill_opacity=0.08, label_zones=False
    )


def volume_zone_shapes(level: str, cfg: Config) -> tuple[list[dict], list[dict]]:
    return band_shapes(
        cfg.volume_zones.get(level, {}),
        VOLUME_ZONE_COLOURS,
        fill_opacity=0.10,
        label_zones=True,
    )


# --- Fælles layout -----------------------------------------------------------


def _subtitle(cfg: Config, dates: ReferenceDates, extra: str) -> str:
    parts = [
        f"Eksisterende kunder: {dates.window_start:%m-%Y} – {dates.today:%m-%Y} "
        f"({cfg.existing_customer_months} mdr.)",
        f"Turnover-vindue: rullende {cfg.turnover_window_months} mdr. "
        "fra seneste aktivitet",
    ]
    if extra:
        parts.append(extra)
    return "  |  ".join(parts)


def axis_range(values: Sequence[float], log: bool, pad: float = 0.06) -> list[float] | None:
    """
    Beregner et akseinterval ud fra de faktiske værdier.

    Uden et eksplicit interval lader Plotly zonerne bestemme udsnittet, og
    zonerne strækker sig med vilje langt uden for data (``X_MAX_ZONE`` og
    ``Y_MAX_ZONE``) for at nå plottets kant. Så bliver punkterne presset
    sammen i et hjørne. Ved at sætte intervallet efter data bliver zonerne
    beskåret i stedet — de fylder stadig baggrunden, men styrer ikke synsfeltet.

    På en logaritmisk akse angives intervallet i tierpotenser, og nul og
    negative værdier må udelades: ``log10(0)`` er minus uendelig og ville
    trække aksen ned i det meningsløse.
    """
    numbers = [
        float(v) for v in values if v is not None and not pd.isna(v) and np.isfinite(v)
    ]
    if log:
        numbers = [v for v in numbers if v > 0]
    if not numbers:
        return None

    low, high = min(numbers), max(numbers)
    if log:
        low, high = np.log10(low), np.log10(high)
    span = high - low
    if span <= 0:  # ét enkelt punkt – giv det lidt luft omkring sig
        span = abs(high) * 0.5 or 1.0
    margin = span * pad
    return [low - margin, high + margin]


def _axes(
    cfg: Config,
    y_title: str,
    x_values: Sequence[float] = (),
    y_values: Sequence[float] = (),
) -> dict:
    x_axis = dict(
        title="Gross Margin (%)",
        type=cfg.x_scale,
        gridcolor=GRID_COLOUR,
    )
    y_axis = dict(
        title=y_title,
        type=cfg.y_scale,
        tickformat=",.0f",
        gridcolor=GRID_COLOUR,
    )
    x_range = axis_range(x_values, log=cfg.x_scale == "log")
    y_range = axis_range(y_values, log=cfg.y_scale == "log")
    if x_range:
        x_axis["range"] = x_range
    if y_range:
        y_axis["range"] = y_range
    return dict(xaxis=x_axis, yaxis=y_axis)


# --- Kundegruppe-plot --------------------------------------------------------


def group_scatter(
    per_group: pd.DataFrame,
    cfg: Config,
    dates: ReferenceDates,
    title_suffix: str = "",
) -> "go.Figure":
    """
    Tegner kundegruppe-plottet: ét punkt pr. kundegruppe.

    Der laves ét spor pr. kunde, så legenden til højre kan liste kunderne ved
    navn under deres kundekategori — ligesom på item-plottet. Dermed kan en
    enkelt kunde slås fra ved at klikke i legenden.

    Farven følger kundetypen (Eksisterende / Ny / Tidligere), eller
    Industry_segment hvis ``colour_by="industry_segment"``. Kundetype,
    kategori og KAM tændes og slukkes med knapperne under plottet.
    """
    data = per_group.copy()
    has_industry = (
        INDUSTRY_SEGMENT in data.columns and data[INDUSTRY_SEGMENT].notna().any()
    )
    segments = (
        sorted(data[INDUSTRY_SEGMENT].dropna().unique().tolist())
        if has_industry
        else []
    )
    segment_colours = _colour_map(segments) if has_industry else {}
    colour_by_segment = cfg.colour_by == "industry_segment" and has_industry

    # De rækker der deles med item-plottet: emne-type, produktion og KAM.
    shared_rows = [
        (column, heading, dimension, _dimension_values(data, column))
        for column, heading, dimension in SHARED_FILTER_ROWS
    ]

    # Samme rækkefølge som item-plottet: kategori-blok først, derefter de
    # største kunder øverst inden for blokken.
    ordered = data.sort_values("samlet_turnover_window", ascending=False)
    ordered = ordered.iloc[
        sorted(
            range(len(ordered)),
            key=lambda i: category_sort_key(
                str(ordered.iloc[i].get("Kundekategori") or "-")
            ),
        )
    ]

    fig = go.Figure()
    category_order: list[str] = []
    trace_categories: list[str] = []
    trace_types: list[object] = []
    trace_segments: list[object] = []
    shared_values: dict[str, list[object]] = {}

    for row in ordered.to_dict("records"):
        name = row[GROUP]
        category = str(row.get("Kundekategori") or "-")
        label = category if category != "-" else "Ingen kategori"
        if category not in category_order:
            category_order.append(category)

        customer_type = row.get("Kundetype")
        segment = row.get(INDUSTRY_SEGMENT)
        segment = segment if pd.notna(segment) else None
        kam = row.get(KAM)
        kam = kam if kam is not None and pd.notna(kam) else None

        trace_categories.append(category)
        trace_types.append(customer_type)
        trace_segments.append(segment)
        for column, _, _, _ in shared_rows:
            shared_values.setdefault(column, []).append(row.get(column))

        if colour_by_segment:
            colour = segment_colours.get(segment, "#7f7f7f")
            edge_colour, edge_width = EDGE_COLOUR_PLAIN, EDGE_WIDTH_PLAIN
        else:
            colour = CUSTOMER_TYPE_COLOURS.get(customer_type, "#7f7f7f")
            if segment is not None:
                edge_colour = segment_colours.get(segment, EDGE_COLOUR_PLAIN)
                edge_width = EDGE_WIDTH_BASE
            else:
                edge_colour, edge_width = EDGE_COLOUR_PLAIN, EDGE_WIDTH_PLAIN

        # Ét punkt pr. spor, så hover-teksten kan skrives færdig med det samme.
        hover = [
            f"<b>{name}</b>",
            "GM%: %{x:.1f}%",
            "Turnover: %{y:,.0f} DKK",
            f"Kundetype: {customer_type}",
            f"Kategori: {category}",
        ]
        if segment is not None:
            hover.append(f"Industry segment: {segment}")
        if kam is not None:
            hover.append(f"KAM: {kam}")

        fig.add_trace(
            go.Scatter(
                x=[row["samlet_GM"] * 100],
                y=[row["samlet_turnover_window"]],
                mode="markers+text",
                name=str(name),
                legendgroup=category,
                legendgrouptitle_text=f"Kategori {label}",
                text=[str(name)],
                textposition="top right",
                textfont=dict(size=9),
                meta={
                    "kundetype": customer_type,
                    "kategori": category,
                    **{
                        dimension: row.get(column)
                        for column, _, dimension, _ in shared_rows
                    },
                },
                marker=dict(
                    size=10,
                    color=colour,
                    line=dict(color=edge_colour, width=edge_width),
                ),
                hovertemplate="<br>".join(hover) + "<extra></extra>",
            )
        )

    shapes, annotations = category_zone_shapes(cfg)

    types_present = [t for t in CUSTOMER_TYPE_ORDER if t in trace_types]
    button_groups: list[tuple[str, str | None, list[dict]]] = [
        ("Vis/skjul kundetype:", "kundetype", toggle_buttons(types_present, trace_types)),
        ("Vis/skjul kategori:", "kategori", toggle_buttons(category_order, trace_categories)),
    ]
    for column, heading, dimension, values in shared_rows:
        button_groups.append(
            (heading, dimension, toggle_buttons(values, shared_values.get(column, [])))
        )
    if has_industry and segments and not colour_by_segment:
        button_groups.append(
            (
                "Fremhæv branche:",
                None,  # fremhæver kun, filtrerer ikke
                _segment_highlight_buttons(segments, trace_segments),
            )
        )

    menus, row_labels, button_rows, dimensions = stack_button_rows(
        button_groups, y_start=-0.14
    )
    annotations = annotations + row_labels
    bottom_margin = 40 if not button_rows else 65 + button_rows * BUTTON_ROW_MARGIN_PX

    subtitle_extra = title_suffix
    if has_industry and not colour_by_segment:
        subtitle_extra = "  |  ".join(
            part for part in (subtitle_extra, "Kant = Industry segment") if part
        )

    fig.update_layout(
        title=dict(
            text=(
                "Kundesegmentering – Kundegruppe<br>"
                f"<sup>{_subtitle(cfg, dates, subtitle_extra)}</sup>"
            ),
            font=dict(size=13),
        ),
        shapes=shapes,
        annotations=annotations,
        updatemenus=menus,
        meta=filter_metadata(dimensions),
        legend=dict(
            title="Kunder (klik = vis/skjul enkelt kunde · knap = hel blok)",
            itemclick="toggle",
            itemdoubleclick="toggleothers",
            groupclick="toggleitem",
            tracegroupgap=8,
        ),
        hovermode="closest",
        plot_bgcolor="white",
        margin=dict(b=bottom_margin),
        width=PLOT_WIDTH,
        height=PLOT_HEIGHT,
        **_axes(
            cfg,
            f"Samlet Turnover DKK ({cfg.turnover_window_months} mdr. vindue)",
            x_values=(data["samlet_GM"] * 100).tolist(),
            y_values=data["samlet_turnover_window"].tolist(),
        ),
    )
    return fig


def _segment_highlight_buttons(
    segments: Sequence[object], trace_segments: Sequence[object]
) -> list[dict]:
    """
    Én knap pr. Industry_segment der fremhæver segmentets punkter.

    Knapperne arbejder på kantbredden. Hvert spor er én kunde med ét segment,
    så hver knap sender blot én bredde pr. spor.
    """
    trace_indices = list(range(len(trace_segments)))
    guard_attribute, guard_value = TOGGLE_GUARD
    guard = [guard_value] * len(trace_indices)
    base_widths = [
        EDGE_WIDTH_BASE if segment is not None else EDGE_WIDTH_PLAIN
        for segment in trace_segments
    ]

    buttons: list[dict] = []
    for segment in segments:
        highlighted = [
            EDGE_WIDTH_HIGHLIGHT if value == segment else base
            for value, base in zip(trace_segments, base_widths)
        ]
        buttons.append(
            dict(
                label=str(segment),
                method="restyle",
                args=[
                    {"marker.line.width": highlighted, guard_attribute: guard},
                    trace_indices,
                ],
                args2=[
                    {"marker.line.width": base_widths, guard_attribute: guard},
                    trace_indices,
                ],
            )
        )
    return buttons


# --- Item-plot ---------------------------------------------------------------


def item_scatter(
    per_item: pd.DataFrame,
    cfg: Config,
    dates: ReferenceDates,
    title_suffix: str = "",
) -> "go.Figure":
    """
    Tegner item-plottet: ét punkt pr. (kundegruppe, item no.).

    Punkterne farves efter kundegruppe og grupperes i legenden efter kundens
    kategori. Kategorien beregnes på kundegruppe-niveau ud fra det samme
    grundlag som kundegruppe-plottet, så en kunde ligger i samme kategori
    begge steder.

    Under plottet er der to rækker knapper: ét sæt der skifter hvilke
    volumen-krav (niveau A–D) der tegnes, og ét sæt der viser/skjuler en hel
    kategori-blok på én gang.
    """
    data = per_item.copy()
    data = data[data[WINDOW_ITEM].fillna(0) > 0]

    categories_by_group, turnover_by_group = _group_categories(data, cfg)
    customer_groups = sorted(
        data[GROUP].dropna().unique().tolist(),
        key=lambda name: (
            category_sort_key(categories_by_group.get(name, "-")),
            -float(turnover_by_group.get(name, 0) or 0),
        ),
    )
    group_colours = _colour_map(sorted(data[GROUP].dropna().unique().tolist()))

    shared_rows = [
        (column, heading, dimension, _dimension_values(data, column))
        for column, heading, dimension in SHARED_FILTER_ROWS
    ]

    fig = go.Figure()
    category_order: list[str] = []
    trace_categories: list[str] = []
    shared_values: dict[str, list[object]] = {}

    for name in customer_groups:
        block = data[data[GROUP] == name]
        if block.empty:
            continue
        category = categories_by_group.get(name, "-")
        label = category if category != "-" else "Ingen kategori"
        if category not in category_order:
            category_order.append(category)
        trace_categories.append(category)
        # Alle en enheds varer deler emne-type, produktionssted og KAM, så
        # værdien kan tages fra den første række.
        first = block.iloc[0]
        for column, _, _, _ in shared_rows:
            shared_values.setdefault(column, []).append(
                first[column] if column in block.columns else None
            )
        kam = first[KAM] if KAM in block.columns and pd.notna(first[KAM]) else None

        fig.add_trace(
            go.Scatter(
                x=block[ITEM_GM] * 100,
                y=block[WINDOW_ITEM],
                mode="markers+text",
                name=str(name),
                legendgroup=category,
                legendgrouptitle_text=f"Kategori {label}",
                text=block[ITEM_NO].astype(str),
                textposition="top right",
                textfont=dict(size=8),
                meta={
                    "kategori": category,
                    **{
                        dimension: (first[column] if column in block.columns else None)
                        for column, _, dimension, _ in shared_rows
                    },
                },
                marker=dict(
                    size=7,
                    color=group_colours[name],
                    line=dict(color="black", width=0.4),
                ),
                customdata=block[[GROUP]].values,
                hovertemplate=(
                    "<b>%{text}</b><br>"
                    "Kundegruppe: %{customdata[0]}<br>"
                    f"Kategori: {category}<br>"
                    + (f"KAM: {kam}<br>" if kam is not None else "")
                    + "GM%: %{x:.1f}%<br>"
                    "Turnover: %{y:,.0f} DKK<br>"
                    "<extra></extra>"
                ),
            )
        )

    levels = list(cfg.volume_zones)
    present = [
        category[0]
        for category in category_order
        if category and category[0] in cfg.volume_zones
    ]
    default_level = present[0] if present else (levels[0] if levels else "A")
    shapes, zone_annotations = volume_zone_shapes(default_level, cfg)

    # Knapperne under plottet stables: først kravniveau, så kategori-blokke og
    # til sidst KAM.
    level_label = "Volumenkrav:"
    below_levels = -0.14 - BUTTON_ROW_GAP
    button_groups: list[tuple[str, str | None, list[dict]]] = [
        ("Vis/skjul kategori:", "kategori", toggle_buttons(category_order, trace_categories))
    ]
    for column, heading, dimension, values in shared_rows:
        button_groups.append(
            (heading, dimension, toggle_buttons(values, shared_values.get(column, [])))
        )

    menus_below, row_labels, rows_below, dimensions_below = stack_button_rows(
        button_groups, below_levels
    )

    # Overskrifterne skal med i HVER kravknaps annotationer: en relayout
    # udskifter hele annotations-listen, så uden dem forsvandt rækkernes
    # navne så snart man skiftede niveau.
    static_annotations = [_row_label(level_label, -0.14)] + row_labels

    level_buttons = []
    for level in levels:
        level_shapes, level_annotations = volume_zone_shapes(level, cfg)
        level_buttons.append(
            dict(
                label=f"Krav {level}",
                method="relayout",
                args=[
                    {
                        "shapes": level_shapes,
                        "annotations": level_annotations + static_annotations,
                    }
                ],
            )
        )

    menus: list[dict] = []
    if level_buttons:
        menus.append(
            dict(
                type="buttons",
                direction="right",
                showactive=True,
                active=levels.index(default_level) if default_level in levels else 0,
                x=_label_width(level_label),
                xanchor="left",
                y=-0.14,
                yanchor="top",
                pad={"r": 6, "t": 4},
                buttons=level_buttons,
            )
        )
    menus.extend(menus_below)
    # Kravmenuen ligger forrest og er ikke et filter, så den fylder en plads.
    dimensions = ([None] * (len(menus) - len(menus_below))) + dimensions_below
    annotations = zone_annotations + static_annotations
    # Plads til kravrækken plus de rækker de øvrige knapper fylder.
    bottom_margin = 60 + (1 + rows_below) * BUTTON_ROW_MARGIN_PX

    fig.update_layout(
        title=dict(
            text=(
                "Kundesegmentering – Item scatter<br>"
                f"<sup>{_subtitle(cfg, dates, title_suffix)}</sup>"
            ),
            font=dict(size=13),
        ),
        shapes=shapes,
        annotations=annotations,
        updatemenus=menus,
        meta=filter_metadata(dimensions),
        margin=dict(b=bottom_margin),
        legend=dict(
            title="Kunder (klik = vis/skjul enkelt kunde · knap = hel blok)",
            itemclick="toggle",
            itemdoubleclick="toggleothers",
            groupclick="toggleitem",
            tracegroupgap=8,
        ),
        hovermode="closest",
        plot_bgcolor="white",
        width=PLOT_WIDTH,
        height=PLOT_HEIGHT,
        **_axes(
            cfg,
            f"Turnover DKK – item niveau ({cfg.turnover_window_months} mdr. vindue)",
            x_values=(data[ITEM_GM] * 100).tolist(),
            y_values=data[WINDOW_ITEM].tolist(),
        ),
    )
    return fig


def _group_categories(
    per_item: pd.DataFrame, cfg: Config
) -> tuple[dict[str, str], dict[str, float]]:
    """Kundekategori og vindue-turnover pr. kundegruppe, til farve og sortering."""
    if per_item.empty:
        return {}, {}

    per_group = per_item.groupby(GROUP, as_index=False).agg(
        samlet_turnover=("Turnover_sum", "sum"),
        samlet_turnover_window=(WINDOW_GROUP, "sum"),
        samlet_GP=("GP_sum", "sum"),
    )
    per_group["samlet_GM"] = np.where(
        per_group["samlet_turnover"] != 0,
        per_group["samlet_GP"] / per_group["samlet_turnover"],
        np.nan,
    )
    categories = {
        name: classify_customer_category(turnover, margin, cfg.category_bands)
        for name, turnover, margin in zip(
            per_group[GROUP],
            per_group["samlet_turnover_window"],
            per_group["samlet_GM"],
        )
    }
    turnovers = dict(
        zip(per_group[GROUP], per_group["samlet_turnover_window"])
    )
    return categories, turnovers


# --- Skrivning ---------------------------------------------------------------


def write_html(fig: "go.Figure", path: str, label: str, log: Log = print) -> None:
    pio.write_html(
        fig, path, include_plotlyjs="cdn", post_script=filter_script(fig)
    )
    log(f"[{label}] gemt til: {path}")

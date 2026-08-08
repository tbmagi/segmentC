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
from .dataio import GROUP, INDUSTRY_SEGMENT, ITEM_NO, ReferenceDates
from .metrics import ITEM_GM, WINDOW_GROUP, WINDOW_ITEM

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


def _danish_thousands(value: float) -> str:
    return f"{value:,.0f}".replace(",", ".")


def _qualitative_palette() -> list[str]:
    return (
        plotly_colours.qualitative.Plotly
        + plotly_colours.qualitative.D3
        + plotly_colours.qualitative.Light24
    )


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


def flow_button_menus(buttons: Sequence[dict], y_start: float) -> tuple[list[dict], int]:
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
    x = 0.0
    rows = 1
    for button in buttons:
        width = _button_width(button.get("label", ""))
        if x > 0 and x + width > 1.0:
            x = 0.0
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
        title="Gross Margin potentiale (%)",
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

    Med ``colour_by="kundetype"`` farves punkterne efter Eksisterende/Ny/
    Tidligere, og Industry_segment vises som kantfarve med en knap pr. segment
    til at fremhæve det. Med ``colour_by="industry_segment"`` farves punkterne
    i stedet direkte efter segment.

    Der oprettes ét spor pr. farvekategori — ikke ét pr. kunde — så figuren
    holder sig lille og hurtig at åbne, uanset hvor mange kunder der er.
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

    colour_by_segment = cfg.colour_by == "industry_segment"
    if colour_by_segment and not has_industry:
        colour_by_segment = False

    if colour_by_segment:
        groups = segments
        column = INDUSTRY_SEGMENT
        colours = _colour_map(segments)
        legend_title = "Industry segment (klik for til/fravælg)"
    else:
        groups = [t for t in CUSTOMER_TYPE_ORDER if (data["Kundetype"] == t).any()]
        column = "Kundetype"
        colours = CUSTOMER_TYPE_COLOURS
        legend_title = "Kundetype (klik for til/fravælg)"

    segment_colours = _colour_map(segments) if has_industry else {}

    fig = go.Figure()
    trace_segments: list[pd.Series] = []

    for name in groups:
        block = data[data[column] == name]
        if block.empty:
            continue
        block = block.sort_values("samlet_turnover_window", ascending=False)

        if colour_by_segment or not has_industry:
            edge_colours = EDGE_COLOUR_PLAIN
            edge_widths = EDGE_WIDTH_PLAIN
        else:
            edge_colours = [
                segment_colours.get(segment, EDGE_COLOUR_PLAIN)
                if pd.notna(segment)
                else EDGE_COLOUR_PLAIN
                for segment in block[INDUSTRY_SEGMENT]
            ]
            edge_widths = [
                EDGE_WIDTH_BASE if pd.notna(segment) else EDGE_WIDTH_PLAIN
                for segment in block[INDUSTRY_SEGMENT]
            ]

        trace_segments.append(
            block[INDUSTRY_SEGMENT]
            if has_industry
            else pd.Series([None] * len(block), index=block.index)
        )

        fig.add_trace(
            go.Scatter(
                x=block["samlet_GM"] * 100,
                y=block["samlet_turnover_window"],
                mode="markers+text",
                name=str(name),
                text=block[GROUP],
                textposition="top right",
                textfont=dict(size=9),
                marker=dict(
                    size=9,
                    color=colours.get(name, "#7f7f7f"),
                    line=dict(color=edge_colours, width=edge_widths),
                ),
                customdata=block[
                    ["Kundetype", "Kundekategori", INDUSTRY_SEGMENT]
                ].astype(object).where(block[["Kundetype", "Kundekategori", INDUSTRY_SEGMENT]].notna(), "").values,
                hovertemplate=(
                    "<b>%{text}</b><br>"
                    "GM%: %{x:.1f}%<br>"
                    "Turnover: %{y:,.0f} DKK<br>"
                    "Kundetype: %{customdata[0]}<br>"
                    "Kategori: %{customdata[1]}<br>"
                    "Industry segment: %{customdata[2]}<br>"
                    "<extra></extra>"
                ),
            )
        )

    shapes, annotations = category_zone_shapes(cfg)

    menus: list[dict] = []
    bottom_margin = 40
    if has_industry and segments and not colour_by_segment:
        menus, button_rows = _segment_highlight_buttons(segments, trace_segments)
        bottom_margin = 65 + button_rows * BUTTON_ROW_MARGIN_PX

    subtitle_extra = title_suffix
    if has_industry and not colour_by_segment:
        subtitle_extra = (
            f"{subtitle_extra}  |  Kant = Industry segment"
            if subtitle_extra
            else "Kant = Industry segment"
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
        legend=dict(
            title=legend_title,
            itemclick="toggle",
            itemdoubleclick="toggleothers",
            tracegroupgap=4,
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
    segments: Sequence[object], trace_segments: Sequence[pd.Series]
) -> tuple[list[dict], int]:
    """
    Én knap pr. Industry_segment der fremhæver segmentets punkter.

    Knapperne arbejder på kantbredden. Fordi hvert spor dækker mange kunder,
    sender hver knap et helt bredde-array pr. spor frem for én værdi.
    """
    trace_indices = list(range(len(trace_segments)))
    base_widths = [
        [
            EDGE_WIDTH_BASE if pd.notna(segment) else EDGE_WIDTH_PLAIN
            for segment in values
        ]
        for values in trace_segments
    ]

    buttons: list[dict] = []
    for segment in segments:
        highlighted = [
            [
                EDGE_WIDTH_HIGHLIGHT
                if value == segment
                else (EDGE_WIDTH_BASE if pd.notna(value) else EDGE_WIDTH_PLAIN)
                for value in values
            ]
            for values in trace_segments
        ]
        buttons.append(
            dict(
                label=str(segment),
                method="restyle",
                args=[{"marker.line.width": highlighted}, trace_indices],
                args2=[{"marker.line.width": base_widths}, trace_indices],
            )
        )
    return flow_button_menus(buttons, y_start=-0.14)


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

    fig = go.Figure()
    traces_by_category: dict[str, list[int]] = {}
    category_order: list[str] = []

    for name in customer_groups:
        block = data[data[GROUP] == name]
        if block.empty:
            continue
        category = categories_by_group.get(name, "-")
        label = category if category != "-" else "Ingen kategori"
        if category not in traces_by_category:
            traces_by_category[category] = []
            category_order.append(category)
        traces_by_category[category].append(len(fig.data))

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
                    "GM%: %{x:.1f}%<br>"
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
    shapes, annotations = volume_zone_shapes(default_level, cfg)

    level_buttons = []
    for level in levels:
        level_shapes, level_annotations = volume_zone_shapes(level, cfg)
        level_buttons.append(
            dict(
                label=f"Krav {level}",
                method="relayout",
                args=[{"shapes": level_shapes, "annotations": level_annotations}],
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
                x=0.0,
                xanchor="left",
                y=-0.14,
                yanchor="top",
                pad={"r": 6, "t": 4},
                buttons=level_buttons,
            )
        )
    category_menus, category_rows = _category_toggle_buttons(
        category_order, traces_by_category
    )
    menus.extend(category_menus)
    # Plads til "Krav"-rækken plus de rækker kategori-knapperne fylder.
    bottom_margin = 60 + (1 + category_rows) * BUTTON_ROW_MARGIN_PX

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


def _category_toggle_buttons(
    category_order: Sequence[str], traces_by_category: Mapping[str, list[int]]
) -> tuple[list[dict], int]:
    """Én knap pr. kategori-blok der viser/skjuler alle kunder i blokken."""
    buttons: list[dict] = []
    for category in category_order:
        indices = traces_by_category[category]
        count = len(indices)
        buttons.append(
            dict(
                label=category if category != "-" else "Ingen kat.",
                method="restyle",
                args=[{"visible": ["legendonly"] * count}, indices],
                args2=[{"visible": [True] * count}, indices],
            )
        )
    # Rækken lægges under "Krav"-rækken, som altid fylder præcis én række.
    return flow_button_menus(buttons, y_start=-0.14 - BUTTON_ROW_GAP)


# --- Skrivning ---------------------------------------------------------------


def write_html(fig: "go.Figure", path: str, label: str, log: Log = print) -> None:
    pio.write_html(fig, path, include_plotlyjs="cdn")
    log(f"[{label}] gemt til: {path}")

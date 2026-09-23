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

from dataclasses import dataclass
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
from .dataio import GROUP, INDUSTRY_SEGMENT, ITEM_NO, KAM, ReferenceDates
from .language import DANISH, Texts
from .metrics import ITEM_GM, LAST_ACTIVITY, WINDOW_GROUP, WINDOW_ITEM, sort_kams

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

CUSTOMER_TYPE_ORDER = ["Eksisterende", "Ny", "Genopstået", "Tidligere"]

GRID_COLOUR = "rgba(200,200,200,0.4)"
PLOT_WIDTH = 1200
PLOT_HEIGHT = 750

# Knaprækker under plottet. Bredden af en knap kendes først når browseren har
# tegnet den, så den anslås ud fra etikettens længde — bevidst en anelse for
# rundhåndet, så knapper hellere står lidt spredt end oven i hinanden.
BUTTON_CHAR_PX = 6.0
BUTTON_PADDING_PX = 32
BUTTON_SPACING_PX = 14
#: Rækkeoverskrifterne står med en mindre skrift end knapperne.
HEADING_CHAR_PX = 4.4
HEADING_GAP_PX = 30
#: Fast afstand i pixels fra overskriftens højre kant til første knap.
HEADING_CLEARANCE_PX = 12
# Knappernes x-koordinat er i "paper"-enheder, der spænder over PLOTOMRÅDET —
# ikke hele figuren. Bredden kendes først ved tegning, men er målt i browseren
# til 730-750 px for begge plots med legenden ved siden af. Tallene ovenfor er
# ligeledes målt: en knap med to tegn fylder 40 px, med tre 50 og med seks 60.
#
# Skønnet var før 640, og det var netop dét der ombrød rækkerne for tidligt:
# hver knap blev regnet 15 % bredere end den er, så den sidste KAM faldt ned
# på en linje for sig selv selv om der var plads.
BUTTON_AREA_PX = 740

# Lodret er det samme problem, bare værre: paper-enheden spænder over
# plotområdets HØJDE, og den højde skrumpede før med hver knaprække, fordi
# rækkerne blev klemt ind i figuren via bundmargenen. En fast paper-afstand
# svarede derfor til færre og færre pixels, og til sidst lå rækkerne oven i
# hinanden. Nu lægges rækkerne TIL figurens højde, så plotområdet er lige højt
# uanset antallet af rækker — og afstanden mellem dem kan regnes i pixels.
BUTTON_ROW_PX = 46  # lodret plads pr. knaprække
BUTTON_FIRST_ROW_PX = 70  # fra x-aksen ned til første række (plads til aksetitlen)
BUTTON_BASE_MARGIN_PX = 90  # bundmargen før rækkerne lægges til
PLOT_TOP_MARGIN = 100  # plads til titel og undertitel

#: Farvekoden og søgefeltet er almindelig HTML og kan derfor ikke tegnes inde
#: i figurens SVG, hvor knapperne bor. De lægges i stedet oven på figuren i et
#: bælte der reserveres mellem x-aksen og første knaprække — så står de under
#: grafen og over filtrene, uden at stjæle plads fra punkterne.
OVERLAY_ROW_PX = 56

#: Plotområdets højde — den samme uanset hvor mange knaprækker der kommer til.
PLOT_AREA_PX = PLOT_HEIGHT - PLOT_TOP_MARGIN - BUTTON_BASE_MARGIN_PX
BUTTON_ROW_GAP = BUTTON_ROW_PX / PLOT_AREA_PX

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

#: Knappen der slår alle filterrækker fra på én gang. Den står nederst, under
#: de rækker den nulstiller. Teksten hentes fra sproget — denne står kun som
#: reserve, hvis figuren ikke selv har en nulstil-knap at læse den fra.
RESET_LABEL = DANISH.reset_button

# Knappernes farver. Grøn = tændt, rød = slukket.
#
# Rød og grøn er svær at skelne for en rødgrønt farveblind, så de to nuancer
# er valgt så de også adskiller sig i lyshed: den røde er mærkbart mørkere end
# den grønne. Så kan tilstanden aflæses uden at kunne se forskel på kulørerne
# (deutan ΔE 16,8 — godt over gulvet på 8).
BUTTON_ON = "#e4f6e7"
BUTTON_ON_EDGE = "#4f9a63"
BUTTON_OFF = "#e0a9a5"
BUTTON_OFF_EDGE = "#b05b56"
BUTTON_NEUTRAL = "#f2f1ee"
BUTTON_NEUTRAL_EDGE = "#b8b6b0"


# Plotly har ingen indstilling for farven på en nedtrykt knap: den tegnes med
# en fast bleg blå, og kun de utrykte følger ``bgcolor``. Tilstanden males
# derfor af scriptet i den færdige HTML, som sætter ``bgcolor`` pr. knap og
# holder Plotlys egen "active" på -1, så den faste blå aldrig kommer i spil.
# Værdierne herunder er kun udgangspunktet inden første klik.


def filter_colours() -> dict:
    """En filterknap starter tændt: værdien vises."""
    return dict(bgcolor=BUTTON_ON, bordercolor=BUTTON_ON_EDGE, borderwidth=1)


def level_colours(chosen: bool) -> dict:
    """
    Volumenkrav er et enten-eller-valg med omvendt fortegn af filtrene: den
    valgte er grøn, de fravalgte røde.
    """
    return dict(
        bgcolor=BUTTON_ON if chosen else BUTTON_OFF,
        bordercolor=BUTTON_ON_EDGE if chosen else BUTTON_OFF_EDGE,
        borderwidth=1,
    )


def highlight_colours() -> dict:
    """
    Fremhæv-knapperne er hverken tændt eller slukket.

    De skjuler ingenting — de gør kun en branche tykkere i kanten. Rød ville
    påstå at noget var slået fra, så de bliver stående neutrale og overlades
    til Plotlys egen markering af hvad der er trykket ned.
    """
    return dict(
        bgcolor=BUTTON_NEUTRAL, bordercolor=BUTTON_NEUTRAL_EDGE, borderwidth=1
    )


def neutral_colours() -> dict:
    """Nulstil-knappen er en handling, ikke en tilstand."""
    return dict(
        bgcolor=BUTTON_NEUTRAL, bordercolor=BUTTON_NEUTRAL_EDGE, borderwidth=1
    )


def button_area_margin(rows: int, overlays: int = 0) -> int:
    """Bundmargen der giver plads til ``rows`` knaprækker og ``overlays`` bælter."""
    return BUTTON_BASE_MARGIN_PX + rows * BUTTON_ROW_PX + overlays * OVERLAY_ROW_PX


def figure_height(rows: int, overlays: int = 0) -> int:
    """Figurens højde: knaprækkerne lægges til i stedet for at klemme plottet."""
    return PLOT_HEIGHT + rows * BUTTON_ROW_PX + overlays * OVERLAY_ROW_PX


def first_row_y(overlays: int = 0) -> float:
    """
    Første knaprækkes y i paper-enheder.

    Er der reserveret plads til et HTML-bælte (farvekode eller søgefelt),
    skubbes rækkerne tilsvarende længere ned, så bæltet kan ligge imellem.
    """
    return -(BUTTON_FIRST_ROW_PX + overlays * OVERLAY_ROW_PX) / PLOT_AREA_PX


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
    label_of: Callable[[object], str] = str,
    scale: "YScale | None" = None,
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
    # Zonerne er angivet i kroner, men tegnes i aksens koordinater. På en
    # symlog-akse er de to ting ikke det samme, så de skal omregnes med
    # nøjagtig den samme funktion som punkterne.
    on_axis = scale.point if scale is not None else (lambda v: v)

    for name, band in bands.items():
        colour = colours.get(name, "#aaaaaa")
        x0 = band.gm_min * 100
        y0 = on_axis(band.turnover_min)
        y1 = on_axis(
            band.turnover_max if band.turnover_max is not None else Y_MAX_ZONE
        )
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
                    text=label_of(name),
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
                y0=on_axis(y_value),
                y1=on_axis(y_value),
                line=dict(color="grey", width=1, dash="dash"),
                opacity=0.6,
                layer="below",
            )
        )
        annotations.append(
            dict(
                x=1.0,
                y=on_axis(y_value),
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


def _row_label(text: str, y: float, x: float = 0.0) -> dict:
    """
    Overskrift til venstre for en knaprække, så rækkerne kan skelnes.

    Teksten hænges op i sin HØJRE kant, et fast stykke til venstre for der
    hvor knapperne begynder. Den voksede før mod højre fra plotområdets
    venstre kant, og da knappernes startpunkt er en brøkdel af et plotområde
    der skrumper når legenden er bred, kunne knapperne ende oven i teksten på
    netop de plots hvor kundenavnene er lange. Nu er afstanden den samme
    uanset hvor bredt plotområdet bliver, og overskriften breder sig i stedet
    ud i den tomme venstremargen.
    """
    return dict(
        x=x,
        y=y,
        xref="paper",
        yref="paper",
        text=text,
        showarrow=False,
        xanchor="right",
        yanchor="top",
        font=dict(size=10, color="#555555"),
        xshift=-HEADING_CLEARANCE_PX,
        yshift=-7,
    )


def _label_width(text: str) -> float:
    """Pladsen en rækkeoverskrift optager, i paper-koordinater."""
    if not text:
        return 0.0
    return (len(text) * HEADING_CHAR_PX + HEADING_GAP_PX) / BUTTON_AREA_PX


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

    Knappens tekst ER den værdi der sammenlignes med. På en engelsk graf
    oversættes derfor både knappen og sporenes ``meta``, så figuren er
    indbyrdes konsistent; ingen uden for figuren læser de værdier.
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
  var RESET_LABEL = "__RESET_LABEL__";
  var PREFIX = "__PREFIX__";
  var ON = "__ON__", ON_EDGE = "__ON_EDGE__";
  var OFF = "__OFF__", OFF_EDGE = "__OFF_EDGE__";
  var gd = document.getElementById('{plot_id}');
  if (!gd) { return; }
  var meta = (gd.layout && gd.layout.meta) || {};
  var dimensionByMenu = meta.filters || {};
  var resetMenu = (meta.reset === undefined || meta.reset === null)
                  ? null : Number(meta.reset);
  var levelMenus = (meta.krav || []).map(Number);
  var chosenLevel = (meta.valgt === undefined || meta.valgt === null)
                    ? null : Number(meta.valgt);
  if (!Object.keys(dimensionByMenu).length && !levelMenus.length) { return; }

  // Scriptet fører selv regnskab med hvad der er trykket ned. Plotlys egen
  // "active" holdes på -1, fordi en aktiv knap ellers tegnes med en fast
  // bleg blå der ikke kan sættes — og så kunne hverken grøn eller rød ses.
  var pressed = {};

  function menus() {
    return (gd._fullLayout && gd._fullLayout.updatemenus)
           || (gd.layout && gd.layout.updatemenus) || [];
  }

  // Grøn = vises, rød = skjult. For volumenkrav er fortegnet omvendt:
  // den valgte er grøn, de fravalgte røde.
  function colours() {
    var update = {};
    Object.keys(dimensionByMenu).forEach(function (index) {
      var on = !pressed[index];
      update['updatemenus[' + index + '].bgcolor'] = on ? ON : OFF;
      update['updatemenus[' + index + '].bordercolor'] = on ? ON_EDGE : OFF_EDGE;
      update['updatemenus[' + index + '].active'] = -1;
    });
    levelMenus.forEach(function (index) {
      var chosen = index === chosenLevel;
      update['updatemenus[' + index + '].bgcolor'] = chosen ? ON : OFF;
      update['updatemenus[' + index + '].bordercolor'] = chosen ? ON_EDGE : OFF_EDGE;
      update['updatemenus[' + index + '].active'] = -1;
    });
    if (resetMenu !== null) {
      update['updatemenus[' + resetMenu + '].active'] = -1;
    }
    return update;
  }

  function apply() {
    var all = menus();
    // Saml de fravalgte værdier pr. række (kundetype, kategori, KAM ...).
    var deselected = {};
    Object.keys(dimensionByMenu).forEach(function (index) {
      var menu = all[Number(index)];
      if (!menu || !menu.buttons || !menu.buttons.length) { return; }
      var dimension = dimensionByMenu[index];
      if (!deselected[dimension]) { deselected[dimension] = []; }
      if (pressed[index]) {
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
    Plotly.relayout(gd, colours());
  }

  function clickedMenuIndex(event) {
    // Navnet bærer pladsen. Objekt-identitet dur ikke: en kravknap laver en
    // relayout, og bagefter er det klikkede objekt ikke det samme længere.
    var name = event.menu && event.menu.name;
    if (typeof name === 'string' && name.indexOf(PREFIX) === 0) {
      return Number(name.slice(PREFIX.length));
    }
    var all = menus();
    for (var i = 0; i < all.length; i++) {
      if (all[i] === event.menu) { return i; }
    }
    // Sidste udvej: nulstil-knappen kendes på sin tekst.
    if (event.button && event.button.label === RESET_LABEL) { return resetMenu; }
    return -1;
  }

  gd.on('plotly_buttonclicked', function (event) {
    var index = clickedMenuIndex(event);
    if (index < 0) { return; }
    if (resetMenu !== null && index === resetMenu) {
      pressed = {};                       // alle filtre tændes igen
    } else if (levelMenus.indexOf(index) !== -1) {
      chosenLevel = index;                // kravene er et enten-eller-valg
    } else if (dimensionByMenu[index] !== undefined) {
      pressed[index] = !pressed[index];
    } else {
      return;                             // fremhæv-knapper passer sig selv
    }
    setTimeout(apply, 0);
  });

  // Dobbeltklik i legenden skal vise den ENE kunde og skjule alle andre.
  //
  // Plotlys egen "toggleothers" gør det kun inden for kundens egen
  // kategori-blok, fordi sporene er grupperet i legenden — dobbeltklikkede
  // man på en A+-kunde, blev resten af A+ skjult, mens B+ og C+ blev stående.
  // Derfor overtages dobbeltklikket her, og Plotlys eget afbrydes ved at
  // returnere false.
  //
  // Om vi allerede står isoleret læses af sporene selv. Et flag dur ikke:
  // Plotly sender ET klik af sted inden dobbeltklikket, så et flag ville
  // være nulstillet inden det blev læst, og andet dobbeltklik ville isolere
  // forfra i stedet for at fortryde.
  function showsOnly(index) {
    return gd.data.every(function (trace, i) {
      var visible = (trace.visible === undefined) ? true : trace.visible;
      return i === index ? visible === true : visible === 'legendonly';
    });
  }

  // Viser kun den ene — eller fortryder, hvis den allerede står alene.
  function isolate(index) {
    if (showsOnly(index)) {
      setTimeout(apply, 0);
    } else {
      Plotly.restyle(gd, {visible: gd.data.map(function (_, i) {
        return i === index ? true : 'legendonly';
      })});
    }
  }

  gd.on('plotly_legenddoubleclick', function (event) {
    isolate(event.curveNumber);
    return false;
  });

  // Det samme skal kunne lade sig gøre ved at dobbeltklikke på selve punktet.
  //
  // Plotly har ingen hændelse for dobbeltklik på et punkt, og at tælle to
  // klik selv dur ikke: Plotly undertrykker med vilje det andet klik, så et
  // dobbeltklik kun giver ÉN 'plotly_click'. Til gengæld skal musen jo hvile
  // på punktet for at kunne ramme det, så det sidst berørte spor huskes og
  // bruges når dobbeltklikket melder sig.
  var hovered = -1;

  gd.on('plotly_hover', function (event) {
    if (event.points && event.points.length) {
      hovered = event.points[0].curveNumber;
    }
  });

  gd.on('plotly_unhover', function () { hovered = -1; });

  gd.on('plotly_doubleclick', function () {
    if (hovered >= 0) { isolate(hovered); }
  });

  Plotly.relayout(gd, colours());         // sæt farverne inden første klik
})();
"""


#: JavaScript der lægger en farveforklaring ind OVER selve grafen — som
#: almindelig HTML, ikke som en annotation inde i plotområdet. Så stjæler den
#: JavaScript der placerer en HTML-kasse i bæltet mellem x-aksen og første
#: knaprække. Kassen lægges oven på figuren, ikke før den, så den står under
#: grafen og over filtrene.
#:
#: Placeringen MÅLES i browseren frem for at regnes ud af figurens tal.
#: Knappernes plads afhænger af hvordan browseren ombryder rækkerne, og et
#: udregnet tal ville skride så snart en etiket blev en smule bredere end
#: anslået. Derfor findes den øverste knaprække i DOM'en, og kassen sættes
#: lige over den. Den måles igen efter hver gentegning og ved resize.
_PLACE_OVERLAY = """
  function place(box) {
    var host = gd.parentNode;
    if (!host) { return; }
    if (getComputedStyle(host).position === 'static') {
      host.style.position = 'relative';
    }
    var hostRect = host.getBoundingClientRect();
    var top = null;
    gd.querySelectorAll('.updatemenu-header-group').forEach(function (row) {
      var r = row.getBoundingClientRect();
      if (r.height > 0 && (top === null || r.top < top)) { top = r.top; }
    });
    // Plotområdets venstre kant og bund. Målene ligger i figurens layout;
    // gitteret bruges som reserve hvis Plotly en dag flytter dem.
    var gdRect = gd.getBoundingClientRect();
    var size = (gd._fullLayout && gd._fullLayout._size) || null;
    var grid = gd.querySelector('.gridlayer');
    var left, bottom;
    if (size) {
      left = gdRect.left + size.l;
      bottom = gdRect.top + size.t + size.h;
    } else if (grid) {
      var g = grid.getBoundingClientRect();
      left = g.left;
      bottom = g.bottom;
    } else {
      left = hostRect.left;
      bottom = hostRect.bottom;
    }
    if (top === null) {
      // Ingen knapper at måle ud fra: læg kassen under plotområdet i stedet.
      top = bottom + 44;
    }
    box.style.left = Math.max(0, left - hostRect.left) + 'px';
    box.style.top = (top - hostRect.top - box.offsetHeight - 10) + 'px';
  }

  function follow(box) {
    place(box);
    // Plotly flytter knapperne ved hver gentegning, og browseren ombryder
    // rækkerne igen når vinduet skifter bredde.
    if (gd.on) { gd.on('plotly_afterplot', function () { place(box); }); }
    window.addEventListener('resize', function () { place(box); });
    setTimeout(function () { place(box); }, 0);
  }
"""


#: ingen plads fra punkterne, og den kan ikke slås fra ved et uheld.
_COLOUR_KEY_SCRIPT = """
(function () {
  var gd = document.getElementById('{plot_id}');
  if (!gd) { return; }
  var meta = (gd.layout && gd.layout.meta) || {};
  var key = meta.farvekode;
  if (!key || !key.items || !key.items.length) { return; }
  var id = 'farvekode-' + gd.id;
  if (document.getElementById(id)) { return; }

  var box = document.createElement('div');
  box.id = id;
  box.style.cssText = 'position:absolute;z-index:5;'
    + 'display:flex;align-items:center;flex-wrap:wrap;gap:18px;'
    + 'font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;'
    + 'font-size:13px;color:#333;padding:9px 14px;margin:0;'
    + 'border:1px solid #d8d6d0;border-radius:6px;background:#fbfbfa;'
    + 'width:max-content;max-width:100%;';

  var title = document.createElement('span');
  title.textContent = key.title;
  title.style.cssText = 'font-weight:600;color:#1a4a7a;';
  box.appendChild(title);

  key.items.forEach(function (item) {
    var entry = document.createElement('span');
    entry.style.cssText = 'display:inline-flex;align-items:center;gap:7px;';
    var dot = document.createElement('span');
    dot.style.cssText = 'width:14px;height:14px;border-radius:50%;flex:0 0 auto;'
      + 'background:' + item.colour + ';border:1px solid rgba(0,0,0,0.35);';
    var label = document.createElement('span');
    label.textContent = item.label;
    entry.appendChild(dot);
    entry.appendChild(label);
    box.appendChild(entry);
  });

  gd.parentNode.appendChild(box);
__PLACE__
  follow(box);
})();
"""


#: JavaScript der lægger et søgefelt over item-plottet.
#:
#: Søgningen skjuler ikke punkter — den fremhæver dem. Et spor er én
#: kundegruppe med mange varer, og Plotly kan kun skjule hele spor ad gangen,
#: så et enkelt varenummer kan ikke slås fra den vej. I stedet markeres de
#: fundne punkter med ``selectedpoints``, hvorefter resten tones ned. Så kan
#: man stadig se HVOR i feltet varen ligger i forhold til alle de andre,
#: hvilket er hele pointen med at slå den op.
_SEARCH_SCRIPT = """
(function () {
  var gd = document.getElementById('{plot_id}');
  if (!gd) { return; }
  var meta = (gd.layout && gd.layout.meta) || {};
  var t = meta.soegning;
  if (!t) { return; }
  var id = 'soegefelt-' + gd.id;
  if (document.getElementById(id)) { return; }

  var box = document.createElement('div');
  box.id = id;
  box.style.cssText = 'position:absolute;z-index:5;'
    + 'display:flex;align-items:center;gap:10px;flex-wrap:wrap;'
    + 'font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;'
    + 'font-size:13px;color:#333;padding:9px 14px;margin:0;'
    + 'border:1px solid #d8d6d0;border-radius:6px;background:#fbfbfa;'
    + 'width:max-content;max-width:100%;';

  var label = document.createElement('span');
  label.textContent = t.label;
  label.style.cssText = 'font-weight:600;color:#1a4a7a;';

  var input = document.createElement('input');
  input.type = 'search';
  input.placeholder = t.placeholder;
  input.style.cssText = 'font:inherit;padding:5px 9px;min-width:230px;'
    + 'border:1px solid #b8b6b0;border-radius:4px;background:#fff;';

  var clear = document.createElement('button');
  clear.type = 'button';
  clear.textContent = t.clear;
  clear.style.cssText = 'font:inherit;padding:5px 11px;cursor:pointer;'
    + 'border:1px solid #b8b6b0;border-radius:4px;background:#f2f1ee;';

  var status = document.createElement('span');
  status.style.cssText = 'color:#52514e;';

  var hint = document.createElement('span');
  hint.textContent = t.hint;
  hint.style.cssText = 'color:#8a8880;font-size:12px;';

  [label, input, clear, status, hint].forEach(function (el) { box.appendChild(el); });
  gd.parentNode.appendChild(box);
__PLACE__
  follow(box);

  function terms() {
    return input.value.split(/[\\s,;]+/)
      .map(function (s) { return s.trim().toLowerCase(); })
      .filter(function (s) { return s.length > 0; });
  }

  function search() {
    var wanted = terms();
    if (!wanted.length) {
      status.textContent = '';
      Plotly.restyle(gd, {selectedpoints: [null]});
      return;
    }
    var found = 0;
    var picked = gd.data.map(function (trace) {
      var labels = trace.text || [];
      var hits = [];
      for (var i = 0; i < labels.length; i++) {
        var item = String(labels[i]).toLowerCase();
        for (var w = 0; w < wanted.length; w++) {
          if (item.indexOf(wanted[w]) !== -1) { hits.push(i); break; }
        }
      }
      found += hits.length;
      return hits;
    });
    status.textContent = !found ? t.none
      : (found === 1 ? t.foundOne : t.found.replace('{count}', found));
    status.style.color = found ? '#12805a' : '#b05b56';
    Plotly.restyle(gd, {selectedpoints: picked});
  }

  input.addEventListener('input', search);
  clear.addEventListener('click', function () { input.value = ''; search(); });
})();
"""


def search_box(texts: Texts) -> dict:
    """Teksterne til søgefeltet, som scriptet bygger ud fra."""
    return {
        "label": texts.search_label,
        "placeholder": texts.search_placeholder,
        "hint": texts.search_hint,
        "found": texts.search_found,
        "foundOne": texts.search_found_one,
        "none": texts.search_none,
        "clear": texts.search_clear,
    }


def search_script(fig: "go.Figure") -> str | None:
    """Returnerer søge-scriptet hvis figuren har et søgefelt."""
    meta = fig.layout.meta or {}
    if not meta.get("soegning"):
        return None
    return _SEARCH_SCRIPT.replace("__PLACE__", _PLACE_OVERLAY)


def colour_key(title: str, items: Sequence[tuple[str, str]]) -> dict:
    """Beskrivelsen af farveforklaringen, som scriptet bygger ud fra."""
    return {
        "title": title,
        "items": [{"label": label, "colour": colour} for label, colour in items],
    }


def colour_key_script(fig: "go.Figure") -> str | None:
    """Returnerer forklarings-scriptet hvis figuren har en farvekode."""
    meta = fig.layout.meta or {}
    if not meta.get("farvekode"):
        return None
    return _COLOUR_KEY_SCRIPT.replace("__PLACE__", _PLACE_OVERLAY)


def reset_button(texts: Texts = DANISH) -> dict:
    """Knappen der nulstiller alle filterrækker. Håndteres af scriptet."""
    return dict(label=texts.reset_button, method="skip", args=[{}])


def _reset_label(fig: "go.Figure") -> str:
    """
    Nulstil-knappens tekst, læst af figuren selv.

    Scriptet bruger teksten som sidste udvej til at genkende knappen, og
    figuren kan være tegnet på engelsk. Læses den af figuren, passer den
    altid til den udgave scriptet sidder i.
    """
    meta = fig.layout.meta or {}
    index = meta.get("reset")
    menus = fig.layout.updatemenus or ()
    if index is None or not (0 <= int(index) < len(menus)):
        return RESET_LABEL
    buttons = menus[int(index)].buttons or ()
    return str(buttons[0].label) if buttons else RESET_LABEL


def filter_script(fig: "go.Figure") -> str | None:
    """
    Returnerer filter-scriptet hvis figuren har filterknapper.

    Etiketten på nulstil-knappen sættes ind her, så scriptet kan genkende
    knappen på teksten hvis menu-identiteten skulle glippe.
    """
    meta = fig.layout.meta or {}
    if not meta.get("filters") and not meta.get("krav"):
        return None
    script = _FILTER_SCRIPT.replace("__RESET_LABEL__", _reset_label(fig))
    for token, colour in (
        ("__ON_EDGE__", BUTTON_ON_EDGE), ("__OFF_EDGE__", BUTTON_OFF_EDGE),
        ("__ON__", BUTTON_ON), ("__OFF__", BUTTON_OFF),
    ):
        script = script.replace(token, colour)
    return script.replace("__PREFIX__", MENU_NAME_PREFIX)


def stack_button_rows(
    groups: Sequence[tuple[str, str | None, list[dict]]],
    y_start: float,
    x_offset: float | None = None,
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
    # Alle rækker begynder samme sted — ved den bredeste overskrift. Ellers
    # rykkede hver række sit eget stykke ind, alt efter hvor lang dens
    # overskrift var, og knapperne stod trappeformet.
    offset = x_offset if x_offset is not None else max(
        (_label_width(label) for label, _, buttons in groups if buttons),
        default=0.0,
    )
    for label, dimension, buttons in groups:
        if not buttons:
            continue
        row_menus, rows = flow_button_menus(
            buttons,
            y_start=y,
            x_offset=offset,
            style=row_colours(dimension),
        )
        menus.extend(row_menus)
        dimensions.extend([dimension] * len(row_menus))
        if label:
            annotations.append(_row_label(label, y, offset))
        y -= rows * BUTTON_ROW_GAP
        total_rows += rows
    return menus, annotations, total_rows, dimensions


#: Markerer den menu der rummer nulstil-knappen.
RESET_DIMENSION = "_reset"

#: Forstavelsen på menu-navnene scriptet genkender knapperne på.
MENU_NAME_PREFIX = "menu-"


def number_menus(menus: list[dict]) -> list[dict]:
    """
    Giver hver menu et navn med sin egen plads i.

    Scriptet skal kunne genkende hvilken knap der blev trykket på. At
    sammenligne objekter dur ikke: en kravknap laver en ``relayout``, og så
    bygger Plotly menuerne forfra, hvorefter det klikkede objekt ikke længere
    er det samme som det i layoutet. Navnet overlever den ombygning.
    """
    for index, menu in enumerate(menus):
        menu["name"] = f"{MENU_NAME_PREFIX}{index}"
    return menus


def row_colours(dimension: str | None) -> dict:
    """Farverne til en knaprække, udledt af hvad rækken gør."""
    if dimension == RESET_DIMENSION:
        return neutral_colours()
    if dimension is None:  # fremhæver kun, skjuler ingenting
        return highlight_colours()
    return filter_colours()


def filter_metadata(dimensions: Sequence[str | None]) -> dict:
    """
    Oversætter menu-rækkefølgen til det opslag scriptet skal bruge.

    Nøglen er menuens plads i ``updatemenus``; værdien er dimensionen.
    Menuer uden dimension udelades. Nulstil-knappen er ikke et filter, men
    dens plads skal med, så scriptet kan kende den igen.
    """
    reset = next(
        (i for i, dimension in enumerate(dimensions) if dimension == RESET_DIMENSION),
        None,
    )
    return {
        "filters": {
            str(index): dimension
            for index, dimension in enumerate(dimensions)
            if dimension and dimension != RESET_DIMENSION
        },
        "reset": reset,
    }


def flow_button_menus(
    buttons: Sequence[dict],
    y_start: float,
    x_offset: float = 0.0,
    style: Mapping[str, object] | None = None,
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
                **(style or {}),
            )
        )
        x += width + spacing
    return menus, rows


def category_zone_shapes(
    cfg: Config, scale: "YScale | None" = None
) -> tuple[list[dict], list[dict]]:
    return band_shapes(
        cfg.category_bands,
        CATEGORY_COLOURS,
        fill_opacity=0.08,
        label_zones=False,
        scale=scale,
    )


def volume_zone_shapes(
    level: str, cfg: Config, texts: Texts = DANISH, scale: "YScale | None" = None
) -> tuple[list[dict], list[dict]]:
    return band_shapes(
        cfg.volume_zones.get(level, {}),
        VOLUME_ZONE_COLOURS,
        fill_opacity=0.10,
        label_zones=True,
        label_of=texts.volume_zone,
        scale=scale,
    )


# --- Fælles layout -----------------------------------------------------------


def _subtitle(
    cfg: Config, dates: ReferenceDates, extra: str, texts: Texts = DANISH
) -> str:
    parts = [
        texts.existing_customers.format(
            start=f"{dates.window_start:%m-%Y}",
            end=f"{dates.today:%m-%Y}",
            months=cfg.existing_customer_months,
        ),
        texts.turnover_window.format(months=cfg.turnover_window_months),
    ]
    # Grafen bliver sendt videre uden Excel-rapporten, så det skal kunne ses
    # på figuren selv at noget er sorteret fra.
    note = texts.gm_limit_note(cfg.gm_limit_min_pct, cfg.gm_limit_max_pct)
    if note:
        parts.append(note)
    if extra:
        parts.append(extra)
    return "  |  ".join(parts)


#: Mindste bredde af det lineære bælte omkring nul, i kroner.
SYMLOG_MIN_THRESHOLD = 1_000.0

#: Hvilke tal der får et mærke på y-aksen inden for hver tierpotens.
SYMLOG_TICK_MULTIPLIERS = (1, 2, 5)

#: Hvor meget lodret plads det lineære bælte omkring nul får, målt i
#: tierpotenser. 0,5 betyder at strækningen fra 0 op til bæltets kant fylder
#: det halve af en tierpotens. Uden den ville bæltet fylde en hel potens i
#: hver retning, og så stod der et stort tomt hul omkring nul hvor der sjældent
#: er noget at se.
SYMLOG_LINEAR_SCALE = 0.5

#: Mindste afstand mellem to mærker på y-aksen, i tierpotenser. Mærkerne
#: uden for det lineære bælte ligger mindst 0,30 fra hinanden (log10 af 2),
#: så det er kun inde i bæltet der tyndes ud.
SYMLOG_MIN_TICK_GAP = 0.15


@dataclass(frozen=True)
class YScale:
    """
    Y-aksens skala. Enten almindelig log, eller symlog hvis der er nuller
    eller negative tal at vise.

    En logaritmisk akse kan ikke vise nul eller negative tal — ``log10`` af
    dem findes ikke — og varer med negativ omsætning (kreditnotaer,
    returvarer) forsvandt derfor fra item-plottet. Plotly har ingen indbygget
    symlog-akse, så den laves her: data omregnes selv, og aksen sættes til
    lineær med mærker der står ved de rigtige kronebeløb.

    Omregningen er, med ``L = SYMLOG_LINEAR_SCALE``::

        |v| <= C :   L * v / C                      (lineær omkring nul)
        |v| >  C :   sign(v) * (L + log10(|v|/C))

    De to stykker mødes i ``|v| = C``, hvor begge giver ``L``, så kurven ikke
    knækker. ``C`` lægges ved den mindste positive værdi der skal vises, så
    det lineære bælte dækker netop det uinteressante område omkring nul og
    ikke klemmer de rigtige tal sammen.
    """

    symmetric: bool
    threshold: float = SYMLOG_MIN_THRESHOLD

    @classmethod
    def for_values(cls, values: Sequence[float]) -> "YScale":
        numbers = _finite(values)
        if not numbers or all(v > 0 for v in numbers):
            return cls(symmetric=False)
        # Bæltet lægges ved den mindste POSITIVE værdi, ikke ved den mindste
        # af alle. Ellers kunne ét enkelt negativt punkt trække bæltet ned og
        # give den negative halvdel en tredjedel af aksen for sin egen skyld.
        positive = [v for v in numbers if v > 0]
        reference = min(positive) if positive else min(abs(v) for v in numbers if v)
        decade = 10.0 ** np.floor(np.log10(reference))
        return cls(symmetric=True, threshold=max(decade, SYMLOG_MIN_THRESHOLD))

    def to_axis(self, values: Sequence[float] | pd.Series) -> np.ndarray:
        """Omregner data til den koordinat punktet tegnes ved."""
        array = np.asarray(values, dtype=float)
        if not self.symmetric:
            return array
        magnitude = np.abs(array)
        with np.errstate(divide="ignore", invalid="ignore"):
            far = np.sign(array) * (
                SYMLOG_LINEAR_SCALE + np.log10(magnitude / self.threshold)
            )
        near = SYMLOG_LINEAR_SCALE * array / self.threshold
        return np.where(magnitude <= self.threshold, near, far)

    def point(self, value: float) -> float:
        """Samme omregning for et enkelt tal — til zoner og referencelinjer."""
        return float(self.to_axis([value])[0])

    def _ticks(self, numbers: Sequence[float]) -> tuple[list[float], list[str]]:
        """
        Mærkerne på aksen: pæne kronebeløb, spredt som på en log-akse.

        Der laves også kandidater et par tierpotenser under det lineære
        bælte, så et lille negativt tal ikke ender uden et mærke i nærheden.
        Inde i bæltet ligger tallene lineært og kan derfor komme til at stå
        oven i hinanden, så mærkerne tyndes ud til sidst.
        """
        biggest = max((abs(v) for v in numbers), default=self.threshold)
        top = int(np.ceil(np.log10(max(biggest, self.threshold)))) + 1
        start = int(np.floor(np.log10(self.threshold))) - 2

        wanted = {0.0}
        for power in range(start, top + 1):
            for multiplier in SYMLOG_TICK_MULTIPLIERS:
                value = multiplier * 10.0**power
                wanted.update((value, -value))

        low, high = min(numbers), max(numbers)
        inside = sorted(v for v in wanted if low <= v <= high)
        kept = self._thin_out(inside)
        return [self.point(v) for v in kept], [f"{v:,.0f}" for v in kept]

    def _thin_out(self, values: Sequence[float]) -> list[float]:
        """
        Fjerner mærker der ville stå oven i hinanden.

        Der arbejdes udad fra nul i begge retninger, så nulpunktet altid
        beholdes og det er de tætte naboer der ryger.
        """
        has_zero = any(v == 0 for v in values)
        kept: list[float] = [0.0] if has_zero else []
        for side in (
            sorted(v for v in values if v > 0),
            sorted((v for v in values if v < 0), reverse=True),
        ):
            # Nulpunktet er allerede sat, så de to halvdele måles begge fra
            # nul og ud. Ellers beholdt hver side sit første mærke uanset
            # hvor tæt på nul det lå, og de to endte oven i hinanden.
            last: float | None = 0.0 if has_zero else None
            for value in side:
                position = self.point(value)
                if last is None or abs(position - last) >= SYMLOG_MIN_TICK_GAP:
                    kept.append(value)
                    last = position
        return sorted(kept)

    def axis_dict(self, title: str, values: Sequence[float]) -> dict:
        """Hele y-aksen, klar til ``update_layout``."""
        axis = dict(title=title, gridcolor=GRID_COLOUR)
        if not self.symmetric:
            axis.update(type="log", tickformat=",.0f")
            span = axis_range(values, log=True)
            if span:
                axis["range"] = span
            return axis

        numbers = _finite(values)
        axis["type"] = "linear"
        if not numbers:
            return axis
        # Mærkerne skal dække hele aksen, også den luft der lægges til, så
        # de beregnes på et interval der er strakt lige så meget som aksen.
        span = axis_range(self.to_axis(numbers), log=False)
        if span:
            axis["range"] = span
            edges = [self._from_axis(span[0]), self._from_axis(span[1])]
        else:
            edges = [min(numbers), max(numbers)]
        tickvals, ticktext = self._ticks(edges)
        axis.update(tickvals=tickvals, ticktext=ticktext, zeroline=True,
                    zerolinecolor="#999999", zerolinewidth=1)
        return axis

    def _from_axis(self, position: float) -> float:
        """Den omvendte vej: fra koordinat tilbage til kroner."""
        if not self.symmetric:
            return position
        if abs(position) <= SYMLOG_LINEAR_SCALE:
            return position * self.threshold / SYMLOG_LINEAR_SCALE
        return float(
            np.sign(position)
            * self.threshold
            * 10.0 ** (abs(position) - SYMLOG_LINEAR_SCALE)
        )


def _finite(values: Sequence[float]) -> list[float]:
    return [
        float(v) for v in values if v is not None and not pd.isna(v) and np.isfinite(v)
    ]


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
    numbers = _finite(values)
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
    texts: Texts = DANISH,
    scale: "YScale | None" = None,
) -> dict:
    """
    Akserne. X er altid lineær, Y altid logaritmisk.

    Gross Margin % ligger inden for et snævert interval og skal læses som
    procentpoint, så den hører hjemme på en lineær akse. Omsætningen spænder
    derimod over flere størrelsesordener — fra små tusinder til mange
    millioner — og på en lineær akse ville alt andet end de største kunder
    klumpe sammen nede ved nul.

    Er der nuller eller negative tal at vise, bliver y-aksen symlog i stedet
    (se ``YScale``). ``y_values`` er altid de rå kronebeløb — omregningen
    sker inde i skalaen — og ``scale`` skal være den samme som punkterne
    blev tegnet med.
    """
    _ = cfg  # akserne afhænger ikke længere af indstillinger
    x_axis = dict(
        title=texts.x_axis,
        type="linear",
        gridcolor=GRID_COLOUR,
    )
    if scale is None:
        scale = YScale.for_values(y_values)
    y_axis = scale.axis_dict(y_title, y_values)
    x_range = axis_range(x_values, log=False)
    if x_range:
        x_axis["range"] = x_range
    return dict(xaxis=x_axis, yaxis=y_axis)


# --- Kundegruppe-plot --------------------------------------------------------


def group_scatter(
    per_group: pd.DataFrame,
    cfg: Config,
    dates: ReferenceDates,
    title_suffix: str = "",
    texts: Texts = DANISH,
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

    has_kam = KAM in data.columns and data[KAM].notna().any()
    kam_values = sort_kams(data[KAM].dropna().unique().tolist()) if has_kam else []

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

    # Skalaen skal kendes inden det første punkt tegnes: er der kunder med
    # nul eller negativ omsætning, tegnes alle punkter på en symlog-akse.
    scale = YScale.for_values(data["samlet_turnover_window"].tolist())

    fig = go.Figure()
    category_order: list[str] = []
    trace_categories: list[str] = []
    trace_types: list[object] = []
    trace_kams: list[object] = []
    trace_segments: list[object] = []

    for row in ordered.to_dict("records"):
        name = row[GROUP]
        category = str(row.get("Kundekategori") or "-")
        label = category if category != "-" else texts.no_category
        if category not in category_order:
            category_order.append(category)

        customer_type = row.get("Kundetype")
        shown_type = texts.customer_type(customer_type)
        segment = row.get(INDUSTRY_SEGMENT)
        segment = segment if pd.notna(segment) else None
        kam = row.get(KAM) if has_kam else None
        kam = kam if kam is not None and pd.notna(kam) else None

        trace_categories.append(category)
        trace_types.append(shown_type)
        trace_segments.append(segment)
        trace_kams.append(kam)

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
            texts.hover_gm + ": %{x:.1f}%",
            texts.hover_turnover + ": %{customdata[0]:,.0f} DKK",
            f"{texts.hover_customer_type}: {shown_type}",
            f"{texts.hover_category}: {category}",
        ]
        if segment is not None:
            hover.append(f"{texts.hover_segment}: {segment}")
        if kam is not None:
            hover.append(f"{texts.hover_kam}: {kam}")

        fig.add_trace(
            go.Scatter(
                x=[row["samlet_GM"] * 100],
                y=[scale.point(row["samlet_turnover_window"])],
                # Hover skal vise kroner, ikke aksens koordinat.
                customdata=[[row["samlet_turnover_window"]]],
                mode="markers+text",
                name=str(name),
                legendgroup=category,
                legendgrouptitle_text=texts.category_group.format(category=label),
                text=[str(name)],
                textposition="top right",
                textfont=dict(size=9),
                meta={
                    "kundetype": shown_type,
                    "kategori": category,
                    "kam": kam,
                },
                marker=dict(
                    size=10,
                    color=colour,
                    line=dict(color=edge_colour, width=edge_width),
                ),
                hovertemplate="<br>".join(hover) + "<extra></extra>",
            )
        )

    shapes, annotations = category_zone_shapes(cfg, scale)

    types_present = [
        texts.customer_type(t) for t in CUSTOMER_TYPE_ORDER
        if texts.customer_type(t) in trace_types
    ]
    button_groups: list[tuple[str, str | None, list[dict]]] = [
        (texts.row_customer_type, "kundetype", toggle_buttons(types_present, trace_types)),
        (texts.row_category, "kategori", toggle_buttons(category_order, trace_categories)),
    ]
    if has_kam and kam_values:
        button_groups.append(
            (texts.row_kam, "kam", toggle_buttons(kam_values, trace_kams))
        )
    if has_industry and segments and not colour_by_segment:
        button_groups.append(
            (
                texts.row_segment,
                None,  # fremhæver kun, filtrerer ikke
                _segment_highlight_buttons(segments, trace_segments),
            )
        )
    # Nulstil står nederst, under de rækker den nulstiller.
    button_groups.append(("", RESET_DIMENSION, [reset_button(texts)]))

    # Farvekoden ligger i et bælte mellem x-aksen og første knaprække, så
    # rækkerne skubbes én bæltehøjde længere ned.
    menus, row_labels, button_rows, dimensions = stack_button_rows(
        button_groups, y_start=first_row_y(overlays=1)
    )
    annotations = annotations + row_labels

    # Farveforklaringen lægges uden for grafen af scriptet. Den skal vise det
    # farven RENT FAKTISK følger — kundetype eller branche.
    if colour_by_segment:
        key = colour_key(
            texts.key_segment,
            [(str(segment), segment_colours[segment]) for segment in segments],
        )
    else:
        key = colour_key(
            texts.key_customer_type,
            [
                (texts.customer_type(t), CUSTOMER_TYPE_COLOURS[t])
                for t in CUSTOMER_TYPE_ORDER
                if texts.customer_type(t) in trace_types
            ],
        )

    # Udsnittet står i overskriften, ikke i undertitlen: så kan man se
    # hvilket plot man har foran sig uden at læse med småt.
    subtitle_extra = texts.edge_is_segment if (has_industry and not colour_by_segment) else ""

    fig.update_layout(
        title=dict(
            text=(
                f"{texts.plot_title(texts.group_title, title_suffix)}<br>"
                f"<sup>{_subtitle(cfg, dates, subtitle_extra, texts)}</sup>"
            ),
            font=dict(size=13),
        ),
        shapes=shapes,
        annotations=annotations,
        updatemenus=number_menus(menus),
        meta={**filter_metadata(dimensions), "farvekode": key},
        legend=dict(
            title=texts.legend_title,
            itemclick="toggle",
            itemdoubleclick="toggleothers",
            groupclick="toggleitem",
            tracegroupgap=8,
        ),
        hovermode="closest",
        plot_bgcolor="white",
        margin=dict(t=PLOT_TOP_MARGIN, b=button_area_margin(button_rows, overlays=1)),
        width=PLOT_WIDTH,
        height=figure_height(button_rows, overlays=1),
        **_axes(
            cfg,
            texts.group_y_axis.format(months=cfg.turnover_window_months),
            x_values=(data["samlet_GM"] * 100).tolist(),
            y_values=data["samlet_turnover_window"].tolist(),
            texts=texts,
            scale=scale,
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
    texts: Texts = DANISH,
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
    # Varer uden et tal kan ikke placeres; varer med nul eller negativ
    # omsætning kan — y-aksen bliver symlog når der er nogen.
    data = data[data[WINDOW_ITEM].notna()]
    scale = YScale.for_values(data[WINDOW_ITEM].tolist())

    categories_by_group, turnover_by_group = _group_categories(data, cfg)
    customer_groups = sorted(
        data[GROUP].dropna().unique().tolist(),
        key=lambda name: (
            category_sort_key(categories_by_group.get(name, "-")),
            -float(turnover_by_group.get(name, 0) or 0),
        ),
    )
    group_colours = _colour_map(sorted(data[GROUP].dropna().unique().tolist()))

    has_kam = KAM in data.columns and data[KAM].notna().any()
    kam_values = sort_kams(data[KAM].dropna().unique().tolist()) if has_kam else []

    fig = go.Figure()
    category_order: list[str] = []
    trace_categories: list[str] = []
    trace_kams: list[object] = []

    for name in customer_groups:
        block = data[data[GROUP] == name]
        if block.empty:
            continue
        category = categories_by_group.get(name, "-")
        label = category if category != "-" else texts.no_category
        if category not in category_order:
            category_order.append(category)
        trace_categories.append(category)
        # KAM er slået op pr. kundegruppe, så alle en kundes varer hører til
        # samme KAM og kan tændes og slukkes under ét.
        kam = block[KAM].dropna().iloc[0] if has_kam and block[KAM].notna().any() else None
        trace_kams.append(kam)

        fig.add_trace(
            go.Scatter(
                x=block[ITEM_GM] * 100,
                y=scale.to_axis(block[WINDOW_ITEM]),
                mode="markers+text",
                name=str(name),
                legendgroup=category,
                legendgrouptitle_text=texts.category_group.format(category=label),
                text=block[ITEM_NO].astype(str),
                textposition="top right",
                textfont=dict(size=8),
                meta={"kategori": category, "kam": kam},
                marker=dict(
                    size=7,
                    color=group_colours[name],
                    line=dict(color="black", width=0.4),
                ),
                # Søgningen markerer de fundne punkter; resten tones ned, så
                # man kan se hvor varen ligger i forhold til alle de andre.
                selected=dict(marker=dict(size=13, opacity=1)),
                unselected=dict(marker=dict(opacity=0.12)),
                # Hover skal vise kroner, ikke aksens koordinat, så beløbet
                # følger med som data frem for at blive læst af y.
                customdata=np.column_stack(
                    [
                        block[GROUP].astype(str),
                        _last_sold(block),
                        block[WINDOW_ITEM].to_numpy(),
                    ]
                ),
                hovertemplate=(
                    "<b>%{text}</b><br>"
                    f"{texts.hover_customer_group}: %{{customdata[0]}}<br>"
                    f"{texts.hover_category}: {category}<br>"
                    + (f"{texts.hover_kam}: {kam}<br>" if kam is not None else "")
                    + f"{texts.hover_gm}: %{{x:.1f}}%<br>"
                    + f"{texts.hover_turnover}: %{{customdata[2]:,.0f}} DKK<br>"
                    + f"{texts.hover_last_sold}: %{{customdata[1]}}<br>"
                    + "<extra></extra>"
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
    shapes, zone_annotations = volume_zone_shapes(default_level, cfg, texts, scale)

    # Knapperne under plottet stables: først kravniveau, så kategori-blokke,
    # så KAM — og nederst nulstil-knappen.
    level_label = texts.row_level
    level_names = [texts.level_button.format(level=level) for level in levels]

    button_groups: list[tuple[str, str | None, list[dict]]] = [
        (texts.row_category, "kategori", toggle_buttons(category_order, trace_categories)),
    ]
    if has_kam and kam_values:
        button_groups.append(
            (texts.row_kam, "kam", toggle_buttons(kam_values, trace_kams))
        )
    button_groups.append(("", RESET_DIMENSION, [reset_button(texts)]))

    # Alle rækker — også kravrækken — begynder ved den bredeste overskrift, så
    # knapperne står på linje i stedet for trappeformet.
    offset = max(
        [_label_width(level_label)]
        + [_label_width(label) for label, _, buttons in button_groups if buttons]
    )

    # Søgefeltet ligger i et bælte mellem x-aksen og første knaprække, så
    # rækkerne begynder én bæltehøjde længere nede.
    top_row = first_row_y(overlays=1)

    # Hvor mange rækker kravknapperne fylder afhænger kun af deres bredde, så
    # det kan tælles før de bygges færdige — og resten kan lægges nedenunder.
    level_rows = (
        flow_button_menus(
            [dict(label=name) for name in level_names],
            y_start=top_row,
            x_offset=offset,
        )[1]
        if level_names
        else 0
    )
    below_levels = top_row - max(level_rows, 1) * BUTTON_ROW_GAP

    menus_below, row_labels, rows_below, dimensions_below = stack_button_rows(
        button_groups, below_levels, x_offset=offset
    )

    # Overskrifterne skal med i HVER kravknaps annotationer: en relayout
    # udskifter hele annotations-listen, så uden dem forsvandt rækkernes
    # navne så snart man skiftede niveau.
    static_annotations = [_row_label(level_label, top_row, offset)] + row_labels

    level_buttons = []
    for level, name in zip(levels, level_names):
        level_shapes, level_annotations = volume_zone_shapes(level, cfg, texts, scale)
        level_buttons.append(
            dict(
                label=name,
                method="relayout",
                args=[
                    {
                        "shapes": level_shapes,
                        "annotations": level_annotations + static_annotations,
                    }
                ],
            )
        )

    # Hver kravknap får sin egen menu. Ellers deler alle fire knapper én
    # baggrundsfarve, og så kan den valgte ikke skille sig ud som grøn.
    menus: list[dict] = []
    if level_buttons:
        menus, _ = flow_button_menus(
            level_buttons, y_start=top_row, x_offset=offset
        )
        for menu, level in zip(menus, levels):
            menu.update(level_colours(level == default_level))

    level_menus = list(range(len(menus)))
    chosen_level = levels.index(default_level) if default_level in levels else None
    menus.extend(menus_below)
    # Kravmenuerne ligger forrest og er ikke filtre, så de fylder hver en plads.
    dimensions = ([None] * len(level_menus)) + dimensions_below
    annotations = zone_annotations + static_annotations
    # Plads til kravrækkerne plus de rækker de øvrige knapper fylder.
    button_rows = max(level_rows, 1) + rows_below

    fig.update_layout(
        title=dict(
            text=(
                f"{texts.plot_title(texts.item_title, title_suffix)}<br>"
                f"<sup>{_subtitle(cfg, dates, '', texts)}</sup>"
            ),
            font=dict(size=13),
        ),
        shapes=shapes,
        annotations=annotations,
        updatemenus=number_menus(menus),
        meta={
            **filter_metadata(dimensions),
            "krav": level_menus,
            "valgt": chosen_level,
            "soegning": search_box(texts),
        },
        margin=dict(t=PLOT_TOP_MARGIN, b=button_area_margin(button_rows, overlays=1)),
        legend=dict(
            title=texts.legend_title,
            itemclick="toggle",
            itemdoubleclick="toggleothers",
            groupclick="toggleitem",
            tracegroupgap=8,
        ),
        hovermode="closest",
        plot_bgcolor="white",
        width=PLOT_WIDTH,
        height=figure_height(button_rows, overlays=1),
        **_axes(
            cfg,
            texts.item_y_axis.format(months=cfg.turnover_window_months),
            x_values=(data[ITEM_GM] * 100).tolist(),
            y_values=data[WINDOW_ITEM].tolist(),
            texts=texts,
            scale=scale,
        ),
    )
    return fig


def _last_sold(block: pd.DataFrame) -> list[str]:
    """
    Seneste salgsmåned pr. vare, skrevet som ÅÅÅÅ-MM til hover-boksen.

    Mangler datoen — hvilket den ikke burde, men data er data — vises en
    tankestreg frem for teksten "NaT".
    """
    if LAST_ACTIVITY not in block.columns:
        return ["–"] * len(block)
    months = pd.to_datetime(block[LAST_ACTIVITY], errors="coerce")
    return [("–" if pd.isna(m) else f"{m:%Y-%m}") for m in months]


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

#: Plotly-biblioteket lægges ind i hver HTML-fil i stedet for at blive hentet
#: fra internettet. Filen bliver ~4 MB større, men til gengæld er den komplet:
#: den virker uden netværk, bag en firewall der blokerer cdn.plot.ly, og efter
#: at være sendt videre til en kollega som en enkelt vedhæftet fil. Hentes
#: biblioteket udefra, ser en tom side nøjagtig ud som en tom analyse.
INCLUDE_PLOTLYJS = True


def write_html(fig: "go.Figure", path: str, label: str, log: Log = print) -> None:
    scripts = [
        s for s in (search_script(fig), colour_key_script(fig), filter_script(fig)) if s
    ]
    pio.write_html(
        fig, path, include_plotlyjs=INCLUDE_PLOTLYJS, post_script=scripts or None
    )
    log(f"[{label}] gemt til: {path}")

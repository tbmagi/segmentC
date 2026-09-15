"""Tests af plot-opbygningen: akseintervaller og knappernes placering."""

import numpy as np
import pandas as pd
import pytest

from segmentering.config import CUSTOMER_TYPE_COLOURS, Config
from segmentering.dataio import GROUP, INDUSTRY_SEGMENT, ITEM_NO, KAM, ReferenceDates
from segmentering.metrics import (
    GP_SUM,
    ITEM_GM,
    TURNOVER_SUM,
    WINDOW_GROUP,
    WINDOW_ITEM,
)
from segmentering.plots import (
    BUTTON_ROW_GAP,
    TOGGLE_GUARD,
    filter_script,
    X_MAX_ZONE,
    Y_MAX_ZONE,
    _segment_highlight_buttons,
    axis_range,
    flow_button_menus,
    group_scatter,
    item_scatter,
    toggle_buttons,
)

DATES = ReferenceDates(
    today=pd.Timestamp("2026-05-01"), window_start=pd.Timestamp("2024-05-01")
)


# --- Akseintervaller ---------------------------------------------------------


def test_range_covers_the_values_with_a_margin():
    low, high = axis_range([10, 50], log=False)
    assert low < 10 and high > 50


def test_log_range_is_returned_in_powers_of_ten():
    low, high = axis_range([1_000, 1_000_000], log=True)
    assert 2.5 < low < 3.0
    assert 6.0 < high < 6.5


def test_log_range_ignores_zero_and_negative_values():
    """
    log10(0) er minus uendelig. Kategori D starter ved turnover 0, så uden
    denne filtrering trak aksen ned i det meningsløse og pressede alle
    punkter op i toppen.
    """
    low, _ = axis_range([0, -5, 1_000, 10_000], log=True)
    assert np.isfinite(low) and low > 2


def test_range_is_none_when_nothing_is_plottable():
    assert axis_range([], log=False) is None
    assert axis_range([0, -1], log=True) is None
    assert axis_range([float("nan")], log=False) is None


def test_single_value_still_gets_a_usable_range():
    low, high = axis_range([500], log=False)
    assert low < 500 < high


def sample_groups():
    return pd.DataFrame(
        [
            {
                GROUP: f"KUNDE {name}",
                "samlet_GM": gm,
                "samlet_turnover_window": turnover,
                "samlet_turnover": turnover,
                "samlet_GP": turnover * gm,
                "Kundetype": "Eksisterende",
                "Kundekategori": "B+",
                INDUSTRY_SEGMENT: segment,
            }
            for name, gm, turnover, segment in [
                ("A", 0.30, 3_000_000, "Automotive"),
                ("B", 0.22, 2_000_000, "Medico"),
            ]
        ]
    )


def test_zones_do_not_dictate_the_group_axes():
    """
    Zonerne tegnes bevidst langt uden for data for at nå plottets kant.
    Uden et eksplicit interval lader Plotly dem bestemme udsnittet, og så
    ender alle kunder i et hjørne. Aksen skal følge data, ikke zonerne.
    """
    fig = group_scatter(sample_groups(), Config(), DATES)
    x_low, x_high = fig.layout.xaxis.range
    y_low, y_high = fig.layout.yaxis.range  # log10-enheder

    assert x_high < X_MAX_ZONE / 10, "x-aksen er strakt ud til zonernes yderkant"
    assert 20 < x_high < 60, f"x-aksen dækker ikke GM%-data pænt: {x_high}"
    assert 10 ** y_high < Y_MAX_ZONE / 1000, "y-aksen er strakt ud til zonernes loft"
    assert 10 ** y_low > 1_000, "y-aksen går alt for langt ned"
    assert 10 ** y_high > 3_000_000, "største kunde falder uden for aksen"


def sample_items():
    return pd.DataFrame(
        [
            {
                GROUP: "KUNDE A",
                ITEM_NO: f"70100{i}",
                TURNOVER_SUM: 100_000.0,
                GP_SUM: 30_000.0,
                WINDOW_ITEM: 400_000.0 + i,
                WINDOW_GROUP: 400_000.0 + i,
                ITEM_GM: 0.30,
            }
            for i in range(3)
        ]
    )


def groups_with_categories():
    """Fire kunder fordelt på to kategorier, to kundetyper og to KAM'er."""
    rows = [
        ("KUNDE A", 0.30, 9_000_000, "Eksisterende", "A+", "Automotive", "PHA"),
        ("KUNDE B", 0.10, 9_000_000, "Ny", "A-", "Medico", "TSP"),
        ("KUNDE C", 0.30, 3_000_000, "Eksisterende", "B+", "Automotive", "PHA"),
        ("KUNDE D", 0.10, 3_000_000, "Tidligere", "B-", None, "(Blank)"),
    ]
    return pd.DataFrame(
        [
            {
                GROUP: name,
                "samlet_GM": gm,
                "samlet_turnover_window": turnover,
                "samlet_turnover": turnover,
                "samlet_GP": turnover * gm,
                "Kundetype": kundetype,
                "Kundekategori": category,
                INDUSTRY_SEGMENT: segment,
                KAM: kam,
            }
            for name, gm, turnover, kundetype, category, segment, kam in rows
        ]
    )


def button_rows(fig):
    """Overskrifterne på knaprækkerne, i den rækkefølge de står."""
    return [
        a.text for a in fig.layout.annotations if a.text and a.text.endswith(":")
    ]


def test_group_plot_has_one_trace_per_customer():
    """
    Legenden skal kunne liste kunderne ved navn, og det kræver ét spor pr.
    kunde — ikke ét pr. kundetype.
    """
    fig = group_scatter(groups_with_categories(), Config(), DATES)
    assert len(fig.data) == 4
    assert {t.name for t in fig.data} == {"KUNDE A", "KUNDE B", "KUNDE C", "KUNDE D"}


def test_customers_are_grouped_by_category_in_the_legend():
    fig = group_scatter(groups_with_categories(), Config(), DATES)
    by_name = {t.name: t for t in fig.data}
    assert by_name["KUNDE A"].legendgroup == "A+"
    assert by_name["KUNDE A"].legendgrouptitle.text == "Kategori A+"
    assert by_name["KUNDE D"].legendgroup == "B-"


def test_categories_are_ordered_a_plus_a_minus_b_plus():
    fig = group_scatter(groups_with_categories(), Config(), DATES)
    assert [t.legendgroup for t in fig.data] == ["A+", "A-", "B+", "B-"]


def test_colour_still_follows_the_customer_type():
    fig = group_scatter(groups_with_categories(), Config(), DATES)
    by_name = {t.name: t for t in fig.data}
    assert by_name["KUNDE A"].marker.color == CUSTOMER_TYPE_COLOURS["Eksisterende"]
    assert by_name["KUNDE B"].marker.color == CUSTOMER_TYPE_COLOURS["Ny"]
    assert by_name["KUNDE D"].marker.color == CUSTOMER_TYPE_COLOURS["Tidligere"]


def test_customer_type_is_toggled_with_buttons_not_the_legend():
    """
    Legenden viser nu kunder, så Eksisterende/Ny/Tidligere skal have sin egen
    knaprække i stedet.
    """
    fig = group_scatter(groups_with_categories(), Config(), DATES)
    assert "Vis/skjul kundetype:" in button_rows(fig)
    labels = [m.buttons[0].label for m in fig.layout.updatemenus]
    assert {"Eksisterende", "Ny", "Tidligere"} <= set(labels)


def test_the_group_plot_has_the_same_button_rows_as_expected():
    fig = group_scatter(groups_with_categories(), Config(), DATES)
    assert button_rows(fig) == [
        "Vis/skjul kundetype:",
        "Vis/skjul kategori:",
        "Vis/skjul KAM:",
        "Fremhæv branche:",
    ]


def test_every_trace_carries_its_filter_values():
    """Scriptet matcher på trace.meta, så hvert spor skal bære sine værdier."""
    fig = group_scatter(groups_with_categories(), Config(), DATES)
    by_name = {t.name: t.meta for t in fig.data}
    assert by_name["KUNDE A"]["kundetype"] == "Eksisterende"
    assert by_name["KUNDE A"]["kategori"] == "A+"
    assert by_name["KUNDE A"]["kam"] == "PHA"
    assert by_name["KUNDE D"]["kam"] == "(Blank)"
    # Emne-type og produktion er også filterdimensioner nu
    assert {"emnetype", "geografi"} <= set(by_name["KUNDE A"])


def test_the_figure_says_which_menu_filters_on_what():
    fig = group_scatter(groups_with_categories(), Config(), DATES)
    filters = fig.layout.meta["filters"]
    menus = fig.layout.updatemenus
    for index, dimension in filters.items():
        label = menus[int(index)].buttons[0].label
        if dimension == "kundetype":
            assert label in {"Eksisterende", "Ny", "Tidligere"}
        elif dimension == "kategori":
            assert label in {"A+", "A-", "B+", "B-"}
        elif dimension == "kam":
            assert label in {"PHA", "TSP", "(Blank)"}
    # Fremhæv-knapperne er ikke filtre og må ikke stå i opslaget
    highlight = [
        i for i, m in enumerate(menus) if m.buttons[0].label == "Automotive"
    ]
    assert all(str(i) not in filters for i in highlight)


def test_the_item_plot_also_declares_its_filters():
    fig = item_scatter(sample_items(), Config(), DATES)
    filters = fig.layout.meta["filters"]
    assert set(filters.values()) <= {"kategori", "kam"}
    # Kravmenuen ligger forrest og er ikke et filter
    assert "0" not in filters


def test_the_filter_script_is_attached_when_there_are_filters():
    fig = group_scatter(groups_with_categories(), Config(), DATES)
    script = filter_script(fig)
    assert script and "plotly_buttonclicked" in script
    assert "legendonly" in script


def test_a_customer_without_a_category_still_gets_a_legend_group():
    frame = groups_with_categories()
    frame.loc[0, "Kundekategori"] = "-"
    fig = group_scatter(frame, Config(), DATES)
    by_name = {t.name: t for t in fig.data}
    assert by_name["KUNDE A"].legendgrouptitle.text == "Kategori Ingen kategori"


def test_the_x_axis_is_labelled_the_same_on_both_plots():
    group = group_scatter(sample_groups(), Config(), DATES)
    item = item_scatter(sample_items(), Config(), DATES)
    assert group.layout.xaxis.title.text == "Gross Margin (%)"
    assert item.layout.xaxis.title.text == "Gross Margin (%)"


def test_zones_do_not_dictate_the_item_axes():
    fig = item_scatter(sample_items(), Config(), DATES)
    assert fig.layout.xaxis.range[1] < X_MAX_ZONE / 10
    assert 10 ** fig.layout.yaxis.range[1] < Y_MAX_ZONE / 1000


# --- Knappernes placering ----------------------------------------------------


def button(label):
    return dict(label=label, method="restyle", args=[{}, []])


def positions(menus):
    return [(round(m["y"], 4), m["x"]) for m in menus]


def test_buttons_never_sit_on_top_of_each_other():
    """
    x-positionen blev tidligere lagt sammen og klippet ved 0.95. Så snart
    rækken var fuld, fik alle resterende knapper samme position og blev
    stablet oven på hinanden. Nu ombrydes der til en ny række i stedet.
    """
    labels = [
        "Automotive OEM",
        "Industriel automation",
        "Medico og pharma",
        "Vedvarende energi",
        "Forsvar og luftfart",
        "Hvidevarer",
        "Emballage og print",
        "Landbrugsmaskiner",
    ]
    menus, rows = flow_button_menus([button(l) for l in labels], y_start=-0.14)

    assert len(menus) == len(labels)
    assert len(set(positions(menus))) == len(labels), "to knapper deler position"
    assert rows > 1, "otte lange etiketter skal ombrydes til flere rækker"


def test_each_row_starts_over_at_the_left_edge():
    menus, rows = flow_button_menus(
        [button("Et ret langt segmentnavn her") for _ in range(6)], y_start=-0.14
    )
    by_row: dict[float, list[float]] = {}
    for menu in menus:
        by_row.setdefault(round(menu["y"], 4), []).append(menu["x"])
    assert len(by_row) == rows
    for xs in by_row.values():
        assert xs == sorted(xs), "knapper i en række skal gå fra venstre mod højre"
        assert xs[0] == pytest.approx(0.0), "hver række starter i venstre kant"


def test_buttons_stay_inside_the_plot_width():
    menus, _ = flow_button_menus([button(f"Kategori {i}") for i in range(12)], -0.14)
    assert all(0.0 <= m["x"] < 1.0 for m in menus)


def test_rows_are_stacked_downwards():
    menus, rows = flow_button_menus([button("Ganske langt navn") for _ in range(8)], -0.14)
    ys = sorted({round(m["y"], 4) for m in menus}, reverse=True)
    assert ys[0] == pytest.approx(-0.14)
    for earlier, later in zip(ys, ys[1:]):
        assert earlier - later == pytest.approx(BUTTON_ROW_GAP)


def test_toggle_buttons_only_record_the_press():
    """
    Knapperne ændrer ikke selv synligheden. De bruger method="skip", så Plotly
    kun husker om de er trykket ned; scriptet i den færdige HTML regner
    synligheden ud som fællesmængden af alle filterrækker.
    """
    buttons = toggle_buttons(["Anders", "Mette"], ["Anders", "Mette", "Anders"])
    assert [b["label"] for b in buttons] == ["Anders", "Mette"]
    for button in buttons:
        assert button["method"] == "skip"
        assert button["args"] == [{}] and button["args2"] == [{}]


def test_a_value_without_traces_gets_no_button():
    assert toggle_buttons(["Anders", "Ukendt"], ["Anders"]) == [
        b for b in toggle_buttons(["Anders", "Ukendt"], ["Anders"]) if b["label"] == "Anders"
    ]
    assert len(toggle_buttons(["Anders", "Ukendt"], ["Anders"])) == 1


def test_filters_do_not_overwrite_each_other():
    """
    Rækkerne skal begrænse hinanden, ikke overskrive hinanden.

    Med én knap pr. værdi der satte visible direkte, ville "vis Tidligere
    igen" tænde for ALLE tidligere kunder — også dem en KAM-knap havde slået
    fra. Derfor må knapperne ikke selv sætte visible.
    """
    for button in toggle_buttons(["Anders"], ["Anders", "Anders"]):
        for slot in ("args", "args2"):
            assert "visible" not in button[slot][0]


def test_highlight_buttons_carry_the_binding_guard():
    # Ét spor pr. kunde, så hvert spor har præcis ét segment.
    buttons = _segment_highlight_buttons(
        ["Automotive", "Medico"], ["Automotive", "Medico", None]
    )
    assert len(buttons) == 2
    for button in buttons:
        for slot in ("args", "args2"):
            assert len(button[slot][0]) > 1


def test_highlight_only_thickens_the_chosen_segment():
    buttons = _segment_highlight_buttons(
        ["Automotive", "Medico"], ["Automotive", "Medico", None]
    )
    automotive = next(b for b in buttons if b["label"] == "Automotive")
    widths = automotive["args"][0]["marker.line.width"]
    assert widths[0] > widths[1], "kun det valgte segment skal fremhæves"
    assert widths[2] == pytest.approx(0.5), "kunder uden segment får tynd kant"


def test_the_guard_does_not_disturb_the_markers():
    """Vagt-egenskaben skal sætte den værdi sporene allerede har."""
    attribute, value = TOGGLE_GUARD
    assert attribute == "marker.opacity"
    assert value == 1  # Plotlys standard – ændrer intet visuelt


def test_a_short_list_stays_on_one_row():
    menus, rows = flow_button_menus([button("A+"), button("A-")], -0.14)
    assert rows == 1
    assert len({m["y"] for m in menus}) == 1


def test_bottom_margin_grows_with_the_number_of_rows():
    """Knapperne må ikke havne uden for figuren når de fylder flere rækker."""
    many = pd.concat(
        [
            sample_groups().assign(**{INDUSTRY_SEGMENT: f"Branchesegment nummer {i}"})
            for i in range(6)
        ],
        ignore_index=True,
    )
    many[GROUP] = [f"KUNDE {i}" for i in range(len(many))]
    one_row = group_scatter(sample_groups(), Config(), DATES)
    several = group_scatter(many, Config(), DATES)
    assert several.layout.margin.b > one_row.layout.margin.b

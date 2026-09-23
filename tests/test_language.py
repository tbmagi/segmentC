"""
Tests af den engelske udgave af graferne.

Det vigtigste her er ikke oversættelsen af den enkelte gloser, men at de to
udgaver hænger sammen indvendigt: en knap hedder det samme som den værdi den
skal filtrere på, og tallene er de samme. Ellers ville den engelske graf se
rigtig ud og filtrere forkert.
"""

import os

import pandas as pd
import pytest

from segmentering.config import Config
from segmentering.dataio import GROUP, INDUSTRY_SEGMENT, ITEM_NO, KAM, ReferenceDates
from segmentering.language import DANISH, ENGLISH, ENGLISH_SUBFOLDER, LANGUAGES
from segmentering.metrics import (
    GP_SUM,
    ITEM_GM,
    LAST_ACTIVITY,
    TURNOVER_SUM,
    WINDOW_GROUP,
    WINDOW_ITEM,
)
from segmentering.plots import (
    PLOTLY_AVAILABLE,
    group_scatter,
    item_scatter,
    reset_button,
)

DATES = ReferenceDates(
    today=pd.Timestamp("2026-05-01"), window_start=pd.Timestamp("2024-05-01")
)

pytestmark = pytest.mark.skipif(not PLOTLY_AVAILABLE, reason="Plotly mangler")


def groups():
    rows = [
        ("KUNDE A", 0.30, 9_000_000, "Eksisterende", "A+", "Automotive", "PHA"),
        ("KUNDE B", 0.10, 9_000_000, "Ny", "A-", "Medico", "TSP"),
        ("KUNDE C", 0.30, 3_000_000, "Genopstået", "B+", "Automotive", "PHA"),
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


def items():
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
                LAST_ACTIVITY: pd.Timestamp("2026-03-01"),
            }
            for i in range(3)
        ]
    )


# --- Selve oversættelsen -----------------------------------------------------


def test_both_languages_fill_in_every_text():
    """En glemt tekst ville stå tom i grafen, ikke fejle."""
    for texts in LANGUAGES.values():
        for field, value in vars(texts).items():
            if isinstance(value, str):
                assert value.strip(), f"{texts.code}.{field} er tom"


def test_an_unknown_value_is_left_alone():
    """KAM-navne og brancher er data, ikke ord vi kan oversætte."""
    assert ENGLISH.customer_type("PHA") == "PHA"
    assert ENGLISH.volume_zone("Noget helt tredje") == "Noget helt tredje"
    assert ENGLISH.segment_label("Landbrugsmaskiner") == "Landbrugsmaskiner"


def test_danish_changes_nothing():
    assert DANISH.customer_type("Genopstået") == "Genopstået"
    assert DANISH.segment_label("Sinter - kun eksisterende kunder") == (
        "Sinter - kun eksisterende kunder"
    )


def test_a_compound_segment_label_is_translated_piece_by_piece():
    """Navnet sættes sammen i pipelinen, så hvert led oversættes for sig."""
    assert ENGLISH.segment_label("Støbe - kun eksisterende kunder") == (
        "Cast - existing customers only"
    )


# --- At figuren hænger sammen med sig selv -----------------------------------


def test_the_english_figure_speaks_english():
    fig = group_scatter(groups(), Config(), DATES, texts=ENGLISH)
    assert fig.layout.title.text.startswith(ENGLISH.group_title)
    assert "month window" in fig.layout.yaxis.title.text
    rows = [a.text for a in fig.layout.annotations if a.text and a.text.endswith(":")]
    assert ENGLISH.row_customer_type in rows
    assert ENGLISH.row_kam in rows


def test_the_buttons_match_the_values_they_filter_on():
    """
    Knappen filtrerer ved at sammenligne sin egen tekst med sporets ``meta``.
    Oversættes kun det ene af de to, holder den engelske graf op med at
    filtrere — derfor skal de to lister passe sammen.
    """
    for texts in (DANISH, ENGLISH):
        fig = group_scatter(groups(), Config(), DATES, texts=texts)
        filters = fig.layout.meta["filters"]
        for index, dimension in filters.items():
            label = fig.layout.updatemenus[int(index)].buttons[0].label
            values = {t.meta[dimension] for t in fig.data}
            assert label in values, f"{texts.code}: knappen '{label}' rammer ingenting"


def test_the_customer_types_are_translated_in_the_traces():
    fig = group_scatter(groups(), Config(), DATES, texts=ENGLISH)
    assert {t.meta["kundetype"] for t in fig.data} == {
        "Existing", "New", "Revived", "Former",
    }


def test_the_colour_key_lists_the_same_types_as_the_buttons():
    fig = group_scatter(groups(), Config(), DATES, texts=ENGLISH)
    key = fig.layout.meta["farvekode"]
    assert key["title"] == ENGLISH.key_customer_type
    labels = [item["label"] for item in key["items"]]
    assert labels == ["Existing", "New", "Revived", "Former"]


def test_the_reset_button_is_translated():
    assert reset_button(ENGLISH)["label"] == ENGLISH.reset_button
    fig = group_scatter(groups(), Config(), DATES, texts=ENGLISH)
    index = fig.layout.meta["reset"]
    assert fig.layout.updatemenus[index].buttons[0].label == ENGLISH.reset_button


def test_the_script_recognises_the_english_reset_button():
    """
    Scriptet kender nulstil-knappen på dens menu-plads, men falder tilbage
    på teksten. Den tekst skal komme fra figuren, ikke fra en dansk konstant.
    """
    from segmentering.plots import filter_script

    fig = group_scatter(groups(), Config(), DATES, texts=ENGLISH)
    assert ENGLISH.reset_button in filter_script(fig)
    assert DANISH.reset_button not in filter_script(fig)


def test_the_item_plot_is_translated_too():
    fig = item_scatter(items(), Config(), DATES, texts=ENGLISH)
    assert fig.layout.title.text.startswith(ENGLISH.item_title)
    box = fig.layout.meta["soegning"]
    assert box["label"] == ENGLISH.search_label
    assert box["clear"] == ENGLISH.search_clear
    assert ENGLISH.hover_last_sold in fig.data[0].hovertemplate
    rows = [a.text for a in fig.layout.annotations if a.text and a.text.endswith(":")]
    assert ENGLISH.row_level in rows


def test_the_volume_levels_are_translated():
    fig = item_scatter(items(), Config(), DATES, texts=ENGLISH)
    labels = [m.buttons[0].label for m in fig.layout.updatemenus]
    assert ENGLISH.level_button.format(level="A") in labels


def test_the_two_languages_plot_the_same_numbers():
    """Udgaverne bygger på ét resultat, så de kan ikke vise hver sit tal."""
    da = group_scatter(groups(), Config(), DATES, texts=DANISH)
    en = group_scatter(groups(), Config(), DATES, texts=ENGLISH)
    assert [t.name for t in da.data] == [t.name for t in en.data]
    for one, other in zip(da.data, en.data):
        assert list(one.x) == list(other.x)
        assert list(one.y) == list(other.y)
        assert one.marker.color == other.marker.color


# --- Indstillingen og mappen -------------------------------------------------


def test_the_english_copy_is_off_by_default():
    assert Config().english_copy is False


def render(tmp_path, english_copy, basename="test", parts=()):
    """Tegner kundegruppe-plottet for ét udsnit ned i ``tmp_path``."""
    from segmentering.pipeline import Segment, SegmentResult, render_plots

    cfg = Config(
        output_dir=str(tmp_path),
        output_basename=basename,
        write_excel=False,
        english_copy=english_copy,
        draw_group_plot=True,
        draw_item_plot=False,
    )
    result = SegmentResult(
        segment=Segment(
            label="Alle emner", sheet_prefix="", file_parts=parts, frame=items()
        ),
        per_group=groups(),
        per_item=items(),
        per_item_filtered=None,
        outliers=None,
    )
    render_plots(result, cfg, DATES, log=lambda *_: None)


def written(folder):
    return sorted(f for f in os.listdir(folder) if f.endswith(".html"))


def test_the_english_plots_land_in_their_own_folder(tmp_path):
    render(tmp_path, english_copy=True)

    danish = written(tmp_path)
    english = written(os.path.join(tmp_path, ENGLISH_SUBFOLDER))
    assert danish, "den danske graf blev ikke skrevet"
    assert len(english) == len(danish), "der mangler en engelsk udgave"


def test_the_english_filenames_are_english(tmp_path):
    """
    Mappen sendes videre til nogen der ikke læser dansk, så filnavnet må
    heller ikke være dansk.
    """
    render(tmp_path, english_copy=True, basename="kunde_segmentering",
           parts=("stoebe", "eks"))

    assert written(tmp_path) == ["kunde_segmentering_kundegruppe_stoebe_eks.html"]
    assert written(os.path.join(tmp_path, ENGLISH_SUBFOLDER)) == [
        "customer_segmentation_customer_group_cast_existing.html"
    ]


def test_a_basename_the_user_chose_is_left_alone(tmp_path):
    """Deres eget navn er deres ord — kun fabriksnavnet er vores at oversætte."""
    render(tmp_path, english_copy=True, basename="Q3_analyse", parts=("sinter",))

    assert written(tmp_path) == ["Q3_analyse_kundegruppe_sinter.html"]
    assert written(os.path.join(tmp_path, ENGLISH_SUBFOLDER)) == [
        "Q3_analyse_customer_group_sinter.html"
    ]


def test_nothing_extra_is_written_when_the_option_is_off(tmp_path):
    render(tmp_path, english_copy=False)
    assert not os.path.isdir(os.path.join(tmp_path, ENGLISH_SUBFOLDER))

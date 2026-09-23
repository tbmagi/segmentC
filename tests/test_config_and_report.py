"""Tests af konfiguration, filnavne og Excel-rapportens kolonner."""

import os

import pandas as pd
import pytest

from segmentering.config import Band, Config, OutputPaths, validate_bands
from segmentering.dataio import GROUP, ITEM_NO, KAM
from segmentering.dataio import ReferenceDates
from segmentering.excel_report import (
    SUMMARY_COLUMNS,
    parameter_sheet,
    prepare_item_sheet,
    prepare_summary_sheet,
)
from segmentering.metrics import (
    FIRST_ACTIVITY,
    GP_SUM,
    ITEM_GM,
    LAST_ACTIVITY,
    TURNOVER_SUM,
    WINDOW_GROUP,
    WINDOW_ITEM,
)


DATES = ReferenceDates(
    today=pd.Timestamp("2026-05-01"), window_start=pd.Timestamp("2024-05-01")
)


# --- Validering --------------------------------------------------------------


def test_overlapping_category_bands_are_rejected():
    """
    Overlappende bånd gjorde resultatet afhængigt af rækkefølgen. Nu fanges
    de med en besked der peger på de to bånd der er i konflikt.
    """
    bands = {"A": Band(1_000, None, 0.2), "B": Band(500, 2_000, 0.3)}
    with pytest.raises(ValueError, match="overlapper"):
        validate_bands(bands, "Kundekategori")


def test_adjacent_bands_are_allowed():
    bands = {"A": Band(1_000, None, 0.2), "B": Band(0, 1_000, 0.3)}
    validate_bands(bands, "Kundekategori")  # må ikke rejse


def test_volume_zones_may_overlap():
    """Volumen-områder tegnes oven på hinanden og bruges ikke til klassifikation."""
    zones = {"Stor": Band(100, None, 0.2), "Mellem": Band(50, 500, 0.3)}
    validate_bands(zones, "Volumenområde A", require_disjoint=False)


def test_inverted_band_is_rejected():
    with pytest.raises(ValueError, match="større end"):
        validate_bands({"A": Band(1_000, 500, 0.2)}, "Kundekategori")


def test_gm_outside_zero_to_one_is_rejected():
    with pytest.raises(ValueError, match="mellem 0 og 100"):
        validate_bands({"A": Band(0, None, 20)}, "Kundekategori")


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"gm_months": 0}, "GM-måneder"),
        ({"turnover_window_months": 0}, "Turnover-vinduet"),
        ({"outlier_metric": "vilkårlig"}, "Outlier-metrik"),
        ({"group_plot_anchor": "kunden"}, "Forankring"),
        ({"colour_by": "regnbue"}, "Farvelogik"),
        (
            {"geo_combined": False, "geo_cn": False, "geo_dk": False},
            "Mindst én geografisk opdeling",
        ),
    ],
)
def test_invalid_settings_are_reported_in_danish(changes, message):
    with pytest.raises(ValueError, match=message):
        Config(**changes).validate()


def test_default_config_is_valid():
    Config().validate()


def test_config_accepts_raw_tuples_for_bands():
    cfg = Config(category_bands={"A": (1_000, None, 0.2), "B": (0, 1_000, 0.3)})
    assert cfg.category_bands["A"] == Band(1_000.0, None, 0.2)


# --- Filnavne ----------------------------------------------------------------


def test_suffixes_compose_in_a_stable_order():
    paths = OutputPaths.create("rapport", "/ud", write_excel=True)
    assert paths.group_plot("sinter", "cn") == os.path.join(
        "/ud", "rapport_kundegruppe_sinter_cn.html"
    )
    assert paths.item_plot("stoebe", "", "eks") == os.path.join(
        "/ud", "rapport_item_stoebe_eks.html"
    )
    assert paths.group_plot() == os.path.join("/ud", "rapport_kundegruppe.html")
    assert paths.excel == os.path.join("/ud", "rapport.xlsx")


def test_extension_in_the_basename_is_stripped_once():
    assert OutputPaths.create("rapport.xlsx", "/ud", True).basename == "rapport"


def test_basename_containing_html_survives():
    """
    Filnavnene blev tidligere dannet ved at erstatte '.html' i en færdig sti.
    Et basisnavn med '.html' midt i kunne dermed ødelægge stien.
    """
    paths = OutputPaths.create("min.html.rapport", "/ud", True)
    assert paths.group_plot("sinter") == os.path.join(
        "/ud", "min.html.rapport_kundegruppe_sinter.html"
    )


def test_empty_basename_falls_back_to_a_default():
    assert OutputPaths.create("", "/ud", True).basename == "kunde_segmentering"


def test_excel_path_is_none_when_disabled():
    assert OutputPaths.create("rapport", "/ud", write_excel=False).excel is None


# --- Excel-faner -------------------------------------------------------------


def sample_group_frame():
    return pd.DataFrame(
        [
            {
                GROUP: "A",
                "Kundetype": "Eksisterende",
                KAM: "Mette Kold",
                "Kundekategori": "A+",
                "Industry_segment": "Medico",
                "antal_items": 3,
                "samlet_turnover_window": 6_000_000.0,
                "gns_turnover_window": 2_000_000.0,
                "samlet_turnover": 500_000.0,
                "gns_turnover": 166_666.0,
                "samlet_GP": 150_000.0,
                "samlet_GM": 0.30,
                "gns_GM": 0.28,
                "tidligste_aktivitet": pd.Timestamp("2024-01-01"),
                "seneste_aktivitet": pd.Timestamp("2025-06-01"),
            }
        ]
    )


def test_the_summary_sheet_always_has_the_same_columns():
    """Rapporten har kun én udgave, så fanen ser ens ud hver gang."""
    sheet = prepare_summary_sheet(sample_group_frame(), Config())
    assert list(sheet.columns) == SUMMARY_COLUMNS


def test_percentages_stay_decimal_so_excel_can_format_them():
    sheet = prepare_summary_sheet(sample_group_frame(), Config())
    assert sheet["samlet_GM_pct"].iloc[0] == pytest.approx(0.30)


def test_dates_are_written_as_year_month():
    sheet = prepare_summary_sheet(sample_group_frame(), Config())
    assert sheet["seneste_aktivitet"].iloc[0] == "2025-06"


def sample_item_frame():
    return pd.DataFrame(
        [
            {
                GROUP: "A",
                ITEM_NO: "701234",
                TURNOVER_SUM: 1000.0,
                GP_SUM: 300.0,
                WINDOW_ITEM: 5000.0,
                WINDOW_GROUP: 4000.0,
                ITEM_GM: 0.30,
                FIRST_ACTIVITY: pd.Timestamp("2024-01-01"),
                LAST_ACTIVITY: pd.Timestamp("2025-06-01"),
            }
        ]
    )


def test_item_sheet_uses_readable_column_names():
    sheet = prepare_item_sheet(sample_item_frame(), Config())
    assert "Turnover_DKK_12mdr_item" in sheet.columns
    assert "Turnover_DKK_12mdr_gruppe" in sheet.columns
    assert "GM_pct" in sheet.columns


def test_item_window_column_follows_the_configured_window():
    sheet = prepare_item_sheet(sample_item_frame(), Config(turnover_window_months=24))
    assert "Turnover_DKK_24mdr_item" in sheet.columns


def test_the_item_sheet_always_has_the_same_columns():
    """
    Kun én udgave af rapporten. KAM står ikke med her, fordi prøve-rammen
    ikke har den kolonne — manglende kolonner springes over i stedet for at
    vælte fanen.
    """
    sheet = prepare_item_sheet(sample_item_frame(), Config())
    assert list(sheet.columns) == [
        GROUP, ITEM_NO, "Turnover_DKK_12mdr_item", "Turnover_DKK_12mdr_gruppe",
        "Turnover_DKK_seneste_md", "GP_DKK_seneste_md", "GM_pct",
        FIRST_ACTIVITY, LAST_ACTIVITY,
    ]


def test_the_item_sheet_keeps_kam_when_the_data_has_it():
    frame = sample_item_frame()
    frame[KAM] = ["PHA"]
    assert list(prepare_item_sheet(frame, Config()).columns)[:3] == [GROUP, KAM, ITEM_NO]


# --- Faste GM%-grænser -------------------------------------------------------


def test_the_gm_limits_are_blank_by_default():
    cfg = Config()
    assert cfg.gm_limit_min_pct is None and cfg.gm_limit_max_pct is None
    cfg.validate()


def test_a_lower_limit_above_the_upper_is_rejected():
    with pytest.raises(ValueError, match="nedre GM%-grænse"):
        Config(gm_limit_min_pct=100, gm_limit_max_pct=-30).validate()


def test_one_limit_alone_is_fine():
    Config(gm_limit_min_pct=-30).validate()
    Config(gm_limit_max_pct=100).validate()


def test_the_limits_are_written_to_the_parameter_sheet():
    rows = parameter_sheet(
        Config(gm_limit_min_pct=-30, gm_limit_max_pct=100), DATES
    )
    values = dict(zip(rows["Parameter"], rows["Værdi"]))
    assert values["GM%-grænse, nedre"] == "-30 %"
    assert values["GM%-grænse, øvre"] == "100 %"


def test_a_blank_limit_says_so_in_the_parameter_sheet():
    rows = parameter_sheet(Config(), DATES)
    values = dict(zip(rows["Parameter"], rows["Værdi"]))
    assert values["GM%-grænse, nedre"] == "ingen"
    assert values["GM%-grænse, øvre"] == "ingen"

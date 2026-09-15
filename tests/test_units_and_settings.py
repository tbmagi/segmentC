"""Tests af de nye analyseenheder, dato-udledning og gemte standardværdier."""

import json
import os
from datetime import date

import pandas as pd
import pytest

from segmentering.classify import ITEM_TYPE_LABELS
from segmentering.config import (
    Config,
    OutputPaths,
    clear_defaults,
    dated_output_directory,
    load_defaults,
    save_defaults,
    todays_fiscal_year,
    todays_reference_date,
)
from segmentering.dataio import (
    CUSTOMER,
    GEO,
    GEO_CN,
    GEO_DK,
    GEO_OTHER,
    ITEM_TYPE,
    geo_of_rows,
)
from segmentering.pipeline import _qualified_names


# --- Dagens dato -------------------------------------------------------------


def test_reference_date_follows_today():
    assert todays_reference_date(date(2026, 9, 15)) == "09-2026"
    assert todays_reference_date(date(2026, 1, 3)) == "01-2026"


def test_fiscal_year_is_this_year_and_the_next():
    assert todays_fiscal_year(date(2026, 9, 15)) == "2026/27"
    assert todays_fiscal_year(date(2029, 2, 1)) == "2029/30"


def test_the_fiscal_year_format_matches_the_data():
    """Kolonnen 'Fiscal year' bruger ÅÅÅÅ/ÅÅ — ikke ÅÅÅÅ/ÅÅÅÅ."""
    assert todays_fiscal_year(date(2026, 1, 1)).count("/") == 1
    assert len(todays_fiscal_year(date(2026, 1, 1)).split("/")[1]) == 2


def test_a_fresh_config_is_dated_today():
    cfg = Config()
    assert cfg.reference_date == todays_reference_date()
    assert cfg.new_fiscal_year == todays_fiscal_year()


# --- Output-mappen -----------------------------------------------------------


def test_the_output_folder_carries_the_date():
    folder = dated_output_directory(date(2026, 9, 15))
    assert folder.endswith("Kundesegmentering 2026-09-15")


def test_an_empty_output_field_uses_the_dated_folder():
    paths = OutputPaths.create("rapport", "", write_excel=True)
    assert "Kundesegmentering " in paths.directory


def test_an_explicit_folder_still_wins():
    paths = OutputPaths.create("rapport", "/et/andet/sted", write_excel=True)
    assert paths.directory == "/et/andet/sted"


# --- Produktionssted ---------------------------------------------------------


def frame_with_types(values):
    return pd.DataFrame({"Turnover type": values})


def test_geo_is_read_from_the_turnover_type():
    cfg = Config()
    geo = geo_of_rows(
        frame_with_types(["DK prod.", "CN prod.", "SE prod."]),
        cfg.cn_turnover_types,
        cfg.dk_turnover_types,
    )
    assert list(geo) == [GEO_DK, GEO_CN, GEO_DK]


def test_an_unknown_turnover_type_becomes_its_own_group():
    """Intet må forsvinde i stilhed — ukendte typer får deres egen knap."""
    cfg = Config()
    geo = geo_of_rows(
        frame_with_types(["Noget helt andet"]),
        cfg.cn_turnover_types,
        cfg.dk_turnover_types,
    )
    assert list(geo) == [GEO_OTHER]


def test_no_turnover_type_column_means_no_geo_split():
    cfg = Config()
    assert (
        geo_of_rows(pd.DataFrame({"andet": [1]}), cfg.cn_turnover_types, cfg.dk_turnover_types)
        is None
    )


# --- Analyseenhedens navn ----------------------------------------------------


def unit_frame(rows):
    """rows: (kunde, item-type, geo)."""
    return pd.DataFrame(
        [{CUSTOMER: c, ITEM_TYPE: t, GEO: g} for c, t, g in rows]
    )


def test_a_customer_with_one_combination_keeps_its_plain_name():
    frame = unit_frame([("GRUNDFOSS", "sintere", GEO_DK)])
    assert list(_qualified_names(frame, has_geo=True)) == ["GRUNDFOSS"]


def test_sinter_and_cast_become_separate_units():
    frame = unit_frame(
        [("GRUNDFOSS", "sintere", GEO_DK), ("GRUNDFOSS", "støbe", GEO_DK)]
    )
    assert list(_qualified_names(frame, has_geo=True)) == [
        "GRUNDFOSS (Sinter)",
        "GRUNDFOSS (Støb)",
    ]


def test_two_countries_become_separate_units():
    frame = unit_frame(
        [("GRUNDFOSS", "sintere", GEO_DK), ("GRUNDFOSS", "sintere", GEO_CN)]
    )
    assert list(_qualified_names(frame, has_geo=True)) == [
        "GRUNDFOSS (DK)",
        "GRUNDFOSS (CN)",
    ]


def test_both_dimensions_are_named_when_both_vary():
    frame = unit_frame(
        [
            ("GRUNDFOSS", "sintere", GEO_DK),
            ("GRUNDFOSS", "støbe", GEO_CN),
        ]
    )
    assert list(_qualified_names(frame, has_geo=True)) == [
        "GRUNDFOSS (Sinter, DK)",
        "GRUNDFOSS (Støb, CN)",
    ]


def test_customers_are_qualified_independently():
    """Én kundes opdeling må ikke give en anden kunde et unødigt kendetegn."""
    frame = unit_frame(
        [
            ("GRUNDFOSS", "sintere", GEO_DK),
            ("GRUNDFOSS", "støbe", GEO_DK),
            ("DANFOSS", "sintere", GEO_DK),
        ]
    )
    names = list(_qualified_names(frame, has_geo=True))
    assert names == ["GRUNDFOSS (Sinter)", "GRUNDFOSS (Støb)", "DANFOSS"]


def test_geo_is_left_out_when_the_column_is_missing():
    frame = unit_frame(
        [("GRUNDFOSS", "sintere", GEO_DK), ("GRUNDFOSS", "støbe", GEO_CN)]
    )
    assert list(_qualified_names(frame, has_geo=False)) == [
        "GRUNDFOSS (Sinter)",
        "GRUNDFOSS (Støb)",
    ]


def test_item_type_labels_are_the_ones_shown_on_the_buttons():
    assert ITEM_TYPE_LABELS["sintere"] == "Sinter"
    assert ITEM_TYPE_LABELS["støbe"] == "Støb"


# --- Gemte standardværdier ---------------------------------------------------


def test_saved_settings_come_back(tmp_path):
    path = str(tmp_path / "indstillinger.json")
    cfg = Config(turnover_window_months=24, outlier_metric="turnover", gm_months=3)
    save_defaults(cfg, path)
    restored = load_defaults(path)
    assert restored.turnover_window_months == 24
    assert restored.outlier_metric == "turnover"
    assert restored.gm_months == 3


def test_bands_survive_a_round_trip(tmp_path):
    path = str(tmp_path / "indstillinger.json")
    cfg = Config(category_bands={"A": (2_000_000, None, 0.3), "B": (0, 2_000_000, 0.4)})
    save_defaults(cfg, path)
    restored = load_defaults(path)
    assert restored.category_bands["A"].turnover_min == 2_000_000
    assert restored.category_bands["B"].gm_min == pytest.approx(0.4)
    restored.validate()


def test_the_date_fields_are_never_saved(tmp_path):
    """
    Dags dato og regnskabsår udledes af dagens dato. Blev de gemt, ville
    programmet stivne på den dag indstillingerne blev gemt.
    """
    path = str(tmp_path / "indstillinger.json")
    save_defaults(Config(reference_date="01-2020", new_fiscal_year="2019/20"), path)
    stored = json.loads(open(path, encoding="utf-8").read())
    assert "reference_date" not in stored
    assert "new_fiscal_year" not in stored
    assert load_defaults(path).reference_date == todays_reference_date()


def test_no_saved_file_gives_the_factory_defaults(tmp_path):
    assert load_defaults(str(tmp_path / "findes-ikke.json")) == Config()


def test_a_damaged_file_is_reported(tmp_path):
    path = tmp_path / "indstillinger.json"
    path.write_text("{ dette er ikke json", encoding="utf-8")
    with pytest.raises(ValueError, match="Kunne ikke læse"):
        load_defaults(str(path))


def test_settings_from_another_version_are_reported(tmp_path):
    path = tmp_path / "indstillinger.json"
    path.write_text(json.dumps({"et_felt_der_ikke_findes": 1}), encoding="utf-8")
    with pytest.raises(ValueError, match="ukendte felter"):
        load_defaults(str(path))


def test_clearing_reports_whether_there_was_anything(tmp_path):
    path = str(tmp_path / "indstillinger.json")
    assert clear_defaults(path) is False
    save_defaults(Config(), path)
    assert clear_defaults(path) is True
    assert not os.path.exists(path)

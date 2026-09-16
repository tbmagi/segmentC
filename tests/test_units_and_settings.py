"""Tests af dato-udledning, output-mappen og gemte standardværdier."""

import json
import os
from datetime import date

import pytest

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


# --- Dagens dato -------------------------------------------------------------


def test_reference_date_follows_today():
    assert todays_reference_date(date(2026, 9, 15)) == "09-2026"
    assert todays_reference_date(date(2026, 1, 3)) == "01-2026"


def test_fiscal_year_is_the_one_the_day_falls_in():
    """
    Regnskabsåret begynder i maj, så januar til april hører til det år der
    begyndte året før. Blev der regnet på kalenderåret, ville programmet i
    de fire måneder foreslå det år der endnu ikke er begyndt — og så ville
    ingen kunde overhovedet blive klassificeret som ny.
    """
    assert todays_fiscal_year(date(2026, 9, 15)) == "2026/2027"
    assert todays_fiscal_year(date(2026, 5, 1)) == "2026/2027"   # første dag
    assert todays_fiscal_year(date(2026, 4, 30)) == "2025/2026"  # sidste dag
    assert todays_fiscal_year(date(2029, 2, 1)) == "2028/2029"


def test_the_fiscal_year_start_month_can_be_moved():
    """Begynder året i januar, følger det kalenderåret."""
    assert todays_fiscal_year(date(2026, 2, 1), start_month=1) == "2026/2027"


def test_the_fiscal_year_is_written_with_four_digits_on_both_sides():
    """Skal matche kolonnen 'Fiscal year' — ellers findes ingen nye kunder."""
    start, end = todays_fiscal_year(date(2026, 1, 1)).split("/")
    assert len(start) == 4 and len(end) == 4


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

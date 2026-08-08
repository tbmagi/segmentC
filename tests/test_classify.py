"""Tests af klassifikation: item-numre, kundetyper og kundekategorier."""

import pandas as pd
import pytest

from segmentering.classify import (
    CAST,
    OTHER,
    SINTER,
    classify_customer_category,
    classify_customer_type,
    classify_item_no,
    has_manual_suffix,
)
from segmentering.config import Band, DEFAULT_CATEGORY_BANDS
from segmentering.dataio import PERIOD, ReferenceDates, parse_period


@pytest.mark.parametrize(
    "value, expected",
    [
        ("701234", SINTER),
        ("771234", SINTER),
        ("601234", CAST),
        ("671234", CAST),
        ("681234", OTHER),  # prefix uden for begge intervaller
        ("7012", OTHER),  # for kort
        ("ABC123456", OTHER),  # ikke numerisk
        ("601234.0", CAST),  # Excel har gjort heltallet til float
        (None, OTHER),
    ],
)
def test_automatic_item_classification(value, expected):
    assert classify_item_no(value) == expected


@pytest.mark.parametrize(
    "value, expected",
    [
        ("601234-S1", SINTER),  # suffix overruler støbe-prefix
        ("701234-S2", CAST),  # suffix overruler sinter-prefix
        ("701234-S0", OTHER),  # eksplicit fjernet
        ("601234-s1", SINTER),  # små bogstaver virker også
        ("ABC-S1", SINTER),  # suffix virker uden gyldigt nummer
    ],
)
def test_manual_suffix_overrides_prefix(value, expected):
    assert classify_item_no(value) == expected


def test_has_manual_suffix():
    series = pd.Series(["701234", "701234-S1", "601234-s0", " 601234-S2 "])
    assert list(has_manual_suffix(series)) == [False, True, True, True]


# --- Kundetyper --------------------------------------------------------------


def _group(months, fiscal_years=None):
    frame = pd.DataFrame({PERIOD: [parse_period(m) for m in months]})
    if fiscal_years is not None:
        frame["Fiscal year"] = fiscal_years
    return frame


DATES = ReferenceDates(today=parse_period("2026-05"), window_start=parse_period("2024-05"))


def test_new_customer_only_active_in_new_fiscal_year():
    group = _group(["2026-06", "2026-07"], ["2026/27", "2026/27"])
    assert classify_customer_type(group, DATES, "2026/27", "Fiscal year") == "Ny"


def test_revived_customer_counts_as_existing():
    """Aktiv i ny-året, men med ældre historik – altså ikke en ny kunde."""
    group = _group(["2020-01", "2026-06"], ["2019/20", "2026/27"])
    assert classify_customer_type(group, DATES, "2026/27", "Fiscal year") == "Eksisterende"


def test_existing_customer_inside_window():
    group = _group(["2025-03"])
    assert classify_customer_type(group, DATES, "", None) == "Eksisterende"


def test_former_customer_outside_all_windows():
    group = _group(["2019-03"])
    assert classify_customer_type(group, DATES, "", None) == "Tidligere"


def test_date_based_fallback_when_no_fiscal_year():
    """Uden regnskabsår regnes aktivitet efter dags dato som en ny kunde."""
    group = _group(["2026-09"])
    assert classify_customer_type(group, DATES, "", None) == "Ny"


def test_group_without_dates_is_unknown():
    assert classify_customer_type(_group([]), DATES, "", None) == "Ukendt"


# --- Kundekategorier ---------------------------------------------------------


@pytest.mark.parametrize(
    "turnover, margin, expected",
    [
        (6_000_000, 0.25, "A+"),  # over A's grænse og over GM-kravet
        (6_000_000, 0.10, "A-"),  # A-båndet, men GM under kravet
        (5_000_000, 0.30, "B+"),  # præcis på grænsen hører til B
        (3_000_000, 0.22, "B+"),  # GM lig med kravet tæller som opfyldt
        (500_000, 0.30, "C+"),
        (50_000, 0.10, "D-"),
        (0, 0.50, "-"),  # nul omsætning matcher intet bånd
    ],
)
def test_category_assignment(turnover, margin, expected):
    assert classify_customer_category(turnover, margin, DEFAULT_CATEGORY_BANDS) == expected


def test_category_is_independent_of_band_order():
    """
    Rækkefølgen båndene er defineret i må ikke kunne ændre resultatet.

    Tidligere blev første match i dict-rækkefølgen valgt, så en omrokering af
    grænserne i GUI'en kunne stille og roligt give en anden kategori.
    """
    reversed_bands = dict(reversed(list(DEFAULT_CATEGORY_BANDS.items())))
    for turnover in (50_000, 500_000, 3_000_000, 6_000_000):
        assert classify_customer_category(
            turnover, 0.30, DEFAULT_CATEGORY_BANDS
        ) == classify_customer_category(turnover, 0.30, reversed_bands)


def test_missing_values_give_no_category():
    assert classify_customer_category(float("nan"), 0.3, DEFAULT_CATEGORY_BANDS) == "-"
    assert classify_customer_category(1_000, float("nan"), DEFAULT_CATEGORY_BANDS) == "-"


def test_band_contains_turnover_is_half_open():
    band = Band(100, 200, 0.2)
    assert not band.contains_turnover(100)  # nedre grænse er eksklusiv
    assert band.contains_turnover(150)
    assert band.contains_turnover(200)  # øvre grænse er inklusiv
    assert not band.contains_turnover(201)

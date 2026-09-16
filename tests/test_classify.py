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
from segmentering.config import Band, Config, DEFAULT_CATEGORY_BANDS
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


def _group(months):
    return pd.DataFrame({PERIOD: [parse_period(m) for m in months]})


#: Opsætningen fra de fem beskrevne scenarier: dags dato 09-2026, 24 måneders
#: vindue (09-2024 – 09-2026) og regnskabsåret 2026/2027 (05-2026 – 04-2027).
#: De to perioder overlapper med vilje fra 05-2026 og frem.
DATES = ReferenceDates.from_config(
    Config(reference_date="09-2026", new_fiscal_year="2026/27",
           existing_customer_months=24)
)

#: Uden ny-regnskabsår findes kategorien "Ny" ikke.
NO_FISCAL_YEAR = ReferenceDates.from_config(
    Config(reference_date="09-2026", new_fiscal_year="", existing_customer_months=24)
)


def test_the_fiscal_year_runs_from_its_start_month():
    """2026/2027 er 05-2026 til og med 04-2027 — ikke kalenderåret."""
    assert (DATES.fiscal_start.month, DATES.fiscal_start.year) == (5, 2026)
    assert (DATES.fiscal_end.month, DATES.fiscal_end.year) == (4, 2027)


@pytest.mark.parametrize(
    "name, months, expected",
    [
        # A: begge handler ligger i ny-regnskabsåret
        ("A", ["2026-09", "2026-05"], "Ny"),
        # B: én i ny-året, én før — altså ikke en ny kunde
        ("B", ["2026-06", "2026-01"], "Eksisterende"),
        # C: én i ny-året, én mange år tilbage — kunden er vendt tilbage
        ("C", ["2026-06", "2023-01"], "Genopstået"),
        # D: ingen aktivitet i ny-året, men én inden for vinduet
        ("D", ["2025-12", "2023-12"], "Eksisterende"),
        # E: al aktivitet ligger før vinduet
        ("E", ["2023-03", "2022-01"], "Tidligere"),
    ],
)
def test_the_five_customer_scenarios(name, months, expected):
    assert classify_customer_type(_group(months), DATES) == expected, name


def test_new_requires_the_whole_history_inside_the_fiscal_year():
    """
    Perioderne overlapper, så det er ikke nok at den seneste handel ligger i
    ny-året — så ville enhver tilbagevendt kunde blive talt som ny.
    """
    assert classify_customer_type(_group(["2026-06"]), DATES) == "Ny"
    assert classify_customer_type(_group(["2026-06", "2026-04"]), DATES) == "Eksisterende"


def test_the_gap_is_what_separates_revived_from_existing():
    """
    Begge kunder har handlet i ny-året og har gammel historik. Forskellen er
    hullet: den ene har handlet i tiden op til året begyndte, den anden har
    ligget helt stille. Det er to forskellige salgssituationer.
    """
    # Handlede i februar, altså inde i vinduet før ny-året — aldrig væk.
    assert classify_customer_type(
        _group(["2023-01", "2026-02", "2026-06"]), DATES
    ) == "Eksisterende"
    # Intet mellem 09-2024 og 05-2026 — har ligget stille og er tilbage.
    assert classify_customer_type(_group(["2023-01", "2026-06"]), DATES) == "Genopstået"


def test_revived_needs_activity_in_the_new_year():
    """Uden en handel i ny-året er kunden bare eksisterende."""
    assert classify_customer_type(_group(["2023-01", "2025-12"]), DATES) == "Eksisterende"


def test_without_a_fiscal_year_nobody_is_revived():
    assert classify_customer_type(
        _group(["2023-01", "2026-06"]), NO_FISCAL_YEAR
    ) == "Eksisterende"


def test_the_month_the_fiscal_year_begins_counts_as_new():
    assert classify_customer_type(_group(["2026-05"]), DATES) == "Ny"
    assert classify_customer_type(_group(["2026-04"]), DATES) == "Eksisterende"


def test_the_window_edges_are_inclusive():
    assert classify_customer_type(_group(["2024-09"]), DATES) == "Eksisterende"
    assert classify_customer_type(_group(["2024-08"]), DATES) == "Tidligere"


def test_without_a_fiscal_year_nobody_is_new():
    assert classify_customer_type(_group(["2026-06"]), NO_FISCAL_YEAR) == "Eksisterende"
    assert classify_customer_type(_group(["2019-03"]), NO_FISCAL_YEAR) == "Tidligere"


def test_the_fiscal_year_column_is_not_consulted():
    """
    Klassifikationen bygger på datoerne. Kolonnen kunne være skrevet
    "2026/27" ét sted og "2026/2027" et andet, og en ny kunde faldt så
    stiltiende ned i "Eksisterende".
    """
    group = _group(["2026-06"])
    group["Fiscal year"] = ["noget helt andet"]
    assert classify_customer_type(group, DATES) == "Ny"


def test_group_without_dates_is_unknown():
    assert classify_customer_type(_group([]), DATES) == "Ukendt"


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

"""Tests af indlæsning: overskriftsrækken, budgetfiltret og KAM."""

import pandas as pd
import pytest

from segmentering.config import Config
from segmentering.dataio import (
    BLANK_KAM,
    GROUP,
    KAM,
    PERIOD,
    REQUIRED_COLUMNS,
    MissingColumnsError,
    ReferenceDates,
    apply_row_filters,
    load_sales_data,
    locate_header_row,
    parse_period,
)
from segmentering.metrics import kam_by_group, sort_kams

QUIET = lambda _message: None


def data_row(group="KUNDE A", item="701234", month="2025-06", turnover=1000.0, **extra):
    row = {
        "Statistics group": group,
        "item no.": item,
        "year-mo": month,
        "cost": 500.0,
        "Qty.": 5,
        "Turnover DKK": turnover,
        "Local_COGS_DKK": 600.0,
        "Local_GP_DKK": 300.0,
    }
    row.update(extra)
    return row


def write_workbook(path, rows, junk_rows=0, extra_columns=()):
    """Skriver et ark hvor overskrifterne kan ligge længere nede."""
    import openpyxl

    frame = pd.DataFrame(rows)
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    for i in range(junk_rows):
        sheet.append([f"Forside-rod linje {i + 1}"])
    sheet.append(list(frame.columns))
    for record in frame.itertuples(index=False):
        sheet.append(list(record))
    workbook.save(path)
    return path


# --- Overskriftsrækken -------------------------------------------------------


def test_header_is_found_on_the_first_row():
    frame = pd.DataFrame([REQUIRED_COLUMNS, ["a"] * len(REQUIRED_COLUMNS)])
    assert locate_header_row(frame) == (0, [])


def test_header_is_found_further_down():
    """Arket kan have en forside over tabellen — overskrifterne skal findes alligevel."""
    junk = [["Salgsudtræk"] + [None] * (len(REQUIRED_COLUMNS) - 1) for _ in range(9)]
    frame = pd.DataFrame(junk + [REQUIRED_COLUMNS])
    row, missing = locate_header_row(frame)
    assert row == 9 and missing == []


def test_header_match_ignores_case_and_spacing():
    messy = [f"  {c.upper()}  " for c in REQUIRED_COLUMNS]
    assert locate_header_row(pd.DataFrame([messy])) == (0, [])


def test_missing_columns_are_reported_with_the_best_candidate():
    partial = list(REQUIRED_COLUMNS[:-1]) + ["Noget andet"]
    row, missing = locate_header_row(pd.DataFrame([partial]))
    assert row == 0
    assert missing == [REQUIRED_COLUMNS[-1]]


def test_reading_a_sheet_with_a_cover_page(tmp_path):
    path = write_workbook(tmp_path / "rod.xlsx", [data_row()], junk_rows=9)
    df = load_sales_data(str(path), QUIET)
    assert GROUP not in df.columns  # tilføjes først i filtreringen
    assert "Statistics group" in df.columns
    assert len(df) == 1


def test_a_file_without_the_required_columns_is_rejected(tmp_path):
    import openpyxl

    workbook = openpyxl.Workbook()
    workbook.active.append(["Helt", "andre", "kolonner"])
    workbook.active.append([1, 2, 3])
    path = tmp_path / "forkert.xlsx"
    workbook.save(path)
    with pytest.raises(MissingColumnsError):
        load_sales_data(str(path), QUIET)


def test_a_missing_column_is_named_in_the_error(tmp_path):
    """
    Fjernes en enkelt obligatorisk kolonne, skal fejlen sige præcis hvilken —
    ikke bare at noget gik galt.
    """
    rows = [data_row()]
    del rows[0]["Local_GP_DKK"]
    path = write_workbook(tmp_path / "mangler.xlsx", rows, junk_rows=3)
    with pytest.raises(MissingColumnsError) as caught:
        load_sales_data(str(path), QUIET)

    error = caught.value
    assert error.missing == ["Local_GP_DKK"]
    assert "Local_GP_DKK" in str(error)
    # Beskeden skal også vise hvad der FAKTISK stod, så en stavefejl kan ses
    assert "Turnover DKK" in str(error)
    assert error.header_row == 3


def test_the_error_message_is_readable_for_a_user():
    error = MissingColumnsError(["Turnover DKK"], ["Statistics group"], header_row=9)
    text = str(error)
    assert text.startswith("Excel-filen mangler obligatoriske kolonner.")
    assert "række 10" in text  # 1-indekseret for brugeren
    assert "Turnover DKK" in text


def test_several_missing_columns_are_all_listed():
    error = MissingColumnsError(["A", "B", "C"], [], None)
    assert all(name in str(error) for name in ("A", "B", "C"))
    assert "ingen kolonnenavne" in str(error)


# --- Budgettal efter dags dato -----------------------------------------------


def frame_with_periods(months, **extra):
    rows = [data_row(month=m, **extra) for m in months]
    df = pd.DataFrame(rows)
    df[PERIOD] = df["year-mo"].apply(parse_period)
    return df


DATES = ReferenceDates(
    today=parse_period("2026-06"), window_start=parse_period("2024-06")
)


def test_periods_after_the_reference_date_are_dropped():
    """
    Rækker efter dags dato er budgettal. Selve måneden for dags dato skal
    blive, alt derefter skal væk.
    """
    df = frame_with_periods(["2026-05", "2026-06", "2026-07", "2026-12"])
    result = apply_row_filters(df, Config(), DATES, QUIET)
    kept = sorted(result[PERIOD].dt.strftime("%Y-%m"))
    assert kept == ["2026-05", "2026-06"]


def test_the_reference_month_itself_is_kept():
    df = frame_with_periods(["2026-06"])
    assert len(apply_row_filters(df, Config(), DATES, QUIET)) == 1


def test_the_budget_filter_can_be_switched_off():
    df = frame_with_periods(["2026-06", "2026-09"])
    result = apply_row_filters(df, Config(drop_future_periods=False), DATES, QUIET)
    assert len(result) == 2


def test_only_future_rows_are_dropped_not_unparseable_ones():
    """En ugyldig periode skal behandles som før, ikke fjernes af budgetfiltret."""
    df = frame_with_periods(["2026-05", "2026-08"])
    df.loc[len(df)] = data_row(month="noget vrøvl")
    df.loc[df.index[-1], PERIOD] = pd.NaT
    result = apply_row_filters(df, Config(), DATES, QUIET)
    assert len(result) == 2  # 2026-05 og NaT-rækken
    assert result[PERIOD].isna().sum() == 1


def test_everything_in_the_future_is_a_clear_error():
    df = frame_with_periods(["2027-01", "2027-02"])
    with pytest.raises(ValueError, match="dags dato"):
        apply_row_filters(df, Config(), DATES, QUIET)


# --- KAM ---------------------------------------------------------------------


def kam_frame(rows):
    """rows: (kundegruppe, 'YYYY-MM', kam)."""
    df = pd.DataFrame(
        [{GROUP: g, PERIOD: parse_period(m), KAM: k} for g, m, k in rows]
    )
    return df


def test_customer_gets_the_kam_from_the_latest_activity():
    """
    En kunde kan have skiftet KAM undervejs. Det er den nyeste der gælder —
    ikke den der optræder oftest eller først.
    """
    df = kam_frame(
        [("KUNDE A", "2024-01", "Anders")] * 1
        + [("KUNDE A", "2024-02", "Anders")]
        + [("KUNDE A", "2025-11", "Mette")]
    )
    assert kam_by_group(df) == {"KUNDE A": "Mette"}


def test_the_most_frequent_kam_does_not_win():
    df = kam_frame(
        [("KUNDE A", f"2024-{m:02d}", "Anders") for m in range(1, 11)]
        + [("KUNDE A", "2025-06", "Søren")]
    )
    assert kam_by_group(df)["KUNDE A"] == "Søren"


def test_each_customer_is_resolved_separately():
    df = kam_frame(
        [("KUNDE A", "2025-01", "Anders"), ("KUNDE B", "2025-02", "Mette")]
    )
    assert kam_by_group(df) == {"KUNDE A": "Anders", "KUNDE B": "Mette"}


def test_blank_kam_values_are_ignored():
    df = kam_frame([("KUNDE A", "2025-01", "Anders"), ("KUNDE A", "2025-06", "   ")])
    assert kam_by_group(df)["KUNDE A"] == "Anders"


def test_missing_kam_on_the_latest_row_falls_back_to_the_last_known():
    df = kam_frame([("KUNDE A", "2025-01", "Anders"), ("KUNDE A", "2025-06", None)])
    assert kam_by_group(df)["KUNDE A"] == "Anders"


def test_no_kam_column_gives_an_empty_lookup():
    df = pd.DataFrame({GROUP: ["KUNDE A"], PERIOD: [parse_period("2025-01")]})
    assert kam_by_group(df) == {}


# --- KAM: store og små bogstaver ---------------------------------------------


def test_kam_is_case_insensitive():
    """'PHA' og 'pHA' er samme person og skal ende under samme knap."""
    df = kam_frame(
        [("KUNDE A", "2025-01", "PHA"), ("KUNDE B", "2025-02", "pHA")]
    )
    result = kam_by_group(df)
    assert len(set(result.values())) == 1, f"to stavemåder blev til to KAM'er: {result}"


def test_the_newest_spelling_becomes_the_label():
    """Samme 'seneste vinder'-regel som ellers afgør hvilken stavemåde der vises."""
    df = kam_frame(
        [("KUNDE A", "2025-01", "pha"), ("KUNDE B", "2025-09", "PHA")]
    )
    assert set(kam_by_group(df).values()) == {"PHA"}


def test_surrounding_spaces_do_not_split_a_kam():
    df = kam_frame(
        [("KUNDE A", "2025-01", " PHA "), ("KUNDE B", "2025-02", "PHA")]
    )
    assert len(set(kam_by_group(df).values())) == 1


def test_case_only_differs_within_one_customer():
    df = kam_frame(
        [("KUNDE A", "2025-01", "pha"), ("KUNDE A", "2025-06", "PHA")]
    )
    assert kam_by_group(df) == {"KUNDE A": "PHA"}


# --- KAM: tomme værdier ------------------------------------------------------


def test_customers_without_any_kam_are_labelled_blank():
    df = kam_frame(
        [("KUNDE A", "2025-01", "PHA"), ("KUNDE B", "2025-01", None)]
    )
    assert kam_by_group(df) == {"KUNDE A": "PHA", "KUNDE B": BLANK_KAM}


def test_an_empty_string_counts_as_blank():
    df = kam_frame([("KUNDE A", "2025-01", "   ")])
    assert kam_by_group(df) == {"KUNDE A": BLANK_KAM}


def test_all_customers_blank_when_the_column_is_empty():
    df = kam_frame([("KUNDE A", "2025-01", None), ("KUNDE B", "2025-01", None)])
    assert set(kam_by_group(df).values()) == {BLANK_KAM}


def test_blank_sorts_last():
    assert sort_kams(["Søren", BLANK_KAM, "Anders"]) == [
        "Anders",
        "Søren",
        BLANK_KAM,
    ]


def test_kam_sorting_ignores_case():
    assert sort_kams(["pha", "ABC"]) == ["ABC", "pha"]

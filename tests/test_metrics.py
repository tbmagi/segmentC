"""Tests af beregningerne bag de to akser."""

import pandas as pd
import pytest

from segmentering.config import Config
from segmentering.dataio import (
    GROSS_PROFIT,
    GROUP,
    ITEM_NO,
    PERIOD,
    TURNOVER,
    parse_period,
)
from segmentering.metrics import (
    ITEM_GM,
    TURNOVER_SUM,
    WINDOW_GROUP,
    WINDOW_ITEM,
    drop_dead_items,
    item_gm_basis,
    item_metrics,
    turnover_window,
)


COLUMNS = [GROUP, ITEM_NO, PERIOD, TURNOVER, GROSS_PROFIT]


def make_frame(rows):
    """rows: (kundegruppe, item, 'YYYY-MM', turnover, gp)."""
    return pd.DataFrame(
        [
            {
                GROUP: group,
                ITEM_NO: item,
                PERIOD: parse_period(month),
                TURNOVER: turnover,
                GROSS_PROFIT: gp,
            }
            for group, item, month, turnover, gp in rows
        ],
        columns=COLUMNS,
    )


# --- GM-grundlag -------------------------------------------------------------


def test_gm_basis_uses_only_latest_month_by_default():
    frame = make_frame(
        [
            ("A", "1", "2025-01", 100, 10),
            ("A", "1", "2025-02", 200, 80),  # seneste måned
        ]
    )
    result = item_gm_basis(frame, gm_months=1)
    assert result[TURNOVER_SUM].iloc[0] == 200
    assert result["GP_sum"].iloc[0] == 80


def test_gm_basis_sums_rows_within_the_same_latest_month():
    frame = make_frame(
        [("A", "1", "2025-02", 100, 10), ("A", "1", "2025-02", 300, 50)]
    )
    result = item_gm_basis(frame, gm_months=1)
    assert result[TURNOVER_SUM].iloc[0] == 400
    assert result["GP_sum"].iloc[0] == 60


def test_gm_basis_over_several_months_is_turnover_weighted():
    """
    Med tre måneder skal GM% blive SUM(GP)/SUM(Turnover) — ikke gennemsnittet
    af de månedlige marginer. Den store måned skal veje tungest.
    """
    frame = make_frame(
        [
            ("A", "1", "2025-01", 1000, 100),  # 10 %
            ("A", "1", "2025-02", 100, 50),  # 50 %
            ("A", "1", "2025-03", 100, 50),  # 50 %
        ]
    )
    result = item_gm_basis(frame, gm_months=3)
    assert result[TURNOVER_SUM].iloc[0] == 1200
    assert result["GP_sum"].iloc[0] == 200
    assert result["GP_sum"].iloc[0] / result[TURNOVER_SUM].iloc[0] == pytest.approx(1 / 6)


def test_gm_basis_counts_activity_months_not_calendar_months():
    """Har item'et kun to aktive måneder, bruges de to — også når N er 3."""
    frame = make_frame(
        [("A", "1", "2020-01", 100, 10), ("A", "1", "2025-03", 100, 10)]
    )
    result = item_gm_basis(frame, gm_months=3)
    assert result[TURNOVER_SUM].iloc[0] == 200


# --- Turnover-vindue ---------------------------------------------------------


def test_item_anchor_measures_each_item_from_its_own_last_month():
    frame = make_frame(
        [
            ("A", "tidlig", "2024-01", 500, 50),
            ("A", "tidlig", "2024-02", 500, 50),
            ("A", "sen", "2025-06", 300, 30),
        ]
    )
    result = turnover_window(frame, months=3, anchor="item").set_index(ITEM_NO)
    # "tidlig" måles fra 2024-02 og får begge måneder med.
    assert result.loc["tidlig", "Turnover_window"] == 1000
    assert result.loc["sen", "Turnover_window"] == 300


def test_group_anchor_measures_every_item_over_the_same_period():
    frame = make_frame(
        [
            ("A", "tidlig", "2024-01", 500, 50),
            ("A", "tidlig", "2024-02", 500, 50),
            ("A", "sen", "2025-06", 300, 30),
        ]
    )
    result = turnover_window(frame, months=3, anchor="group").set_index(ITEM_NO)
    # Vinduet slutter ved kundens seneste aktivitet (2025-06), så "tidlig"
    # ligger helt uden for og får 0 — men beholder sin række.
    assert result.loc["tidlig", "Turnover_window"] == 0
    assert result.loc["sen", "Turnover_window"] == 300


def test_every_item_keeps_a_row_regardless_of_anchor():
    """Begge forankringer skal dække præcis de samme items."""
    frame = make_frame(
        [("A", "x", "2020-01", 10, 1), ("A", "y", "2025-06", 20, 2)]
    )
    by_item = turnover_window(frame, months=3, anchor="item")
    by_group = turnover_window(frame, months=3, anchor="group")
    assert set(by_item[ITEM_NO]) == set(by_group[ITEM_NO]) == {"x", "y"}


# --- Døde items --------------------------------------------------------------


def test_drop_dead_items_removes_items_outside_the_group_window():
    frame = make_frame(
        [
            ("A", "levende", "2025-06", 100, 10),
            ("A", "død", "2020-01", 100, 10),
        ]
    )
    result = drop_dead_items(frame, window_months=12, log=lambda _: None)
    assert set(result[ITEM_NO]) == {"levende"}


def test_drop_dead_items_anchors_on_the_customer_not_the_item():
    """
    Vinduet forankres altid i kundens seneste aktivitet. Et item der selv
    stoppede for længe siden ryger ud, selv om det var aktivt i 12 måneder.
    """
    frame = make_frame(
        [("A", "sen", "2025-12", 100, 10)]
        + [("A", "tidlig", f"2020-{m:02d}", 100, 10) for m in range(1, 13)]
    )
    result = drop_dead_items(frame, window_months=12, log=lambda _: None)
    assert set(result[ITEM_NO]) == {"sen"}


def test_drop_dead_items_is_a_no_op_for_a_zero_window():
    frame = make_frame([("A", "1", "2020-01", 100, 10)])
    assert len(drop_dead_items(frame, window_months=0, log=lambda _: None)) == 1


# --- Samlet item-tabel -------------------------------------------------------


def test_identical_anchors_produce_identical_window_columns():
    cfg = Config(group_plot_anchor="item", item_plot_anchor="item", gm_months=1)
    frame = make_frame(
        [("A", "1", "2025-01", 100, 10), ("A", "2", "2025-06", 200, 40)]
    )
    result = item_metrics(frame, cfg)
    assert list(result[WINDOW_ITEM]) == list(result[WINDOW_GROUP])


def test_item_gm_is_gp_over_turnover():
    cfg = Config(gm_months=1)
    frame = make_frame([("A", "1", "2025-01", 200, 50)])
    result = item_metrics(frame, cfg)
    assert result[ITEM_GM].iloc[0] == pytest.approx(0.25)


def test_customer_types_do_not_affect_item_metrics():
    """
    Den gamle kode delte data op i (eksisterende + ny) og (tidligere), kørte
    identisk kode på hver del og satte dem sammen igen. Ingen beregning går på
    tværs af kundegrupper, så opdelingen var uden virkning. Denne test holder
    fast i det, så opdelingen ikke sniger sig ind igen.
    """
    cfg = Config(gm_months=1)
    frame = make_frame(
        [
            ("A", "1", "2025-01", 100, 10),
            ("A", "2", "2025-03", 300, 90),
            ("B", "1", "2020-05", 200, 60),
            ("C", "9", "2025-06", 400, 40),
        ]
    )
    whole = item_metrics(frame, cfg).sort_values([GROUP, ITEM_NO]).reset_index(drop=True)

    first, second = {"A", "B"}, {"C"}
    split = (
        pd.concat(
            [
                item_metrics(frame[frame[GROUP].isin(first)], cfg),
                item_metrics(frame[frame[GROUP].isin(second)], cfg),
            ],
            ignore_index=True,
        )
        .sort_values([GROUP, ITEM_NO])
        .reset_index(drop=True)
    )
    pd.testing.assert_frame_equal(whole, split)


def test_empty_input_gives_empty_output():
    assert item_metrics(make_frame([]), Config()).empty

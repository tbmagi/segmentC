"""Tests af GM%-grænserne."""

import pandas as pd

from segmentering.dataio import GROUP, ITEM_NO
from segmentering.metrics import ITEM_GM, TURNOVER_SUM
from segmentering.outliers import OUTLIER_REASON, filter_outliers, limit_text

QUIET = lambda _message: None


def make_items(rows):
    """rows: (kundegruppe, item, turnover, gm)."""
    return pd.DataFrame(
        [
            {GROUP: group, ITEM_NO: item, TURNOVER_SUM: turnover, ITEM_GM: gm}
            for group, item, turnover, gm in rows
        ]
    )


def test_without_limits_nothing_is_touched():
    items = make_items([("A", "1", 1, 0.1), ("A", "2", 10_000, 0.9)])
    kept, removed = filter_outliers(items, QUIET)
    assert len(kept) == 2
    assert removed.empty


def test_a_lower_limit_removes_a_wild_margin():
    """
    Det virkelige tilfælde: tre varer, hvor den ene har -1014 % margin.

    Det var netop dén et z-score-filter ikke kunne fange, fordi den største
    score der overhovedet kan opstå med tre varer er 1,41.
    """
    items = make_items(
        [("A", "1", 1_846_007, 0.206), ("A", "2", 14_766, 0.719),
         ("A", "3", 2_056, -10.140)]
    )
    kept, removed = filter_outliers(items, QUIET, gm_limit_min_pct=-50)
    assert list(removed[ITEM_NO]) == ["3"]
    assert list(kept[ITEM_NO]) == ["1", "2"]


def test_an_upper_limit_catches_an_impossible_margin():
    """GM over 100 % betyder at GP er større end omsætningen."""
    items = make_items(
        [("A", str(i), 100, 0.30) for i in range(3)] + [("A", "kredit", 100, 4.2)]
    )
    _, removed = filter_outliers(items, QUIET, gm_limit_max_pct=100)
    assert list(removed[ITEM_NO]) == ["kredit"]
    assert removed[OUTLIER_REASON].iloc[0] == "GM% over 100 %"


def test_a_blank_limit_means_no_limit_in_that_direction():
    # Den normale vare skal med, ellers ligger ALLE kundens varer uden for
    # spændet, og så holder filteret hånden over dem.
    items = make_items(
        [("A", "lav", 100, -5.0), ("A", "høj", 100, 4.0), ("A", "normal", 100, 0.30)]
    )
    _, only_low = filter_outliers(items, QUIET, gm_limit_min_pct=-50)
    assert list(only_low[ITEM_NO]) == ["lav"]
    _, only_high = filter_outliers(items, QUIET, gm_limit_max_pct=100)
    assert list(only_high[ITEM_NO]) == ["høj"]
    _, both = filter_outliers(items, QUIET, gm_limit_min_pct=-50, gm_limit_max_pct=100)
    assert sorted(both[ITEM_NO]) == ["høj", "lav"]


def test_the_limit_is_exclusive():
    """Præcis på grænsen er inden for: "under -50" betyder ikke "-50 og under"."""
    items = make_items(
        [("A", "præcis", 100, -0.50), ("A", "under", 100, -0.501),
         ("A", "over", 100, 0.30)]
    )
    _, removed = filter_outliers(items, QUIET, gm_limit_min_pct=-50)
    assert list(removed[ITEM_NO]) == ["under"]


def test_a_group_of_any_size_is_checked():
    """
    Grænserne kender ikke til antal varer. Det var hele pointen med at
    erstatte z-scoren, som var slukket for kunder med under seks varer.
    """
    items = make_items(
        [("A", "a1", 100, 0.30), ("A", "a2", 100, -5.0)]
        + [("B", f"b{i}", 100, 0.30) for i in range(9)]
        + [("B", "b_daarlig", 100, -5.0)]
    )
    _, removed = filter_outliers(items, QUIET, gm_limit_min_pct=-50)
    assert sorted(removed[ITEM_NO]) == ["a2", "b_daarlig"]


def test_a_customer_whose_items_are_all_outside_is_left_alone():
    """Ellers ville kunden forsvinde helt — også ud af sin egen omsætning."""
    items = make_items([("A", "1", 100, -5.0), ("A", "2", 100, -6.0)])
    beskeder: list[str] = []
    kept, removed = filter_outliers(items, beskeder.append, gm_limit_min_pct=-50)
    assert removed.empty
    assert list(kept[ITEM_NO]) == ["1", "2"]
    assert any("'A'" in m and "uden for GM%-spændet" in m for m in beskeder), beskeder


def test_a_customer_with_one_bad_item_and_nothing_else_is_left_alone():
    items = make_items([("A", "1", 100, -5.0), ("B", "2", 100, 0.30)])
    kept, removed = filter_outliers(items, QUIET, gm_limit_min_pct=-50)
    assert removed.empty
    assert sorted(kept[ITEM_NO]) == ["1", "2"]


def test_groups_are_handled_independently():
    """B mister en vare; A må ikke blive rørt af det."""
    items = make_items(
        [("A", "a1", 100, 0.30), ("A", "a2", 100, 0.32),
         ("B", "b1", 100, -5.0), ("B", "b2", 100, 0.30)]
    )
    kept, removed = filter_outliers(items, QUIET, gm_limit_min_pct=-50)
    assert sorted(kept[ITEM_NO]) == ["a1", "a2", "b2"]
    assert list(removed[ITEM_NO]) == ["b1"]


def test_a_removal_says_why():
    items = make_items([("A", "1", 100, 0.30), ("A", "2", 100, -5.0)])
    _, removed = filter_outliers(items, QUIET, gm_limit_min_pct=-50)
    assert removed[OUTLIER_REASON].iloc[0] == "GM% under -50 %"


def test_a_missing_margin_is_not_removed():
    """NaN er ikke "uden for spændet" — det er "ved ikke"."""
    items = make_items([("A", "1", 100, 0.30), ("A", "2", 100, float("nan"))])
    _, removed = filter_outliers(items, QUIET, gm_limit_min_pct=-50, gm_limit_max_pct=100)
    assert removed.empty


def test_empty_input_is_handled():
    kept, removed = filter_outliers(pd.DataFrame(), QUIET, gm_limit_min_pct=-50)
    assert kept.empty and removed.empty


def test_the_limits_are_described_in_words():
    assert limit_text(None, None) == "ingen"
    assert limit_text(-50, None) == "GM% under -50 %"
    assert limit_text(None, 100) == "GM% over 100 %"
    assert limit_text(-50, 100) == "GM% uden for -50–100 %"

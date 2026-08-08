"""Tests af outlier-filteret."""

import pandas as pd
import pytest

from segmentering.dataio import GROUP, ITEM_NO
from segmentering.metrics import ITEM_GM, TURNOVER_SUM
from segmentering.outliers import OUTLIER_REASON, filter_outliers

QUIET = lambda _message: None


def make_items(rows):
    """rows: (kundegruppe, item, turnover, gm)."""
    return pd.DataFrame(
        [
            {GROUP: group, ITEM_NO: item, TURNOVER_SUM: turnover, ITEM_GM: gm}
            for group, item, turnover, gm in rows
        ]
    )


def test_extreme_turnover_is_removed():
    items = make_items(
        [("A", str(i), 100, 0.30) for i in range(10)] + [("A", "ekstrem", 100_000, 0.30)]
    )
    kept, removed = filter_outliers(items, 2.0, "turnover", QUIET)
    assert list(removed[ITEM_NO]) == ["ekstrem"]
    assert "ekstrem" not in set(kept[ITEM_NO])


def test_metric_choice_limits_what_counts_as_extreme():
    items = make_items(
        [("A", str(i), 100, 0.30) for i in range(10)] + [("A", "ekstrem", 100_000, 0.30)]
    )
    # Kun GM bruges som kriterium, og GM er ens for alle – intet fjernes.
    kept, removed = filter_outliers(items, 2.0, "gm", QUIET)
    assert removed.empty
    assert len(kept) == 11


def test_metric_ingen_keeps_everything():
    items = make_items([("A", "1", 1, 0.1), ("A", "2", 10_000, 0.9)])
    kept, removed = filter_outliers(items, 1.0, "ingen", QUIET)
    assert len(kept) == 2
    assert removed.empty


def test_single_item_group_is_never_filtered():
    """Med kun ét item kan spredningen ikke beregnes, så kunden må ikke forsvinde."""
    items = make_items([("A", "1", 999_999, 0.99)])
    kept, removed = filter_outliers(items, 0.5, "begge", QUIET)
    assert len(kept) == 1
    assert removed.empty


def test_group_is_kept_when_every_item_looks_extreme():
    """Sikkerhedsnet: en kundegruppe må aldrig miste alle sine items."""
    items = make_items([("A", "1", 10, 0.1), ("A", "2", 10_000, 0.9)])
    kept, removed = filter_outliers(items, 0.5, "begge", QUIET)
    assert len(kept) == 2
    assert removed.empty


def test_zero_spread_removes_nothing():
    items = make_items([("A", str(i), 100, 0.3) for i in range(5)])
    kept, removed = filter_outliers(items, 1.0, "begge", QUIET)
    assert len(kept) == 5
    assert removed.empty


def test_groups_are_scored_independently():
    """
    B's items er alle små. De må ikke blive outliers, blot fordi A har
    langt større tal.
    """
    items = make_items(
        [("A", str(i), 1_000_000, 0.3) for i in range(5)]
        + [("B", str(i), 10, 0.3) for i in range(5)]
    )
    kept, removed = filter_outliers(items, 2.0, "begge", QUIET)
    assert removed.empty
    assert len(kept) == 10


def test_removed_items_carry_a_readable_reason():
    items = make_items(
        [("A", str(i), 100, 0.30) for i in range(10)] + [("A", "ekstrem", 100_000, 0.30)]
    )
    _, removed = filter_outliers(items, 2.0, "begge", QUIET)
    assert removed[OUTLIER_REASON].iloc[0] == "Turnover"


def test_unknown_metric_is_rejected():
    with pytest.raises(ValueError, match="Outlier-metrik"):
        filter_outliers(make_items([("A", "1", 1, 0.1)]), 2.0, "sludder", QUIET)


def test_empty_input_is_handled():
    kept, removed = filter_outliers(pd.DataFrame(), 2.0, "begge", QUIET)
    assert kept.empty and removed.empty

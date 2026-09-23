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


# --- Faste GM%-grænser -------------------------------------------------------


def test_a_limit_removes_what_the_z_score_cannot():
    """
    Det virkelige tilfælde: tre varer, hvor den ene har -1014 % margin.

    Z-scoren har et loft på sqrt(n-1), så med tre varer kan ingen af dem nå
    over 1,41 — tærskel 2 fjerner derfor aldrig noget. Grænsen kan.
    """
    items = make_items(
        [("A", "1", 1_846_007, 0.206), ("A", "2", 14_766, 0.719),
         ("A", "3", 2_056, -10.140)]
    )
    _, uden = filter_outliers(items, 2.0, "gm", QUIET)
    assert uden.empty, "z-scoren burde ikke kunne fange noget med tre varer"

    kept, removed = filter_outliers(items, 2.0, "gm", QUIET, gm_limit_min_pct=-30)
    assert list(removed[ITEM_NO]) == ["3"]
    assert list(kept[ITEM_NO]) == ["1", "2"]


def test_limits_work_with_the_z_score_switched_off():
    items = make_items([("A", "1", 100, 0.30), ("A", "2", 100, -5.0)])
    kept, removed = filter_outliers(items, 2.0, "ingen", QUIET, gm_limit_min_pct=-30)
    assert list(removed[ITEM_NO]) == ["2"]
    assert list(kept[ITEM_NO]) == ["1"]


def test_an_upper_limit_catches_an_impossible_margin():
    """GM over 100 % betyder at GP er større end omsætningen."""
    items = make_items([("A", str(i), 100, 0.30) for i in range(3)]
                       + [("A", "kredit", 100, 4.2)])
    _, removed = filter_outliers(items, 2.0, "ingen", QUIET, gm_limit_max_pct=100)
    assert list(removed[ITEM_NO]) == ["kredit"]
    assert removed[OUTLIER_REASON].iloc[0] == "GM% over 100 %"


def test_a_blank_limit_means_no_limit_in_that_direction():
    items = make_items([("A", "lav", 100, -5.0), ("A", "høj", 100, 4.0)])
    _, only_low = filter_outliers(items, 2.0, "ingen", QUIET, gm_limit_min_pct=-30)
    assert list(only_low[ITEM_NO]) == ["lav"]
    _, only_high = filter_outliers(items, 2.0, "ingen", QUIET, gm_limit_max_pct=100)
    assert list(only_high[ITEM_NO]) == ["høj"]
    _, neither = filter_outliers(items, 2.0, "ingen", QUIET)
    assert neither.empty


def test_a_two_item_group_is_checked_although_the_z_score_cannot():
    """
    Med to varer er z-scorens loft 1,0, så den kan aldrig fjerne noget. En
    fast grænse kan — og det er netop de små kunder grænserne er til for.
    """
    items = make_items([("A", "1", 100, 0.30), ("A", "2", 100, -5.0)])
    _, uden = filter_outliers(items, 2.0, "gm", QUIET)
    assert uden.empty
    _, med = filter_outliers(items, 2.0, "gm", QUIET, gm_limit_min_pct=-30)
    assert list(med[ITEM_NO]) == ["2"]


def test_a_customer_with_one_bad_item_and_nothing_else_is_left_alone():
    """
    Har kunden kun én vare, og ligger den uden for spændet, ville den blive
    slettet helt — kunden ville forsvinde ud af analysen og ud af sin egen
    omsætning. Så hellere lade den stå og sige det i loggen.
    """
    items = make_items([("A", "1", 100, -5.0), ("B", "2", 100, 0.30)])
    beskeder: list[str] = []
    kept, removed = filter_outliers(
        items, 2.0, "ingen", beskeder.append, gm_limit_min_pct=-30
    )
    assert removed.empty
    assert sorted(kept[ITEM_NO]) == ["1", "2"]
    assert any("'A'" in m and "uden for GM%-spændet" in m for m in beskeder), beskeder


def test_a_customer_whose_items_are_all_outside_is_left_alone():
    """Ellers ville kunden forsvinde helt — også ud af sin egen omsætning."""
    items = make_items([("A", "1", 100, -5.0), ("A", "2", 100, -6.0)])
    kept, removed = filter_outliers(items, 2.0, "ingen", QUIET, gm_limit_min_pct=-30)
    assert removed.empty
    assert list(kept[ITEM_NO]) == ["1", "2"]


def test_the_limit_is_applied_before_the_z_score():
    """
    En vare der ligger uden for grænsen skal ikke nå at trække spredningen op
    og skjule de øvrige afvigere.
    """
    items = make_items(
        [("A", str(i), 100, 0.30) for i in range(6)]
        + [("A", "lidt_skæv", 100, 0.80), ("A", "vanvittig", 100, -50.0)]
    )
    _, uden = filter_outliers(items, 2.0, "gm", QUIET)
    assert "lidt_skæv" not in list(uden[ITEM_NO]), (
        "den vanvittige vare skjuler den lidt skæve, som forventet"
    )

    _, med = filter_outliers(items, 2.0, "gm", QUIET, gm_limit_min_pct=-30)
    fjernet = list(med[ITEM_NO])
    assert "vanvittig" in fjernet, "grænsen fangede den ikke"
    assert "lidt_skæv" in fjernet, "z-scoren blev ikke renset af grænsen først"


def test_a_limit_removal_says_why():
    items = make_items([("A", "1", 100, 0.30), ("A", "2", 100, -5.0)])
    _, removed = filter_outliers(items, 2.0, "ingen", QUIET, gm_limit_min_pct=-30)
    assert removed[OUTLIER_REASON].iloc[0] == "GM% under -30 %"


def test_a_group_can_lose_every_item_to_the_limits_without_breaking():
    """
    Kunde B mister sine varer til grænsen, mens kunde A beholder sine.
    Den tomme gruppe må ikke vælte sammenlægningen til sidst.
    """
    items = make_items(
        [("A", "1", 100, 0.30), ("A", "2", 100, 0.32),
         ("B", "3", 100, -5.0), ("B", "4", 100, 0.30)]
    )
    kept, removed = filter_outliers(items, 2.0, "ingen", QUIET, gm_limit_min_pct=-30)
    assert sorted(kept[ITEM_NO]) == ["1", "2", "4"]
    assert list(removed[ITEM_NO]) == ["3"]

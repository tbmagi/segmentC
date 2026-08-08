"""
Outlier-filter på item-niveau.

Outliers vurderes altid INDEN FOR den enkelte kundegruppe: et item er kun
ekstremt sammenlignet med kundens øvrige items, ikke med hele datasættet.
"""

from __future__ import annotations

from typing import Callable, NamedTuple

import numpy as np
import pandas as pd

from .dataio import GROUP
from .metrics import ITEM_GM, TURNOVER_SUM

Log = Callable[[str], None]

TURNOVER_Z = f"{TURNOVER_SUM}_z"
GM_Z = f"{ITEM_GM}_z"
OUTLIER_REASON = "Outlier_paa"

_Z_COLUMNS = [TURNOVER_Z, GM_Z]


class OutlierSplit(NamedTuple):
    """Resultatet af filtreringen: de beholdte og de fjernede items."""

    kept: pd.DataFrame
    removed: pd.DataFrame


def _z_scores(values: pd.Series) -> pd.Series:
    """
    Z-score for en serie: ``(værdi − gennemsnit) / standardafvigelse``.

    Er spredningen 0 (alle items ens) eller uberegnelig, returneres NaN, så
    ingen items markeres som ekstreme på den metrik.
    """
    std = values.std(ddof=0)
    if pd.isna(std) or std == 0:
        return pd.Series(np.nan, index=values.index)
    return (values - values.mean()) / std


def filter_outliers(
    per_item: pd.DataFrame,
    std_threshold: float,
    metric: str = "begge",
    log: Log = print,
) -> OutlierSplit:
    """
    Fjerner items hvor |z-score| overstiger ``std_threshold``.

    ``metric`` vælger hvilke mål der udløser frasortering:

        "begge"    – Turnover ELLER GM% er ekstrem
        "turnover" – kun usædvanlig høj/lav omsætning
        "gm"       – kun usædvanlig høj/lav margin
        "ingen"    – ingen filtrering

    To sikkerhedsregler gælder: kundegrupper med kun ét item filtreres aldrig
    (spredning kan ikke beregnes), og en gruppe hvor alle items ser ekstreme
    ud beholdes urørt frem for at forsvinde helt fra plottet.

    De fjernede items returneres med deres z-scores og en læsbar årsag, så de
    kan gennemgås på Excel-fanen 'Outliers'.
    """
    if metric not in ("begge", "turnover", "gm", "ingen"):
        raise ValueError(
            "Outlier-metrik skal være 'begge', 'turnover', 'gm' eller 'ingen', "
            f"fik: {metric!r}"
        )

    if per_item.empty or metric == "ingen":
        return OutlierSplit(kept=per_item.copy(), removed=pd.DataFrame())

    use_turnover = metric in ("begge", "turnover")
    use_gm = metric in ("begge", "gm")

    kept_frames: list[pd.DataFrame] = []
    removed_frames: list[pd.DataFrame] = []

    for _, group_df in per_item.groupby(GROUP, sort=False):
        if len(group_df) < 2:
            kept_frames.append(group_df)
            continue

        scored = group_df.copy()
        scored[TURNOVER_Z] = _z_scores(scored[TURNOVER_SUM])
        scored[GM_Z] = _z_scores(scored[ITEM_GM])

        no_outliers = pd.Series(False, index=scored.index)
        turnover_extreme = (
            scored[TURNOVER_Z].abs() > std_threshold if use_turnover else no_outliers
        )
        gm_extreme = scored[GM_Z].abs() > std_threshold if use_gm else no_outliers
        is_outlier = turnover_extreme.fillna(False) | gm_extreme.fillna(False)

        if is_outlier.all():
            kept_frames.append(scored.drop(columns=_Z_COLUMNS))
            continue

        if is_outlier.any():
            removed = scored[is_outlier].copy()
            removed[OUTLIER_REASON] = [
                ", ".join(
                    reason
                    for reason, hit in (
                        ("Turnover", turnover_extreme.get(index, False)),
                        ("GM%", gm_extreme.get(index, False)),
                    )
                    if hit
                )
                for index in removed.index
            ]
            removed_frames.append(removed)

        kept_frames.append(scored[~is_outlier].drop(columns=_Z_COLUMNS))

    kept = pd.concat(kept_frames, ignore_index=True)
    removed_all = (
        pd.concat(removed_frames, ignore_index=True)
        if removed_frames
        else pd.DataFrame()
    )

    log(
        f"  Outlier-filter (±{std_threshold} std, metrik='{metric}'): "
        f"fjernede {len(removed_all)} items, beholder {len(kept)} items"
    )
    return OutlierSplit(kept=kept, removed=removed_all)

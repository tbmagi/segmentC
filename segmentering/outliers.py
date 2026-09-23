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


def _gm_limit_reasons(
    values: pd.Series, low: float | None, high: float | None
) -> pd.Series:
    """
    Årsagsteksten for hver vare der ligger uden for GM%-spændet — ellers "".

    Grænserne er i procent, mens ``values`` er en brøkdel, så 20,6 % står som
    0,206. Sammenligningen sker i procent, fordi det er det brugeren har
    skrevet i indstillingerne og det der skal stå i Excel-arket.
    """
    percent = values * 100
    reasons = pd.Series("", index=values.index, dtype=object)
    if low is not None:
        below = percent < low
        reasons[below.fillna(False)] = f"GM% under {low:g} %"
    if high is not None:
        above = percent > high
        reasons[above.fillna(False)] = f"GM% over {high:g} %"
    return reasons


def filter_outliers(
    per_item: pd.DataFrame,
    std_threshold: float,
    metric: str = "begge",
    log: Log = print,
    gm_limit_min_pct: float | None = None,
    gm_limit_max_pct: float | None = None,
) -> OutlierSplit:
    """
    Fjerner items der falder uden for et fast GM%-spænd eller har en ekstrem
    z-score.

    De to mekanismer er uafhængige og kan bruges hver for sig:

    **Faste grænser** (``gm_limit_min_pct`` / ``gm_limit_max_pct``, i procent)
    fjerner varer hvis margin ligger uden for spændet. En grænse på ``None``
    betyder ingen grænse i den retning. Grænserne virker uanset ``metric`` —
    også når z-score-filteret er slået helt fra — og uanset hvor få varer
    kunden har.

    **Z-score** (``std_threshold``, ``metric``) fjerner varer der er ekstreme
    *sammenlignet med kundens øvrige varer*::

        "begge"    – Turnover ELLER GM% er ekstrem
        "turnover" – kun usædvanlig høj/lav omsætning
        "gm"       – kun usædvanlig høj/lav margin
        "ingen"    – ingen z-score-filtrering

    Grænserne anvendes FØRST, og z-scoren beregnes på det der er tilbage. Det
    er ikke en detalje: en vare med −1014 % margin trækker selv gennemsnittet
    og spredningen så meget at dens egen z-score bliver lille, og den skjuler
    samtidig de øvrige afvigere. Fjernes den først, måles resten mod et
    fornuftigt målebånd.

    To sikkerhedsregler gælder for z-scoren: kundegrupper med kun ét item
    filtreres aldrig (spredning kan ikke beregnes), og en gruppe hvor alle
    items ser ekstreme ud beholdes urørt frem for at forsvinde helt fra
    plottet. Den sidste regel gælder også de faste grænser, så en kunde aldrig
    kan forsvinde helt ud af analysen — er det tilfældet, siges det i loggen.

    De fjernede items returneres med deres z-scores og en læsbar årsag, så de
    kan gennemgås på Excel-fanen 'Outliers'.
    """
    if metric not in ("begge", "turnover", "gm", "ingen"):
        raise ValueError(
            "Outlier-metrik skal være 'begge', 'turnover', 'gm' eller 'ingen', "
            f"fik: {metric!r}"
        )

    has_limits = gm_limit_min_pct is not None or gm_limit_max_pct is not None
    if per_item.empty or (metric == "ingen" and not has_limits):
        return OutlierSplit(kept=per_item.copy(), removed=pd.DataFrame())

    use_turnover = metric in ("begge", "turnover")
    use_gm = metric in ("begge", "gm")

    kept_frames: list[pd.DataFrame] = []
    removed_frames: list[pd.DataFrame] = []
    kept_whole: list[str] = []

    for name, group_df in per_item.groupby(GROUP, sort=False):
        # --- Trin 1: de faste grænser, uafhængigt af antal varer ------------
        limit_reasons = (
            _gm_limit_reasons(group_df[ITEM_GM], gm_limit_min_pct, gm_limit_max_pct)
            if has_limits
            else pd.Series("", index=group_df.index, dtype=object)
        )
        outside = limit_reasons != ""
        if outside.all() and len(group_df) > 0:
            # Alle kundens varer ligger uden for spændet. Fjernes de, ryger
            # kunden helt ud af analysen — også ud af sin egen omsætning.
            kept_whole.append(str(name))
            kept_frames.append(group_df)
            continue
        if outside.any():
            removed = group_df[outside].copy()
            removed[TURNOVER_Z] = np.nan
            removed[GM_Z] = np.nan
            removed[OUTLIER_REASON] = limit_reasons[outside]
            removed_frames.append(removed)
            group_df = group_df[~outside]

        # --- Trin 2: z-score på det der er tilbage --------------------------
        if metric == "ingen" or len(group_df) < 2:
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

    # Tomme rammer sorteres fra: en kundegruppe kan have mistet alle sine
    # varer til grænserne, og pandas brokker sig over at lægge tomme sammen.
    kept_parts = [frame for frame in kept_frames if not frame.empty]
    kept = (
        pd.concat(kept_parts, ignore_index=True)
        if kept_parts
        else per_item.iloc[0:0].copy()
    )
    removed_all = (
        pd.concat(removed_frames, ignore_index=True)
        if removed_frames
        else pd.DataFrame()
    )

    limits = _limit_text(gm_limit_min_pct, gm_limit_max_pct)
    rule = f"±{std_threshold} std, metrik='{metric}'" if metric != "ingen" else "kun grænser"
    log(
        f"  Outlier-filter ({rule}{limits}): "
        f"fjernede {len(removed_all)} items, beholder {len(kept)} items"
    )
    for name in kept_whole:
        log(
            f"    BEMÆRK: alle varer hos '{name}' ligger uden for GM%-spændet "
            "– kundegruppen er beholdt urørt frem for at forsvinde"
        )
    return OutlierSplit(kept=kept, removed=removed_all)


def _limit_text(low: float | None, high: float | None) -> str:
    """Grænserne skrevet til loggen, eller "" hvis der ingen er."""
    if low is None and high is None:
        return ""
    if low is None:
        return f", GM% over {high:g} %"
    if high is None:
        return f", GM% under {low:g} %"
    return f", GM% uden for {low:g}–{high:g} %"

"""
Frasortering af varer med en urimelig GM%.

Filteret er et fast spænd: ligger en vares margin uden for det, ryger den ud.
Ingen statistik, ingen sammenligning med kundens øvrige varer.

Det var der før et z-score-filter, og det blev taget ud igen. Grunden er at
den største z-score der overhovedet kan opstå i en gruppe med ``n`` varer er
``√(n−1)``: med tre varer kan ingen af dem nå over 1,41, og med tærskel 2
fjernedes der derfor aldrig noget hos en kunde med under seks varer — uanset
hvor vild marginen var. Varen var selv med til at bestemme det målebånd den
blev målt med. Langt de fleste af vores kunder har under seks varer, så
filteret var reelt slukket netop dér hvor der var brug for det.
"""

from __future__ import annotations

from typing import Callable, NamedTuple

import pandas as pd

from .dataio import GROUP
from .metrics import ITEM_GM

Log = Callable[[str], None]

OUTLIER_REASON = "Outlier_paa"


class OutlierSplit(NamedTuple):
    """Resultatet af filtreringen: de beholdte og de fjernede items."""

    kept: pd.DataFrame
    removed: pd.DataFrame


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
        reasons[(percent < low).fillna(False)] = f"GM% under {low:g} %"
    if high is not None:
        reasons[(percent > high).fillna(False)] = f"GM% over {high:g} %"
    return reasons


def filter_outliers(
    per_item: pd.DataFrame,
    log: Log = print,
    gm_limit_min_pct: float | None = None,
    gm_limit_max_pct: float | None = None,
) -> OutlierSplit:
    """
    Fjerner varer hvis GM% ligger uden for spændet.

    En grænse på ``None`` betyder ingen grænse i den retning, så man kan
    nøjes med en nedre, en øvre eller begge. Er begge ``None``, røres der
    ingenting.

    Grænsen gælder hver vare for sig og kender ikke til kundens størrelse:
    en kunde med én vare under grænsen mister den vare, ligesom en kunde med
    halvtreds ville. Mister en kunde ALLE sine varer, forsvinder den ud af
    analysen — også ud af den samlede omsætning. Det er med vilje: har kunden
    kun urimelige tal tilbage, ville den blive tegnet et meningsløst sted.
    Kunden nævnes ved navn i loggen, og dens varer står stadig på Excel-fanen
    'Outliers' med en årsag, så det kan efterprøves.

    De fjernede varer returneres med en læsbar årsag, så de kan gennemgås på
    Excel-fanen 'Outliers'.
    """
    has_limits = gm_limit_min_pct is not None or gm_limit_max_pct is not None
    if per_item.empty or not has_limits:
        return OutlierSplit(kept=per_item.copy(), removed=pd.DataFrame())

    kept_frames: list[pd.DataFrame] = []
    removed_frames: list[pd.DataFrame] = []
    emptied: list[str] = []

    for name, group_df in per_item.groupby(GROUP, sort=False):
        reasons = _gm_limit_reasons(
            group_df[ITEM_GM], gm_limit_min_pct, gm_limit_max_pct
        )
        outside = reasons != ""
        if outside.any():
            removed = group_df[outside].copy()
            removed[OUTLIER_REASON] = reasons[outside]
            removed_frames.append(removed)
        if outside.all():
            emptied.append(str(name))
        kept_frames.append(group_df[~outside])

    # Tomme rammer sorteres fra: pandas brokker sig over at lægge tomme sammen.
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

    log(
        f"  GM%-grænser ({limit_text(gm_limit_min_pct, gm_limit_max_pct)}): "
        f"fjernede {len(removed_all)} varer, beholder {len(kept)} varer"
    )
    if emptied:
        log(
            f"    ADVARSEL: {len(emptied)} kundegruppe(r) mistede ALLE deres "
            "varer til GM%-grænsen og indgår derfor ikke i analysen:"
        )
        for name in emptied:
            log(f"      - {name}")
        log("      (varerne står på Excel-fanen 'Outliers' med en årsag)")
    return OutlierSplit(kept=kept, removed=removed_all)


def limit_text(low: float | None, high: float | None) -> str:
    """Grænserne skrevet som tekst, til loggen og plottets undertitel."""
    if low is None and high is None:
        return "ingen"
    if low is None:
        return f"GM% over {high:g} %"
    if high is None:
        return f"GM% under {low:g} %"
    return f"GM% uden for {low:g}–{high:g} %"

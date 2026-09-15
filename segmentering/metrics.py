"""
Beregningerne bag de to akser.

X-aksen er Gross Margin % pr. item, aggregeret vægtet op til kundegruppe.
Y-aksen er omsætningen i et rullende vindue på N måneder.

Alle funktioner tager de parametre de bruger som argumenter — der er ingen
skjult afhængighed af global opsætning.
"""

from __future__ import annotations

from typing import Callable, Iterable

import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta

from .classify import classify_customer_category
from .config import Config
from .dataio import (
    BLANK_KAM,
    GROSS_PROFIT,
    GROUP,
    INDUSTRY_SEGMENT,
    ITEM_NO,
    KAM,
    PERIOD,
    TURNOVER,
    find_column,
)

Log = Callable[[str], None]

# Kolonner der produceres i dette modul.
TURNOVER_SUM = "Turnover_sum"
GP_SUM = "GP_sum"
FIRST_ACTIVITY = "tidligste_dato"
LAST_ACTIVITY = "seneste_dato"
WINDOW_ITEM = "Turnover_window_item"
WINDOW_GROUP = "Turnover_window_group"
ITEM_GM = "GM_pct_item"

ITEM_KEYS = [GROUP, ITEM_NO]

_EMPTY_ITEM_COLUMNS = [
    *ITEM_KEYS,
    TURNOVER_SUM,
    GP_SUM,
    LAST_ACTIVITY,
    FIRST_ACTIVITY,
    WINDOW_ITEM,
    WINDOW_GROUP,
    ITEM_GM,
    KAM,
]


# --- Frasortering af døde items ---------------------------------------------


def drop_dead_items(
    df: pd.DataFrame, window_months: int, log: Log = print
) -> pd.DataFrame:
    """
    Fjerner items uden aktivitet i kundegruppens turnover-vindue.

    Frasorteringen sker FØR alle beregninger, så GM% (X-aksen),
    turnover-vinduet (Y-aksen) og item-plottet bygger på præcis det samme
    grundlag.

    Forankringen er altid kundens seneste aktivitetsdato — uafhængigt af
    forankringsvalget for de to plots. Vinduet er
    ``[seneste − (window_months − 1) måneder ; seneste]``, og et item beholdes
    kun hvis dets egen seneste aktivitet falder inden for det.
    """
    if df.empty or window_months < 1:
        return df

    group_last = df.groupby(GROUP)[PERIOD].transform("max")
    window_start = group_last - pd.offsets.DateOffset(months=window_months - 1)
    item_last = df.groupby(ITEM_KEYS)[PERIOD].transform("max")

    keep = item_last >= window_start
    dropped_rows = int((~keep).sum())
    if dropped_rows:
        dropped_items = len(df.loc[~keep, ITEM_KEYS].drop_duplicates())
        log(
            f"  Frasortering af døde items: fjernede {dropped_items} unikke items "
            f"({dropped_rows} rækker) uden aktivitet i turnover-vinduet "
            f"({window_months} mdr. forankret i kundens seneste aktivitet)"
        )
    return df[keep].copy()


# --- Grundlag for GM% pr. item ----------------------------------------------


def item_gm_basis(df: pd.DataFrame, gm_months: int) -> pd.DataFrame:
    """
    Summerer Turnover og GP pr. (kundegruppe, item no.) over item'ets seneste
    aktivitetsmåneder.

    ``gm_months=1`` bruger kun den seneste måned. For N > 1 summeres de N
    seneste DISTINKTE aktivitetsmåneder, hvilket giver et omsætningsvægtet
    GM% over perioden: en stor måned vejer mere end en lille, og støj fra
    enkeltmåneder (kampagnepris, engangsrabat, valutaudsving) dæmpes.

    Der tælles i aktivitetsmåneder, ikke kalendermåneder: har et item kun to
    måneder med salg og ``gm_months=3``, bruges de to.
    """
    if df.empty:
        return pd.DataFrame(
            columns=[*ITEM_KEYS, TURNOVER_SUM, GP_SUM, LAST_ACTIVITY]
        )

    if gm_months <= 1:
        month_rank = df.groupby(ITEM_KEYS)[PERIOD].transform("max")
        relevant = df[df[PERIOD] == month_rank]
    else:
        month_rank = df.groupby(ITEM_KEYS)[PERIOD].rank(
            method="dense", ascending=False
        )
        relevant = df[month_rank <= gm_months]

    return relevant.groupby(ITEM_KEYS, as_index=False).agg(
        **{
            TURNOVER_SUM: (TURNOVER, "sum"),
            GP_SUM: (GROSS_PROFIT, "sum"),
            LAST_ACTIVITY: (PERIOD, "max"),
        }
    )


# --- Rullende turnover-vindue ------------------------------------------------


def turnover_window(
    df: pd.DataFrame, months: int, anchor: str = "item"
) -> pd.DataFrame:
    """
    Summerer omsætningen pr. (kundegruppe, item no.) over et rullende vindue.

    ``anchor="item"``  – vinduet slutter ved hvert items egen seneste aktivitet,
    så hvert item måles over sine egne seneste N aktive måneder.

    ``anchor="group"`` – vinduet slutter ved kundegruppens seneste aktivitet,
    så alle items i én kunde dækker præcis samme kalenderperiode.

    Alle items i input får en række. Items uden omsætning i vinduet får 0 frem
    for at mangle, så item-sættet bliver det samme uanset forankring.
    """
    if df.empty:
        return pd.DataFrame(columns=[*ITEM_KEYS, "Turnover_window"])

    anchor_keys = [GROUP] if anchor == "group" else ITEM_KEYS
    anchors = (
        df.groupby(anchor_keys)[PERIOD].max().rename("_anchor_end").reset_index()
    )
    joined = df.merge(anchors, on=anchor_keys)
    joined["_window_start"] = joined["_anchor_end"].apply(
        lambda end: end - relativedelta(months=months - 1)
    )

    in_window = joined[
        (joined[PERIOD] >= joined["_window_start"])
        & (joined[PERIOD] <= joined["_anchor_end"])
    ]
    totals = in_window.groupby(ITEM_KEYS, as_index=False).agg(
        Turnover_window=(TURNOVER, "sum")
    )

    all_items = df[ITEM_KEYS].drop_duplicates()
    result = all_items.merge(totals, on=ITEM_KEYS, how="left")
    result["Turnover_window"] = result["Turnover_window"].fillna(0)
    return result


# --- Samlet item-tabel -------------------------------------------------------


def item_metrics(df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """
    Bygger én række pr. (kundegruppe, item no.) med alt hvad plots og rapport
    skal bruge: GM%-grundlag, begge turnover-vinduer og aktivitetsdatoer.

    Begge vinduer beregnes, fordi kundegruppe-plottet og item-plottet kan have
    hver sin forankring. Er forankringerne ens, genbruges resultatet frem for
    at regne det samme to gange — så er de to kolonner garanteret identiske.
    """
    if df.empty:
        return pd.DataFrame(columns=_EMPTY_ITEM_COLUMNS)

    per_item = item_gm_basis(df, cfg.gm_months)

    by_item_anchor = turnover_window(
        df, cfg.turnover_window_months, cfg.item_plot_anchor
    ).rename(columns={"Turnover_window": WINDOW_ITEM})

    if cfg.group_plot_anchor == cfg.item_plot_anchor:
        windows = by_item_anchor.copy()
        windows[WINDOW_GROUP] = windows[WINDOW_ITEM]
    else:
        by_group_anchor = turnover_window(
            df, cfg.turnover_window_months, cfg.group_plot_anchor
        ).rename(columns={"Turnover_window": WINDOW_GROUP})
        windows = by_item_anchor.merge(by_group_anchor, on=ITEM_KEYS, how="inner")

    per_item = per_item.merge(windows, on=ITEM_KEYS, how="inner")

    first_activity = (
        df.groupby(ITEM_KEYS)[PERIOD]
        .min()
        .reset_index()
        .rename(columns={PERIOD: FIRST_ACTIVITY})
    )
    per_item = per_item.merge(first_activity, on=ITEM_KEYS, how="left")

    per_item[ITEM_GM] = np.where(
        per_item[TURNOVER_SUM] != 0,
        per_item[GP_SUM] / per_item[TURNOVER_SUM],
        np.nan,
    )
    # KAM slås op pr. kundegruppe, ikke pr. item, så en vare altid følger den
    # KAM der har kunden. Ellers kunne to varer hos samme kunde havne under
    # hver sin knap på item-plottet.
    per_item[KAM] = per_item[GROUP].map(kam_by_group(df))
    return per_item


# --- Aggregering til kundegruppe --------------------------------------------


def group_metrics(
    per_item: pd.DataFrame,
    source_df: pd.DataFrame,
    cfg: Config,
    customer_types: dict[str, str],
) -> pd.DataFrame:
    """
    Aggregerer item-tabellen op til én række pr. kundegruppe.

    ``customer_types`` slås op frem for at blive genberegnet, så kundetypen er
    den samme i plot og rapport uanset hvilket udsnit der køres.

    ``samlet_GM`` er det omsætningsvægtede GM% (samlet GP / samlet turnover) —
    kundens reelle samlede margin. ``gns_GM`` er det simple gennemsnit af
    item-margener og indgår kun i den fulde Excel-rapport.
    """
    if per_item.empty:
        return pd.DataFrame(
            columns=[
                GROUP,
                "gns_turnover",
                "samlet_turnover",
                "samlet_turnover_window",
                "gns_turnover_window",
                "samlet_GP",
                "antal_items",
                "tidligste_aktivitet",
                "seneste_aktivitet",
                "samlet_GM",
                "gns_GM",
                "Kundekategori",
                "Kundetype",
                INDUSTRY_SEGMENT,
                KAM,
            ]
        )

    per_group = per_item.groupby(GROUP, as_index=False).agg(
        gns_turnover=(TURNOVER_SUM, "mean"),
        samlet_turnover=(TURNOVER_SUM, "sum"),
        samlet_turnover_window=(WINDOW_GROUP, "sum"),
        gns_turnover_window=(WINDOW_GROUP, "mean"),
        samlet_GP=(GP_SUM, "sum"),
        gns_GM=(ITEM_GM, "mean"),
        antal_items=(ITEM_NO, "nunique"),
        tidligste_aktivitet=(FIRST_ACTIVITY, "min"),
        seneste_aktivitet=(LAST_ACTIVITY, "max"),
    )

    per_group["samlet_GM"] = np.where(
        per_group["samlet_turnover"] != 0,
        per_group["samlet_GP"] / per_group["samlet_turnover"],
        np.nan,
    )
    per_group["Kundekategori"] = [
        classify_customer_category(turnover, margin, cfg.category_bands)
        for turnover, margin in zip(
            per_group["samlet_turnover_window"], per_group["samlet_GM"]
        )
    ]
    per_group["Kundetype"] = per_group[GROUP].map(customer_types)
    per_group[INDUSTRY_SEGMENT] = per_group[GROUP].map(
        _industry_segment_by_group(source_df)
    )
    per_group[KAM] = per_group[GROUP].map(kam_by_group(source_df))
    return per_group


def _clean_kam(value: object) -> str | None:
    """Trimmer en KAM-værdi. Tomt eller manglende giver None."""
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def sort_kams(values: Iterable[object]) -> list[object]:
    """Sorterer KAM-navne alfabetisk med '(Blank)' sidst."""
    return sorted(values, key=lambda v: (v == BLANK_KAM, str(v).casefold()))


def kam_by_group(df: pd.DataFrame) -> dict[str, object]:
    """
    Finder den ansvarlige KAM pr. kundegruppe.

    Kolonnen ligger på rækkeniveau, så den samme kunde kan have flere KAM'er
    hen over historikken — fx efter en overdragelse. Kunden tildeles den KAM
    der står på den SENESTE aktivitet, så plottet viser hvem der har kunden
    i dag frem for hvem der engang havde den.

    Store og små bogstaver er uden betydning: 'PHA' og 'pHA' er samme person
    og havner under samme knap. Som visningsform bruges den stavemåde der står
    på den nyeste række — samme "seneste vinder"-regel som ellers.

    Kunder helt uden KAM får ``BLANK_KAM``. Står feltet tomt på de nyeste
    rækker, men har kunden en KAM længere tilbage, bruges den sidst kendte —
    et tomt felt er som regel manglende data, ikke en kunde uden ansvarlig.

    Kolonnen er valgfri. Findes den ikke, returneres et tomt opslag, og
    KAM-opdelingen springes helt over.
    """
    column = find_column(df, KAM)
    if column is None:
        return {}

    all_groups = df[GROUP].dropna().unique()
    working = df[[GROUP, PERIOD, column]].copy()
    working["_kam"] = working[column].map(_clean_kam)
    named = working[working["_kam"].notna()]
    if named.empty:
        return {group: BLANK_KAM for group in all_groups}

    # sort_values er stabil, så den sidste række er den nyeste.
    ordered = named.sort_values(PERIOD)

    # Kanonisk stavemåde pr. person: den der står på den nyeste række.
    canonical: dict[str, str] = {}
    for value in ordered["_kam"]:
        canonical[value.casefold()] = value

    latest = ordered.groupby(GROUP)["_kam"].last()
    result: dict[str, object] = {
        group: canonical[value.casefold()] for group, value in latest.items()
    }
    for group in all_groups:
        result.setdefault(group, BLANK_KAM)
    return result


def _industry_segment_by_group(df: pd.DataFrame) -> dict[str, object]:
    """
    Slår Industry_segment op pr. kundegruppe.

    Kolonnen er valgfri. Findes den, bruges den hyppigste værdi pr. gruppe,
    så enkelte afvigende rækker ikke ændrer kundens segment.
    """
    column = find_column(df, INDUSTRY_SEGMENT)
    if column is None:
        return {}
    modes = df.groupby(GROUP)[column].agg(
        lambda values: values.mode().iloc[0] if not values.mode().empty else None
    )
    return modes.to_dict()

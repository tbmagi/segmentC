"""
Klassifikation af item-numre, kundetyper og kundekategorier.

Funktionerne her er rene: de læser kun deres argumenter og har ingen
sideeffekter, så de kan afprøves enkeltvis.
"""

from __future__ import annotations

from typing import Mapping

import pandas as pd

from .config import Band
from .dataio import FISCAL_YEAR, GROUP, PERIOD, ReferenceDates, find_column

# Item-typer
SINTER = "sintere"
CAST = "støbe"
OTHER = "andet"

#: Visningsnavne — det der står i knapperne og i kundenavnet.
ITEM_TYPE_LABELS = {SINTER: "Sinter", CAST: "Støb", OTHER: "Andet"}

#: Manuelle suffikser på item no. der overruler den automatiske regel.
MANUAL_SUFFIXES = {"-S0": OTHER, "-S1": SINTER, "-S2": CAST}


def classify_item_no(value: object) -> str:
    """
    Klassificerer et item no. som sinter-, støbe- eller andet-emne.

    Et manuelt suffix vinder altid over den automatiske regel:

        -S1  ->  sinteremne
        -S2  ->  støbeemne
        -S0  ->  fjernes fra segmenteringen

    Uden suffix bruges nummerets to første cifre, og nummeret skal være
    reelt numerisk og mindst 6 cifre langt:

        60-67  ->  støbe
        70-77  ->  sintere
        alt andet  ->  andet
    """
    if pd.isna(value):
        return OTHER

    text = str(value).strip()
    # Excel gør ofte heltal til float, så "601234" bliver til "601234.0".
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]

    upper = text.upper()
    for suffix, item_type in MANUAL_SUFFIXES.items():
        if upper.endswith(suffix):
            return item_type

    if not text.isdigit() or len(text) < 6:
        return OTHER
    prefix = int(text[:2])
    if 60 <= prefix <= 67:
        return CAST
    if 70 <= prefix <= 77:
        return SINTER
    return OTHER


def has_manual_suffix(series: pd.Series) -> pd.Series:
    """Maske over item-numre med et eksplicit -S0/-S1/-S2 suffix."""
    upper = series.astype(str).str.strip().str.upper()
    return upper.str.endswith(tuple(MANUAL_SUFFIXES))


def classify_customer_type(
    group_df: pd.DataFrame,
    dates: ReferenceDates,
    new_fiscal_year: str | None = None,
    fiscal_year_column: str | None = None,
) -> str:
    """
    Klassificerer én kundegruppe ud fra dens samlede historik.

    Reglerne evalueres i denne rækkefølge:

    1. Har kunden aktivitet i ``new_fiscal_year`` og ingen anden historik
       -> "Ny".
    2. Har kunden aktivitet i vinduet [window_start ; today], eller er den
       aktiv i ny-året men har også ældre historik (genoplivet kunde)
       -> "Eksisterende".
    3. Er der intet ny-regnskabsår sat, og ligger mindst én række efter
       'dags dato' -> "Ny" (dato-baseret fallback).
    4. Ellers -> "Tidligere".
    """
    periods = group_df[PERIOD].dropna()
    if periods.empty:
        return "Ukendt"

    active_in_new_year = False
    active_in_other_year = False
    if new_fiscal_year and fiscal_year_column and fiscal_year_column in group_df.columns:
        target = str(new_fiscal_year).strip().lower()
        values = (
            group_df[fiscal_year_column].dropna().astype(str).str.strip().str.lower()
        )
        active_in_new_year = bool((values == target).any())
        active_in_other_year = bool((values != target).any())

        if active_in_new_year and not active_in_other_year:
            return "Ny"

    in_window = ((periods >= dates.window_start) & (periods <= dates.today)).any()
    if in_window or (active_in_new_year and active_in_other_year):
        return "Eksisterende"

    if not new_fiscal_year and (periods > dates.today).any():
        return "Ny"

    return "Tidligere"


def customer_types_by_group(
    df: pd.DataFrame,
    dates: ReferenceDates,
    new_fiscal_year: str | None,
) -> dict[str, str]:
    """Klassificerer hver kundegruppe i ``df`` og returnerer et opslag."""
    fiscal_column = find_column(df, FISCAL_YEAR)
    return {
        group: classify_customer_type(group_df, dates, new_fiscal_year, fiscal_column)
        for group, group_df in df.groupby(GROUP)
    }


def classify_customer_category(
    turnover_window: float, gross_margin: float, bands: Mapping[str, Band]
) -> str:
    """
    Klassificerer en kundegruppe som A/B/C/D med et "+"- eller "-"-suffix.

    Bogstavet bestemmes alene af omsætningen i turnover-vinduet. Suffikset
    fortæller om kundens GM% når kategoriens GM-krav:

        GM% >= krav  ->  "+"
        GM% <  krav  ->  "-"

    Båndene gennemløbes fra det højeste turnover-krav og nedad, så resultatet
    ikke afhænger af den rækkefølge de er defineret i. ``Config.validate``
    sikrer samtidig at båndene er disjunkte, så højst ét kan matche.

    Returnerer "-" hvis værdier mangler, eller hvis ingen bånd matcher.
    """
    if pd.isna(turnover_window) or pd.isna(gross_margin):
        return "-"
    ordered = sorted(bands.items(), key=lambda item: item[1].turnover_min, reverse=True)
    for name, band in ordered:
        if band.contains_turnover(turnover_window):
            return f"{name}{'+' if gross_margin >= band.gm_min else '-'}"
    return "-"


def category_sort_key(category: str) -> tuple[int, int]:
    """
    Sorteringsnøgle for kategori-blokke i Plotly-legender.

    Giver rækkefølgen A+, A-, B+, B-, C+, C-, D+, D- med ukendte til sidst.
    """
    if not category or category == "-":
        return (99, 9)
    rank = {"A": 0, "B": 1, "C": 2, "D": 3}.get(category[0], 50)
    sign = 0 if category.endswith("+") else (1 if category.endswith("-") else 2)
    return (rank, sign)

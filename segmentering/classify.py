"""
Klassifikation af item-numre, kundetyper og kundekategorier.

Funktionerne her er rene: de læser kun deres argumenter og har ingen
sideeffekter, så de kan afprøves enkeltvis.
"""

from __future__ import annotations

from typing import Mapping

import pandas as pd

from .config import Band
from .dataio import GROUP, PERIOD, ReferenceDates

# Item-typer
SINTER = "sintere"
CAST = "støbe"
OTHER = "andet"

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


def classify_customer_type(group_df: pd.DataFrame, dates: ReferenceDates) -> str:
    """
    Klassificerer én kundegruppe ud fra hvornår den har handlet.

    Alt afgøres af datoerne i data — ikke af kolonnen 'Fiscal year'. Den
    kolonne kunne være skrevet "2026/27" ét sted og "2026/2027" et andet, og
    så faldt en ny kunde stiltiende ned i "Eksisterende". Ny-regnskabsåret
    udledes nu af sin startmåned: 2026/2027 er 05-2026 til og med 04-2027.

    Reglerne evalueres i denne rækkefølge:

    1. Ligger **al** aktivitet inden for ny-regnskabsåret -> "Ny".
       Det er hele historikken der skal ligge der, ikke bare den seneste
       handel; en kunde der også har handlet før, er ikke ny.
    2. Er kunden i gang i ny-regnskabsåret, men har den ikke handlet i
       vinduet i tiden op til året begyndte -> "Genopstået". Det er kunden
       der har ligget stille længe og nu er tilbage.
    3. Ligger **mindst én** aktivitet i vinduet [window_start ; today]
       -> "Eksisterende". Den kunde der handler løbende.
    4. Ellers -> "Tidligere".

    De to perioder overlapper: med 24 måneders vindue og et regnskabsår der
    begyndte for fire måneder siden, ligger ny-årets måneder også i vinduet.
    Rækkefølgen afgør det — regel 1 kommer først, så en kunde hvis historik
    ligger helt inden for ny-året bliver "Ny" og ikke "Eksisterende".

    Forskellen på 2 og 3 er hullet. To kunder kan begge have handlet i sidste
    måned og begge have gammel historik; den ene har handlet støt hele vejen
    (eksisterende), den anden har ikke rørt os i årevis (genopstået). Det er
    to forskellige salgssituationer, og de skal kunne skelnes på plottet.
    """
    periods = group_df[PERIOD].dropna()
    if periods.empty:
        return "Ukendt"

    in_window = ((periods >= dates.window_start) & (periods <= dates.today)).any()

    if dates.fiscal_start is not None:
        in_fiscal_year = (periods >= dates.fiscal_start) & (periods <= dates.fiscal_end)
        if in_fiscal_year.all():
            return "Ny"
        if in_fiscal_year.any():
            # Har kunden ikke handlet i vinduet FØR ny-året begyndte, har den
            # været væk — uanset hvor langt tilbage den gamle historik går.
            dormant = (periods >= dates.window_start) & (periods < dates.fiscal_start)
            if not dormant.any():
                return "Genopstået"

    if in_window:
        return "Eksisterende"

    return "Tidligere"


def customer_types_by_group(
    df: pd.DataFrame, dates: ReferenceDates
) -> dict[str, str]:
    """Klassificerer hver kundegruppe i ``df`` og returnerer et opslag."""
    return {
        group: classify_customer_type(group_df, dates)
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

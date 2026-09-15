"""
Orkestrering af hele analysen.

Emne-type (sinter/støb) og geografi (DK/CN) er ikke længere adskilte kørsler
med hver sit sæt filer. De er nu egenskaber ved den enkelte analyseenhed, så
de kan tændes og slukkes direkte i grafen sammen med kundetype, kategori og
KAM.

Det betyder at en kunde med både sinter og støb bliver til FLERE enheder —
"GRUNDFOSS (Sinter)" og "GRUNDFOSS (Støb)" — der hver især har deres egen
omsætning og margin. Kendetegnene tilføjes kun når de er nødvendige for at
skelne: har en kunde kun sinter, hedder den bare "GRUNDFOSS".

Tilbage som egentligt udsnit er kun kundeudvalget: alle kunder, og valgfrit
en ekstra kørsel med kun eksisterende.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable

import pandas as pd

from .classify import ITEM_TYPE_LABELS, classify_item_no, customer_types_by_group
from .config import Config
from .dataio import (
    CUSTOMER,
    CUSTOMER_TYPE_GLOBAL,
    GEO,
    GROUP,
    ITEM_NO,
    ITEM_TYPE,
    KAM,
    ReferenceDates,
    apply_row_filters,
    geo_of_rows,
    load_sales_data,
)
from .excel_report import ExcelReport, parameter_sheet
from .metrics import drop_dead_items, group_metrics, item_metrics, kam_by_group
from .outliers import filter_outliers
from . import plots

Log = Callable[[str], None]


@dataclass(frozen=True)
class Segment:
    """Ét udsnit af data med de navne dets output skal have."""

    label: str  # vises i logs og plot-titler
    sheet_prefix: str  # prefix på Excel-fanenavne
    file_parts: tuple[str, ...]  # suffikser i filnavnene
    frame: pd.DataFrame


@dataclass
class SegmentResult:
    """Resultatet af at analysere ét udsnit."""

    segment: Segment
    per_group: pd.DataFrame
    per_item: pd.DataFrame
    per_item_filtered: pd.DataFrame | None
    outliers: pd.DataFrame | None

    @property
    def plot_items(self) -> pd.DataFrame:
        """Item-tabellen plottene skal bruge (efter et eventuelt outlier-filter)."""
        return self.per_item if self.per_item_filtered is None else self.per_item_filtered


# --- Forberedelse ------------------------------------------------------------


def _qualified_names(df: pd.DataFrame, has_geo: bool) -> pd.Series:
    """
    Bygger analysens enhedsnavne.

    En kunde med både sinter og støb skal kunne skilles ad i grafen, så den
    bliver til "GRUNDFOSS (Sinter)" og "GRUNDFOSS (Støb)". Kendetegn tilføjes
    kun for de dimensioner der faktisk varierer inden for kunden — har en
    kunde kun sinter, hedder den bare "GRUNDFOSS".
    """
    names = df[CUSTOMER].astype(str)
    type_labels = df[ITEM_TYPE].map(ITEM_TYPE_LABELS).fillna("")
    varies_type = df.groupby(CUSTOMER)[ITEM_TYPE].transform("nunique") > 1
    type_part = type_labels.where(varies_type, "")

    if has_geo:
        varies_geo = df.groupby(CUSTOMER)[GEO].transform("nunique") > 1
        geo_part = df[GEO].astype(str).where(varies_geo, "")
    else:
        geo_part = pd.Series("", index=df.index)

    both = (type_part != "") & (geo_part != "")
    suffix = (type_part + geo_part).mask(both, type_part + ", " + geo_part)
    decorated = (" (" + suffix + ")").where(suffix != "", "")
    return names + decorated


def annotate(df: pd.DataFrame, cfg: Config, dates: ReferenceDates, log: Log) -> pd.DataFrame:
    """
    Gør rækkerne klar til analyse.

    Her afgøres hvad der udgør én analyseenhed. Emne-type og produktionssted
    bestemmes pr. række, og kunder der spænder over flere af dem deles op i
    hver sin enhed med et sigende navn.

    KAM slås op på det RÅ kundenavn, så en kundes dele altid hører til samme
    key account manager. Kundetypen beregnes derimod pr. enhed: en kundes
    sinter-del kan sagtens være aktiv mens støbe-delen er stoppet.
    """
    annotated = df.copy()
    annotated[CUSTOMER] = annotated[GROUP]
    annotated[ITEM_TYPE] = annotated[ITEM_NO].apply(classify_item_no)

    geo = geo_of_rows(annotated, cfg.cn_turnover_types, cfg.dk_turnover_types)
    has_geo = geo is not None
    if has_geo:
        annotated[GEO] = geo

    # KAM hører til kunden som helhed, ikke til den enkelte del af den.
    if KAM in annotated.columns:
        annotated[KAM] = annotated[CUSTOMER].map(
            kam_by_group(annotated, key=CUSTOMER)
        )

    annotated[GROUP] = _qualified_names(annotated, has_geo)

    customer_types = customer_types_by_group(annotated, dates, cfg.new_fiscal_year)
    annotated[CUSTOMER_TYPE_GLOBAL] = annotated[GROUP].map(customer_types)

    log(f"Emne-type fordeling: {annotated[ITEM_TYPE].map(ITEM_TYPE_LABELS).value_counts().to_dict()}")
    if has_geo:
        log(f"Geografi-fordeling: {annotated[GEO].value_counts().to_dict()}")
    log(f"Kundetype-fordeling: {pd.Series(customer_types).value_counts().to_dict()}")
    split = annotated[GROUP].nunique() - annotated[CUSTOMER].nunique()
    if split > 0:
        log(f"  {split} ekstra analyseenheder fordi kunder spænder over flere emne-typer eller lande")
    return annotated


def build_segments(df: pd.DataFrame, cfg: Config, log: Log) -> list[Segment]:
    """
    Udsnittene er nu kun kundeudvalget.

    Emne-type og geografi håndteres som filtre i selve grafen, så de laver
    ikke længere hver sit sæt filer.
    """
    # Varer der hverken er sinter eller støb beholdes som deres egen gruppe,
    # så intet forsvinder uden at kunne ses. Kun -S0 fjerner en vare helt,
    # og det er allerede sket i klassifikationen.
    segments = [Segment(label="Alle kunder", sheet_prefix="", file_parts=(), frame=df)]
    if cfg.existing_customers_only:
        existing = df[df[CUSTOMER_TYPE_GLOBAL] == "Eksisterende"].copy()
        segments.append(
            Segment(
                label="Kun eksisterende",
                sheet_prefix="eks",
                file_parts=("eks",),
                frame=existing,
            )
        )
    return segments


# --- Analyse af ét udsnit ----------------------------------------------------


def analyse_segment(
    segment: Segment, cfg: Config, dates: ReferenceDates, log: Log
) -> SegmentResult | None:
    """Kører beregningerne for ét udsnit. Returnerer None hvis der ikke er data."""
    frame = segment.frame
    if frame.empty:
        log(f"\n[{segment.label}] Ingen rækker – springes over.")
        return None

    log(
        f"\n=== Udsnit: {segment.label} ({len(frame)} rækker, "
        f"{frame[GROUP].nunique()} kundegrupper) ==="
    )

    if cfg.drop_dead_items:
        frame = drop_dead_items(frame, cfg.turnover_window_months, log)
        if frame.empty:
            log(f"[{segment.label}] Ingen items tilbage efter frasortering – springes over.")
            return None

    per_item = item_metrics(frame, cfg)
    if per_item.empty:
        log(f"[{segment.label}] Ingen items at beregne på – springes over.")
        return None

    customer_types = customer_types_by_group(frame, dates, cfg.new_fiscal_year)

    per_item_filtered: pd.DataFrame | None = None
    outliers: pd.DataFrame | None = None
    if cfg.remove_outliers:
        log(f"\n[{segment.label}] Filtrerer outliers (±{cfg.outlier_std_threshold} std):")
        split = filter_outliers(
            per_item, cfg.outlier_std_threshold, cfg.outlier_metric, log
        )
        per_item_filtered, outliers = split.kept, split.removed
        per_group = group_metrics(split.kept, frame, cfg, customer_types)
    else:
        per_group = group_metrics(per_item, frame, cfg, customer_types)

    log(f"\n[{segment.label}] Top 20 efter samlet_turnover_window:")
    log(
        per_group.sort_values("samlet_turnover_window", ascending=False)
        .head(20)
        .to_string(index=False)
    )

    return SegmentResult(
        segment=segment,
        per_group=per_group,
        per_item=per_item,
        per_item_filtered=per_item_filtered,
        outliers=outliers,
    )


# --- Plots -------------------------------------------------------------------


def _plot_title(result: SegmentResult, cfg: Config) -> str:
    if cfg.remove_outliers:
        return f"{result.segment.label} - Outliers fjernet (±{cfg.outlier_std_threshold} std)"
    return result.segment.label


def render_plots(result: SegmentResult, cfg: Config, dates: ReferenceDates, log: Log) -> None:
    """Tegner og gemmer de valgte plots for ét udsnit."""
    if not (cfg.draw_group_plot or cfg.draw_item_plot):
        return
    if not plots.PLOTLY_AVAILABLE:
        log(
            "ADVARSEL: Plotly er ikke installeret (pip install plotly) – "
            "HTML-plots springes over."
        )
        return

    paths = cfg.paths
    parts = result.segment.file_parts
    title = _plot_title(result, cfg)

    if cfg.draw_group_plot and not result.per_group.empty:
        figure = plots.group_scatter(result.per_group, cfg, dates, title)
        plots.write_html(
            figure, paths.group_plot(*parts), f"{result.segment.label} · kundegruppe", log
        )
    if cfg.draw_item_plot and not result.plot_items.empty:
        figure = plots.item_scatter(result.plot_items, cfg, dates, title)
        plots.write_html(
            figure, paths.item_plot(*parts), f"{result.segment.label} · item", log
        )


# --- Indgangspunkt -----------------------------------------------------------


def run_analysis(cfg: Config, log: Log = print) -> list[SegmentResult]:
    """
    Kører hele analysen og returnerer resultatet for hvert udsnit.

    ``log`` modtager al fremdriftstekst. GUI'en sender sin egen funktion ind,
    så beskederne havner i log-vinduet uden at der skal omdirigeres stdout.
    """
    cfg.validate()

    # Output-mappen oprettes hvis den mangler. Ellers ville kørslen først bryde
    # sammen langt inde i forløbet, når det første plot skulle skrives.
    directory = cfg.paths.directory
    try:
        os.makedirs(directory, exist_ok=True)
    except OSError as exc:
        raise ValueError(
            f"Kunne ikke oprette output-mappen:\n{directory}\n\n"
            f"Årsag: {exc.strerror or exc}\n"
            "Vælg en anden mappe, eller kontrollér at du har skriveadgang."
        ) from exc

    df = load_sales_data(cfg.input_path, log)
    dates = ReferenceDates.from_config(cfg)
    log(f"Dags dato:           {dates.today:%Y-%m}")
    log(
        f"Dags dato bagud:     {dates.window_start:%Y-%m} "
        f"({cfg.existing_customer_months} mdr. tilbage)"
    )
    log(
        f"Turnover-vindue:     Rullende {cfg.turnover_window_months} mdr. bagud fra "
        "seneste aktivitet"
    )

    df = apply_row_filters(df, cfg, dates, log)
    df = annotate(df, cfg, dates, log)

    report = ExcelReport(cfg) if cfg.write_excel else None
    results: list[SegmentResult] = []

    for segment in build_segments(df, cfg, log):
        result = analyse_segment(segment, cfg, dates, log)
        if result is None:
            continue
        results.append(result)
        render_plots(result, cfg, dates, log)
        if report is not None:
            report.add_segment(
                prefix=segment.sheet_prefix,
                per_group=result.per_group,
                per_item=result.per_item,
                per_item_filtered=result.per_item_filtered,
                outliers=result.outliers,
            )

    if report is not None and not report.is_empty:
        report.add("Parametre", parameter_sheet(cfg, dates))
        report.write(cfg.paths.excel, log)

    if not results:
        log("\nIngen udsnit gav data – der blev ikke produceret noget output.")
    return results

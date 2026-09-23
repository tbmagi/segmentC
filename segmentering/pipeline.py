"""
Orkestrering af hele analysen.

Kørslen er bygget op om ét begreb: et **udsnit** (``Segment``). Et udsnit er
en delmængde af rækkerne — fx "sinter-emner produceret i CN" — og hvert udsnit
giver præcis ét kundegruppe-plot, ét item-plot og ét sæt Excel-faner.

Udsnittene udspændes af tre uafhængige valg:

* emne-type   – sinter / støbe, eller alt under ét
* geografi    – samlet / CN / DK
* kundeudvalg – alle kunder, og valgfrit en ekstra kørsel med kun eksisterende

Fordi hvert udsnit filtreres én gang og derefter beregnes forfra, svarer
plottet altid til de Excel-faner der hører til samme udsnit.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from typing import Callable

import pandas as pd

from .classify import CAST, SINTER, classify_item_no, customer_types_by_group, has_manual_suffix
from .config import Config
from .dataio import (
    CUSTOMER_TYPE_GLOBAL,
    GROUP,
    HAS_MANUAL_SUFFIX,
    ITEM_NO,
    ITEM_TYPE,
    KAM,
    ReferenceDates,
    apply_row_filters,
    load_sales_data,
    turnover_type_mask,
)
from .excel_report import ExcelReport, parameter_sheet
from .language import DANISH, ENGLISH, ENGLISH_SUBFOLDER, Texts
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


def annotate(df: pd.DataFrame, cfg: Config, dates: ReferenceDates, log: Log) -> pd.DataFrame:
    """
    Tilføjer de kolonner udsnits-opdelingen har brug for.

    ``CUSTOMER_TYPE_GLOBAL`` beregnes på det FULDE datasæt og styrer alene
    hvilke items nye kunder må tage med sig gennem emne-type-filteret. Den
    kundetype der vises i plot og rapport beregnes derimod pr. udsnit, fordi
    en kunde kan se anderledes ud når man kun betragter fx dens sinter-emner.
    """
    annotated = df.copy()
    annotated[ITEM_TYPE] = annotated[ITEM_NO].apply(classify_item_no)
    annotated[HAS_MANUAL_SUFFIX] = has_manual_suffix(annotated[ITEM_NO])

    customer_types = customer_types_by_group(annotated, dates)
    annotated[CUSTOMER_TYPE_GLOBAL] = annotated[GROUP].map(customer_types)

    # KAM opløses ÉN gang på hele datasættet og skrives tilbage i kolonnen.
    # Gjorde hvert udsnit det selv, kunne den valgte stavemåde variere mellem
    # sinter- og støbe-plottet, fordi den nyeste række ikke er den samme i de
    # to udsnit. Nu står den samme person som det samme overalt.
    if KAM in annotated.columns:
        annotated[KAM] = annotated[GROUP].map(kam_by_group(annotated))

    distribution = pd.Series(customer_types).value_counts().to_dict()
    log(f"Kundetype-fordeling: {distribution}")
    return annotated


def _new_customer_wildcards(df: pd.DataFrame) -> pd.Series:
    """
    Rækker fra nye kunder uden manuelt suffix.

    De medtages i BEGGE emne-type-udsnit, så en ny kunde altid kan ses på
    begge plots. Et eksplicit -S0/-S1/-S2 suffix vinder dog altid, også for
    nye kunder.
    """
    return (df[CUSTOMER_TYPE_GLOBAL] == "Ny") & ~df[HAS_MANUAL_SUFFIX]


def _item_type_dimension(
    df: pd.DataFrame, cfg: Config, log: Log
) -> list[tuple[str, str, pd.DataFrame]]:
    """Opdeler på emne-type og returnerer (label, filnavn-del, data)."""
    wildcards = _new_customer_wildcards(df)

    if not cfg.split_by_item_type:
        combined = df[df[ITEM_TYPE].isin([SINTER, CAST]) | wildcards].copy()
        return [("Alle emner", "", combined)]

    log(f"\nItem-type fordeling: {df[ITEM_TYPE].value_counts().to_dict()}")
    new_rows = int(wildcards.sum())
    if new_rows:
        groups = df.loc[wildcards, GROUP].nunique()
        log(
            f"Ny-kunder: {new_rows} rækker fra {groups} kundegrupper uden suffix "
            "tilføjes til BEGGE emne-type-plots"
        )

    return [
        ("Sinter", "sinter", df[(df[ITEM_TYPE] == SINTER) | wildcards].copy()),
        ("Støbe", "stoebe", df[(df[ITEM_TYPE] == CAST) | wildcards].copy()),
    ]


def _geo_dimension(cfg: Config) -> list[tuple[str, str, list[str] | None]]:
    """Returnerer (label, filnavn-del, tilladte turnover-typer) pr. geo-udsnit."""
    variants: list[tuple[str, str, list[str] | None]] = []
    if cfg.geo_combined:
        variants.append(("", "", None))
    if cfg.geo_cn:
        variants.append(("CN", "cn", cfg.cn_turnover_types))
    if cfg.geo_dk:
        variants.append(("DK", "dk", cfg.dk_turnover_types))
    return variants


def build_segments(df: pd.DataFrame, cfg: Config, log: Log) -> list[Segment]:
    """Udspænder alle udsnit af emne-type × geografi × kundeudvalg."""
    segments: list[Segment] = []
    customer_selections = [("", "", False)]
    if cfg.existing_customers_only:
        customer_selections.append(("kun eksisterende", "eks", True))

    for type_label, type_part, type_frame in _item_type_dimension(df, cfg, log):
        for geo_label, geo_part, geo_types in _geo_dimension(cfg):
            if geo_types is None:
                frame = type_frame
            else:
                # Nye kunder uden suffix følger med i alle geo-udsnit, så de
                # ikke forsvinder fordi deres turnover-type endnu er ukendt.
                mask = turnover_type_mask(type_frame, geo_types) | _new_customer_wildcards(
                    type_frame
                )
                frame = type_frame[mask].copy()

            for selection_label, selection_part, existing_only in customer_selections:
                if existing_only:
                    frame_for_run = frame[
                        frame[CUSTOMER_TYPE_GLOBAL] == "Eksisterende"
                    ].copy()
                else:
                    frame_for_run = frame

                label = " – ".join(
                    part for part in (type_label, geo_label, selection_label) if part
                )
                prefix = "_".join(
                    part
                    for part in (
                        type_label.replace(" ", "_") if type_label != "Alle emner" else "",
                        geo_label,
                        selection_part,
                    )
                    if part
                )
                segments.append(
                    Segment(
                        label=label or "Alle emner",
                        sheet_prefix=prefix,
                        file_parts=tuple(
                            part for part in (type_part, geo_part, selection_part) if part
                        ),
                        frame=frame_for_run,
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

    customer_types = customer_types_by_group(frame, dates)

    per_item_filtered: pd.DataFrame | None = None
    outliers: pd.DataFrame | None = None
    has_gm_limits = (
        cfg.gm_limit_min_pct is not None or cfg.gm_limit_max_pct is not None
    )
    if has_gm_limits:
        log(f"\n[{segment.label}] Frasorterer varer med urimelig margin:")
        split = filter_outliers(
            per_item,
            log,
            gm_limit_min_pct=cfg.gm_limit_min_pct,
            gm_limit_max_pct=cfg.gm_limit_max_pct,
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
    """Udsnittets navn, som kommer til at stå i plottets overskrift."""
    _ = cfg
    return result.segment.label


def render_plots(result: SegmentResult, cfg: Config, dates: ReferenceDates, log: Log) -> None:
    """
    Tegner og gemmer de valgte plots for ét udsnit.

    Er en engelsk udgave slået til, tegnes de samme figurer en gang til med
    engelske tekster og lægges i en undermappe. Beregningen køres ikke om —
    de to udgaver bygger på nøjagtig det samme resultat, så de kan ikke komme
    til at vise forskellige tal.
    """
    if not (cfg.draw_group_plot or cfg.draw_item_plot):
        return
    if not plots.PLOTLY_AVAILABLE:
        log(
            "ADVARSEL: Plotly er ikke installeret (pip install plotly) – "
            "HTML-plots springes over."
        )
        return

    editions: list[tuple[Texts, str]] = [(DANISH, cfg.paths.directory)]
    if cfg.english_copy:
        editions.append(
            (ENGLISH, os.path.join(cfg.paths.directory, ENGLISH_SUBFOLDER))
        )

    title = _plot_title(result, cfg)

    for texts, directory in editions:
        paths = replace(
            cfg.paths,
            directory=directory,
            basename=_basename(cfg, texts),
            group_role=texts.file_role_group,
            item_role=texts.file_role_item,
        )
        parts = tuple(texts.file_part(part) for part in result.segment.file_parts)
        os.makedirs(directory, exist_ok=True)
        tag = "" if texts is DANISH else " (engelsk)"
        if cfg.draw_group_plot and not result.per_group.empty:
            figure = plots.group_scatter(result.per_group, cfg, dates, title, texts)
            plots.write_html(
                figure, paths.group_plot(*parts),
                f"{result.segment.label} · kundegruppe{tag}", log,
            )
        if cfg.draw_item_plot and not result.plot_items.empty:
            figure = plots.item_scatter(result.plot_items, cfg, dates, title, texts)
            plots.write_html(
                figure, paths.item_plot(*parts),
                f"{result.segment.label} · item{tag}", log,
            )


def _basename(cfg: Config, texts: Texts) -> str:
    """
    Basisnavnet til filerne i denne sprogudgave.

    Har brugeren selv skrevet et navn, er det deres ord og bliver stående på
    begge sprog — vi kan ikke vide hvad "Q3_analyse_til_ledelsen" hedder på
    engelsk. Står feltet på fabriksnavnet, er det derimod vores eget ord, og
    så oversættes det, så den engelske mappe ikke ender med filer der hedder
    "kunde_segmentering_customer_group_sinter.html".
    """
    chosen = (cfg.output_basename or "").strip()
    if not chosen or chosen == DANISH.file_basename:
        return texts.file_basename
    return chosen


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

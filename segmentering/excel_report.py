"""
Excel-rapporten.

Rapporten samles i hukommelsen og skrives i én omgang til sidst. Det er både
enklere og mere robust end at åbne filen igen for hvert udsnit: der findes
ingen halvfærdig fil hvis en senere beregning fejler, og rækkefølgen af
faneblade afhænger ikke af hvilket udsnit der tilfældigvis kørte først.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import pandas as pd

from .config import Config
from .dataio import GROUP, INDUSTRY_SEGMENT, ITEM_NO
from .metrics import (
    FIRST_ACTIVITY,
    GP_SUM,
    ITEM_GM,
    LAST_ACTIVITY,
    TURNOVER_SUM,
    WINDOW_GROUP,
    WINDOW_ITEM,
)
from .outliers import GM_Z, OUTLIER_REASON, TURNOVER_Z

Log = Callable[[str], None]

EXCEL_SHEET_NAME_LIMIT = 31

PERCENT_FORMAT = "0.0%"
THOUSANDS_FORMAT = "#,##0"

#: Kolonner hvis værdi er en decimal (0,42) og som vises som procent i Excel.
#: Selve celleværdien forbliver 0,42, så der kan regnes videre på den.
PERCENT_COLUMNS = {"samlet_GM_pct", "gns_GM_pct", "GM_pct"}

#: Kolonner pr. detaljeringsgrad for oversigts-fanen, i visningsrækkefølge.
SUMMARY_COLUMNS: dict[str, list[str]] = {
    "minimal": [
        GROUP,
        "Kundetype",
        "Kundekategori",
        INDUSTRY_SEGMENT,
        "antal_items",
        "samlet_turnover_window",
        "samlet_GM_pct",
    ],
    "kompakt": [
        GROUP,
        "Kundetype",
        "Kundekategori",
        INDUSTRY_SEGMENT,
        "antal_items",
        "samlet_turnover_window",
        "samlet_turnover",
        "samlet_GP",
        "samlet_GM_pct",
        "tidligste_aktivitet",
        "seneste_aktivitet",
    ],
    "fuld": [
        GROUP,
        "Kundetype",
        "Kundekategori",
        INDUSTRY_SEGMENT,
        "antal_items",
        "samlet_turnover_window",
        "gns_turnover_window",
        "samlet_turnover",
        "gns_turnover",
        "samlet_GM_pct",
        "gns_GM_pct",
        "samlet_GP",
        "tidligste_aktivitet",
        "seneste_aktivitet",
    ],
}


def _is_money_column(name: object) -> bool:
    text = str(name).lower()
    return (
        text.startswith("turnover_dkk")
        or text.startswith("samlet_turnover")
        or text.startswith("gns_turnover")
        or text.startswith("gp_dkk")
        or text == "samlet_gp"
    )


def _format_months(df: pd.DataFrame, columns: tuple[str, ...]) -> pd.DataFrame:
    """Konverterer dato-kolonner til 'YYYY-MM', som er lettere at læse i Excel."""
    result = df.copy()
    for column in columns:
        if column in result.columns:
            result[column] = pd.to_datetime(
                result[column], errors="coerce"
            ).dt.strftime("%Y-%m")
    return result


def prepare_summary_sheet(per_group: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Bygger oversigts-fanen: én række pr. kundegruppe."""
    summary = _format_months(per_group, ("tidligste_aktivitet", "seneste_aktivitet"))
    for source, target in (("samlet_GM", "samlet_GM_pct"), ("gns_GM", "gns_GM_pct")):
        if source in summary.columns:
            summary[target] = summary[source]

    columns = [c for c in SUMMARY_COLUMNS[cfg.excel_detail] if c in summary.columns]
    summary = summary[columns]
    if "samlet_turnover_window" in summary.columns:
        summary = summary.sort_values(
            "samlet_turnover_window", ascending=False, na_position="last"
        )
    return summary


def prepare_item_sheet(
    per_item: pd.DataFrame, cfg: Config, include_z_scores: bool = False
) -> pd.DataFrame:
    """
    Bygger en item-fane med læsbare kolonnenavne og en fast rækkefølge.

    Bruges til alle tre item-faner (alle, filtrerede og outliers), så de altid
    ser ens ud.
    """
    months = cfg.turnover_window_months
    item_window = f"Turnover_DKK_{months}mdr_item"
    group_window = f"Turnover_DKK_{months}mdr_gruppe"

    items = _format_months(per_item, (FIRST_ACTIVITY, LAST_ACTIVITY)).rename(
        columns={
            TURNOVER_SUM: "Turnover_DKK_seneste_md",
            WINDOW_ITEM: item_window,
            WINDOW_GROUP: group_window,
            GP_SUM: "GP_DKK_seneste_md",
            ITEM_GM: "GM_pct",
            TURNOVER_Z: "z_score_Turnover",
            GM_Z: "z_score_GM",
        }
    )

    if include_z_scores:
        preferred = [
            GROUP,
            ITEM_NO,
            OUTLIER_REASON,
            "z_score_Turnover",
            "z_score_GM",
            "Turnover_DKK_seneste_md",
            item_window,
            "GP_DKK_seneste_md",
            "GM_pct",
            FIRST_ACTIVITY,
            LAST_ACTIVITY,
        ]
    elif cfg.excel_detail == "minimal":
        preferred = [GROUP, ITEM_NO, item_window, "GM_pct"]
    elif cfg.excel_detail == "kompakt":
        preferred = [
            GROUP,
            ITEM_NO,
            item_window,
            group_window,
            "Turnover_DKK_seneste_md",
            "GP_DKK_seneste_md",
            "GM_pct",
            FIRST_ACTIVITY,
            LAST_ACTIVITY,
        ]
    else:  # "fuld" – behold alle kolonner i en fornuftig rækkefølge
        leading = [GROUP, ITEM_NO, item_window, group_window]
        preferred = leading + [c for c in items.columns if c not in leading]

    items = items[[c for c in preferred if c in items.columns]]
    if item_window in items.columns:
        items = items.sort_values([GROUP, item_window], ascending=[True, False])
    return items


def parameter_sheet(cfg: Config, dates) -> pd.DataFrame:
    """Dokumenterer de indstillinger kørslen brugte."""
    rows = [
        ("Dags dato", f"{dates.today:%Y-%m}"),
        ("Dags dato bagud", f"{dates.window_start:%Y-%m}"),
        ("Antal måneder bagud", cfg.existing_customer_months),
        ("Ny-regnskabsår", cfg.new_fiscal_year or "(ikke sat)"),
        (
            "Turnover-vindue mdr (rullende fra seneste aktivitet)",
            cfg.turnover_window_months,
        ),
        ("Turnover-forankring kundegruppe-plot", cfg.group_plot_anchor),
        ("Turnover-forankring item-plot", cfg.item_plot_anchor),
        ("Frasortering af døde items", cfg.drop_dead_items),
        ("GM-måneder pr. item", cfg.gm_months),
        ("Outlier-filter aktivt", cfg.remove_outliers),
        ("Outlier-tærskel (std)", cfg.outlier_std_threshold),
        ("Outlier metrik", cfg.outlier_metric),
        ("Farvelogik på kundegruppe-plot", cfg.colour_by),
        ("Excel-detaljer", cfg.excel_detail),
    ]
    return pd.DataFrame(rows, columns=["Parameter", "Værdi"])


@dataclass
class ExcelReport:
    """Samler faneblade og skriver dem til én fil."""

    cfg: Config
    sheets: dict[str, pd.DataFrame] = field(default_factory=dict)

    def add(self, name: str, frame: pd.DataFrame) -> None:
        if frame is None or frame.empty:
            return
        self.sheets[self._safe_name(name)] = frame

    def add_segment(
        self,
        prefix: str,
        per_group: pd.DataFrame,
        per_item: pd.DataFrame,
        per_item_filtered: pd.DataFrame | None,
        outliers: pd.DataFrame | None,
    ) -> None:
        def sheet(name: str) -> str:
            return f"{prefix}_{name}" if prefix else name

        self.add(sheet("Oversigt"), prepare_summary_sheet(per_group, self.cfg))
        self.add(sheet("Items_alle"), prepare_item_sheet(per_item, self.cfg))
        if per_item_filtered is not None:
            self.add(
                sheet("Items_filt"), prepare_item_sheet(per_item_filtered, self.cfg)
            )
        if outliers is not None and not outliers.empty:
            self.add(
                sheet("Outliers"),
                prepare_item_sheet(outliers, self.cfg, include_z_scores=True),
            )

    def _safe_name(self, name: str) -> str:
        """Excel tillader højst 31 tegn i et fanenavn."""
        if len(name) <= EXCEL_SHEET_NAME_LIMIT:
            return name
        return name[: EXCEL_SHEET_NAME_LIMIT - 2] + "~1"

    @property
    def is_empty(self) -> bool:
        return not self.sheets

    def write(self, path: str, log: Log = print) -> None:
        if self.is_empty:
            log("Ingen data at skrive til Excel – rapporten springes over.")
            return
        try:
            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                for name, frame in self.sheets.items():
                    frame.to_excel(writer, sheet_name=name, index=False)
                for worksheet in writer.sheets.values():
                    _format_worksheet(worksheet)
        except PermissionError:
            log(
                f"\nADVARSEL: Kunne ikke gemme {path} – er filen åben i Excel? "
                "Luk den og kør igen."
            )
            return

        log(f"\nExcel-rapport gemt til: {path}")
        for name, frame in self.sheets.items():
            log(f"  - {len(frame)} rækker på fanen '{name}'")


def _format_worksheet(worksheet) -> None:
    """Fryser overskriftsrækken og sætter filtre, talformater og kolonnebredder."""
    from openpyxl.utils import get_column_letter

    worksheet.freeze_panes = "A2"
    if worksheet.max_row >= 1 and worksheet.max_column >= 1:
        worksheet.auto_filter.ref = worksheet.dimensions

    for column_index, cells in enumerate(worksheet.columns, start=1):
        header = worksheet.cell(row=1, column=column_index).value
        if header in PERCENT_COLUMNS:
            number_format = PERCENT_FORMAT
        elif _is_money_column(header):
            number_format = THOUSANDS_FORMAT
        else:
            number_format = None

        if number_format is not None:
            for cell in cells[1:]:
                if isinstance(cell.value, (int, float)):
                    cell.number_format = number_format

        # Bredden estimeres ud fra den FORMATEREDE visning. Den rå decimal
        # (0,359730…) ville ellers give en misvisende bred kolonne.
        if number_format == PERCENT_FORMAT:
            lengths = [len(str(header))] + [
                6 for cell in cells[1:] if cell.value is not None
            ]
        elif number_format == THOUSANDS_FORMAT:
            lengths = [len(str(header))] + [
                len(f"{cell.value:,.0f}")
                for cell in cells[1:]
                if isinstance(cell.value, (int, float))
            ]
        else:
            lengths = [
                len(str(cell.value)) if cell.value is not None else 0 for cell in cells
            ]
        width = min(max(lengths + [10]) + 4, 40)
        worksheet.column_dimensions[get_column_letter(column_index)].width = width

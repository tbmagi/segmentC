"""
Indlæsning og indledende filtrering af salgsdata.

Modulet kender Excel-filens kolonner og oversætter dem til de kanoniske navne
resten af pakken bruger. Alle filtre er rene funktioner: de tager et
DataFrame ind og giver et nyt ud.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Iterable

import pandas as pd
from dateutil.relativedelta import relativedelta

from .config import Config, fiscal_year_start

Log = Callable[[str], None]

# Kanoniske kolonnenavne. Excel-filens overskrifter matches case-insensitivt
# og omdøbes hertil, så resten af koden kan regne med præcis disse navne.
CUSTOMER_GROUP = "Statistics group"
ITEM_NO = "item no."
YEAR_MONTH = "year-mo"
TURNOVER = "Turnover DKK"
GROSS_PROFIT = "Local_GP_DKK"

#: Kolonner filen skal indeholde. Bemærk at "cost", "Qty." og "Local_COGS_DKK"
#: ikke indgår i nogen beregning — de kræves fordi de hører til det aftalte
#: dataudtræk, og et udtræk uden dem er sandsynligvis forkert eksporteret.
REQUIRED_COLUMNS = [
    CUSTOMER_GROUP,
    ITEM_NO,
    YEAR_MONTH,
    "cost",
    "Qty.",
    TURNOVER,
    "Local_COGS_DKK",
    GROSS_PROFIT,
]

#: Valgfrie kolonner. Findes de ikke, springes den tilhørende funktion over.
TURNOVER_TYPE = "Turnover type"
FISCAL_YEAR = "Fiscal year"
INDUSTRY_SEGMENT = "Industry_segment"
KAM = "KAM"

#: Kunder uden nogen KAM samles under denne etiket, så de får deres egen knap
#: frem for at forsvinde fra opdelingen.
BLANK_KAM = "(Blank)"

OPTIONAL_COLUMNS = [TURNOVER_TYPE, FISCAL_YEAR, INDUSTRY_SEGMENT, KAM]

#: Hvor langt ned i arket der ledes efter overskriftsrækken.
HEADER_SCAN_ROWS = 200

# Kolonner pakken selv tilføjer undervejs.
GROUP = "KundeGruppe"
PERIOD = "year-mo-parsed"
ITEM_TYPE = "ItemType"
CUSTOMER_TYPE_GLOBAL = "_customer_type_global"
HAS_MANUAL_SUFFIX = "_has_manual_suffix"


def find_column(df: pd.DataFrame, name: str) -> str | None:
    """Finder en kolonne case-insensitivt og uafhængigt af omkringliggende mellemrum."""
    target = name.strip().lower()
    return next((c for c in df.columns if str(c).strip().lower() == target), None)


# --- Dato-parsing ------------------------------------------------------------


def parse_month(value: str) -> pd.Timestamp:
    """Parser "MM-YYYY" til en Timestamp sat til den 1. i måneden."""
    return pd.to_datetime(value, format="%m-%Y")


def parse_period(value: object) -> pd.Timestamp:
    """
    Robust parser for kolonnen 'year-mo'.

    Accepterer 'YYYY-MM', 'MM-YYYY', 'YYYYMM' samt datetime/Timestamp.
    Returnerer NaT for værdier der ikke kan tolkes.
    """
    if pd.isna(value):
        return pd.NaT
    if isinstance(value, (pd.Timestamp, datetime)):
        return pd.Timestamp(value).to_period("M").to_timestamp()

    text = str(value).strip()
    if re.fullmatch(r"\d{4}-\d{1,2}", text):
        return pd.to_datetime(text, format="%Y-%m", errors="coerce")
    if re.fullmatch(r"\d{1,2}-\d{4}", text):
        return pd.to_datetime(text, format="%m-%Y", errors="coerce")
    if re.fullmatch(r"\d{6}", text):
        return pd.to_datetime(text, format="%Y%m", errors="coerce")
    return pd.to_datetime(text, errors="coerce")


@dataclass(frozen=True)
class ReferenceDates:
    """
    De datoer kundetyperne afgøres af.

    ``window_start``–``today`` er 'eksisterende kunde'-vinduet.
    ``fiscal_start``–``fiscal_end`` er ny-regnskabsåret, udledt af dets
    startmåned: med start i maj løber 2026/2027 fra 05-2026 til 04-2027.
    De to perioder overlapper med vilje — en kunde kan ligge i begge, og
    rækkefølgen af reglerne i :func:`classify_customer_type` afgør udfaldet.

    ``fiscal_start`` er ``None`` hvis der ikke er sat et ny-regnskabsår; så
    findes kategorien "Ny" ikke.
    """

    today: pd.Timestamp
    window_start: pd.Timestamp
    fiscal_start: pd.Timestamp | None = None
    fiscal_end: pd.Timestamp | None = None

    @classmethod
    def from_config(cls, cfg: Config) -> "ReferenceDates":
        today = parse_month(cfg.reference_date)
        start_year = fiscal_year_start(cfg.new_fiscal_year)
        fiscal_start = fiscal_end = None
        if start_year is not None:
            fiscal_start = pd.Timestamp(
                year=start_year, month=cfg.fiscal_year_start_month, day=1
            )
            fiscal_end = fiscal_start + relativedelta(months=11)
        return cls(
            today=today,
            window_start=today - relativedelta(months=cfg.existing_customer_months),
            fiscal_start=fiscal_start,
            fiscal_end=fiscal_end,
        )


# --- Indlæsning --------------------------------------------------------------


class MissingColumnsError(ValueError):
    """
    Rejses når Excel-filen ikke indeholder alle de obligatoriske kolonner.

    Beskeden er skrevet til at kunne vises direkte for brugeren: den siger
    hvad der mangler, hvad der rent faktisk stod i overskriftsrækken, og hvad
    man typisk gør ved det.
    """

    def __init__(
        self,
        missing: Iterable[str],
        found: Iterable[str],
        header_row: int | None = None,
    ) -> None:
        self.missing = list(missing)
        self.found = list(found)
        self.header_row = header_row
        super().__init__(self._build_message())

    def _build_message(self) -> str:
        lines = ["Excel-filen mangler obligatoriske kolonner.", "", "Mangler:"]
        lines += [f"  • {name}" for name in self.missing]
        where = (
            f"række {self.header_row + 1}"
            if self.header_row is not None
            else "overskriftsrækken"
        )
        lines += ["", f"Fundet i {where}:"]
        lines += (
            [f"  • {name}" for name in self.found]
            if self.found
            else ["  (ingen kolonnenavne kunne genkendes)"]
        )
        lines += [
            "",
            "Store og små bogstaver er lige gyldige, og mellemrum omkring "
            "navnet betyder ingenting —",
            "men stavemåden skal ellers passe. Tjek at kolonnen ikke er "
            "omdøbt eller udeladt i udtrækket.",
        ]
        return "\n".join(lines)


def locate_header_row(frame: pd.DataFrame) -> tuple[int | None, list[str]]:
    """
    Finder den række der indeholder kolonneoverskrifterne.

    Arket kan have en forside, et logo eller nogle nøgletal over selve
    tabellen, så overskrifterne står ikke nødvendigvis i første række. Her
    gennemsøges de øverste rækker, og den første række der indeholder samtlige
    påkrævede kolonnenavne vinder.

    ``frame`` skal være læst med ``header=None``, så alle rækker er data.

    Returnerer rækkens indeks og en liste over manglende kolonner. Er listen
    tom, blev alle påkrævede kolonner fundet. Blev ingen fuldtræffer fundet,
    peger indekset på den bedste kandidat, så fejlbeskeden kan vise hvad der
    faktisk stod der.
    """
    best_row: int | None = None
    best_hits = -1
    best_missing = list(REQUIRED_COLUMNS)

    for index in range(len(frame)):
        cells = {
            str(value).strip().lower()
            for value in frame.iloc[index].tolist()
            if pd.notna(value)
        }
        missing = [c for c in REQUIRED_COLUMNS if c.lower() not in cells]
        if not missing:
            return index, []
        hits = len(REQUIRED_COLUMNS) - len(missing)
        if hits > best_hits:
            best_row, best_hits, best_missing = index, hits, missing

    return best_row, best_missing


def load_sales_data(path: str, log: Log = print) -> pd.DataFrame:
    """
    Læser Excel-filen, normaliserer kolonnenavne og tilføjer den parsede
    periode-kolonne.

    Overskriftsrækken findes automatisk, så det ikke gør noget at tabellen
    starter længere nede i arket.
    """
    log(f"Indlæser: {path}")
    try:
        preview = pd.read_excel(path, header=None, nrows=HEADER_SCAN_ROWS)
        header_row, missing = locate_header_row(preview)
        if missing:
            found = (
                [str(v).strip() for v in preview.iloc[header_row] if pd.notna(v)]
                if header_row is not None
                else []
            )
            raise MissingColumnsError(missing, found, header_row)
        if header_row:
            log(f"  Fandt kolonneoverskrifter i række {header_row + 1}")
        df = pd.read_excel(path, header=header_row)
    except PermissionError as exc:
        raise PermissionError(
            f"Kunne ikke åbne filen: {path}\n"
            "Mulige årsager:\n"
            "  1) Filen er åben i Excel – luk den helt og prøv igen.\n"
            "  2) OneDrive har filen som 'kun online'. Højreklik filen i "
            "Stifinder og vælg 'Behold altid på denne enhed'.\n"
            "  3) OneDrive synkroniserer lige nu – vent et øjeblik.\n"
            "  4) Kopier filen lokalt og peg på kopien i stedet."
        ) from exc
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Filen blev ikke fundet: {path}") from exc

    df.columns = [str(c).strip() for c in df.columns]
    # Tomme rækker under tabellen (eller mellem afsnit) bærer ingen data.
    df = df.dropna(how="all").copy()

    # Omdøb til de kanoniske navne, så resten af koden slipper for at lede
    # case-insensitivt. Både påkrævede og valgfrie kolonner normaliseres.
    rename_map: dict[str, str] = {}
    missing: list[str] = []
    for canonical in REQUIRED_COLUMNS + OPTIONAL_COLUMNS:
        found = find_column(df, canonical)
        if found is None:
            if canonical in REQUIRED_COLUMNS:
                missing.append(canonical)
        elif found != canonical:
            rename_map[found] = canonical
    if missing:
        # Sikkerhedsnet: overskriftsrækken blev godkendt ovenfor, så her burde
        # intet mangle. Sker det alligevel, får brugeren samme tydelige besked.
        raise MissingColumnsError(missing, list(df.columns), header_row)
    if rename_map:
        df = df.rename(columns=rename_map)

    df[PERIOD] = df[YEAR_MONTH].apply(parse_period)
    return df


# --- Filtrering --------------------------------------------------------------


def _normalised(values: object) -> set[str]:
    return {str(v).strip().lower() for v in values}  # type: ignore[union-attr]


def apply_row_filters(
    df: pd.DataFrame, cfg: Config, dates: ReferenceDates, log: Log = print
) -> pd.DataFrame:
    """
    Fjerner de rækker der aldrig skal indgå i analysen:

    1. perioder efter dags dato (budgettal)
    2. uønskede værdier i 'Turnover type'
    3. tomme kundegrupper
    4. eksplicit ekskluderede kundegrupper
    5. rækker med Turnover DKK = 0 (valgfrit)
    """
    if cfg.drop_future_periods:
        # Alt efter dags dato er budget, ikke realiseret salg. Selve
        # måneden for dags dato regnes med: er dags dato 06-2026, beholdes
        # 06-2026, mens 07-2026 og frem falder fra.
        future = df[PERIOD].notna() & (df[PERIOD] > dates.today)
        dropped = int(future.sum())
        if dropped:
            log(
                f"Frasorterede budgettal efter {dates.today:%m-%Y}: "
                f"fjernede {dropped} rækker"
            )
        df = df[~future].copy()
        if df.empty:
            raise ValueError(
                f"Ingen rækker ligger på eller før dags dato ({dates.today:%m-%Y}). "
                "Tjek at 'Dags dato' passer til perioderne i filen."
            )

    if cfg.excluded_turnover_types:
        column = find_column(df, TURNOVER_TYPE)
        if column is None:
            log(
                f"BEMÆRK: Kolonnen '{TURNOVER_TYPE}' blev ikke fundet – "
                "frasortering af turnover-typer springes over."
            )
        else:
            excluded = _normalised(cfg.excluded_turnover_types)
            before = len(df)
            values = df[column].astype(str).str.strip().str.lower()
            df = df[~values.isin(excluded)].copy()
            log(
                "Frasorterede uønskede Turnover type-værdier: fjernede "
                f"{before - len(df)} rækker"
            )

    df = df.copy()
    df[GROUP] = df[CUSTOMER_GROUP].astype(str).str.strip()
    df = df[df[GROUP].ne("") & df[GROUP].str.lower().ne("nan")].copy()

    if df.empty:
        raise ValueError(
            f"Ingen kundegrupper at plotte – tjek at '{CUSTOMER_GROUP}' har værdier."
        )

    if cfg.excluded_customer_groups:
        excluded = {name.strip().upper() for name in cfg.excluded_customer_groups}
        rows_before, groups_before = len(df), df[GROUP].nunique()
        df = df[~df[GROUP].str.upper().isin(excluded)].copy()
        log(
            f"Ekskluderede kundegrupper: fjernede {rows_before - len(df)} rækker, "
            f"{groups_before - df[GROUP].nunique()} kundegrupper"
        )

    if cfg.drop_zero_turnover:
        before = len(df)
        df = df[df[TURNOVER].fillna(0) != 0].copy()
        log(
            "Frasorterede rækker med Turnover DKK = 0: fjernede "
            f"{before - len(df)} rækker"
        )

    if df.empty:
        raise ValueError(
            "Ingen rækker tilbage efter filtrering – tjek dine indstillinger."
        )

    log(f"Antal unikke kundegrupper: {df[GROUP].nunique()}")
    return df


def turnover_type_mask(
    df: pd.DataFrame, allowed_types: list[str]
) -> pd.Series:
    """
    Boolesk maske over rækker hvis 'Turnover type' står på listen.

    Returnerer en helt falsk maske hvis kolonnen mangler, eller hvis listen
    er tom, så kalderen kan behandle "ingen match" ensartet.
    """
    column = find_column(df, TURNOVER_TYPE)
    if column is None or not allowed_types:
        return pd.Series(False, index=df.index)
    values = df[column].astype(str).str.strip().str.lower()
    return values.isin(_normalised(allowed_types))

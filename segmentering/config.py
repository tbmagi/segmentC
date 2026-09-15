"""
Konfiguration for kundesegmenteringen.

Al opsætning samles i ét ``Config``-objekt, der sendes som argument gennem
hele pipelinen. Ingen funktion i pakken læser modul-globale indstillinger, og
ingen funktion ændrer dem. Det gør hvert trin testbart i isolation og gør det
muligt at køre flere analyser i samme proces uden at de påvirker hinanden.

Brugervendte tekster (labels, fejlbeskeder, Excel-faner) er på dansk;
kode-identifikatorer er på engelsk.
"""

from __future__ import annotations

import os
import sys
import json
from dataclasses import asdict, dataclass, field, fields, replace
from datetime import date
from typing import Iterable, Literal, Mapping, Sequence

# --- Værdi-domæner for de valgfrie indstillinger -----------------------------

#: Hvor det rullende turnover-vindue forankres.
#:   "group" -> N måneder bagud fra KUNDEGRUPPENS seneste aktivitet, så alle
#:              items i én kunde dækker præcis samme kalenderperiode.
#:   "item"  -> N måneder bagud fra HVERT ITEMS egen seneste aktivitet.
Anchor = Literal["group", "item"]

AxisScale = Literal["linear", "log"]
OutlierMetric = Literal["begge", "turnover", "gm", "ingen"]
ExcelDetail = Literal["minimal", "kompakt", "fuld"]
ColourBy = Literal["kundetype", "industry_segment"]

TDKK = 1_000  # tabel-referencerne nedenfor er i tusinde DKK

#: Mappen med resultatet oprettes ved siden af programmet og navngives med
#: dagens dato, så hver kørsel kan findes igen.
OUTPUT_FOLDER_PREFIX = "Kundesegmentering"

#: Filen med brugerens egne standardværdier, gemt ved siden af programmet.
SETTINGS_FILENAME = "segmentering_indstillinger.json"


def program_directory() -> str:
    """
    Mappen programmet ligger i.

    Pakkes programmet til en enkelt exe-fil, er det mappen med exe-filen —
    ikke den midlertidige mappe Python pakkes ud i. Derfor bruges
    ``sys.executable`` når ``sys.frozen`` er sat.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def todays_reference_date(today: date | None = None) -> str:
    """Dags dato som MM-ÅÅÅÅ. Er det 15-09-2026, bliver det "09-2026"."""
    today = today or date.today()
    return f"{today.month:02d}-{today.year}"


def todays_fiscal_year(today: date | None = None) -> str:
    """
    Regnskabsåret som ÅÅÅÅ/ÅÅÅÅ — indeværende år og året efter.

    Er det 2026, bliver det "2026/2027". Formatet skal passe med det der står
    i kolonnen 'Fiscal year' i salgsudtrækket; matcher det ikke, findes der
    ingen nye kunder.
    """
    today = today or date.today()
    return f"{today.year}/{today.year + 1}"


def dated_output_directory(today: date | None = None) -> str:
    """Stien til dagens resultatmappe ved siden af programmet."""
    today = today or date.today()
    return os.path.join(
        program_directory(), f"{OUTPUT_FOLDER_PREFIX} {today:%Y-%m-%d}"
    )


# --- Turnover/GM-bånd --------------------------------------------------------


@dataclass(frozen=True)
class Band:
    """
    Et turnover-bånd med et tilhørende GM%-krav.

    ``turnover_max=None`` betyder "ingen øvre grænse".
    ``gm_min`` er en decimal, så 0.20 svarer til 20 %.

    Intervallet er halvåbent: ``turnover_min < turnover <= turnover_max``.
    """

    turnover_min: float
    turnover_max: float | None
    gm_min: float

    @classmethod
    def from_value(cls, value: "Band | Sequence[float | None]") -> "Band":
        """Accepterer både et ``Band`` og en ``(min, max, gm)``-tuple."""
        if isinstance(value, Band):
            return value
        turnover_min, turnover_max, gm_min = value
        return cls(
            turnover_min=float(turnover_min),
            turnover_max=None if turnover_max is None else float(turnover_max),
            gm_min=float(gm_min),
        )

    def contains_turnover(self, turnover: float) -> bool:
        if turnover <= self.turnover_min:
            return False
        return self.turnover_max is None or turnover <= self.turnover_max

    def as_tuple(self) -> tuple[float, float | None, float]:
        return (self.turnover_min, self.turnover_max, self.gm_min)


def _normalise_bands(raw: Mapping[str, object]) -> dict[str, Band]:
    return {name: Band.from_value(value) for name, value in raw.items()}


def _normalise_zones(raw: Mapping[str, Mapping[str, object]]) -> dict[str, dict[str, Band]]:
    return {level: _normalise_bands(zones) for level, zones in raw.items()}


# --- Standardværdier ---------------------------------------------------------

DEFAULT_INPUT_PATH = ""

#: Bogstavet A/B/C/D bestemmes alene af turnover-båndet; GM%-grænsen afgør
#: om kunden får "+" eller "-" som suffix.
DEFAULT_CATEGORY_BANDS: dict[str, Band] = _normalise_bands(
    {
        #      turnover_min  turnover_max  gm_min
        "A": (5_000_000, None, 0.20),
        "B": (1_000_000, 5_000_000, 0.22),
        "C": (100_000, 1_000_000, 0.25),
        "D": (0, 100_000, 0.60),
    }
)

#: Tre volumen-områder pr. niveau, tegnet ét niveau ad gangen på item-plottet.
DEFAULT_VOLUME_ZONES: dict[str, dict[str, Band]] = _normalise_zones(
    {
        "A": {
            "Stor volumen": (500 * TDKK, None, 0.20),
            "Mellem volumen": (200 * TDKK, 500 * TDKK, 0.25),
            "Lille volumen": (50 * TDKK, 200 * TDKK, 0.35),
        },
        "B": {
            "Stor volumen": (500 * TDKK, 5_000 * TDKK, 0.22),
            "Mellem volumen": (200 * TDKK, 500 * TDKK, 0.30),
            "Lille volumen": (50 * TDKK, 200 * TDKK, 0.40),
        },
        "C": {
            "Stor volumen": (500 * TDKK, 1_000 * TDKK, 0.25),
            "Mellem volumen": (200 * TDKK, 500 * TDKK, 0.35),
            "Lille volumen": (50 * TDKK, 200 * TDKK, 0.50),
        },
        "D": {
            "Lille volumen": (50 * TDKK, 100 * TDKK, 0.60),
        },
    }
)

DEFAULT_EXCLUDED_TURNOVER_TYPES: list[str] = [
    "CN misc.",
    "CN misc. internal",
    "CN prod. internal",
    "CN tools",
    "CN tools internal",
    "DK correction",
    "DK misc.",
    "DK misc. internal",
    "DK prod. internal",
    "DK tools",
    "SE correction",
    "SE misc.",
]

DEFAULT_CN_TURNOVER_TYPES: list[str] = ["CN prod.", "CN+ DK prod."]
DEFAULT_DK_TURNOVER_TYPES: list[str] = ["DK prod.", "DK+ SE prod.", "SE prod."]

CATEGORY_COLOURS = {"A": "#2ecc71", "B": "#3498db", "C": "#f39c12", "D": "#9b59b6"}
VOLUME_ZONE_COLOURS = {
    "Stor volumen": "#2ecc71",
    "Mellem volumen": "#3498db",
    "Lille volumen": "#f39c12",
}
CUSTOMER_TYPE_COLOURS = {
    "Eksisterende": "#2ca02c",
    "Tidligere": "#ff7f0e",
    "Ny": "#1f77b4",
}


# --- Output-stier ------------------------------------------------------------


@dataclass(frozen=True)
class OutputPaths:
    """
    Afleder alle output-filnavne fra ét basisnavn.

    Filnavne sammensættes af basisnavnet, en fast rolle-del og de suffikser
    det aktuelle udsnit giver anledning til::

        <basis>_kundegruppe[_sinter][_cn][_eks].html
        <basis>_item[_sinter][_cn][_eks].html
        <basis>.xlsx

    Suffikserne føjes på som strukturerede dele frem for tekstsubstitution i
    et færdigt filnavn, så et basisnavn der tilfældigvis indeholder ".html"
    ikke kan ødelægge stien.
    """

    directory: str
    basename: str
    write_excel: bool = True

    @classmethod
    def create(
        cls, basename: str, directory: str | None, write_excel: bool
    ) -> "OutputPaths":
        base = (basename or "kunde_segmentering").strip()
        for extension in (".html", ".xlsx", ".xlsm", ".xls"):
            if base.lower().endswith(extension):
                base = base[: -len(extension)]
                break
        if not base:
            base = "kunde_segmentering"

        folder = (directory or "").strip() if isinstance(directory, str) else ""
        if not folder:
            # Uden en eksplicit mappe lægges resultatet i en dateret mappe
            # ved siden af programmet, så hver kørsel kan findes igen.
            folder = dated_output_directory()

        return cls(directory=folder, basename=base, write_excel=write_excel)

    def _build(self, role: str, parts: Iterable[str]) -> str:
        segments = [self.basename, role, *[p for p in parts if p]]
        return os.path.join(self.directory, "_".join(segments) + ".html")

    def group_plot(self, *parts: str) -> str:
        return self._build("kundegruppe", parts)

    def item_plot(self, *parts: str) -> str:
        return self._build("item", parts)

    @property
    def excel(self) -> str | None:
        if not self.write_excel:
            return None
        return os.path.join(self.directory, f"{self.basename}.xlsx")


# --- Hovedkonfiguration ------------------------------------------------------


@dataclass
class Config:
    """
    Samlet konfiguration for én analyse-kørsel.

    Standardværdierne svarer til den opsætning GUI'en starter med.
    """

    # Datakilde
    input_path: str = DEFAULT_INPUT_PATH

    # Datoer og kundetyper
    reference_date: str = field(default_factory=todays_reference_date)  # "MM-ÅÅÅÅ"
    existing_customer_months: int = 24
    new_fiscal_year: str = field(default_factory=todays_fiscal_year)

    # Frasortering
    excluded_customer_groups: list[str] = field(default_factory=lambda: ["FJ"])
    excluded_turnover_types: list[str] = field(
        default_factory=lambda: list(DEFAULT_EXCLUDED_TURNOVER_TYPES)
    )
    drop_zero_turnover: bool = True
    drop_dead_items: bool = True
    #: Rækker med en periode efter 'dags dato' er budgettal og udelades.
    #: Slås den fra, indgår budgetrækker i beregningen som var de realiseret.
    drop_future_periods: bool = True

    # Outliers
    remove_outliers: bool = True
    outlier_std_threshold: float = 2.0
    outlier_metric: OutlierMetric = "gm"

    # Opdeling af plots
    split_by_item_type: bool = True
    geo_combined: bool = True
    geo_cn: bool = False
    geo_dk: bool = False
    cn_turnover_types: list[str] = field(
        default_factory=lambda: list(DEFAULT_CN_TURNOVER_TYPES)
    )
    dk_turnover_types: list[str] = field(
        default_factory=lambda: list(DEFAULT_DK_TURNOVER_TYPES)
    )

    # Beregning
    turnover_window_months: int = 12
    group_plot_anchor: Anchor = "group"
    item_plot_anchor: Anchor = "item"
    gm_months: int = 1
    existing_customers_only: bool = False

    # Plots
    draw_group_plot: bool = True
    draw_item_plot: bool = True
    colour_by: ColourBy = "kundetype"
    x_scale: AxisScale = "linear"
    y_scale: AxisScale = "log"
    category_bands: dict[str, Band] = field(
        default_factory=lambda: dict(DEFAULT_CATEGORY_BANDS)
    )
    volume_zones: dict[str, dict[str, Band]] = field(
        default_factory=lambda: {k: dict(v) for k, v in DEFAULT_VOLUME_ZONES.items()}
    )

    # Output
    output_basename: str = "kunde_segmentering"
    output_dir: str | None = None
    write_excel: bool = True
    excel_detail: ExcelDetail = "kompakt"

    def __post_init__(self) -> None:
        # Tillad at kalderen sender rå (min, max, gm)-tupler.
        self.category_bands = _normalise_bands(self.category_bands)
        self.volume_zones = _normalise_zones(self.volume_zones)

    # -- Afledte værdier ------------------------------------------------------

    @property
    def uses_geo_split(self) -> bool:
        return self.geo_cn or self.geo_dk

    @property
    def paths(self) -> OutputPaths:
        return OutputPaths.create(
            self.output_basename, self.output_dir, self.write_excel
        )

    def replace(self, **changes: object) -> "Config":
        """Returnerer en kopi med ændrede felter (konfigurationen er aldrig delt)."""
        return replace(self, **changes)

    # -- Validering -----------------------------------------------------------

    def validate(self) -> None:
        """
        Kontrollerer indstillingerne og rejser ``ValueError`` med en dansk
        besked ved første fejl. Kaldes af pipelinen inden data indlæses, så
        brugeren får besked med det samme frem for midt i en lang kørsel.
        """
        if not isinstance(self.gm_months, int) or self.gm_months < 1:
            raise ValueError(
                f"GM-måneder skal være et helt tal >= 1, fik: {self.gm_months!r}"
            )
        if self.turnover_window_months < 1:
            raise ValueError(
                "Turnover-vinduet skal være mindst 1 måned, fik: "
                f"{self.turnover_window_months!r}"
            )
        if self.existing_customer_months < 0:
            raise ValueError(
                "'Eksisterende kunde vindue' kan ikke være negativt, fik: "
                f"{self.existing_customer_months!r}"
            )
        if self.excel_detail not in ("fuld", "kompakt", "minimal"):
            raise ValueError(
                "Excel-detaljeringsgrad skal være 'fuld', 'kompakt' eller "
                f"'minimal', fik: {self.excel_detail!r}"
            )
        if self.outlier_metric not in ("begge", "turnover", "gm", "ingen"):
            raise ValueError(
                "Outlier-metrik skal være 'begge', 'turnover', 'gm' eller "
                f"'ingen', fik: {self.outlier_metric!r}"
            )
        for name, anchor in (
            ("kundegruppe-plottet", self.group_plot_anchor),
            ("item-plottet", self.item_plot_anchor),
        ):
            if anchor not in ("group", "item"):
                raise ValueError(
                    f"Forankring for {name} skal være 'group' eller 'item', "
                    f"fik: {anchor!r}"
                )
        for name, scale in (("X-aksen", self.x_scale), ("Y-aksen", self.y_scale)):
            if scale not in ("linear", "log"):
                raise ValueError(
                    f"Skala for {name} skal være 'linear' eller 'log', fik: {scale!r}"
                )
        if self.colour_by not in ("kundetype", "industry_segment"):
            raise ValueError(
                "Farvelogik skal være 'kundetype' eller 'industry_segment', "
                f"fik: {self.colour_by!r}"
            )
        if not (self.geo_combined or self.geo_cn or self.geo_dk):
            raise ValueError(
                "Mindst én geografisk opdeling skal være valgt (Samlet, CN eller DK)."
            )
        validate_bands(self.category_bands, "Kundekategori")
        for level, zones in self.volume_zones.items():
            validate_bands(zones, f"Volumenområde {level}", require_disjoint=False)


# --- Brugerens egne standardværdier -----------------------------------------

#: Felter der ALDRIG gemmes som standard, fordi de udledes af dagens dato.
#: Gemte man dem, ville programmet stivne på den dag indstillingerne blev
#: gemt, og ændring af dags dato ville miste sin pointe.
DATE_DERIVED_FIELDS = ("reference_date", "new_fiscal_year")


def settings_path() -> str:
    """Stien til filen med brugerens egne standardværdier."""
    return os.path.join(program_directory(), SETTINGS_FILENAME)


def _band_to_list(band: Band) -> list:
    return [band.turnover_min, band.turnover_max, band.gm_min]


def config_to_dict(cfg: "Config") -> dict:
    """Gør et Config klar til at blive gemt som JSON."""
    data = asdict(cfg)
    for field_name in DATE_DERIVED_FIELDS:
        data.pop(field_name, None)
    data["category_bands"] = {
        name: _band_to_list(band) for name, band in cfg.category_bands.items()
    }
    data["volume_zones"] = {
        level: {name: _band_to_list(band) for name, band in zones.items()}
        for level, zones in cfg.volume_zones.items()
    }
    return data


def save_defaults(cfg: "Config", path: str | None = None) -> str:
    """
    Gemmer indstillingerne som brugerens nye standardværdier.

    Filen lægges ved siden af programmet, så den følger med hvis mappen
    flyttes eller kopieres til en kollega.
    """
    target = path or settings_path()
    try:
        with open(target, "w", encoding="utf-8") as handle:
            json.dump(config_to_dict(cfg), handle, ensure_ascii=False, indent=2)
    except OSError as exc:
        raise ValueError(
            f"Kunne ikke gemme standardindstillingerne:\n{target}\n\n"
            f"Årsag: {exc.strerror or exc}\n"
            "Programmet skal kunne skrive i sin egen mappe."
        ) from exc
    return target


def load_defaults(path: str | None = None) -> "Config":
    """
    Læser brugerens gemte standardværdier.

    Findes filen ikke, bruges fabriksindstillingerne. Er den ødelagt eller
    indeholder den felter programmet ikke kender, gives der besked frem for
    at starte med halvt indlæste indstillinger.
    """
    source = path or settings_path()
    if not os.path.isfile(source):
        return Config()
    try:
        with open(source, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"Kunne ikke læse de gemte standardindstillinger:\n{source}\n\n"
            f"Årsag: {exc}\n"
            "Slet filen for at vende tilbage til fabriksindstillingerne."
        ) from exc

    known = {f.name for f in fields(Config)}
    unknown = sorted(set(data) - known)
    if unknown:
        raise ValueError(
            f"De gemte standardindstillinger indeholder ukendte felter: "
            f"{', '.join(unknown)}\n\n"
            f"Filen stammer sandsynligvis fra en anden version. Slet den for "
            f"at vende tilbage til fabriksindstillingerne:\n{source}"
        )
    # Dato-felterne er bevidst ikke gemt og udledes af dagens dato.
    for field_name in DATE_DERIVED_FIELDS:
        data.pop(field_name, None)
    return Config(**data)


def clear_defaults(path: str | None = None) -> bool:
    """Fjerner de gemte standardværdier. Returnerer True hvis der var nogen."""
    target = path or settings_path()
    if os.path.isfile(target):
        os.remove(target)
        return True
    return False


def validate_bands(
    bands: Mapping[str, Band], label: str, require_disjoint: bool = True
) -> None:
    """
    Kontrollerer et sæt bånd.

    Kundekategori-båndene skal være disjunkte: hver turnover-værdi må højst
    matche ét bånd. Uden det krav ville resultatet afhænge af den rækkefølge
    båndene tilfældigvis står i, hvilket er en usynlig faldgrube når grænserne
    redigeres i GUI'en.

    Volumen-områder må gerne overlappe — de tegnes som gennemsigtige zoner
    oven på hinanden og bruges ikke til klassifikation.
    """
    for name, band in bands.items():
        if band.turnover_max is not None and band.turnover_max <= band.turnover_min:
            raise ValueError(
                f"{label} {name}: øvre turnover-grænse ({band.turnover_max:,.0f}) "
                f"skal være større end den nedre ({band.turnover_min:,.0f})."
            )
        if not 0.0 <= band.gm_min <= 1.0:
            raise ValueError(
                f"{label} {name}: GM%-grænsen skal ligge mellem 0 og 100 %, "
                f"fik: {band.gm_min * 100:g} %"
            )

    if not require_disjoint:
        return

    ordered = sorted(bands.items(), key=lambda item: item[1].turnover_min)
    for (lower_name, lower), (upper_name, upper) in zip(ordered, ordered[1:]):
        if lower.turnover_max is None or lower.turnover_max > upper.turnover_min:
            raise ValueError(
                f"{label} {lower_name} og {upper_name} overlapper. "
                f"{lower_name} slutter ved "
                f"{'ingen øvre grænse' if lower.turnover_max is None else format(lower.turnover_max, ',.0f')} "
                f"og {upper_name} starter ved {upper.turnover_min:,.0f}. "
                "Hvert turnover-beløb må kun kunne matche én kategori."
            )

"""
Pakker kundesegmenteringen til ét program der kan dobbeltklikkes.

    python build_exe.py

Resultatet lægges i mappen ``dist``. Det færdige program indeholder Python,
pandas, plotly og hele brugerfladen, så det kan flyttes til en maskine uden
Python og startes derfra.

Nyttige tilvalg::

    python build_exe.py --mappe        en mappe i stedet for én enkelt fil
    python build_exe.py --spring-over  installer ikke afhængigheder først
    python build_exe.py --behold       ryd ikke op efter byggeriet

PyInstaller kan ikke bygge på tværs af styresystemer: en Windows-exe skal
bygges på Windows, og et Mac-program på en Mac. Kør derfor scriptet på den
slags maskine programmet skal bruges på.
"""

from __future__ import annotations

import argparse
import importlib
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

#: Navnet brugeren ser på filen.
APP_NAME = "Kundesegmentering"
ENTRY_POINT = "run_gui.py"
ICON = "kundesegmentering.ico"

#: Pakker PyInstaller ikke selv finder. ``openpyxl`` og ``xlrd`` slås først op
#: når pandas åbner en fil, så de står ikke i nogen import-linje.
HIDDEN_IMPORTS = ["openpyxl", "xlrd", "dateutil.relativedelta"]

#: plotly.min.js ligger som datafil i pakken. Uden den kan plots ikke skrives
#: med biblioteket lagt ind i HTML-filen, og graferne ville kræve internet.
COLLECT_DATA = ["plotly"]

#: Udviklingsværktøjer der ellers bliver slæbt med og fylder unødigt.
EXCLUDES = [
    "pytest", "matplotlib", "IPython", "notebook", "jupyter", "sphinx",
    "PyQt5", "PyQt6", "PySide2", "PySide6", "wx", "tornado", "zmq",
]

BUILD_DIRS = ["build", "__pycache__"]


def run(command: list[str], what: str) -> None:
    """Kører en kommando og stopper med en læselig besked hvis den fejler."""
    print(f"\n> {' '.join(command)}\n")
    result = subprocess.run(command)
    if result.returncode != 0:
        raise SystemExit(
            f"\n{what} fejlede (kode {result.returncode}).\n"
            "Se udskriften ovenfor for hvad der gik galt."
        )


def install_dependencies() -> None:
    """Henter det programmet skal bruge, plus PyInstaller selv."""
    requirements = os.path.join(HERE, "requirements.txt")
    run(
        [sys.executable, "-m", "pip", "install", "-r", requirements],
        "Installation af afhængigheder",
    )
    run(
        [sys.executable, "-m", "pip", "install", "pyinstaller>=6.0"],
        "Installation af PyInstaller",
    )


def check_tkinter() -> None:
    """
    Brugerfladen er bygget på Tkinter, og det følger ikke med alle Python'er.

    Det opdages hellere her end midt i et byg der tager flere minutter.
    """
    try:
        importlib.import_module("tkinter")
    except ImportError as exc:
        raise SystemExit(
            "Denne Python har ikke Tkinter, og brugerfladen kan ikke bygges "
            "uden.\n\n"
            "  • Windows/Mac: installer Python fra python.org — der følger "
            "Tkinter med.\n"
            "  • Debian/Ubuntu: sudo apt install python3-tk\n"
            f"\nDetaljer: {exc}"
        )


def pyinstaller_command(one_file: bool) -> list[str]:
    command = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--name", APP_NAME,
        # Uden konsol: der skal ikke poppe et sort vindue op ved siden af.
        "--windowed",
        "--onefile" if one_file else "--onedir",
    ]
    icon = os.path.join(HERE, ICON)
    if os.path.exists(icon):
        command += ["--icon", icon]
    for module in HIDDEN_IMPORTS:
        command += ["--hidden-import", module]
    for package in COLLECT_DATA:
        command += ["--collect-data", package]
    for module in EXCLUDES:
        command += ["--exclude-module", module]
    command.append(os.path.join(HERE, ENTRY_POINT))
    return command


def built_path(one_file: bool) -> str:
    """Hvor PyInstaller lagde resultatet."""
    dist = os.path.join(HERE, "dist")
    suffix = ".exe" if sys.platform == "win32" else ""
    if one_file:
        return os.path.join(dist, APP_NAME + suffix)
    return os.path.join(dist, APP_NAME, APP_NAME + suffix)


def tidy_up() -> None:
    for name in BUILD_DIRS:
        shutil.rmtree(os.path.join(HERE, name), ignore_errors=True)
    spec = os.path.join(HERE, f"{APP_NAME}.spec")
    if os.path.exists(spec):
        os.remove(spec)


def describe(path: str, one_file: bool) -> None:
    size = os.path.getsize(path) / 1e6
    print("\n" + "=" * 68)
    print(f"  Færdig: {path}")
    print(f"  Størrelse: {size:.0f} MB")
    print("=" * 68)
    if one_file:
        print(
            "\n  Programmet er én enkelt fil. Kopier den hen hvor den skal\n"
            "  bruges og dobbeltklik. Der skal ikke installeres Python.\n"
            "\n  Første start tager 5-15 sekunder: filen pakker sig selv ud i\n"
            "  en midlertidig mappe. Vil du have den til at starte hurtigere,\n"
            "  så byg med --mappe i stedet."
        )
    else:
        print(
            f"\n  Programmet ligger i mappen dist/{APP_NAME}. Hele mappen\n"
            "  skal følge med — dobbeltklik på programfilen inde i den."
        )
    print(
        "\n  Rapporten og graferne lægges i en dateret mappe ved siden af\n"
        "  programfilen, fx “Kundesegmentering 2026-09-15”. Læg derfor\n"
        "  programmet et sted hvor der må skrives — skrivebordet eller et\n"
        "  drev, ikke C:\\Program Files.\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pakker kundesegmenteringen til et program der kan "
                    "dobbeltklikkes."
    )
    parser.add_argument(
        "--mappe", action="store_true",
        help="byg en mappe i stedet for én fil (starter hurtigere)",
    )
    parser.add_argument(
        "--spring-over", action="store_true",
        help="spring installationen af afhængigheder over",
    )
    parser.add_argument(
        "--behold", action="store_true",
        help="behold PyInstallers arbejdsmapper bagefter",
    )
    args = parser.parse_args()
    one_file = not args.mappe

    print(f"Bygger {APP_NAME} med {sys.version.split()[0]} på {sys.platform}")
    if sys.version_info < (3, 10):
        raise SystemExit(
            f"Python 3.10 eller nyere er nødvendig — her køres "
            f"{sys.version.split()[0]}."
        )

    check_tkinter()
    if not args.spring_over:
        install_dependencies()

    shutil.rmtree(os.path.join(HERE, "dist"), ignore_errors=True)
    run(pyinstaller_command(one_file), "Byggeriet")

    path = built_path(one_file)
    if not os.path.exists(path):
        raise SystemExit(
            f"Byggeriet sagde god for sig selv, men {path} findes ikke.\n"
            "Kig i udskriften ovenfor efter advarsler fra PyInstaller."
        )
    if not args.behold:
        tidy_up()
    describe(path, one_file)


if __name__ == "__main__":
    main()

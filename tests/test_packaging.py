"""
Tests af det der skal holde når programmet er pakket til én exe-fil.

Selve pakningen kan ikke afprøves her — den kræver PyInstaller og det
styresystem programmet skal køre på. Til gengæld kan de antagelser afprøves,
som en pakket fil bryder hvis de er forkerte: hvor resultatet lægges, og at
graferne er komplette uden internet.
"""

import os
import sys

import pandas as pd
import pytest

from segmentering.config import Config, dated_output_directory, program_directory
from segmentering.dataio import GROUP, INDUSTRY_SEGMENT, ReferenceDates
from segmentering.plots import group_scatter, write_html

DATES = ReferenceDates(
    today=pd.Timestamp("2026-05-01"), window_start=pd.Timestamp("2024-05-01")
)


def sample():
    return pd.DataFrame(
        [
            {
                GROUP: "KUNDE A",
                "samlet_GM": 0.30,
                "samlet_turnover_window": 3_000_000,
                "samlet_turnover": 3_000_000,
                "samlet_GP": 900_000,
                "Kundetype": "Eksisterende",
                "Kundekategori": "B+",
                INDUSTRY_SEGMENT: "Automotive",
            }
        ]
    )


# --- Hvor programmet mener det ligger ----------------------------------------


def test_a_packed_program_writes_next_to_the_exe_file(monkeypatch, tmp_path):
    """
    Pakket med PyInstaller pakker programmet sig selv ud i en midlertidig
    mappe, og ``__file__`` peger derind. Resultatet skal ikke havne i en mappe
    Windows rydder op i, men ved siden af den fil brugeren dobbeltklikkede på.
    """
    exe = tmp_path / "Kundesegmentering.exe"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    assert program_directory() == str(tmp_path)
    assert dated_output_directory().startswith(str(tmp_path))


def test_an_unpacked_program_writes_next_to_the_source():
    """Uden pakning er det projektmappen — den der rummer run_gui.py."""
    assert os.path.exists(os.path.join(program_directory(), "run_gui.py"))


# --- Graferne skal virke uden internet ---------------------------------------


def test_the_plots_carry_plotly_with_them(tmp_path):
    """
    Hentes plotly fra et CDN, ser en graf uden netværk nøjagtig ud som en
    tom analyse: en hvid side. Filen skal kunne åbnes offline og sendes
    videre til en kollega som en enkelt vedhæftet fil.
    """
    path = str(tmp_path / "plot.html")
    write_html(group_scatter(sample(), Config(), DATES), path, "test", log=lambda _: None)
    html = open(path, encoding="utf-8").read()

    assert "<script src=" not in html, "grafen henter noget udefra"
    assert "Plotly.newPlot" in html
    assert os.path.getsize(path) > 1_000_000, "plotly-biblioteket mangler i filen"


def test_the_filter_script_travels_with_the_plot(tmp_path):
    """Knapperne virker kun hvis scriptet kom med ind i filen."""
    path = str(tmp_path / "plot.html")
    write_html(group_scatter(sample(), Config(), DATES), path, "test", log=lambda _: None)
    html = open(path, encoding="utf-8").read()
    assert "plotly_buttonclicked" in html
    assert "Nulstil alle filtre" in html


# --- Uden konsolvindue -------------------------------------------------------

# run_gui starter brugerfladen, så modulet kan ikke importeres uden Tkinter.
needs_tkinter = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("tkinter") is None,
    reason="Tkinter er ikke installeret i denne Python",
)


@needs_tkinter
def test_printing_still_works_without_a_console(monkeypatch):
    """
    En exe bygget uden konsol har stdout og stderr sat til None. Rører noget
    dem, dør programmet uden at vise hvorfor — vinduet ville bare forsvinde.
    """
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)

    import run_gui

    run_gui._silence_missing_console()
    assert sys.stdout is not None and sys.stderr is not None
    print("det her må ikke vælte noget")  # ville ellers rejse AttributeError


@needs_tkinter
@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_an_existing_console_is_left_alone(monkeypatch, stream):
    import run_gui

    sentinel = object()
    monkeypatch.setattr(sys, stream, sentinel)
    run_gui._silence_missing_console()
    assert getattr(sys, stream) is sentinel

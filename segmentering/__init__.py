"""
Kundesegmentering – beregning, plots og Excel-rapport.

Typisk brug fra et script::

    from segmentering import Config, run_analysis

    cfg = Config(
        input_path=r"C:\\data\\Clean_data.xlsx",
        reference_date="05-2026",
        output_basename="kunde_segmentering",
    )
    results = run_analysis(cfg)

GUI'en i pakken ``gui`` bygger det samme ``Config``-objekt ud fra felterne på
skærmen og kalder ``run_analysis`` med sin egen log-funktion.
"""

from .config import Band, Config, OutputPaths
from .dataio import ReferenceDates
from .pipeline import Segment, SegmentResult, run_analysis

__all__ = [
    "Band",
    "Config",
    "OutputPaths",
    "ReferenceDates",
    "Segment",
    "SegmentResult",
    "run_analysis",
]

__version__ = "11.0.0"

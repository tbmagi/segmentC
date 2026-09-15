"""
Start brugerfladen til kundesegmenteringen.

    python run_gui.py

Filen er også indgangen når programmet pakkes til en exe-fil med
``build_exe.py``.
"""

from __future__ import annotations

import os
import sys

# Gør pakkerne importerbare uanset hvor programmet startes fra.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _silence_missing_console() -> None:
    """
    Giver ``print`` et sted at skrive hen når der ikke er noget konsolvindue.

    En exe bygget uden konsol har hverken stdout eller stderr — de er ``None``.
    Så snart noget skriver en linje, ville programmet ellers falde over et
    ``AttributeError`` på ``None.write``, og brugeren ville bare se vinduet
    forsvinde. Udskriften fra selve analysen går til logfilen ved siden af
    resultatet, så der går intet tabt her.
    """
    for name in ("stdout", "stderr"):
        if getattr(sys, name, None) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))


_silence_missing_console()

from gui import main  # noqa: E402 - skal ligge efter stien ovenfor

if __name__ == "__main__":
    main()

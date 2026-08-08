"""
Start brugerfladen til kundesegmenteringen.

    python run_gui.py
"""

from __future__ import annotations

import os
import sys

# Gør pakkerne importerbare uanset hvor programmet startes fra.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gui import main

if __name__ == "__main__":
    main()

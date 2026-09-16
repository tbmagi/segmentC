"""
Adgangskoden der spørges om inden brugerfladen åbnes.

Koden står ikke i klartekst nogen steder i programmet — kun som et SHA-256
aftryk, der ikke kan regnes tilbage til koden. Det betyder ikke at det er en
sikkerhedsforanstaltning: enhver der kan køre programmet, kan også prøve sig
frem, og enhver der kan læse kildekoden kan skifte aftrykket ud. Formålet er
at holde programmet fra at blive åbnet ved et tilfælde af nogen der ikke skal
bruge det — ikke at beskytte data mod nogen der vil ind.
"""

from __future__ import annotations

import hashlib
import tkinter as tk
from tkinter import ttk
from typing import Callable

#: SHA-256 af den gyldige kode. Skal den skiftes, så kør:
#:     python -c "import hashlib; print(hashlib.sha256('nykode'.encode()).hexdigest())"
ACCESS_CODE_HASH = "f6c93a9bf6be98fe44d03f226486902e7f724354c85ecbc98cf880b2c559569d"

WINDOW_TITLE = "Kundesegmentering"
PROMPT = "Indtast adgangskode for at åbne programmet:"
MAX_ATTEMPTS = 3


def code_is_correct(text: str) -> bool:
    """
    Er den indtastede kode den rigtige?

    Mellemrum i hver ende ses der bort fra, og store og små bogstaver er uden
    betydning — koden deles mundtligt, og der er ingen grund til at afvise
    nogen fordi de har Caps Lock slået til.
    """
    normalised = str(text or "").strip().casefold()
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest() == ACCESS_CODE_HASH


def ask_for_access_code(
    attempts: int = MAX_ATTEMPTS,
    on_ready: Callable[[tk.Misc, ttk.Entry, Callable[[], None]], None] | None = None,
) -> bool:
    """
    Viser kodeboksen og returnerer om der blev tastet rigtigt.

    Boksen har sit eget vindue og kommer FØR hovedvinduet bygges. Den var
    først et ``Toplevel`` oven på et skjult hovedvindue, men Tk skjuler et
    transient vindue sammen med det vindue det hører til — så ville der ikke
    komme noget frem på skærmen overhovedet, og programmet ville se ud som om
    det hang.

    ``on_ready`` er en krog til afprøvning: den kaldes når felterne står
    klar, med vinduet, indtastningsfeltet og den funktion knappen kalder.
    """
    window = tk.Tk()
    window.title(WINDOW_TITLE)
    window.resizable(False, False)

    state = {"granted": False, "left": attempts}

    frame = ttk.Frame(window, padding=(22, 18))
    frame.pack(fill="both", expand=True)

    ttk.Label(frame, text="🔒  Kundesegmentering", font=("Helvetica", 13, "bold")).grid(
        row=0, column=0, columnspan=2, sticky="w", pady=(0, 10)
    )
    ttk.Label(frame, text=PROMPT).grid(row=1, column=0, columnspan=2, sticky="w")

    code = tk.StringVar()
    entry = ttk.Entry(frame, textvariable=code, show="•", width=26)
    entry.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 4))

    message = ttk.Label(frame, text="", foreground="#b05b56")
    message.grid(row=3, column=0, columnspan=2, sticky="w", pady=(0, 10))

    def submit(_event: object = None) -> None:
        if code_is_correct(code.get()):
            state["granted"] = True
            window.destroy()
            return
        state["left"] -= 1
        code.set("")
        if state["left"] <= 0:
            window.destroy()
            return
        message.configure(
            text=f"Forkert kode. {state['left']} forsøg tilbage."
        )
        entry.focus_set()

    ttk.Button(frame, text="Luk", command=window.destroy).grid(
        row=4, column=0, sticky="w"
    )
    ttk.Button(frame, text="Åbn", command=submit).grid(row=4, column=1, sticky="e")
    frame.columnconfigure(0, weight=1)

    window.bind("<Return>", submit)
    window.bind("<Escape>", lambda _event: window.destroy())
    window.protocol("WM_DELETE_WINDOW", window.destroy)

    entry.focus_set()
    _centre(window)
    if on_ready is not None:
        window.after(50, lambda: on_ready(window, entry, submit))
    window.mainloop()
    return state["granted"]


def _centre(window: tk.Misc) -> None:
    """Sætter boksen midt på skærmen — hovedvinduet findes jo ikke endnu."""
    window.update_idletasks()
    width, height = window.winfo_width(), window.winfo_height()
    x = (window.winfo_screenwidth() - width) // 2
    y = (window.winfo_screenheight() - height) // 3
    window.geometry(f"+{max(x, 0)}+{max(y, 0)}")

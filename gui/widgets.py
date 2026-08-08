"""
Genbrugelige Tkinter-byggeklodser.

Her ligger de småting hver sektion i vinduet har brug for: hjælpebobler,
rammer med overskrift, en rulbar side og den ene linje "label + felt + hint"
der ellers ville blive gentaget hundrede gange.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

TOOLTIP_BACKGROUND = "#ffffe0"
HINT_COLOUR = "#777"
DISABLED_COLOUR = "#aaa"
ENABLED_COLOUR = "#000"
HEADING_COLOUR = "#1a4a7a"


class Tooltip:
    """
    En hjælpeboble der vises når musen hviler over et widget.

    Boblen kan også slås til og fra med et klik, så teksten kan blive stående
    mens man læser den.
    """

    def __init__(
        self,
        widget: tk.Widget,
        text: str,
        delay_ms: int = 400,
        wraplength: int = 320,
    ) -> None:
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self.wraplength = wraplength
        self._pending_id: str | None = None
        self._window: tk.Toplevel | None = None

        widget.bind("<Enter>", self._on_enter)
        widget.bind("<Leave>", self._on_leave)
        widget.bind("<Button-1>", self._on_click)

    def _on_enter(self, _event: object = None) -> None:
        self._cancel_pending()
        self._pending_id = self.widget.after(self.delay_ms, self.show)

    def _on_leave(self, _event: object = None) -> None:
        self._cancel_pending()
        self.hide()

    def _on_click(self, _event: object = None) -> None:
        self._cancel_pending()
        if self._window:
            self.hide()
        else:
            self.show()

    def _cancel_pending(self) -> None:
        if self._pending_id is not None:
            self.widget.after_cancel(self._pending_id)
            self._pending_id = None

    def show(self) -> None:
        if self._window or not self.text:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4

        self._window = window = tk.Toplevel(self.widget)
        window.wm_overrideredirect(True)
        window.wm_geometry(f"+{x}+{y}")
        try:
            window.attributes("-topmost", True)
        except tk.TclError:  # ikke understøttet på alle platforme
            pass
        tk.Label(
            window,
            text=self.text,
            justify="left",
            background=TOOLTIP_BACKGROUND,
            relief="solid",
            borderwidth=1,
            font=("Helvetica", 9),
            wraplength=self.wraplength,
            padx=8,
            pady=6,
        ).pack()

    def hide(self) -> None:
        if self._window:
            self._window.destroy()
            self._window = None


def help_icon(parent: tk.Widget, text: str) -> tk.Label:
    """Det lille blå '?' med en hjælpeboble. Kalderen placerer det selv."""
    label = tk.Label(
        parent,
        text=" ? ",
        font=("Helvetica", 8, "bold"),
        foreground="white",
        background="#4a90d9",
        cursor="question_arrow",
        padx=1,
        pady=0,
        borderwidth=0,
    )
    Tooltip(label, text)
    return label


def section(parent: tk.Widget, title: str) -> ttk.LabelFrame:
    return ttk.LabelFrame(parent, text=title, padding=(10, 5))


def heading(parent: tk.Widget, text: str) -> ttk.Label:
    return ttk.Label(
        parent, text=text, font=("Helvetica", 9, "bold"), foreground=HEADING_COLOUR
    )


def labelled_entry(
    parent: tk.Widget,
    text: str,
    variable: tk.Variable,
    row: int,
    width: int = 12,
    hint: str = "",
    tooltip: str = "",
    column: int = 0,
) -> ttk.Entry:
    """Én linje med etiket, indtastningsfelt og valgfrit hint og hjælpeboble."""
    ttk.Label(parent, text=text).grid(
        row=row, column=column, sticky="w", pady=3, padx=(0, 4)
    )
    entry = ttk.Entry(parent, textvariable=variable, width=width)
    entry.grid(row=row, column=column + 1, sticky="w", pady=3)
    if hint:
        ttk.Label(parent, text=hint, foreground=HINT_COLOUR).grid(
            row=row, column=column + 2, sticky="w", padx=5
        )
    if tooltip:
        help_icon(parent, tooltip).grid(
            row=row, column=column + 3, sticky="w", padx=(4, 0)
        )
    return entry


class Disclosure:
    """
    En knap der folder et panel ud og i.

    Bruges til de avancerede indstillinger, så vinduet er overskueligt når man
    ikke har brug for dem.
    """

    def __init__(
        self,
        parent: tk.Widget,
        title: str,
        panel: tk.Widget,
        grid_options: dict,
    ) -> None:
        self.title = title
        self.panel = panel
        self.grid_options = grid_options
        self.is_open = False
        self.button = ttk.Button(
            parent, text=self._label(), command=self.toggle, style="Toolbutton"
        )

    def _label(self) -> str:
        return f"{'▾' if self.is_open else '▸'}  {self.title}"

    def toggle(self) -> None:
        if self.is_open:
            self.panel.grid_remove()
        else:
            self.panel.grid(**self.grid_options)
        self.is_open = not self.is_open
        self.button.configure(text=self._label())


class ScrollableFrame(ttk.Frame):
    """
    En lodret rulbar beholder.

    Musehjulet bindes kun mens markøren er over området — ikke globalt — så
    hjulet stadig virker som forventet i lister og drop-down-felter.
    """

    def __init__(self, parent: tk.Widget) -> None:
        container = ttk.Frame(parent)
        container.pack(fill="both", expand=True)

        self._canvas = tk.Canvas(container, borderwidth=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(
            container, orient="vertical", command=self._canvas.yview
        )
        super().__init__(self._canvas)

        self._window = self._canvas.create_window((0, 0), window=self, anchor="nw")
        self._canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        self.bind("<Configure>", self._on_content_resize)
        self._canvas.bind("<Configure>", self._on_canvas_resize)
        self._canvas.bind("<Enter>", self._bind_wheel)
        self._canvas.bind("<Leave>", self._unbind_wheel)

    def _on_content_resize(self, _event: object) -> None:
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_resize(self, event: tk.Event) -> None:
        # Lad indholdet fylde hele bredden, så felterne strækker sig med vinduet.
        self._canvas.itemconfigure(self._window, width=event.width)

    def _bind_wheel(self, _event: object) -> None:
        self._canvas.bind_all("<MouseWheel>", self._on_wheel)
        self._canvas.bind_all("<Button-4>", self._on_wheel)
        self._canvas.bind_all("<Button-5>", self._on_wheel)

    def _unbind_wheel(self, _event: object) -> None:
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self._canvas.unbind_all(sequence)

    def _on_wheel(self, event: tk.Event) -> None:
        if getattr(event, "num", None) == 4:
            steps = -1
        elif getattr(event, "num", None) == 5:
            steps = 1
        else:
            steps = int(-event.delta / 120)
        self._canvas.yview_scroll(steps, "units")


def set_enabled(enabled: bool, *widgets: tk.Widget, readonly: bool = False) -> None:
    """
    Slår en gruppe widgets til eller fra.

    Etiketter har ingen 'disabled'-tilstand i ttk, så de gråtones i stedet.
    """
    state = ("readonly" if readonly else "normal") if enabled else "disabled"
    for widget in widgets:
        if isinstance(widget, ttk.Label):
            widget.configure(
                foreground=ENABLED_COLOUR if enabled else DISABLED_COLOUR
            )
        else:
            widget.configure(state=state)

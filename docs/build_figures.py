"""
Tegner forklarende figurer til Word-introduktionen.

    python docs/build_figures.py

Figurerne skrives som SVG til ``docs/figurer``. Er Playwright installeret,
skrives de også som PNG i dobbelt opløsning — det er PNG-filerne Word bruger.

SVG'en skrives i hånden, uden tegnebibliotek, så scriptet kan køres hvor som
helst uden at installere noget. Figurerne er illustrationer af reglerne, ikke
udtræk af rigtige data; tallene er de samme som i regneeksemplet i kapitel 5,
så figur og tekst passer sammen.
"""

from __future__ import annotations

import os
from html import escape

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "figurer")

# --- Farver ------------------------------------------------------------------
#
# Blå betyder "tælles med", grå betyder "sorteres fra". Grå er bevidst uden
# kulør: det er ikke en kategori på linje med de andre, men fraværet af en.
# Farven står aldrig alene — hver frasorteret række har både en overstregning
# og ordet "Fjernes" ved siden af sig.

INK = "#0b0b0b"
INK_2 = "#52514e"
SURFACE = "#ffffff"
KEEP = "#2a78d6"        # kategorisk slot 1
KEEP_SOFT = "#e8f1fd"
KEEP_EDGE = "#86b6ef"
ALT = "#eb6834"         # kategorisk slot 2
ALT_SOFT = "#fdeee7"
ALT_EDGE = "#f3a683"
DROP = "#7c7a73"        # neutral: "tælles ikke med"
DROP_SOFT = "#f0efec"
RULE = "#d8d6d0"

FONT = "Liberation Sans, Arial, Helvetica, sans-serif"

# --- Små SVG-hjælpere --------------------------------------------------------


def text(x, y, content, size=13, colour=INK, weight="normal", anchor="start"):
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{colour}" '
        f'font-weight="{weight}" text-anchor="{anchor}" '
        f'font-family="{FONT}">{escape(str(content))}</text>'
    )


def rect(x, y, w, h, fill, radius=0, stroke=None, width=1, dash=None, opacity=None):
    parts = [
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}"',
        f'rx="{radius}" fill="{fill}"',
    ]
    if stroke:
        parts.append(f'stroke="{stroke}" stroke-width="{width}"')
    if dash:
        parts.append(f'stroke-dasharray="{dash}"')
    if opacity is not None:
        parts.append(f'opacity="{opacity}"')
    return " ".join(parts) + "/>"


def line(x1, y1, x2, y2, colour=RULE, width=1, dash=None):
    parts = [
        f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}"',
        f'stroke="{colour}" stroke-width="{width}"',
    ]
    if dash:
        parts.append(f'stroke-dasharray="{dash}"')
    return " ".join(parts) + "/>"


def circle(cx, cy, r, fill, stroke=None, width=2):
    parts = [f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" fill="{fill}"']
    if stroke:
        parts.append(f'stroke="{stroke}" stroke-width="{width}"')
    return " ".join(parts) + "/>"


def chip(x, y, label, kept):
    """Mærkatet til højre for en række: Beholdes eller Fjernes."""
    colour = KEEP if kept else DROP
    fill = KEEP_SOFT if kept else DROP_SOFT
    width = 96
    return [
        rect(x, y - 13, width, 26, fill, radius=13, stroke=colour, width=1.5),
        text(x + width / 2, y + 5, label, size=13, colour=colour,
             weight="bold", anchor="middle"),
    ]


def svg(width, height, parts):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}">'
        + rect(0, 0, width, height, SURFACE)
        + "".join(parts)
        + "</svg>"
    )


def months(start_year, start_month, count):
    """['2023-10', '2023-11', ...]"""
    out = []
    year, month = start_year, start_month
    for _ in range(count):
        out.append(f"{year}-{month:02d}")
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return out


# --- Figur 1: døde items -----------------------------------------------------


def month_label(cx, y, label, colour):
    """
    Mærkat over en markør, sat så den slutter lige til højre for markørens
    midte. Så vokser den altid ind over det tomme felt til venstre og lander
    hverken oven i vinduets kant til højre eller i etiketterne til venstre.
    """
    return text(cx + 10, y - 17, label, size=12, colour=colour,
                weight="bold", anchor="end")


def _month_axis(parts, scale, x_of, axis_y, left, right):
    """Tidslinjen nederst. Kun kvartalsmånederne får en etiket."""
    parts.append(line(left, axis_y, right, axis_y, RULE, 1.5))
    for month in scale:
        cx = x_of(month)
        tick = month.endswith(("-01", "-04", "-07", "-10"))
        parts.append(line(cx, axis_y, cx, axis_y + (6 if tick else 3), RULE, 1))
        if tick:
            parts.append(
                text(cx, axis_y + 24, month, size=12.5, colour=INK_2, anchor="middle")
            )


def dead_items():
    """
    Tre varer på samme kunde. Vinduet regnes 12 måneder bagud fra kundens
    seneste aktivitet, og alt hvad der ligger før vinduets start falder ud.
    """
    W, H = 1000, 584
    left, right = 186, 846
    scale = months(2023, 10, 24)
    step = (right - left) / len(scale)

    def x_of(label):
        return left + scale.index(label) * step + step / 2

    rows = [
        ("712345", ["2025-02", "2025-05"], True, "8.000 / 2.400"),
        ("712346", ["2024-11", "2025-03", "2025-08"], True, "20.000 / 10.000"),
        ("712347", ["2023-11"], False, "12.000 / 1.200"),
    ]
    top = 128
    row_h = 54
    axis_y = top + len(rows) * row_h + 10

    parts = [
        text(28, 38, "Døde items sorteres fra", size=22, weight="bold"),
        text(
            28, 64,
            "Eksempel A/S · turnover-vindue 12 måneder · kundens seneste "
            "aktivitet er 2025-08",
            size=14.5, colour=INK_2,
        ),
        text(28, 116, "Item", size=12, colour=INK_2),
        text(96, 116, "Turnover / GP", size=12, colour=INK_2),
    ]

    # Vinduet som ét ubrudt bånd bag rækkerne.
    window_x0 = x_of("2024-09") - step / 2
    window_x1 = x_of("2025-08") + step / 2
    parts += [
        rect(window_x0, top - 14, window_x1 - window_x0, axis_y - top + 14,
             KEEP_SOFT, radius=4),
        line(window_x0, top - 14, window_x0, axis_y + 4, KEEP, 2.5),
        line(window_x1, top - 14, window_x1, axis_y + 4, KEEP, 2.5, dash="5 4"),
        text((window_x0 + window_x1) / 2, top - 24,
             "Turnover-vindue: de seneste 12 måneder",
             size=14, colour=KEEP, weight="bold", anchor="middle"),
    ]

    # Rækkerne. En frasorteret række kendes på fire ting, ikke kun farven:
    # grå tone, overstregning, hul markør og mærkatet "Fjernes".
    for index, (item, activity, kept, figures) in enumerate(rows):
        y = top + index * row_h + row_h / 2
        colour = KEEP if kept else DROP
        parts.append(text(28, y + 5, item, size=15, weight="bold", colour=colour))
        if not kept:
            parts.append(line(26, y, 26 + 58, y, DROP, 2))
        parts.append(text(96, y + 5, figures, size=12.5, colour=INK_2))
        for month in activity:
            cx = x_of(month)
            if kept:
                parts.append(circle(cx, y, 8, colour, stroke=SURFACE, width=2))
            else:
                parts.append(circle(cx, y, 8, SURFACE, stroke=colour, width=2.5))
        # Kun den seneste aktivitet mærkes — ikke hver eneste prik.
        parts.append(month_label(x_of(activity[-1]), y, activity[-1], colour))
        parts += chip(858, y, "Beholdes" if kept else "Fjernes", kept)

    _month_axis(parts, scale, x_of, axis_y, left, right)

    # Pil fra teksten hen til vinduets startkant.
    note_y = axis_y + 52
    parts += [
        text(window_x0 - 78, note_y + 5,
             "Vinduets start — alt til venstre falder ud",
             size=13.5, colour=DROP, weight="bold", anchor="end"),
        line(window_x0 - 68, note_y, window_x0 - 4, note_y, DROP, 2),
        line(window_x0 - 4, note_y, window_x0 - 12, note_y - 5, DROP, 2),
        line(window_x0 - 4, note_y, window_x0 - 12, note_y + 5, DROP, 2),
    ]

    # Konsekvensen: kundens GM% med og uden filteret.
    panel_y = note_y + 30
    parts += [
        line(28, panel_y, 962, panel_y, RULE, 1),
        text(28, panel_y + 30, "Hvad det betyder for kundens GM%",
             size=16.5, weight="bold"),
    ]
    bar_x, bar_w = 320, 400
    for index, (label, value, basis, colour) in enumerate([
        ("Med filteret", 44.3, "12.400 / 28.000", KEEP),
        ("Uden filteret", 34.0, "13.600 / 40.000", DROP),
    ]):
        y = panel_y + 56 + index * 38
        parts.append(text(28, y + 15, label, size=14.5, colour=INK))
        parts.append(text(170, y + 15, basis, size=13, colour=INK_2))
        parts.append(rect(bar_x, y, bar_w * value / 50, 22, colour, radius=4))
        parts.append(
            text(bar_x + bar_w * value / 50 + 12, y + 17,
                 f"{value:.1f} %".replace(".", ","), size=14.5,
                 colour=colour, weight="bold")
        )

    parts.append(
        text(28, panel_y + 164,
             "712347 blev sidst handlet i 2023-11 til 10 % margin. Uden "
             "filteret ville den to år gamle handel stadig trække kunden ned.",
             size=13.5, colour=INK_2)
    )
    return W, H, parts


# --- Figur 2: perioder efter dags dato ---------------------------------------


def budget_rows():
    """Måneder efter dags dato er budgettal og tælles ikke med."""
    W, H = 1000, 268
    left, right = 40, 960
    scale = months(2026, 1, 10)
    step = (right - left) / len(scale)
    cut = scale.index("2026-07")

    parts = [
        text(28, 38, "Perioder efter dags dato regnes som budgettal",
             size=22, weight="bold"),
        text(28, 64,
             "Er dags dato 06-2026, tæller juni med — juli og frem falder fra.",
             size=14.5, colour=INK_2),
    ]

    top = 122
    for index, month in enumerate(scale):
        x = left + index * step
        kept = index < cut
        colour = KEEP if kept else DROP
        fill = KEEP_SOFT if kept else DROP_SOFT
        # 2px luft mellem felterne, så de ikke løber sammen til én flade.
        parts.append(rect(x + 1, top, step - 2, 60, fill, radius=5,
                          stroke=colour, width=1.5))
        parts.append(
            text(x + step / 2, top + 27, month, size=13.5, colour=colour,
                 weight="bold", anchor="middle")
        )
        parts.append(
            text(x + step / 2, top + 48, "Tælles med" if kept else "Budget",
                 size=12, colour=colour, anchor="middle")
        )

    cut_x = left + cut * step
    parts += [
        line(cut_x, top - 26, cut_x, top + 86, INK, 2.5),
        text(cut_x - 10, top - 34, "Dags dato: 06-2026", size=14.5,
             colour=INK, weight="bold", anchor="end"),
        text(cut_x + 10, top - 34, "herfra er tallene budget", size=14,
             colour=DROP, weight="bold"),
    ]

    parts.append(
        text(28, top + 126,
             "Frasorteringen sker før alle beregninger, så en måned der endnu "
             "ikke er realiseret hverken løfter eller sænker marginen.",
             size=13.5, colour=INK_2)
    )
    return W, H, parts


# --- Figur 3: forankring -----------------------------------------------------


def anchoring():
    """Vinduet kan regnes fra kundens eller fra varens egen seneste aktivitet."""
    W, H = 1000, 502
    left, right = 150, 880
    scale = months(2024, 4, 18)
    step = (right - left) / len(scale)

    def x_of(label):
        return left + scale.index(label) * step + step / 2

    items = [("712345", "2025-05"), ("712346", "2025-08")]

    parts = [
        text(28, 38, "To måder at forankre turnover-vinduet", size=22,
             weight="bold"),
        text(28, 64,
             "Samme to varer, samme data — kun forankringen er forskellig.",
             size=14.5, colour=INK_2),
    ]

    def panel(title, y0, colour, soft, windows):
        block = [text(28, y0, title, size=16, weight="bold", colour=colour)]
        for index, (item, last) in enumerate(items):
            y = y0 + 38 + index * 48
            start, stop = windows[index]
            x0, x1 = x_of(start) - step / 2, x_of(stop) + step / 2
            block += [
                rect(x0, y - 18, x1 - x0, 36, soft, radius=4),
                line(x0, y - 18, x0, y + 18, colour, 2.5),
                line(x1, y - 18, x1, y + 18, colour, 2.5, dash="5 4"),
                text(28, y + 5, item, size=14.5, weight="bold"),
                circle(x_of(last), y, 8, colour, stroke=SURFACE, width=2),
                month_label(x_of(last), y, last, colour),
                text(892, y + 5, "12 mdr.", size=12.5, colour=colour),
            ]
        return block

    # Forankret i kunden: ét fælles vindue for begge varer.
    parts += panel(
        "Forankret i KUNDEN — begge varer dækker samme periode",
        112, KEEP, KEEP_SOFT,
        [("2024-09", "2025-08"), ("2024-09", "2025-08")],
    )
    parts.append(line(28, 256, 962, 256, RULE, 1))

    # Forankret i item: hver vare sit eget vindue.
    parts += panel(
        "Forankret i ITEM — hver vare har sin egen periode",
        290, ALT, ALT_SOFT,
        [("2024-06", "2025-05"), ("2024-09", "2025-08")],
    )

    axis_y = 414
    _month_axis(parts, scale, x_of, axis_y, left, right)
    parts.append(
        text(28, axis_y + 58,
             "Filteret for døde items bruger altid kundens forankring — også "
             "når item-plottet er sat til at forankre i varen.",
             size=13.5, colour=INK_2)
    )
    return W, H, parts


# --- Skrivning ---------------------------------------------------------------

FIGURES = {
    "doede-items": dead_items,
    "budgettal": budget_rows,
    "forankring": anchoring,
}


def write_png(paths: dict[str, tuple[int, int]]) -> bool:
    """Gengiver SVG'erne som PNG i dobbelt opløsning. Kræver Playwright."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False

    browser_path = os.environ.get("CHROMIUM_PATH")
    with sync_playwright() as p:
        launch = {"args": ["--no-sandbox"]}
        if browser_path:
            launch["executable_path"] = browser_path
        browser = p.chromium.launch(**launch)
        page = browser.new_page(device_scale_factor=2)
        for name, (width, height) in paths.items():
            page.set_viewport_size({"width": width, "height": height})
            page.goto(f"file://{os.path.join(OUT_DIR, name)}.svg")
            page.screenshot(path=os.path.join(OUT_DIR, f"{name}.png"))
        browser.close()
    return True


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    sizes = {}
    for name, build in FIGURES.items():
        width, height, parts = build()
        with open(os.path.join(OUT_DIR, f"{name}.svg"), "w", encoding="utf-8") as fh:
            fh.write(svg(width, height, parts))
        sizes[name] = (width, height)
        print(f"  {name}.svg   {width}x{height}")

    if write_png(sizes):
        print(f"\nPNG skrevet i dobbelt opløsning til {OUT_DIR}")
    else:
        print(
            "\nPlaywright er ikke installeret, så der blev kun skrevet SVG.\n"
            "  pip install playwright && playwright install chromium"
        )


if __name__ == "__main__":
    main()

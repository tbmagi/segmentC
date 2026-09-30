"""Tests af valutaomregningen."""

import pandas as pd
import pytest

from segmentering.config import Config
from segmentering.currency import (
    BASE_CURRENCY,
    CURRENCY_CODES,
    DEFAULT_RATES,
    DKK,
    money_for,
    rate_of,
)
from segmentering.dataio import GROUP, INDUSTRY_SEGMENT, ITEM_NO, KAM, ReferenceDates
from segmentering.metrics import (
    GP_SUM,
    ITEM_GM,
    LAST_ACTIVITY,
    TURNOVER_SUM,
    WINDOW_GROUP,
    WINDOW_ITEM,
)
from segmentering.plots import PLOTLY_AVAILABLE, group_scatter, item_scatter

DATES = ReferenceDates(
    today=pd.Timestamp("2026-05-01"), window_start=pd.Timestamp("2024-05-01")
)


# --- Selve omregningen -------------------------------------------------------


def test_the_default_rates_are_the_ones_we_were_given():
    assert DEFAULT_RATES["CNY"] == 102.0
    assert DEFAULT_RATES["EUR"] == 13.38


def test_the_base_currency_is_not_converted():
    assert DKK.factor == 1.0
    assert DKK.amount(1_234.0) == 1_234.0
    assert DKK.is_base


def test_a_rate_is_per_hundred_kroner():
    """
    Kurserne skrives som "hvor meget svarer 100 DKK til", fordi det er sådan
    de står når man slår dem op.
    """
    cny = money_for("CNY", DEFAULT_RATES)
    assert cny.factor == pytest.approx(1.02)
    assert cny.amount(1_000_000) == pytest.approx(1_020_000)

    eur = money_for("EUR", DEFAULT_RATES)
    assert eur.factor == pytest.approx(0.1338)
    assert eur.amount(1_000_000) == pytest.approx(133_800)


def test_a_whole_column_converts_the_same_way():
    eur = money_for("EUR", DEFAULT_RATES)
    assert list(eur.amounts([100.0, -200.0, 0.0])) == pytest.approx(
        [13.38, -26.76, 0.0]
    )


def test_the_base_currency_ignores_the_rate_table():
    """DKK kan ikke have en anden kurs end sig selv, uanset hvad der står."""
    assert rate_of(BASE_CURRENCY, {"DKK": 7.0, "CNY": 102.0}) == 100.0
    assert money_for(BASE_CURRENCY, {}).factor == 1.0


def test_an_unknown_currency_is_rejected():
    with pytest.raises(KeyError, match="Ukendt valuta"):
        money_for("USD", DEFAULT_RATES)


def test_updated_rates_are_used():
    """Kurserne skal kunne opdateres løbende."""
    assert money_for("EUR", {"EUR": 13.50}).amount(100) == pytest.approx(13.50)


# --- Indstillingerne ---------------------------------------------------------


def test_both_editions_start_in_kroner():
    cfg = Config()
    assert cfg.currency == BASE_CURRENCY
    assert cfg.english_currency == BASE_CURRENCY
    assert cfg.currency_rates == DEFAULT_RATES
    cfg.validate()


def test_the_two_editions_are_chosen_separately():
    Config(currency="DKK", english_currency="EUR").validate()
    Config(currency="CNY", english_currency="DKK").validate()


def test_an_unknown_currency_is_rejected_in_the_settings():
    with pytest.raises(ValueError, match="Valuta"):
        Config(currency="USD").validate()
    with pytest.raises(ValueError, match="engelsk"):
        Config(english_currency="GBP").validate()


def test_a_missing_or_silly_rate_is_rejected():
    with pytest.raises(ValueError, match="Kursen for EUR"):
        Config(currency="EUR", currency_rates={"CNY": 102.0}).validate()
    with pytest.raises(ValueError, match="Kursen for CNY"):
        Config(currency="CNY", currency_rates={"CNY": 0.0}).validate()


def test_a_rate_for_an_unused_currency_is_not_checked():
    """Der er ingen grund til at kræve en EUR-kurs hvis grafen står i DKK."""
    Config(currency="DKK", english_currency="DKK", currency_rates={}).validate()


# --- I graferne --------------------------------------------------------------


pytestmark = pytest.mark.skipif(not PLOTLY_AVAILABLE, reason="Plotly mangler")


def groups():
    return pd.DataFrame(
        [
            {
                GROUP: "KUNDE A",
                "samlet_GM": 0.30,
                "samlet_turnover_window": 9_000_000.0,
                "samlet_turnover": 9_000_000.0,
                "samlet_GP": 2_700_000.0,
                "Kundetype": "Eksisterende",
                "Kundekategori": "A+",
                INDUSTRY_SEGMENT: "Automotive",
                KAM: "PHA",
            },
            {
                GROUP: "KUNDE B",
                "samlet_GM": 0.10,
                "samlet_turnover_window": 800_000.0,
                "samlet_turnover": 800_000.0,
                "samlet_GP": 80_000.0,
                "Kundetype": "Ny",
                "Kundekategori": "C-",
                INDUSTRY_SEGMENT: "Medico",
                KAM: "TSP",
            },
        ]
    )


def items():
    return pd.DataFrame(
        [
            {
                GROUP: "KUNDE A",
                ITEM_NO: f"70100{i}",
                TURNOVER_SUM: 100_000.0,
                GP_SUM: 30_000.0,
                WINDOW_ITEM: 500_000.0 + i,
                WINDOW_GROUP: 9_000_000.0,
                ITEM_GM: 0.30,
                LAST_ACTIVITY: pd.Timestamp("2026-03-01"),
            }
            for i in range(3)
        ]
    )


def test_the_amounts_are_converted_in_the_group_plot():
    eur = money_for("EUR", DEFAULT_RATES)
    fig = group_scatter(groups(), Config(), DATES, money=eur)
    beløb = [t.customdata[0][0] for t in fig.data]
    assert beløb == pytest.approx([9_000_000 * 0.1338, 800_000 * 0.1338])


def test_the_amounts_are_converted_in_the_item_plot():
    cny = money_for("CNY", DEFAULT_RATES)
    fig = item_scatter(items(), Config(), DATES, money=cny)
    beløb = sorted(row[2] for t in fig.data for row in t.customdata)
    assert beløb == pytest.approx([500_000 * 1.02, 500_001 * 1.02, 500_002 * 1.02])


def test_the_axis_says_which_currency():
    for code, expected in (("DKK", "DKK"), ("CNY", "CNY"), ("EUR", "EUR")):
        money = money_for(code, DEFAULT_RATES)
        assert expected in group_scatter(
            groups(), Config(), DATES, money=money
        ).layout.yaxis.title.text
        assert expected in item_scatter(
            items(), Config(), DATES, money=money
        ).layout.yaxis.title.text


def test_the_hover_says_which_currency():
    eur = money_for("EUR", DEFAULT_RATES)
    assert "EUR" in group_scatter(groups(), Config(), DATES, money=eur).data[0].hovertemplate
    assert "EUR" in item_scatter(items(), Config(), DATES, money=eur).data[0].hovertemplate


def test_the_category_does_not_move_with_the_currency():
    """
    Kategorien afgøres af DKK-beløbet mod DKK-grænserne. Flyttede den sig,
    ville den samme kunde ligge i to forskellige kategorier på den danske og
    den engelske graf.
    """
    kategorier = {
        code: [t.meta["kategori"] for t in
               group_scatter(groups(), Config(), DATES,
                             money=money_for(code, DEFAULT_RATES)).data]
        for code in CURRENCY_CODES
    }
    assert kategorier["DKK"] == kategorier["CNY"] == kategorier["EUR"] == ["A+", "C-"]


def test_the_zones_move_with_the_amounts():
    """
    Grænserne står i DKK. Blev de ikke regnet om sammen med punkterne, ville
    en kunde pludselig ligge i den forkerte zone på en EUR-graf.
    """
    cfg = Config()
    dkk = group_scatter(groups(), cfg, DATES, money=DKK)
    eur = group_scatter(groups(), cfg, DATES, money=money_for("EUR", DEFAULT_RATES))

    def kanter(fig):
        return [float(s.y0) for s in fig.layout.shapes if s.y0 is not None]

    assert kanter(eur) == pytest.approx([v * 0.1338 for v in kanter(dkk)])


def test_a_point_sits_in_the_same_place_regardless_of_currency():
    """
    Både punkter og zoner ganges med den samme kurs, så billedet er identisk
    — kun tallene på aksen er forskellige. Alle punkter skal derfor flytte
    sig med præcis den samme faktor.
    """
    cfg = Config()
    dkk = group_scatter(groups(), cfg, DATES, money=DKK)
    eur = group_scatter(groups(), cfg, DATES, money=money_for("EUR", DEFAULT_RATES))
    forhold = [b.y[0] / a.y[0] for a, b in zip(dkk.data, eur.data)]
    assert forhold == pytest.approx([0.1338] * len(forhold))


def test_the_danish_edition_is_kroner_by_default():
    fig = group_scatter(groups(), Config(), DATES)
    assert "DKK" in fig.layout.yaxis.title.text
    assert fig.data[0].customdata[0][0] == 9_000_000.0

"""
Valuta i graferne.

Data er altid i DKK. Omregningen sker først når figuren tegnes — præcis som
oversættelsen — så beregningen selv rører den ikke. Det betyder blandt andet
at en kundes kategori (A+, B- …) ikke kan flytte sig fordi man skifter
valuta: kategorien afgøres af DKK-beløbet mod DKK-grænserne, og valutaen er
kun det tal der står på skærmen.

Kurserne angives som "hvor meget svarer 100 DKK til", fordi det er sådan de
står når man slår dem op. 100 DKK = 102 CNY betyder altså kursen 1,02.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np

#: Grundvalutaen. Data er i DKK, så den har altid kurs 1.
BASE_CURRENCY = "DKK"

#: De valutaer graferne kan vises i.
CURRENCY_CODES = (BASE_CURRENCY, "CNY", "EUR")

#: Kurser pr. 100 DKK. Kun de valutaer der ikke er grundvalutaen står her —
#: DKK kan ikke have en anden kurs end sig selv.
DEFAULT_RATES: dict[str, float] = {"CNY": 102.0, "EUR": 13.38}


@dataclass(frozen=True)
class Money:
    """Én valuta med sin kurs, klar til at omregne beløb."""

    code: str
    per_100_dkk: float

    @property
    def factor(self) -> float:
        """Det tal et DKK-beløb ganges med."""
        return self.per_100_dkk / 100.0

    @property
    def is_base(self) -> bool:
        return self.code == BASE_CURRENCY

    def amount(self, value: float) -> float:
        """Omregner ét beløb."""
        return float(value) * self.factor

    def amounts(self, values: Sequence[float]) -> np.ndarray:
        """Omregner en hel kolonne."""
        return np.asarray(values, dtype=float) * self.factor


#: DKK er sig selv: ingen omregning.
DKK = Money(code=BASE_CURRENCY, per_100_dkk=100.0)


def rate_of(code: str, rates: Mapping[str, float] | None = None) -> float:
    """Kursen pr. 100 DKK for en valuta. Grundvalutaen er altid 100."""
    if code == BASE_CURRENCY:
        return 100.0
    table = DEFAULT_RATES if rates is None else rates
    return float(table[code])


def money_for(code: str, rates: Mapping[str, float] | None = None) -> Money:
    """
    Slår en valuta op og giver den med sin kurs.

    En ukendt kode giver ``KeyError``; koden er valideret i ``Config``, så
    det bør kun kunne ske hvis en gemt indstillingsfil er rettet i hånden.
    """
    if code not in CURRENCY_CODES:
        raise KeyError(f"Ukendt valuta: {code!r}. Vælg mellem {CURRENCY_CODES}.")
    return Money(code=code, per_100_dkk=rate_of(code, rates))

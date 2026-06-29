"""Pruebas de los cálculos financieros puros (domain/finance)."""

from __future__ import annotations

from datetime import date

from brujula.domain.finance import net_salary, target_date_for_age


def test_net_salary_matches_ecuador_iess() -> None:
    """1600 con IESS 9.45% y sin impuesto → ~1448.80 netos."""
    assert round(net_salary(1600, 0.0945, 0), 2) == 1448.80


def test_net_salary_with_income_tax() -> None:
    assert round(net_salary(1600, 0.0945, 30), 2) == 1418.80


def test_target_date_for_age() -> None:
    assert target_date_for_age(date(1998, 3, 15), 30) == date(2028, 3, 15)
    assert target_date_for_age(date(1998, 3, 15), 35) == date(2033, 3, 15)

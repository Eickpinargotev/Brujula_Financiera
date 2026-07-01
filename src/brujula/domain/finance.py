"""Cálculos financieros puros (sin IO). Reciben parámetros, no leen la BD.

Los valores (sueldo, tasa IESS, fecha de nacimiento…) los provee la capa que llama,
normalmente leídos desde la base de datos.
"""

from __future__ import annotations

from datetime import date

from dateutil.relativedelta import relativedelta


def net_salary(
    base_salary: float,
    iess_personal_rate: float,
    income_tax_monthly: float = 0.0,
) -> float:
    """Sueldo neto mensual tras aporte IESS e impuesto a la renta.

    Ej. Ecuador: 1600 * (1 - 0.0945) - 0 = 1448.80
    """
    return base_salary * (1 - iess_personal_rate) - income_tax_monthly


def target_date_for_age(birth_date: date, edad: int) -> date:
    """Fecha en la que se cumplen `edad` años a partir de la fecha de nacimiento."""
    objetivo: date = birth_date + relativedelta(years=edad)
    return objetivo

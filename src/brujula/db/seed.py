"""Siembra inicial de la base de datos (parámetros, metas, sobres y recurrentes).

Idempotente: solo inserta lo que falta. Punto de partida; luego se edita en el dashboard.
NADA de esto vive en `.env`.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from brujula.db.models import Account, Envelope, Goal, IncomeSource, Parameter, Recurrente
from brujula.domain.loans import is_loan_category

# Parámetros financieros iniciales. (clave -> (valor, descripción))
_DEFAULT_PARAMETERS: dict[str, tuple[str, str]] = {
    "birth_date": ("1998-01-01", "Fecha de nacimiento — AJUSTAR a la real (AAAA-MM-DD)"),
    "base_salary": ("1600", "Sueldo base bruto mensual (USD)"),
    "iess_personal_rate": ("0.0945", "Aporte personal IESS Ecuador (9.45%)"),
    "income_tax_monthly": ("0", "Impuesto a la renta mensual (USD)"),
    "extra_income_baseline": ("100", "Promedio mensual de proyectos externos (USD)"),
    "timezone": ("America/Guayaquil", "Zona horaria"),
    "currency": ("USD", "Moneda"),
}

# Metas en cascada por prioridad (1 = primera). Fecha objetivo opcional (edad o exacta).
_DEFAULT_GOALS: list[dict[str, object]] = [
    {
        "nombre": "carro",
        "monto_objetivo": 27000.0,
        "edad_objetivo": 30,
        "prioridad": 1,
        "emoji": "🚗",
    },
    {
        "nombre": "casa",
        "monto_objetivo": 100000.0,
        "edad_objetivo": 35,
        "prioridad": 2,
        "emoji": "🏠",
    },
]

# Sobres: los % se aplican sobre el ingreso TOTAL del mes; 'ahorro' es el residual → metas.
_DEFAULT_ENVELOPES: list[dict[str, object]] = [
    {"nombre": "familia", "tipo": "porcentaje", "valor": 0.10, "arrastre": True},
    {"nombre": "pareja", "tipo": "porcentaje", "valor": 0.10, "arrastre": True},
    {"nombre": "personal", "tipo": "porcentaje", "valor": 0.05, "arrastre": True},
    {"nombre": "iglesia", "tipo": "fijo", "valor": 60.0, "arrastre": False},
    {"nombre": "transporte", "tipo": "fijo", "valor": 60.0, "arrastre": False},
    {"nombre": "ahorro", "tipo": "residual", "valor": 0.0, "arrastre": True},
    {"nombre": "prestamo", "tipo": "fijo", "valor": 0.0, "arrastre": True},
]

# Categorías de ingreso iniciales (editables desde el dashboard, igual que los sobres).
_DEFAULT_INCOME_SOURCES: list[str] = ["trabajo", "proyecto_personal", "prestamo"]

_DEFAULT_ACCOUNTS: list[str] = [
    "Banco Guayaquil",
    "Banco Pichincha",
    "Binance",
    "UglyCash",
]

# Cargos recurrentes reales (para pronóstico). Shopify: estudiantil + IVA 15% + ISD 5%.
_DEFAULT_RECURRENTES: list[dict[str, object]] = [
    {
        "nombre": "Shopify",
        "monto_base": 3.99,
        "iva": 0.15,
        "isd": 0.05,
        "periodicidad": "mensual",
        "sobre": "ahorro",
        "comercio": "Shopify",
        "activo": True,
    },
]


async def seed_if_empty(session: AsyncSession) -> bool:
    """Inserta parámetros/metas/sobres/fuentes/recurrentes que falten. True si sembró algo."""
    seeded = False

    existing_keys = set((await session.execute(select(Parameter.key))).scalars().all())
    for key, (value, desc) in _DEFAULT_PARAMETERS.items():
        if key not in existing_keys:
            session.add(Parameter(key=key, value=value, description=desc))
            seeded = True

    if (await session.execute(select(Goal.id))).first() is None:
        session.add_all(Goal(**g) for g in _DEFAULT_GOALS)
        seeded = True

    existing_envelopes = list((await session.execute(select(Envelope.nombre))).scalars().all())
    if not existing_envelopes:
        session.add_all(Envelope(**e) for e in _DEFAULT_ENVELOPES)
        seeded = True
    elif not any(is_loan_category(name) for name in existing_envelopes):
        session.add(Envelope(nombre="prestamo", tipo="fijo", valor=0.0, arrastre=True))
        seeded = True

    existing_sources = list((await session.execute(select(IncomeSource.nombre))).scalars().all())
    if not existing_sources:
        session.add_all(IncomeSource(nombre=n) for n in _DEFAULT_INCOME_SOURCES)
        seeded = True
    elif not any(is_loan_category(name) for name in existing_sources):
        session.add(IncomeSource(nombre="prestamo"))
        seeded = True

    existing_accounts = set((await session.execute(select(Account.nombre))).scalars().all())
    for nombre in _DEFAULT_ACCOUNTS:
        if nombre not in existing_accounts:
            session.add(Account(nombre=nombre, moneda="USD", activa=True))
            seeded = True

    if (await session.execute(select(Recurrente.id))).first() is None:
        session.add_all(Recurrente(**r) for r in _DEFAULT_RECURRENTES)
        seeded = True

    return seeded

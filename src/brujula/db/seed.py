"""Siembra inicial de la base de datos (parámetros, metas, sobres y recurrentes).

Idempotente: solo inserta lo que falta. Punto de partida; luego se edita por Telegram /
dashboard. NADA de esto vive en `.env`.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from brujula.db.models import Envelope, Goal, Parameter, Recurrente

# Parámetros financieros iniciales. (clave -> (valor, descripción))
_DEFAULT_PARAMETERS: dict[str, tuple[str, str]] = {
    "birth_date": ("1998-01-01", "Fecha de nacimiento — AJUSTAR a la real (AAAA-MM-DD)"),
    "base_salary": ("1600", "Sueldo base bruto mensual (USD)"),
    "iess_personal_rate": ("0.0945", "Aporte personal IESS Ecuador (9.45%)"),
    "income_tax_monthly": ("0", "Impuesto a la renta mensual (USD)"),
    "extra_income_baseline": ("100", "Promedio mensual de proyectos externos (USD)"),
    "saldo_inicial": ("0", "Saldo inicial en banco (USD)"),
    "timezone": ("America/Guayaquil", "Zona horaria"),
    "currency": ("USD", "Moneda"),
}

# Metas pagadas a contado (fecha objetivo = nacimiento + edad_objetivo).
_DEFAULT_GOALS: list[dict[str, object]] = [
    {"nombre": "carro", "monto_objetivo": 27000.0, "edad_objetivo": 30},
    {"nombre": "casa", "monto_objetivo": 100000.0, "edad_objetivo": 35},
]

# Sobres: los % se aplican sobre el ingreso TOTAL del mes; 'ahorro' es el residual → metas.
_DEFAULT_ENVELOPES: list[dict[str, object]] = [
    {"nombre": "familia", "tipo": "porcentaje", "valor": 0.10, "arrastre": True},
    {"nombre": "pareja", "tipo": "porcentaje", "valor": 0.10, "arrastre": True},
    {"nombre": "personal", "tipo": "porcentaje", "valor": 0.05, "arrastre": True},
    {"nombre": "iglesia", "tipo": "fijo", "valor": 60.0, "arrastre": False},
    {"nombre": "transporte", "tipo": "fijo", "valor": 60.0, "arrastre": False},
    {"nombre": "ahorro", "tipo": "residual", "valor": 0.0, "arrastre": True},
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
        "categoria": "suscripcion",
        "comercio": "Shopify",
        "activo": True,
    },
]


async def seed_if_empty(session: AsyncSession) -> bool:
    """Inserta parámetros/metas/sobres/recurrentes que falten. True si sembró algo."""
    seeded = False

    existing_keys = set((await session.execute(select(Parameter.key))).scalars().all())
    for key, (value, desc) in _DEFAULT_PARAMETERS.items():
        if key not in existing_keys:
            session.add(Parameter(key=key, value=value, description=desc))
            seeded = True

    if (await session.execute(select(Goal.id))).first() is None:
        session.add_all(Goal(**g) for g in _DEFAULT_GOALS)
        seeded = True

    if (await session.execute(select(Envelope.id))).first() is None:
        session.add_all(Envelope(**e) for e in _DEFAULT_ENVELOPES)
        seeded = True

    if (await session.execute(select(Recurrente.id))).first() is None:
        session.add_all(Recurrente(**r) for r in _DEFAULT_RECURRENTES)
        seeded = True

    return seeded

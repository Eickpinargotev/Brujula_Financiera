"""Datos de ejemplo (inventados) para ver el dashboard funcionando en desarrollo.

Se siembra UNA sola vez (flag `demo_seeded`) y SOLO fuera de producción, para no
contaminar los datos reales en la nube. Genera unos cuantos ingresos y egresos en los
últimos meses, repartidos por sobre/categoría/comercio.
"""

from __future__ import annotations

import logging
from datetime import date

from dateutil.relativedelta import relativedelta
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from brujula.db.models import Movimiento, Parameter

logger = logging.getLogger(__name__)

_FLAG = "demo_seeded"


def _demo_movimientos(hoy: date) -> list[dict[str, object]]:
    """Construye ~3 meses de movimientos de ejemplo relativos a `hoy`."""
    movs: list[dict[str, object]] = []
    for meses_atras in (2, 1, 0):
        primero = hoy.replace(day=1) - relativedelta(months=meses_atras)

        def dia(d: int, base: date = primero) -> date:
            return base.replace(day=d)

        movs += [
            {
                "tipo": "ingreso",
                "fecha": dia(5),
                "monto": 1448.80,
                "descripcion": "Sueldo neto del mes",
                "fuente_ingreso": "trabajo",
                "comercio": "Empleador",
            },
            {
                "tipo": "gasto",
                "fecha": dia(2),
                "monto": 60.0,
                "descripcion": "Diezmo",
                "sobre": "iglesia",
                "categoria": "iglesia",
                "comercio": "Iglesia",
            },
            {
                "tipo": "gasto",
                "fecha": dia(6),
                "monto": 45.0,
                "descripcion": "Recarga de transporte",
                "sobre": "transporte",
                "categoria": "transporte",
                "comercio": "Metro",
            },
            {
                "tipo": "gasto",
                "fecha": dia(9),
                "monto": 78.5,
                "descripcion": "Salida con la pareja",
                "sobre": "pareja",
                "categoria": "entretenimiento",
                "comercio": "Restaurante",
            },
            {
                "tipo": "gasto",
                "fecha": dia(14),
                "monto": 120.0,
                "descripcion": "Mercado familiar",
                "sobre": "familia",
                "categoria": "comida",
                "comercio": "Supermercado",
            },
            {
                "tipo": "gasto",
                "fecha": dia(20),
                "monto": 40.0,
                "descripcion": "Mensualidad del gimnasio",
                "sobre": "personal",
                "categoria": "salud",
                "comercio": "Gym",
            },
        ]

    # Un par de ingresos extra por proyectos y una compra tecnológica puntual.
    mes_pasado = hoy.replace(day=1) - relativedelta(months=1)
    mes_actual = hoy.replace(day=1)
    hace_dos = hoy.replace(day=1) - relativedelta(months=2)
    movs += [
        {
            "tipo": "ingreso",
            "fecha": mes_pasado.replace(day=18),
            "monto": 150.0,
            "descripcion": "Proyecto freelance",
            "fuente_ingreso": "proyecto_personal",
            "comercio": "Cliente",
        },
        {
            "tipo": "ingreso",
            "fecha": mes_actual.replace(day=12),
            "monto": 90.0,
            "descripcion": "Proyecto personal",
            "fuente_ingreso": "proyecto_personal",
            "comercio": "Cliente",
        },
        {
            "tipo": "gasto",
            "fecha": hace_dos.replace(day=22),
            "monto": 210.0,
            "descripcion": "Auriculares",
            "sobre": "ahorro",
            "categoria": "tecnologia",
            "comercio": "Amazon",
        },
    ]
    return movs


async def seed_demo_if_needed(session: AsyncSession, hoy: date | None = None) -> bool:
    """Siembra los datos de ejemplo una sola vez. True si sembró algo."""
    hoy = hoy or date.today()
    existe = (
        await session.execute(select(Parameter).where(Parameter.key == _FLAG))
    ).scalar_one_or_none()
    if existe is not None:
        return False

    for mov in _demo_movimientos(hoy):
        session.add(Movimiento(**mov))

    # Ahorro previo (patrimonio inicial) para que la cascada de metas tenga algo repartido.
    await session.execute(
        update(Parameter).where(Parameter.key == "saldo_inicial").values(value="6000")
    )

    session.add(
        Parameter(
            key=_FLAG,
            value="1",
            description="Datos de ejemplo ya sembrados (solo desarrollo).",
        )
    )
    return True

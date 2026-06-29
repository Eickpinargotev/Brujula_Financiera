"""Presupuesto por sobres con arrastre (rollover) y semáforo. A completar en desarrollo.

Ver docs/finance-model.md §2.
    saldo_sobre(mes) = saldo_sobre(mes-1) + asignacion(mes) - gastado(mes)
    estado: verde (<= asignado) | amarillo (cerca del límite) | rojo (excedido)
"""

from __future__ import annotations

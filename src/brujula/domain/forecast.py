"""Proyecciones y simulador "¿y si subo mis ingresos?". A completar en desarrollo.

Ver docs/finance-model.md §3 y §4.
    fecha_proyectada = hoy + (restante / ahorro_actual) meses
    nueva_fecha      = hoy + (restante / (ahorro_actual + delta)) meses
    meses_ahorrados  = fecha_proyectada - nueva_fecha
"""

from __future__ import annotations
